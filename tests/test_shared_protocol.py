"""The shared cross-language tables: channel matching, channel subjects, every subject string.

Each describes behaviour implemented once per language. They are read from the SAME files in
every SDK, so a divergence fails a test here instead of surfacing as a message that silently
never arrives — a wrong subject or a wrong `>` rule produces no error anywhere.
"""

import json
from pathlib import Path

import pytest

from easybus.protocol import (
    ch_channel,
    ch_config,
    ch_file_get,
    ch_file_ingest,
    ch_hook_call,
    ch_hook_event,
    ch_interrupt,
    ch_interrupt_all,
    ch_lifecycle,
    ch_mailbox,
    ch_session_changed,
    ch_session_events,
    ch_tool_call,
    ch_tool_progress,
    ch_variable,
    match_subject,
    parse_channel_subject,
    subject_tenant,
)

CASES_DIR = Path(__file__).resolve().parents[1] / "conformance-cases"


def _table(name: str) -> dict:
    return json.loads((CASES_DIR / name).read_text())


# ── channel matching ────────────────────────────────────────────────────────

_MATCH = _table("channel-matching.json")["cases"]


def test_matching_table_not_empty() -> None:
    assert _MATCH


@pytest.mark.parametrize("case", _MATCH, ids=lambda c: c["why"][:40])
def test_shared_channel_matching(case: dict) -> None:
    assert match_subject(case["pattern"], case["topic"]) is case["want"]


# ── channel build / parse ───────────────────────────────────────────────────

_SUBJ = _table("channel-subjects.json")["cases"]


@pytest.mark.parametrize("case", _SUBJ, ids=lambda c: c["why"][:40])
def test_shared_channel_subjects(case: dict) -> None:
    if "build" in case:
        b = case["build"]
        assert ch_channel(b["tenant"], b["channel"], b["topic"]) == case["want"]
        return
    if "parse" in case:
        got = parse_channel_subject(case["parse"])
        if case["want"] is None:
            assert got is None
        else:
            assert list(got) == case["want"]
        return
    if "reject" in case:
        r = case["reject"]
        # A wildcard or empty segment must be refused, not published as a broadcast.
        with pytest.raises(ValueError):
            ch_channel(r["tenant"], r["channel"], r["topic"])


# ── every subject string ────────────────────────────────────────────────────

_FNS = {
    "chMailbox": lambda a: ch_mailbox(a["tenant"], a["session"]),
    "chToolCall": lambda a: ch_tool_call(a["tenant"], a["ext"], a["tool"]),
    "chToolProgress": lambda a: ch_tool_progress(a["tenant"], a["callId"]),
    "chVariable": lambda a: ch_variable(a["tenant"], a["ext"], a["name"]),
    "chSessionEvents": lambda a: ch_session_events(a["tenant"], a["session"]),
    "chSessionChanged": lambda a: ch_session_changed(a["tenant"]),
    "chInterrupt": lambda a: ch_interrupt(a["tenant"], a["ext"]),
    "chInterruptAll": lambda a: ch_interrupt_all(a["tenant"]),
    "chLifecycle": lambda a: ch_lifecycle(a["tenant"], a["kind"]),
    "chHookCall": lambda a: ch_hook_call(a["tenant"], a["ext"], a["hook"]),
    "chHookEvent": lambda a: ch_hook_event(a["tenant"], a["hook"]),
    "chConfig": lambda a: ch_config(a["tenant"], a["ext"]),
    "chFileGet": lambda a: ch_file_get(a["tenant"]),
    "chFileIngest": lambda a: ch_file_ingest(a["tenant"]),
    "chChannel": lambda a: ch_channel(a["tenant"], a["channel"], a["topic"]),
    "subjectTenant": lambda a: subject_tenant(a["subject"]),
}

_PROTO = _table("protocol-subjects.json")["cases"]


@pytest.mark.parametrize("case", _PROTO, ids=lambda c: f"{c['fn']}-{c['why'][:30]}")
def test_shared_protocol_subjects(case: dict) -> None:
    fn = _FNS.get(case["fn"])
    assert fn is not None, f"no mapping for {case['fn']}"
    assert fn(case["args"]) == case["want"]
