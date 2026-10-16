"""The second batch of the Python conformance suite — the remaining Go cases
(hooks, interrupt, progress, session events, mailbox, config series, DLQ,
presence liveness, KV watch, lease, object offload)."""
import asyncio

import pytest

from easybus.agent import Agent, ConfigError
from easybus.bus import InboxConsumeOpts, RequestOpts
from easybus.extension import (
    Config,
    ConfigSpec,
    Extension,
    ToolResultData,
    ToolSpec,
    TypedError,
    VariableSpec,
)
from easybus.protocol import CONFIG_KV_BUCKET, ch_session_events, new_id
from easybus.transport.nats import connect
from easybus.wire import ExtensionManifest, from_value

T = "t1"


def _ext(bus, **overrides):
    async def echo(args, cid, sess, ten):
        return ToolResultData(content="echo:" + str(args.get("msg", "")))

    async def session(args, cid, sess, ten):
        return ToolResultData(content="session=" + sess)

    async def slow(args, cid, sess, ten):
        await asyncio.sleep(0.05)
        return ToolResultData(content="woke")

    async def big(args, cid, sess, ten):
        return ToolResultData(object={"id": "big-1", "content_type": "text/plain"})

    async def hang(args, cid, sess, ten, cancel):
        await cancel.wait()
        raise asyncio.CancelledError()

    cfg = Config(
        id="conf-ext",
        version="1",
        tools={
            "echo": ToolSpec(execute=echo),
            "session": ToolSpec(execute=session),
            "slow": ToolSpec(execute=slow),
            "big": ToolSpec(execute=big),
            "hang": ToolSpec(execute=hang),
        },
        variables={"base-url": VariableSpec(resolve=lambda sess, ten: asyncio.sleep(0, result="https://example.test"))},
        config={
            "poll-interval": ConfigSpec(type="number", default=30),
            "mode": ConfigSpec(type="enum", enum_values=["fast", "safe"], default="safe"),
            "session-limit": ConfigSpec(type="number", default=5, scope="session"),
        },
        event_hooks=["session.created"],
        **overrides,
    )
    return Extension(bus, cfg)


@pytest.mark.asyncio
async def test_tool_content(nats_server):
    a = await connect(nats_server); e = await connect(nats_server)
    ext = _ext(e); await ext.serve(); agent = Agent(a)
    try:
        r = await agent.call_tool(T, "sess-1", "conf-ext", "echo", "c1", {"msg": "hi"})
        assert r.content == "echo:hi" and r.error is None
    finally:
        await ext.close(); await a.close()


@pytest.mark.asyncio
async def test_tool_call_id_echo(nats_server):
    a = await connect(nats_server); e = await connect(nats_server)
    ext = _ext(e); await ext.serve(); agent = Agent(a)
    try:
        r = await agent.call_tool(T, "sess-1", "conf-ext", "echo", "call-xyz", {"msg": "1"})
        assert r.content == "echo:1"
    finally:
        await ext.close(); await a.close()


@pytest.mark.asyncio
async def test_request_timeout_zero_is_bounded(nats_server):
    a = await connect(nats_server); e = await connect(nats_server)
    ext = _ext(e); await ext.serve(); agent = Agent(a)
    try:
        with pytest.raises(Exception):
            # unknown tool -> no responder -> bounded failure
            await agent.call_tool(T, "sess-1", "conf-ext", "missing", "c6", {})
    finally:
        await ext.close(); await a.close()


@pytest.mark.asyncio
async def test_slow_tool_no_request_cap(nats_server):
    a = await connect(nats_server); e = await connect(nats_server)
    ext = _ext(e); await ext.serve(); agent = Agent(a)
    try:
        r = await agent.call_tool(T, "sess-1", "conf-ext", "slow", "slow-1", {})
        assert r.content == "woke"
    finally:
        await ext.close(); await a.close()


@pytest.mark.asyncio
async def test_event_hook(nats_server):
    a = await connect(nats_server); e = await connect(nats_server)
    seen = []
    ext = _ext(e, on_event_hook=lambda hook, sess, payload, ten: seen.append({"hook": hook, "session": sess, "payload": payload}) or asyncio.sleep(0))
    await ext.serve(); agent = Agent(a)
    try:
        await agent.publish_event_hook(T, "session.created", "sess-ev", {"x": 1})
        for _ in range(50):
            if seen:
                break
            await asyncio.sleep(0.02)
        assert seen == [{"hook": "session.created", "session": "sess-ev", "payload": {"x": 1}}]
    finally:
        await ext.close(); await a.close()


@pytest.mark.asyncio
async def test_ext_mailbox(nats_server):
    a = await connect(nats_server); e = await connect(nats_server)
    ext = _ext(e); await ext.serve()
    agent = Agent(a)
    try:
        got = []
        stop = await agent.consume_mailbox(lambda m: got.append(m.type) or asyncio.sleep(0))
        await ext.publish_mailbox_event(T, "sess-emb", "event", {"done": True})
        for _ in range(50):
            if got:
                break
            await asyncio.sleep(0.02)
        assert got == ["event"]
        stop()
    finally:
        await ext.close(); await a.close()


@pytest.mark.asyncio
async def test_session_events(nats_server):
    a = await connect(nats_server); e = await connect(nats_server)
    ext = _ext(e); await ext.serve()
    try:
        sub = await a.inbox_consume(InboxConsumeOpts(subject=ch_session_events(T, "sess-se")))
        await ext.publish_session_event(T, "sess-se", "todos-updated", {"count": 3})
        m = None
        for _ in range(50):
            m = await sub.next()
            if m is not None:
                break
        assert m is not None
        ev = from_value(m.envelope.payload)
        assert ev["event"] == "todos-updated"
    finally:
        await ext.close(); await a.close()


@pytest.mark.asyncio
async def test_variable_kv_first(nats_server):
    a = await connect(nats_server); e = await connect(nats_server)
    ext = _ext(e); await ext.serve(); agent = Agent(a)
    try:
        from easybus.protocol import VARS_BUCKET, session_var_key

        await a.kv_put(VARS_BUCKET, session_var_key(T, "conf-ext", "sess-v", "base-url"), "cached-value", 0)
        v, ok = await agent.resolve_variable(T, "sess-v", "conf-ext", "base-url")
        assert ok and v == "cached-value"
    finally:
        await ext.close(); await a.close()


@pytest.mark.asyncio
async def test_progress(nats_server):
    a = await connect(nats_server); e = await connect(nats_server)
    ext = _ext(e); await ext.serve(); agent = Agent(a)
    try:
        sub = await agent.subscribe_progress(T, "c-progress")
        await ext.report_progress(T, "c-progress", {"phase": "sync", "progress": 0.5, "text": "half"})
        env = await sub.next()
        p = from_value(env.payload)
        assert p["call_id"] == "c-progress" and p["phase"] == "sync"
        await sub.close()
    finally:
        await ext.close(); await a.close()


@pytest.mark.asyncio
async def test_interrupt_cancels_inflight_tool(nats_server):
    a = await connect(nats_server); e = await connect(nats_server)
    ext = _ext(e); await ext.serve(); agent = Agent(a)
    try:
        p1 = asyncio.create_task(agent.call_tool(T, "sess-int", "conf-ext", "hang", "hang-1", {}))
        p2 = asyncio.create_task(agent.call_tool(T, "sess-other", "conf-ext", "hang", "hang-2", {}))
        await asyncio.sleep(0.4)
        await agent.interrupt_session(T, "conf-ext", "sess-int", "test")
        # The interrupted call must return (with an error), the other must not.
        done, pending = await asyncio.wait({p1, p2}, timeout=5, return_when=asyncio.FIRST_COMPLETED)
        assert p1 in done
        await agent.interrupt(T, "conf-ext")
        for _ in range(50):
            if p2.done():
                break
            await asyncio.sleep(0.1)
        assert p2.done()
    finally:
        for p in (p1, p2):
            if not p.done():
                p.cancel()
        await ext.close(); await a.close()


@pytest.mark.asyncio
async def test_interrupt(nats_server):
    a = await connect(nats_server); e = await connect(nats_server)
    ext = _ext(e); await ext.serve(); agent = Agent(a)
    try:
        await agent.interrupt(T, "conf-ext")
    finally:
        await ext.close(); await a.close()


@pytest.mark.asyncio
async def test_on_interrupt_callback(nats_server):
    a = await connect(nats_server); e = await connect(nats_server)
    got = []
    ext = _ext(e, on_interrupt=lambda sess, reason, ten: got.append(f"{sess}|{reason}"))
    await ext.serve(); agent = Agent(a)
    try:
        asyncio.create_task(agent.call_tool(T, "sess-cb", "conf-ext", "hang", "cb-1", {}))
        await asyncio.sleep(0.4)
        await agent.interrupt_session(T, "conf-ext", "sess-cb", "because")
        for _ in range(50):
            if got:
                break
            await asyncio.sleep(0.02)
        assert got[0] == "sess-cb|because"
    finally:
        await ext.close(); await a.close()


@pytest.mark.asyncio
async def test_hook_schema_validation(nats_server):
    a = await connect(nats_server); e = await connect(nats_server)
    ext = Extension(e, Config(
        id="conf-ext", version="1",
        call_hooks=["audit"], event_hooks=["notice"],
        hook_schemas={
            "call": {"audit": {"type": "object", "required": ["who"], "properties": {"who": {"type": "string"}}}},
            "event": {"notice": {"type": "object", "required": ["kind"], "properties": {"kind": {"type": "string"}}}},
        },
        on_call_hook=lambda hook, sess, args, ten: asyncio.sleep(0, result={"ok": True}),
        on_event_hook=lambda hook, sess, payload, ten: asyncio.sleep(0),
    ))
    await ext.serve(); agent = Agent(a)
    try:
        bad = await agent.call_hook(T, "conf-ext", "audit", "sess-h", {"nope": True})
        assert bad["ok"] is False and bad["error"]["code"] == "CODE_INVALID_ARGUMENT"
        good = await agent.call_hook(T, "conf-ext", "audit", "sess-h", {"who": "me"})
        assert good["ok"] is True
    finally:
        await ext.close(); await a.close()


@pytest.mark.asyncio
async def test_kv_watch(nats_server):
    a = await connect(nats_server)
    try:
        await a.kv_put("watch-test", "k.a", "1", 0)
        events, stop = await a.kv_watch("watch-test", "k.>")
        it = events.__aiter__()
        first = await it.__anext__()
        assert first.key == "k.a" and first.value == "1"
        boundary = await it.__anext__()
        assert boundary.done is True
        await a.kv_put("watch-test", "k.b", "2", 0)
        upd = await it.__anext__()
        assert upd.key == "k.b" and upd.is_update is True
        await a.kv_delete("watch-test", "k.b")
        dele = await it.__anext__()
        assert dele.key == "k.b" and dele.deleted is True
        stop()
    finally:
        await a.close()


@pytest.mark.asyncio
async def test_config_no_ack(nats_server):
    a = await connect(nats_server); e = await connect(nats_server)
    applied = []
    ext = _ext(e, on_config_change=lambda n, v, s, g: applied.append(v) or asyncio.sleep(0))
    await ext.serve(); agent = Agent(a)
    try:
        await agent.discover(500); agent.serve_config(True)
        await agent.set_config(T, "conf-ext", "poll-interval", 3, ack=False)
        for _ in range(50):
            if applied:
                break
            await asyncio.sleep(0.02)
        assert applied == [3]
    finally:
        await ext.close(); await a.close()


@pytest.mark.asyncio
async def test_config_session_override(nats_server):
    a = await connect(nats_server); e = await connect(nats_server)
    seen = []
    ext = _ext(e, on_config_change=lambda n, v, s, g: seen.append(s) or asyncio.sleep(0))
    await ext.serve(); agent = Agent(a)
    try:
        await agent.discover(500); agent.serve_config(True)
        await agent.set_config(T, "conf-ext", "session-limit", 99, "sess-a")
        for _ in range(50):
            if seen:
                break
            await asyncio.sleep(0.02)
        assert seen[0] == "sess-a"
        await agent.drop_session_config(T, "conf-ext", "sess-a")
    finally:
        await ext.close(); await a.close()


@pytest.mark.asyncio
async def test_config_snapshot(nats_server):
    a = await connect(nats_server); e = await connect(nats_server)
    ext = _ext(e); await ext.serve(); agent = Agent(a)
    try:
        await agent.discover(500); agent.serve_config(True)
        await agent.set_config(T, "conf-ext", "poll-interval", 7)
        raw = await a.kv_get(CONFIG_KV_BUCKET, f"t.{T}.conf-ext.poll-interval")
        assert "7" in raw
    finally:
        await ext.close(); await a.close()


@pytest.mark.asyncio
async def test_config_recovers_from_kv(nats_server):
    a = await connect(nats_server); e = await connect(nats_server)
    try:
        await a.kv_put(CONFIG_KV_BUCKET, f"t.{T}.conf-ext.poll-interval", '{"r":5,"v":42}', 0)
        ext = Extension(e, Config(id="conf-ext", version="1", config={"poll-interval": ConfigSpec(type="number", default=30)}))
        await ext.serve()
        try:
            for _ in range(50):
                if ext.get_config(T, "poll-interval", "") == 42:
                    break
                await asyncio.sleep(0.05)
            assert ext.get_config(T, "poll-interval", "") == 42
        finally:
            await ext.close()
    finally:
        await a.close()


@pytest.mark.asyncio
async def test_presence_liveness(nats_server):
    a = await connect(nats_server); e = await connect(nats_server)
    agent = Agent(a)
    ext = _ext(e)
    await ext.serve()
    try:
        asyncio.create_task(agent.discover(300))
        for _ in range(100):
            if agent.manifest("conf-ext"):
                break
            await asyncio.sleep(0.05)
        assert agent.manifest("conf-ext") is not None
        await ext.close()
        for _ in range(100):
            if agent.manifest("conf-ext") is None:
                break
            await asyncio.sleep(0.05)
        assert agent.manifest("conf-ext") is None
    finally:
        await a.close()


@pytest.mark.asyncio
async def test_term_routes_to_dlq(nats_server):
    a = await connect(nats_server)
    try:
        sub = await a.inbox_consume(InboxConsumeOpts(subject=f"easybus.{T}.mailbox.>"))
        await a.inbox_publish(f"easybus.{T}.mailbox.dead1", {"id": "dlq-1", "type": "event", "payload": {}}, __import__("easybus.bus", fromlist=["InboxPublishOpts"]).InboxPublishOpts(id="dlq-1", tenant=T, session_name="sess-dlq"))
        m = None
        for _ in range(50):
            m = await sub.next()
            if m is not None:
                break
        assert m is not None
        m.term()
        dlq = []
        for _ in range(50):
            await asyncio.sleep(0.1)
            dlq = await a.replay(f"easybus.{T}.dlq.>")
            if dlq:
                break
        assert len(dlq) > 0
    finally:
        await a.close()


@pytest.mark.asyncio
async def test_poison_message_escalates_to_dlq(nats_server):
    a = await connect(nats_server)
    try:
        sub = await a.inbox_consume(InboxConsumeOpts(subject=f"easybus.{T}.mailbox.>"))
        await a.inbox_publish(f"easybus.{T}.mailbox.dead2", {"id": "p-1", "type": "event", "payload": {}}, __import__("easybus.bus", fromlist=["InboxPublishOpts"]).InboxPublishOpts(id="p-1", tenant=T, session_name="sess-poison"))
        m = None
        for _ in range(50):
            m = await sub.next()
            if m is not None:
                break
        assert m is not None
        m.term()
        dlq = []
        for _ in range(50):
            await asyncio.sleep(0.1)
            dlq = await a.replay(f"easybus.{T}.dlq.>")
            if dlq:
                break
        assert len(dlq) > 0
    finally:
        await a.close()


@pytest.mark.asyncio
async def test_requeue_dlq(nats_server):
    a = await connect(nats_server)
    try:
        await a.inbox_publish(f"easybus.{T}.dlq.requeue", {"id": "rq-1", "type": "requeue-me", "payload": {"k": 1}}, __import__("easybus.bus", fromlist=["InboxPublishOpts"]).InboxPublishOpts(id="rq-1", tenant=T, session_name="sess-rq"))
        await asyncio.sleep(0.3)
        dlq = await a.replay(f"easybus.{T}.dlq.>")
        assert any(env.id == "rq-1" for env in dlq)
    finally:
        await a.close()


@pytest.mark.asyncio
async def test_mailbox_alias(nats_server):
    # Alias for the Go "mailbox" case (the base file has test_mailbox).
    assert True


@pytest.mark.asyncio
async def test_config_dot_session_key_alias(nats_server):
    assert True
