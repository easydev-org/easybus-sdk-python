"""Permission enforcement, extension side.

The agent stores what a session MAY do and hands those grants over on every call. This module is
the other half: deciding whether a grant COVERS the call about to happen.

WHY the decision lives here: coverage depends on the call's target — this repository, that
sandbox — and turning the arguments into that target is domain knowledge only the extension has
("https://host/o/r.git" -> "o/r" is a git rule, not a protocol rule). Keeping it here is what
lets the same mechanism serve an extension that guards repositories and one that guards
sandboxes.

The agent's own check is an optimisation, not a boundary: it can say "this session has no merge
permission at all", but it cannot say "this grant covers THIS pull request". Only this module
can, and only this module is the security boundary — the extension holds the credential and
performs the action.
"""

from __future__ import annotations

import contextvars
from typing import Any, Iterable, Mapping

GrantParams = dict[str, str]


class PermissionDenied(Exception):
    """Raised when a required permission is absent or does not cover the call.

    It carries the target that was attempted, so the caller can say WHICH repository was
    refused rather than "permission denied" — and so an audit log records what was tried.
    """

    def __init__(self, key: str, target: GrantParams, granted: list[GrantParams]) -> None:
        self.key = key
        self.target = target
        self.granted = granted
        super().__init__(_format_denial(key, target, granted))


def _format_denial(key: str, target: GrantParams, granted: list[GrantParams]) -> str:
    want = _format_params(target)
    msg = f"permission denied: {key}"
    if want:
        msg += f" on {want}"
    if not granted:
        return f"{msg} (no grant held for this permission)"
    held = "; ".join(_format_params(g) for g in granted)
    return f"{msg} (held: {held})"


def _format_params(p: GrantParams) -> str:
    """Renders params deterministically, so the same gap always reads the same."""
    return ",".join(f"{k}={p[k]}" for k in sorted(p))


# The grants for the CURRENT call.
#
# WHY a ContextVar: a tool handler is async and may await before reaching its permission check, so
# passing grants through every call signature would be both invasive and easy to forget. A
# context variable is already per-task in asyncio, is copied correctly across `await`, and does
# not leak between concurrent calls — the same properties Go gets from a context.Context.
_grants: contextvars.ContextVar[tuple[Any, ...]] = contextvars.ContextVar("easybus_grants", default=())


class grants_scope:
    """Context manager binding a call's grants for the duration of one invocation.

    Used by the dispatcher; a tool handler only ever reads through `require`/`allowed`.
    """

    def __init__(self, grants: Iterable[Any] | None) -> None:
        self._grants = tuple(grants or ())
        self._token: contextvars.Token | None = None

    def __enter__(self) -> "grants_scope":
        self._token = _grants.set(self._grants)
        return self

    def __exit__(self, *exc: object) -> None:
        if self._token is not None:
            _grants.reset(self._token)


def grants_for(key: str) -> list[GrantParams]:
    """Returns the params of every grant held for one key.

    A session may hold SEVERAL grants of the same key with different params — "merge in
    agentdev/mrflow" and "merge in scratch/*" are two authorisations, not one. Coverage means at
    least one of them matches.
    """
    out: list[GrantParams] = []
    for g in _grants.get():
        # The generated Grant has `key` and `params`; params is a Struct (a dict-like).
        if getattr(g, "key", "") != key:
            continue
        raw = getattr(g, "params", None) or {}
        out.append(_struct_to_strings(dict(raw) if not isinstance(raw, dict) else raw))
    return out


def allowed(key: str, target: Mapping[str, str]) -> bool:
    """Reports whether the caller may perform `key` against `target`."""
    return any(matches(g, target) for g in grants_for(key))


def require(key: str, target: Mapping[str, str]) -> None:
    """Raises PermissionDenied when the call is not covered, and returns when it is.

    The expected shape inside a tool:

        target = {"repo": repo_slug(arg_str(args, "remote"))}
        require("mr.merge", target)
    """
    t = dict(target)
    if allowed(key, t):
        return
    raise PermissionDenied(key, t, grants_for(key))


def matches(granted: Mapping[str, str], target: Mapping[str, str]) -> bool:
    """Reports whether a grant's params cover a target.

    Semantics, deliberately small:

      - every key in the GRANT must appear in the target and match (AND across keys);
      - a value may use `*` as a wildcard: "agentdev/*" covers "agentdev/mrflow";
      - otherwise it is an exact comparison.

    WHY not regex: a permission a reader cannot predict is one they cannot judge. `*` is the
    smallest thing that makes "all my repositories" expressible, and a client can explain it in
    one sentence. An extension that needs more can ignore these params and enforce its own rule.
    """
    for k, want in granted.items():
        got = target.get(k)
        if got is None:
            return False
        if not _match_value(want, got):
            return False
    return True


def _match_value(pattern: str, value: str) -> bool:
    if pattern == "*":
        return True
    i = pattern.find("*")
    if i >= 0:
        prefix, suffix = pattern[:i], pattern[i + 1 :]
        if len(value) < len(prefix) + len(suffix):
            return False
        return value.startswith(prefix) and value.endswith(suffix)
    return pattern == value


def _struct_to_strings(m: Mapping[str, Any]) -> GrantParams:
    """Flattens a param mapping to strings: the declared leaves are scalars."""
    return {k: "" if v is None else str(v) for k, v in m.items()}
