"""Frozen derivations — the cross-language interop vectors. These MUST equal the
Go vectors in easybus-sdk/conformance/golden_test.go and the TS vectors in
easybus-sdk-typescript/src/protocol/golden.ts.

v2: every data-plane channel is easybus.<tenant>.<...>.
"""

from __future__ import annotations

from . import (
    CH_DISCOVER,
    MAILBOX_WILDCARD_ALL,
    ch_config,
    ch_hook_call,
    ch_hook_event,
    ch_interrupt,
    ch_mailbox,
    ch_session_events,
    ch_tool_call,
    ch_tool_progress,
    ch_variable,
    session_token,
    session_var_key,
    var_key,
)

GOLDEN_TENANT = "alice"

#: name -> (got, want). Every entry must hold exactly.
GOLDEN_VECTORS: dict[str, tuple[str, str]] = {
    "session_token": (session_token("sess-1"), "q-Yz86R6J1gXTqvpFg2vNs"),
    "discover": (CH_DISCOVER, "easybus.discover"),
    "tool_call": (ch_tool_call(GOLDEN_TENANT, "ops", "echo"), "easybus.alice.tool.call.ops.echo"),
    "tool_progress": (ch_tool_progress(GOLDEN_TENANT, "c1"), "easybus.alice.tool.progress.c1"),
    "variable": (ch_variable(GOLDEN_TENANT, "ops", "base-url"), "easybus.alice.var.ops.base-url"),
    "interrupt": (ch_interrupt(GOLDEN_TENANT, "ops"), "easybus.alice.ctl.interrupt.ops"),
    "hook_call": (ch_hook_call(GOLDEN_TENANT, "ops", "session.before_create"), "easybus.alice.hook.call.ops.session.before_create"),
    "hook_event": (ch_hook_event(GOLDEN_TENANT, "session.created"), "easybus.alice.hook.event.session.created"),
    "mailbox_wildcard": (MAILBOX_WILDCARD_ALL + ">", "easybus.*.mailbox.>"),
    "mailbox_sess1": (ch_mailbox(GOLDEN_TENANT, "sess-1"), "easybus.alice.mailbox.q-Yz86R6J1gXTqvpFg2vNs"),
    "session_events_s1": (ch_session_events(GOLDEN_TENANT, "sess-1"), "easybus.alice.session.events.q-Yz86R6J1gXTqvpFg2vNs"),
    "config": (ch_config(GOLDEN_TENANT, "ops"), "easybus.alice.config.ops"),
    "var_key": (var_key(GOLDEN_TENANT, "ops", "base-url"), "t.alice.ops.base-url"),
    "session_var_key": (session_var_key(GOLDEN_TENANT, "ops", "sess-1", "ws"), "t.alice.ops.q-Yz86R6J1gXTqvpFg2vNs.ws"),
}
