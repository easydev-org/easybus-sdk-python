"""Runtime protocol conventions — the Python twin of the Go `easybus-sdk/protocol`
package. Every derivation here MUST match the Go implementation byte-for-byte
(see `golden` for the frozen vectors).

The wire MESSAGES come from proto/easybus/v1/protocol.proto (the single source
of truth); this module owns the SUBJECT layout, KV-key layout, tenant rules and
small arg readers that proto cannot express.
"""

from __future__ import annotations

import base64
import hashlib
import re
import uuid


def session_token(session_name: str) -> str:
    """Derive the transport-safe token for a session name."""
    digest = hashlib.sha256(session_name.encode("utf-8")).digest()
    # base64url WITHOUT padding, truncated to 22 chars (matches Go's
    # base64.RawURLEncoding.EncodeToString(sum)[:22]).
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")[:22]


# ---- tenant namespacing (v2) ----------------------------------------------
#
# A tenant is an opaque, plaintext isolation key (typically a user id). It is
# the SECOND subject segment for every data-plane channel — easybus.<tenant>.<...>
# — and rides every envelope in its tenant field. The strict charset prevents a
# tenant from injecting a subject separator ('.'), wildcard ('*'/'>'), or
# whitespace.

_TENANT_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

#: GlobalTenant is the reserved tenant for GLOBAL control-plane messages.
GLOBAL_TENANT = "global"


def is_valid_tenant(raw: str) -> bool:
    return bool(_TENANT_RE.match(raw))


def tenant_prefix(tenant: str) -> str:
    """The data-plane subject prefix for a tenant: easybus.<tenant>."""
    return f"easybus.{tenant}."


def subject_tenant(ch: str) -> str:
    """Extract the tenant segment, or '' when not namespaced."""
    p = "easybus."
    if not ch.startswith(p):
        return ""
    rest = ch[len(p):]
    dot = rest.find(".")
    if dot <= 0:
        return ""
    tenant = rest[:dot]
    return tenant if _TENANT_RE.match(tenant) else ""


def tenant_kv_key(tenant: str, rest: str) -> str:
    """A tenant-scoped KV key in a shared bucket: t.<tenant>.<rest>."""
    return f"t.{tenant}.{rest}"


def tenant_object_name(tenant: str, name: str) -> str:
    """A tenant-scoped object-store name: t.<tenant>.<name>."""
    return f"t.{tenant}.{name}"


CH_DISCOVER = "easybus.discover"
MAILBOX_WILDCARD = "easybus."
MAILBOX_WILDCARD_ALL = "easybus.*.mailbox."
LIFECYCLE_WILDCARD = "easybus.*.session.lifecycle."
VARS_BUCKET = "vars"
CONFIG_KV_BUCKET = "cfg"


def ch_tool_call(tenant: str, ext_id: str, tool: str) -> str:
    return f"{tenant_prefix(tenant)}tool.call.{ext_id}.{tool}"


def ch_tool_progress(tenant: str, call_id: str) -> str:
    return f"{tenant_prefix(tenant)}tool.progress.{call_id}"


def ch_variable(tenant: str, ext_id: str, name: str) -> str:
    return f"{tenant_prefix(tenant)}var.{ext_id}.{name}"


def ch_mailbox(tenant: str, session: str) -> str:
    return f"{tenant_prefix(tenant)}mailbox.{session_token(session)}"


def ch_session_events(tenant: str, session: str) -> str:
    return f"{tenant_prefix(tenant)}session.events.{session_token(session)}"


def ch_session_changed(tenant: str) -> str:
    return f"{tenant_prefix(tenant)}session.changed"


def ch_interrupt(tenant: str, ext_id: str) -> str:
    return f"{tenant_prefix(tenant)}ctl.interrupt.{ext_id}"


def ch_interrupt_all(tenant: str) -> str:
    return f"{tenant_prefix(tenant)}ctl.interrupt.>"


def ch_hook_call(tenant: str, ext_id: str, hook: str) -> str:
    return f"{tenant_prefix(tenant)}hook.call.{ext_id}.{hook}"


def ch_hook_event(tenant: str, hook: str) -> str:
    return f"{tenant_prefix(tenant)}hook.event.{hook}"


def ch_lifecycle(tenant: str, kind: str) -> str:
    return f"{tenant_prefix(tenant)}session.lifecycle.{kind}"


def ch_config(tenant: str, ext_id: str) -> str:
    return f"{tenant_prefix(tenant)}config.{ext_id}"


def var_key(tenant: str, ext_id: str, name: str) -> str:
    """The global variable KV key (t.<tenant>.<extId>.<name>)."""
    return tenant_kv_key(tenant, f"{ext_id}.{name}")


def session_var_key(tenant: str, ext_id: str, session_name: str, name: str) -> str:
    """The session variable KV key (t.<tenant>.<extId>.<token>.<name>)."""
    return tenant_kv_key(tenant, f"{ext_id}.{session_token(session_name)}.{name}")


# ---- arg readers -----------------------------------------------------------


def arg_string(args: dict, key: str) -> str:
    v = args.get(key)
    return v if isinstance(v, str) else ""


def arg_int(args: dict, key: str, default: int) -> int:
    v = args.get(key)
    return int(v) if isinstance(v, (int, float)) else default


def arg_float(args: dict, key: str, default: float) -> float:
    v = args.get(key)
    return float(v) if isinstance(v, (int, float)) else default


def arg_bool(args: dict, key: str, default: bool) -> bool:
    v = args.get(key)
    return v if isinstance(v, bool) else default


# ---- id / KV escaping ------------------------------------------------------


def new_id() -> str:
    """A fresh random UUID-v4-shaped id (matches Go's protocol.NewID)."""
    return str(uuid.uuid4())


_HEX = "0123456789ABCDEF"
_KV_SAFE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_/")


def escape_kv_segment(s: str) -> str:
    """Encode a string into a NATS KV-safe key segment using only
    [a-zA-Z0-9-/_=]. The escape char '=' introduces a two-hex-digit byte
    ('.' -> "=2E", '=' -> "=3D"). Never produces the '.' separator.
    """
    out = []
    for ch in s:
        if ch in _KV_SAFE:
            out.append(ch)
        else:
            c = ord(ch)
            out.append("=" + _HEX[(c >> 4) & 0xF] + _HEX[c & 0xF])
    return "".join(out)


def _hex_val(c: str) -> int:
    if "0" <= c <= "9":
        return ord(c) - ord("0")
    if "A" <= c <= "F":
        return ord(c) - ord("A") + 10
    if "a" <= c <= "f":
        return ord(c) - ord("a") + 10
    return -1


def unescape_kv_segment(s: str) -> str:
    """Reverse escape_kv_segment."""
    out = []
    i = 0
    while i < len(s):
        if s[i] == "=" and i + 2 < len(s):
            hi = _hex_val(s[i + 1])
            lo = _hex_val(s[i + 2])
            if hi >= 0 and lo >= 0:
                out.append(chr((hi << 4) | lo))
                i += 3
                continue
        out.append(s[i])
        i += 1
    return "".join(out)
