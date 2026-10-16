"""The agent-served file RPCs: an extension ingests bytes through a stub agent
and gets back a canonical file code; it can fetch them back. Runs against a real
nats-server (skips when the binary is unavailable)."""
import asyncio

import pytest

from easybus.bus import PublishOpts
from easybus.extension import get_file_via_agent, ingest_file_via_agent
from easybus.protocol import ch_file_get, ch_file_ingest, tenant_object_name
from easybus.transport.nats import connect
from easybus.wire import from_value

T = "t1"


async def _stub_agent(bus, tenant: str):
    """A minimal stand-in for easyagent's file service."""
    ing = await bus.subscribe(ch_file_ingest(tenant))
    get = await bus.subscribe(ch_file_get(tenant))
    store: dict[str, dict] = {}

    async def ingest_loop():
        while True:
            env = await ing.next()
            if env is None or not env.reply_to:
                continue
            req = from_value(env.payload) or {}
            code = "abc123def4567890"
            data = await bus.object_get(tenant_object_name(tenant, req["object"]))
            store[code] = {"name": req.get("name", ""), "mime": "image/png", "bytes": data or b""}
            await bus.publish(env.reply_to, {"ok": True, "code": code, "mime": "image/png"}, PublishOpts(tenant=tenant))

    async def get_loop():
        while True:
            env = await get.next()
            if env is None or not env.reply_to:
                continue
            req = from_value(env.payload) or {}
            rec = store.get(req.get("code", ""))
            if rec is None:
                await bus.publish(env.reply_to, {"ok": False}, PublishOpts(tenant=tenant))
                continue
            obj = f"out-{req['code']}"
            await bus.object_put(tenant_object_name(tenant, obj), rec["bytes"])
            await bus.publish(
                env.reply_to,
                {"ok": True, "meta": {"code": req["code"], "name": rec["name"], "mime": rec["mime"], "size": len(rec["bytes"])}, "object": obj},
                PublishOpts(tenant=tenant),
            )

    asyncio.create_task(ingest_loop())
    asyncio.create_task(get_loop())
    return ing, get


@pytest.mark.asyncio
async def test_ingest_and_get_via_agent(nats_server):
    ext = await connect(nats_server)
    agent = await connect(nats_server)
    ing, get = await _stub_agent(agent, T)
    try:
        code, mime = await ingest_file_via_agent(ext, T, "shot.png", b"\x89PNG fake bytes", "sess-1")
        assert code == "abc123def4567890"
        assert mime == "image/png"
        got = await get_file_via_agent(ext, T, code)
        assert got is not None
        meta, data = got
        assert meta["name"] == "shot.png"
        assert data == b"\x89PNG fake bytes"
    finally:
        await ing.close()
        await get.close()
        await ext.close()
        await agent.close()


@pytest.mark.asyncio
async def test_get_missing_returns_none(nats_server):
    ext = await connect(nats_server)
    agent = await connect(nats_server)
    ing, get = await _stub_agent(agent, T)
    try:
        assert await get_file_via_agent(ext, T, "nope") is None
    finally:
        await ing.close()
        await get.close()
        await ext.close()
        await agent.close()
