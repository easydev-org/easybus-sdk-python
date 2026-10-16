"""The protocol conformance suite — the Python twin of easybus-sdk's Go
conformance and easybus-sdk-typescript's conformance tests. Runs against a real
nats-server (skips when the binary is unavailable)."""
import asyncio

import pytest

from easybus.agent import Agent, ConfigError
from easybus.bus import InboxConsumeOpts, RequestOpts
from easybus.extension import Config, ConfigSpec, Extension, ToolResultData, ToolSpec, TypedError, VariableSpec
from easybus.protocol import CONFIG_KV_BUCKET, ch_config, new_id
from easybus.transport.nats import connect
from easybus.wire import Envelope, from_value

T = "t1"


def _full_ext(bus, **overrides):
    async def echo(args, cid, sess, ten):
        return ToolResultData(content="echo:" + str(args.get("msg", "")))

    async def add(args, cid, sess, ten):
        return ToolResultData(data={"sum": float(args.get("a", 0)) + float(args.get("b", 0))})

    async def session(args, cid, sess, ten):
        return ToolResultData(content="session=" + sess)

    async def slow(args, cid, sess, ten):
        await asyncio.sleep(0.05)
        return ToolResultData(content="woke")

    async def big(args, cid, sess, ten):
        return ToolResultData(object={"id": "big-1", "content_type": "text/plain"})

    async def boom(args, cid, sess, ten):
        raise TypedError("CODE_BUSINESS", "nope")

    cfg = Config(
        id="conf-ext",
        version="1",
        tools={
            "echo": ToolSpec(execute=echo),
            "add": ToolSpec(execute=add),
            "session": ToolSpec(execute=session),
            "slow": ToolSpec(execute=slow),
            "big": ToolSpec(execute=big),
            "boom": ToolSpec(execute=boom),
        },
        variables={"base-url": VariableSpec(resolve=lambda sess, ten: asyncio.sleep(0, result="https://example.test"))},
        config={
            "poll-interval": ConfigSpec(type="number", default=30),
            "mode": ConfigSpec(type="enum", enum_values=["fast", "safe"], default="safe"),
            "session-limit": ConfigSpec(type="number", default=5, scope="session"),
        },
        call_hooks=["session.before_create"],
        on_call_hook=overrides.pop("on_call_hook", lambda hook, sess, args, ten: asyncio.sleep(0, result={"ok": True, "data": {"session": sess, "hook": hook}})),
        event_hooks=["session.created"],
        **overrides,
    )
    return Extension(bus, cfg)


@pytest.mark.asyncio
async def test_discover(nats_server):
    a = await connect(nats_server)
    e = await connect(nats_server)
    ext = _full_ext(e)
    await ext.serve()
    agent = Agent(a)
    try:
        ms = await agent.discover(500)
        m = next((x for x in ms if x.id == "conf-ext"), None)
        assert m is not None
        assert sorted(t.name for t in m.tools) == ["add", "big", "boom", "echo", "session", "slow"]
        assert "tools" in m.capabilities
        assert "prompt" in m.capabilities
    finally:
        await ext.close()
        await a.close()


@pytest.mark.asyncio
async def test_tool_content_and_data(nats_server):
    a = await connect(nats_server)
    e = await connect(nats_server)
    ext = _full_ext(e)
    await ext.serve()
    agent = Agent(a)
    try:
        r = await agent.call_tool(T, "sess-1", "conf-ext", "echo", "c1", {"msg": "hi"})
        assert r.content == "echo:hi"
        assert r.error is None
        d = await agent.call_tool(T, "sess-1", "conf-ext", "add", "c2", {"a": 2, "b": 3})
        assert d.data == {"sum": 5.0}
    finally:
        await ext.close()
        await a.close()


@pytest.mark.asyncio
async def test_tool_error_mapping(nats_server):
    a = await connect(nats_server)
    e = await connect(nats_server)
    ext = _full_ext(e)
    await ext.serve()
    agent = Agent(a)
    try:
        r = await agent.call_tool(T, "sess-1", "conf-ext", "boom", "c3", {})
        assert r.error["code"] == "CODE_BUSINESS"
        assert r.error["message"] == "nope"
    finally:
        await ext.close()
        await a.close()


@pytest.mark.asyncio
async def test_tool_session_name(nats_server):
    a = await connect(nats_server)
    e = await connect(nats_server)
    ext = _full_ext(e)
    await ext.serve()
    agent = Agent(a)
    try:
        r = await agent.call_tool(T, "my-session", "conf-ext", "session", "c4", {})
        assert r.content == "session=my-session"
    finally:
        await ext.close()
        await a.close()


@pytest.mark.asyncio
async def test_slow_tool(nats_server):
    a = await connect(nats_server)
    e = await connect(nats_server)
    ext = _full_ext(e)
    await ext.serve()
    agent = Agent(a)
    try:
        r = await agent.call_tool(T, "sess-1", "conf-ext", "slow", "slow-1", {})
        assert r.content == "woke"
    finally:
        await ext.close()
        await a.close()


@pytest.mark.asyncio
async def test_tool_object_offload(nats_server):
    a = await connect(nats_server)
    e = await connect(nats_server)
    ext = _full_ext(e)
    await ext.serve()
    agent = Agent(a)
    try:
        r = await agent.call_tool(T, "sess-1", "conf-ext", "big", "c5", {})
        assert r.object["id"] == "big-1"
    finally:
        await ext.close()
        await a.close()


@pytest.mark.asyncio
async def test_variable(nats_server):
    a = await connect(nats_server)
    e = await connect(nats_server)
    ext = _full_ext(e)
    await ext.serve()
    agent = Agent(a)
    try:
        v, ok = await agent.resolve_variable(T, "sess-1", "conf-ext", "base-url")
        assert ok and v == "https://example.test"
    finally:
        await ext.close()
        await a.close()


@pytest.mark.asyncio
async def test_call_hook(nats_server):
    a = await connect(nats_server)
    e = await connect(nats_server)
    ext = _full_ext(e)
    await ext.serve()
    agent = Agent(a)
    try:
        hr = await agent.call_hook(T, "conf-ext", "session.before_create", "sess-h", {"k": "v"})
        assert hr["ok"] is True
        assert hr["data"] == {"session": "sess-h", "hook": "session.before_create"}
    finally:
        await ext.close()
        await a.close()


@pytest.mark.asyncio
async def test_kv(nats_server):
    a = await connect(nats_server)
    try:
        await a.kv_put("test-bucket", "k1", "v1", 0)
        assert await a.kv_get("test-bucket", "k1") == "v1"
        await a.kv_delete("test-bucket", "k1")
        assert await a.kv_get("test-bucket", "k1") == ""
    finally:
        await a.close()


@pytest.mark.asyncio
async def test_object_store(nats_server):
    a = await connect(nats_server)
    try:
        await a.object_put("o1", b"hello bytes")
        got = await a.object_get("o1")
        assert got == b"hello bytes"
    finally:
        await a.close()


@pytest.mark.asyncio
async def test_mailbox(nats_server):
    a = await connect(nats_server)
    agent = Agent(a)
    try:
        got = []
        agent2 = Agent(a)
        stop = await agent2.consume_mailbox(lambda m: got.append(m.type) or asyncio.sleep(0))
        await agent2.publish_mailbox(T, "sess-mb", "trigger", {"text": "hello"}, "user")
        for _ in range(50):
            if got:
                break
            await asyncio.sleep(0.02)
        assert got == ["trigger"]
        stop()
    finally:
        await a.close()


@pytest.mark.asyncio
async def test_config_set_and_apply(nats_server):
    a = await connect(nats_server)
    e = await connect(nats_server)
    applied = []
    ext = _full_ext(e, on_config_change=lambda name, value, sess, get: applied.append({"name": name, "value": value}) or asyncio.sleep(0))
    await ext.serve()
    agent = Agent(a)
    try:
        await agent.discover(500)
        agent.serve_config(True)
        await agent.set_config(T, "conf-ext", "poll-interval", 60)
        for _ in range(30):
            if applied:
                break
            await asyncio.sleep(0.02)
        assert applied == [{"name": "poll-interval", "value": 60}]
        assert ext.get_config(T, "poll-interval", "") == 60
    finally:
        await ext.close()
        await a.close()


@pytest.mark.asyncio
async def test_config_rejected(nats_server):
    a = await connect(nats_server)
    e = await connect(nats_server)

    def reject(name, value, sess, get):
        if name == "poll-interval":
            raise ValueError("rejected")
        return asyncio.sleep(0)

    ext = _full_ext(e, on_config_change=reject)
    await ext.serve()
    agent = Agent(a)
    try:
        await agent.discover(500)
        agent.serve_config(True)
        with pytest.raises(ConfigError) as ei:
            await agent.set_config(T, "conf-ext", "poll-interval", 99)
        assert ei.value.code == "retryable"
        assert "rejected" in ei.value.message
    finally:
        await ext.close()
        await a.close()


@pytest.mark.asyncio
async def test_config_validation(nats_server):
    a = await connect(nats_server)
    e = await connect(nats_server)
    ext = _full_ext(e)
    await ext.serve()
    agent = Agent(a)
    try:
        await agent.discover(500)
        agent.serve_config(True)
        with pytest.raises(ConfigError):
            await agent.set_config(T, "conf-ext", "poll-interval", "fast")
        with pytest.raises(ConfigError):
            await agent.set_config(T, "conf-ext", "mode", "turbo")
        with pytest.raises(ConfigError):
            await agent.set_config(T, "conf-ext", "nope", 1)
    finally:
        await ext.close()
        await a.close()


@pytest.mark.asyncio
async def test_lifecycle(nats_server):
    a = await connect(nats_server)
    e = await connect(nats_server)
    received = []
    ext = Extension(e, Config(id="lc-ext", version="1", lifecycle=["created", "forked", "renamed", "deleted"], on_lifecycle=lambda ev, ten: received.append(ev["kind"]) or asyncio.sleep(0)))
    await ext.serve()
    agent = Agent(a)
    try:
        for kind in ["created", "forked", "renamed", "deleted"]:
            await agent.publish_lifecycle_event(T, kind, "sess-lc", {"k": kind})
        for _ in range(100):
            if len(received) >= 4:
                break
            await asyncio.sleep(0.02)
        assert received == ["created", "forked", "renamed", "deleted"]
    finally:
        await ext.close()
        await a.close()


@pytest.mark.asyncio
async def test_session_lease(nats_server):
    a1 = await connect(nats_server)
    a2 = await connect(nats_server)
    ag1 = Agent(a1)
    ag2 = Agent(a2)
    session = "sess-lease-" + new_id()[:8]
    try:
        r1 = await ag1.claim_session(T, session, 1000)
        r2 = await ag2.claim_session(T, session, 1000)
        assert not (r1 is None and r2 is None)
        assert not (r1 is not None and r2 is not None)
        holder = ag1 if r1 is not None else ag2
        other = ag2 if r1 is not None else ag1
        rev = r1 or r2
        assert await holder.is_session_running(T, session) is True
        nxt = await holder.renew_session(T, session, rev, 1000)
        assert nxt is not None and nxt > rev
        assert await holder.renew_session(T, session, rev, 1000) is None
        await holder.release_session(T, session)
        assert await holder.is_session_running(T, session) is False
        assert await other.claim_session(T, session, 1000) is not None
        await other.release_session(T, session)
    finally:
        await a1.close()
        await a2.close()


@pytest.mark.asyncio
async def test_config_dot_session_key(nats_server):
    a = await connect(nats_server)
    e = await connect(nats_server)
    agent = Agent(a)
    agent.serve_config(True)
    sess = "weird.session.name:main"
    try:
        from easybus.wire import ExtensionManifest

        m = ExtensionManifest(id="conf-ext", version="1")
        item = m.config.add()
        item.name = "dots"
        item.type = "string"
        item.scope = "session"
        await agent.set_config(T, "conf-ext", "dots", "escaped-ok", sess, manifest=m)
        ext = Extension(e, Config(id="conf-ext", version="1", config={"dots": ConfigSpec(type="string", scope="session")}))
        await ext.serve()
        try:
            for _ in range(50):
                if ext.get_config(T, "dots", sess) == "escaped-ok":
                    break
                await asyncio.sleep(0.05)
            assert ext.get_config(T, "dots", sess) == "escaped-ok"
        finally:
            await ext.close()
    finally:
        await a.close()


@pytest.mark.asyncio
async def test_presence_replica_keys(nats_server):
    a = await connect(nats_server)
    e1 = await connect(nats_server)
    e2 = await connect(nats_server)

    async def echo(args, cid, sess, ten):
        return ToolResultData(content="x")

    r1 = Extension(e1, Config(id="conf-ext", version="1", replica_id="pod-a", tools={"echo": ToolSpec(execute=echo)}))
    r2 = Extension(e2, Config(id="conf-ext", version="1", replica_id="pod-b", tools={"echo": ToolSpec(execute=echo)}))
    await r1.serve()
    await r2.serve()
    try:
        for _ in range(50):
            v1 = await a.kv_get("easybus-presence", "conf-ext.pod-a")
            v2 = await a.kv_get("easybus-presence", "conf-ext.pod-b")
            if v1 and v2:
                break
            await asyncio.sleep(0.05)
        assert await a.kv_get("easybus-presence", "conf-ext.pod-a")
        assert await a.kv_get("easybus-presence", "conf-ext.pod-b")
        await r1.close()
        for _ in range(50):
            if not await a.kv_get("easybus-presence", "conf-ext.pod-a"):
                break
            await asyncio.sleep(0.05)
        assert await a.kv_get("easybus-presence", "conf-ext.pod-a") == ""
        assert await a.kv_get("easybus-presence", "conf-ext.pod-b")
    finally:
        await r2.close()
        await a.close()
