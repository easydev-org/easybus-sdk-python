"""Agent-served file RPCs — the Python twin of the Go `easybus-sdk/extension`
`filerpc.go` (and the TS `extension/filerpc.ts`).

A DB-less, store-less extension (no S3 credentials, no agent DB) cannot mint a
canonical ``file:<code>`` on its own, so it asks the AGENT to persist the bytes
+ metadata via the SAME path as an in-process ingest.

BYTES NEVER RIDE THE MESSAGE: the bytes are first put in the transient object
store (chunked by the transport, so any size is fine) and only the object
reference travels in the request.
"""

from __future__ import annotations

from typing import Any

from easybus.bus import RequestOpts
from easybus.protocol import ch_file_get, ch_file_ingest, new_id, tenant_object_name


async def ingest_file_via_agent(bus, tenant: str, name: str, data: bytes, session_name: str = "") -> tuple[str, str]:
    """Store bytes through the AGENT (a 1:1 ``req`` on
    ``easybus.<tenant>.file.ingest``) and return the canonical ``file:<code>``
    plus the content type the agent DERIVED from the bytes (callers pass no mime).
    """
    obj = f"{new_id()}.ingest"
    await bus.object_put(tenant_object_name(tenant, obj), data)
    req: dict[str, Any] = {"name": name, "object": obj}
    if session_name:
        req["session_name"] = session_name
    env = await bus.request(
        ch_file_ingest(tenant),
        req,
        RequestOpts(timeout_ms=60_000, tenant=tenant, session_name=session_name),
    )
    if env is None:
        raise RuntimeError("file ingest: no reply")
    from easybus.wire import from_value

    res = from_value(env.payload) or {}
    if not res.get("ok"):
        msg = (res.get("error") or {}).get("message", "failed")
        raise RuntimeError(f"file ingest: {msg}")
    return res.get("code", ""), res.get("mime", "")


async def get_file_via_agent(bus, tenant: str, code: str) -> tuple[dict, bytes] | None:
    """Fetch a stored file's bytes + metadata through the agent (a 1:1 ``req``
    on ``easybus.<tenant>.file.get``). Returns None when the file is absent. The
    agent writes the bytes to the transient object store and returns the
    reference, so the bytes never ride the message.
    """
    env = await bus.request(
        ch_file_get(tenant),
        {"code": code},
        RequestOpts(timeout_ms=60_000, tenant=tenant),
    )
    if env is None:
        return None
    from easybus.wire import from_value

    res = from_value(env.payload) or {}
    if not res.get("ok") or not res.get("meta") or not res.get("object"):
        return None
    data = await bus.object_get(tenant_object_name(tenant, res["object"]))
    if data is None:
        return None
    return res["meta"], data
