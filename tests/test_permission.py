"""The permission rules, which must agree with the Go and TypeScript SDKs.

These are the rules an extension uses to decide whether a grant covers a call. If they disagree
across SDKs, the same grant authorises different things depending on which language the extension
happens to be written in — which is the one thing a shared contract must not allow.
"""

from types import SimpleNamespace

import pytest

from easybus.extension import (
    PermissionDenied,
    allowed,
    grants_for,
    grants_scope,
    matches,
    require,
)


def grant(key: str, params: dict) -> SimpleNamespace:
    """A stand-in for the generated Grant message."""
    return SimpleNamespace(key=key, params=params)


class TestMatches:
    def test_exact(self) -> None:
        assert matches({"repo": "agentdev/mrflow"}, {"repo": "agentdev/mrflow"})
        assert not matches({"repo": "agentdev/mrflow"}, {"repo": "agentdev/other"})

    def test_wildcard(self) -> None:
        cases = [
            ("agentdev/*", "agentdev/mrflow", True),
            ("agentdev/*", "easydev-org/x", False),
            ("*", "anything/at/all", True),
            ("agentdev/*.go", "agentdev/main.go", True),
            ("agentdev/*.go", "agentdev/main.md", False),
            # A wildcard must not match the parent it was anchored to.
            ("agentdev/*", "agentdev", False),
        ]
        for pattern, value, want in cases:
            assert matches({"repo": pattern}, {"repo": value}) is want, f"{pattern} vs {value}"

    def test_all_params_required(self) -> None:
        g = {"namespace": "dev", "service": "api"}
        assert matches(g, {"namespace": "dev", "service": "api"})
        assert not matches(g, {"namespace": "dev", "service": "web"})
        assert not matches(g, {"namespace": "dev"})

    def test_undeclared_target_params_ignored(self) -> None:
        assert matches({"repo": "agentdev/*"}, {"repo": "agentdev/mrflow", "branch": "x"})


class TestAllowed:
    def test_one_instance_suffices(self) -> None:
        with grants_scope(
            [
                grant("mr.merge", {"repo": "agentdev/mrflow"}),
                grant("mr.merge", {"repo": "scratch/*"}),
            ]
        ):
            assert allowed("mr.merge", {"repo": "agentdev/mrflow"})
            assert allowed("mr.merge", {"repo": "scratch/anything"})
            assert not allowed("mr.merge", {"repo": "easydev-org/easyagent"})

    def test_keys_do_not_leak(self) -> None:
        with grants_scope([grant("mr.merge", {"repo": "*"})]):
            assert not allowed("repo.delete", {"repo": "anything"})

    def test_nothing_without_grants(self) -> None:
        with grants_scope([]):
            assert not allowed("anything", {})

    def test_scope_does_not_leak_after_exit(self) -> None:
        # A context variable, not a module global: a grant bound for one call must be gone once
        # that call returns, or the next call would inherit it.
        with grants_scope([grant("mr.merge", {"repo": "*"})]):
            assert allowed("mr.merge", {"repo": "x/y"})
        assert not allowed("mr.merge", {"repo": "x/y"})


class TestRequire:
    def test_passes_when_covered(self) -> None:
        with grants_scope([grant("mr.merge", {"repo": "agentdev/*"})]):
            require("mr.merge", {"repo": "agentdev/mrflow"})

    def test_names_the_gap(self) -> None:
        with grants_scope([grant("mr.merge", {"repo": "agentdev/mrflow"})]):
            with pytest.raises(PermissionDenied) as ei:
                require("mr.merge", {"repo": "easydev-org/easyagent"})
        msg = str(ei.value)
        assert "easydev-org/easyagent" in msg
        assert "agentdev/mrflow" in msg

    def test_distinguishes_none_from_not_covering(self) -> None:
        with grants_scope([]):
            with pytest.raises(PermissionDenied, match="no grant held"):
                require("mr.merge", {"repo": "x/y"})


class TestGrantsFor:
    def test_returns_every_instance(self) -> None:
        with grants_scope(
            [
                grant("mr.merge", {"repo": "a/one"}),
                grant("mr.merge", {"repo": "a/two"}),
                grant("exec", {"sandbox": "s"}),
            ]
        ):
            assert len(grants_for("mr.merge")) == 2
            assert len(grants_for("exec")) == 1
