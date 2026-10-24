"""The agent role — the Python twin of the Go `easybus-sdk/agent` package.
Discovers extensions (presence-first, broadcast fallback), calls tools,
resolves variables, fires hooks, interrupts, drives the mailbox, and owns the
config authority + session lease.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Callable

from easybus.bus import (
    InboxConsumeOpts,
    InboxPublishOpts,
    PublishOpts,
    RequestOpts,
    SubscribeOpts,
)
from easybus.extension import code_from_wire
from easybus.protocol import (
    CH_DISCOVER,
    GLOBAL_TENANT,
    ch_config,
    ch_hook_call,
    ch_hook_event,
    ch_interrupt,
    ch_lifecycle,
    ch_mailbox,
    ch_session_events,
    ch_tool_call,
    new_id,
    session_token,
    session_var_key,
    subject_tenant,
    tenant_kv_key,
    tenant_object_name,
    var_key,
    VARS_BUCKET,
    escape_kv_segment,
)
from easybus.wire import (
    ConfigSet,
    Envelope,
    ExtensionManifest,
    decode_message,
    encode_message,
    from_value,
    to_value,
)

PRESENCE_BUCKET = "easybus-presence"
LEASE_BUCKET = "easybus-session-state"
LEASE_TTL_DEFAULT_MS = 30_000


class ConfigError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass
class ToolResult:
    content: str = ""
    data: Any = None
    metadata: Any = None
    object: dict | None = None
    error: dict | None = None


@dataclass
class MailboxMessage:
    id: str
    type: str
    source: str
    payload: Any
    session_name: str
    tenant: str


def _manifest_from_wire(payload: Any) -> ExtensionManifest | None:
    if not isinstance(payload, dict) or not payload.get("id"):
        return None
    return decode_message(ExtensionManifest, json.dumps(payload).encode("utf-8"))


class Agent:
    """The agent-side role."""

    def __init__(self, bus) -> None:
        self._b = bus
        self._manifest_cache: dict[str, ExtensionManifest] = {}
        self._live_presence: dict[str, set[str]] = {}
        self._presence_started = False
        self._presence_stop = None
        # config authority
        self._declarations: dict[str, dict[str, list]] = {}
        self._global: dict[str, dict[str, dict]] = {}
        self._sessions: dict[str, dict[str, dict[str, dict]]] = {}
        self._config_started = False
        self._default_ack = False

    # ---- discovery ---------------------------------------------------------

    def ext_supports(self, ext_id: str, feature: str) -> bool:
        m = self._manifest_cache.get(ext_id)
        return bool(m) and feature in (m.features or [])

    def manifest(self, ext_id: str) -> ExtensionManifest | None:
        return self._manifest_cache.get(ext_id)

    async def discover(self, max_wait_ms: int = 500) -> list[ExtensionManifest]:
        await self._ensure_presence()
        if self._manifest_cache:
            return list(self._manifest_cache.values())
        replies = await self._b.request_many(CH_DISCOVER, {}, RequestOpts(max_wait_ms=max_wait_ms, tenant=GLOBAL_TENANT))
        seen: set[str] = set()
        out: list[ExtensionManifest] = []
        for r in replies:
            m = _manifest_from_wire(from_value(r.payload))
            if m is None or m.id in seen:
                continue
            seen.add(m.id)
            self._manifest_cache[m.id] = m
            out.append(m)
        return out

    async def _ensure_presence(self) -> None:
        if self._presence_started:
            return
        self._presence_started = True
        try:
            events, stop = await self._b.kv_watch(PRESENCE_BUCKET, ">")
            self._presence_stop = stop
            asyncio.create_task(self._presence_loop(events))
        except Exception:
            self._presence_started = False

    async def _presence_loop(self, events) -> None:
        async for ev in events:
            if ev.done or not ev.key:
                continue
            ext_id = ev.key.split(".", 1)[0]
            if ev.deleted:
                self._forget_presence(ext_id, ev.key)
                continue
            m = _manifest_from_wire(json.loads(ev.value)) if ev.value else None
            if m is not None:
                self._manifest_cache[m.id] = m
            self._live_presence.setdefault(ext_id, set()).add(ev.key)

    def _forget_presence(self, ext_id: str, key: str) -> None:
        s = self._live_presence.get(ext_id)
        if not s:
            return
        s.discard(key)
        if not s:
            self._live_presence.pop(ext_id, None)
            self._manifest_cache.pop(ext_id, None)

    # ---- tool calls --------------------------------------------------------

    async def call_tool(self, tenant: str, session_name: str, ext_id: str, tool: str, call_id: str, args: dict) -> ToolResult:
        reply = await self._b.request(ch_tool_call(tenant, ext_id, tool), {"call_id": call_id, "arguments": args}, RequestOpts(session_name=session_name, tenant=tenant))
        if reply is None:
            raise RuntimeError(f'tool "{tool}": no reply')
        tr = from_value(reply.payload) or {}
        r = ToolResult(content=tr.get("content", "") or "", data=tr.get("data"), metadata=tr.get("metadata"))
        if tr.get("error"):
            r.error = {"code": code_from_wire(tr["error"].get("code")), "message": tr["error"].get("message", "")}
        if tr.get("object"):
            obj = tr["object"]
            r.object = {"id": obj.get("id", ""), "content_type": obj.get("content_type", "")}
        return r

    async def resolve_variable(self, tenant: str, session_name: str, provider: str, name: str) -> tuple[str, bool]:
        cached = await self._b.kv_get(VARS_BUCKET, session_var_key(tenant, provider, session_name, name))
        if cached:
            return cached, True
        cached_global = await self._b.kv_get(VARS_BUCKET, var_key(tenant, provider, name))
        if cached_global:
            return cached_global, True
        reply = await self._b.request(f"easybus.{tenant}.var.{provider}.{name}", {}, RequestOpts(session_name=session_name, tenant=tenant))
        if reply is None:
            return "", False
        v = from_value(reply.payload) or {}
        return v.get("value", ""), True

    async def call_hook(self, tenant: str, ext_id: str, hook: str, session_name: str, args: dict) -> dict | None:
        reply = await self._b.request(ch_hook_call(tenant, ext_id, hook), {"hook": hook, "session_name": session_name, "arguments": args}, RequestOpts(session_name=session_name, tenant=tenant))
        if reply is None:
            return None
        r = from_value(reply.payload) or {}
        if r.get("error"):
            r["error"] = {"code": code_from_wire(r["error"].get("code")), "message": r["error"].get("message", "")}
        return r

    async def interrupt(self, tenant: str, ext_id: str) -> None:
        await self._b.publish(ch_interrupt(tenant, ext_id), {}, PublishOpts(tenant=tenant))

    async def interrupt_session(self, tenant: str, ext_id: str, session_name: str, reason: str = "") -> None:
        body = {"session_name": session_name}
        if reason:
            body["reason"] = reason
        await self._b.publish(ch_interrupt(tenant, ext_id), body, PublishOpts(tenant=tenant))

    async def publish_lifecycle_event(self, tenant: str, kind: str, session_name: str, payload: Any = None) -> None:
        body: dict[str, Any] = {"kind": _lifecycle_kind_enum(kind), "session_name": session_name}
        if payload is not None:
            body["payload"] = payload
        await self._b.publish(ch_lifecycle(tenant, kind), body, PublishOpts(tenant=tenant))

    async def publish_event_hook(self, tenant: str, hook: str, session_name: str, payload: Any) -> None:
        await self._b.publish(ch_hook_event(tenant, hook), {"hook": hook, "session_name": session_name, "payload": payload}, PublishOpts(tenant=tenant))

    async def subscribe_progress(self, tenant: str, call_id: str):
        return await self._b.subscribe(f"easybus.{tenant}.tool.progress.{call_id}")

    async def publish_mailbox(self, tenant: str, session_name: str, typ: str, payload: Any, source: str = "") -> None:
        id_ = new_id()
        body = {"id": id_, "type": typ, "payload": payload}
        if source:
            body["source"] = source
        await self._b.inbox_publish(ch_mailbox(tenant, session_name), body, InboxPublishOpts(id=id_, session_name=session_name, tenant=tenant))

    async def consume_dlq(self, handler) -> Callable[[], None]:
        """Subscribes to every dead-letter message and hands each to ``handler``.

        Dead letters are messages a consumer gave up on after repeated failures. Without this they
        accumulate in the DLQ stream and nobody finds out — the failure is real but silent, which
        is the worst combination.

        ``handler`` returns True to ack the message, False to leave it in the DLQ (nacked, retried
        later). A message that cannot be resolved to a tenant or session is TERMINATED rather than
        dead-lettered again: dead letters of dead letters help nobody.

        Returns a stop function.
        """
        sub = await self._b.inbox_consume(InboxConsumeOpts(subject="easybus.*.dlq.>"))
        stopped = False
        task = asyncio.create_task(self._dlq_loop(sub, handler, lambda: stopped))

        def stop() -> None:
            nonlocal stopped
            stopped = True
            task.cancel()

        return stop

    async def _dlq_loop(self, sub, handler, is_stopped) -> None:
        while not is_stopped():
            msg = await sub.next()
            if msg is None:
                return
            env = msg.envelope
            session_name = env.session_name or ""
            tenant = env.tenant or subject_tenant(env.ch)
            payload = from_value(env.payload) if env.payload is not None else {}
            if not isinstance(payload, dict):
                payload = {}
            if not session_name or not tenant or not env.id or not payload.get("id"):
                # A dead letter with no address cannot be retried meaningfully.
                msg.term_no_dlq()
                continue
            resolved = {
                "id": payload.get("id", ""),
                "tenant": tenant,
                "session_name": session_name,
                "type": payload.get("type", ""),
                "payload": payload.get("payload"),
            }
            if await handler(resolved):
                msg.ack()
            else:
                msg.nak(5000)

    async def publish_session_event(self, tenant: str, session_name: str, event: str, params: Any) -> None:
        id_ = new_id()
        await self._b.inbox_publish(ch_session_events(tenant, session_name), {"event": event, "params": params, "eid": id_}, InboxPublishOpts(id=id_, session_name=session_name, tenant=tenant))

    async def consume_mailbox(self, handler) -> callable:
        sub = await self._b.inbox_consume(InboxConsumeOpts(subject="easybus.*.mailbox.>"))
        stopped = {"v": False}

        async def loop() -> None:
            while not stopped["v"]:
                m = await sub.next()
                if m is None:
                    continue
                env = m.envelope
                tenant = env.tenant or subject_tenant(env.ch)
                body = from_value(env.payload) or {}
                msg = MailboxMessage(
                    id=body.get("id", env.id),
                    type=body.get("type", ""),
                    source=body.get("source", ""),
                    payload=body.get("payload"),
                    session_name=env.session_name or "",
                    tenant=tenant,
                )
                try:
                    await handler(msg)
                    m.ack()
                except Exception:
                    m.nak(1000)

        asyncio.create_task(loop())

        def stop() -> None:
            stopped["v"] = True

        return stop

    async def put_object(self, tenant: str, name: str, data: bytes) -> None:
        await self._b.object_put(tenant_object_name(tenant, name), data)

    async def get_object(self, tenant: str, name: str) -> bytes | None:
        return await self._b.object_get(tenant_object_name(tenant, name))

    # ---- config authority --------------------------------------------------

    def serve_config(self, default_ack: bool = True) -> None:
        self._config_started = True
        self._default_ack = default_ack

    async def set_config(self, tenant: str, ext_id: str, name: str, value: Any, session_name: str = "", manifest: ExtensionManifest | None = None, ack: bool | None = None) -> None:
        if not self._config_started:
            raise ConfigError("invalid_argument", "ServeConfig() was not called")
        m = manifest or self._manifest_cache.get(ext_id)
        if m is None:
            raise ConfigError("not_found", f"no manifest for {ext_id}; Discover() first")
        await self._declare(tenant, m)
        await self._set(tenant, ext_id, name, value, session_name, ack)

    async def _declare(self, tenant: str, m: ExtensionManifest) -> None:
        self._declarations.setdefault(tenant, {})[m.id] = list(m.config)
        for item in m.config:
            raw = await self._b.kv_get("cfg", _config_kv_key(tenant, m.id, "global", "", item.name))
            if not raw:
                continue
            try:
                env = json.loads(raw)
                rev = env.get("r", 0)
                val = env.get("v") if isinstance(env, dict) and "v" in env else env
            except Exception:
                continue
            by = self._global.setdefault(tenant, {}).setdefault(m.id, {})
            cur = by.get(item.name)
            if cur is None or rev > cur["revision"]:
                by[item.name] = {"revision": rev, "value": val}

    async def _set(self, tenant: str, ext_id: str, name: str, value: Any, session_name: str, ack: bool | None) -> None:
        items = self._declarations.get(tenant, {}).get(ext_id, [])
        item = next((it for it in items if it.name == name), None)
        if item is None:
            raise ConfigError("not_found", f"config {name} not declared by {ext_id}")
        scope = item.scope or "global"
        if scope == "session" and not session_name:
            raise ConfigError("invalid_argument", f"config {name} requires a session name (scope=session)")
        msg = _validate_config_value(item, value)
        if msg:
            raise ConfigError("invalid_argument", msg)

        use_ack = self._default_ack if ack is None else ack
        if scope == "global":
            by = self._global.setdefault(tenant, {}).setdefault(ext_id, {})
            revision = (by.get(name, {}).get("revision", 0)) + 1
            by[name] = {"revision": revision, "value": value}
        else:
            by = self._sessions.setdefault(tenant, {}).setdefault(ext_id, {}).setdefault(session_name, {})
            revision = (by.get(name, {}).get("revision", 0)) + 1
            by[name] = {"revision": revision, "value": value}

        await self._b.kv_put("cfg", _config_kv_key(tenant, ext_id, scope, session_name, name), json.dumps({"r": revision, "v": value}), 0)

        payload = {"name": name, "value": value, "revision": revision, "scope": scope, "ack": use_ack, "tenant": tenant}
        if session_name:
            payload["session_name"] = session_name
        reply = await self._b.request(ch_config(tenant, ext_id), payload, RequestOpts(timeout_ms=5000 if use_ack else 300, tenant=tenant, session_name=session_name))
        if not use_ack or reply is None:
            return
        hr = from_value(reply.payload) or {}
        if not hr.get("ok"):
            if scope == "global":
                b = self._global.get(tenant, {}).get(ext_id, {})
                if b.get(name, {}).get("revision") == revision:
                    b.pop(name, None)
            else:
                b = self._sessions.get(tenant, {}).get(ext_id, {}).get(session_name, {})
                if b.get(name, {}).get("revision") == revision:
                    b.pop(name, None)
            await self._b.kv_delete("cfg", _config_kv_key(tenant, ext_id, scope, session_name, name))
            raise ConfigError("retryable", (hr.get("error") or {}).get("message", "extension rejected the config change"))

    async def drop_session_config(self, tenant: str, ext_id: str, session_name: str) -> None:
        by = self._sessions.get(tenant, {}).get(ext_id, {}).get(session_name)
        if not by:
            return
        for name in list(by.keys()):
            await self._b.kv_delete("cfg", _config_kv_key(tenant, ext_id, "session", session_name, name))
        self._sessions.get(tenant, {}).get(ext_id, {}).pop(session_name, None)

    # ---- session lease -----------------------------------------------------

    async def claim_session(self, tenant: str, session_name: str, ttl_ms: int = LEASE_TTL_DEFAULT_MS) -> int | None:
        ttl = ttl_ms if ttl_ms > 0 else LEASE_TTL_DEFAULT_MS
        rev = await self._b.kv_create(LEASE_BUCKET, tenant_kv_key(tenant, session_token(session_name)), "running", ttl)
        return rev or None

    async def renew_session(self, tenant: str, session_name: str, revision: int, ttl_ms: int = LEASE_TTL_DEFAULT_MS) -> int | None:
        rev = await self._b.kv_cas(LEASE_BUCKET, tenant_kv_key(tenant, session_token(session_name)), "running", revision)
        return rev or None

    async def release_session(self, tenant: str, session_name: str) -> None:
        await self._b.kv_delete(LEASE_BUCKET, tenant_kv_key(tenant, session_token(session_name)))

    async def is_session_running(self, tenant: str, session_name: str) -> bool:
        v = await self._b.kv_get(LEASE_BUCKET, tenant_kv_key(tenant, session_token(session_name)))
        return bool(v)

    async def close(self) -> None:
        if self._presence_stop:
            r = self._presence_stop()
            if asyncio.iscoroutine(r):
                await r
        await self._b.close()


def _config_kv_key(tenant: str, ext_id: str, scope: str, session_name: str, name: str) -> str:
    if scope == "session":
        return tenant_kv_key(tenant, f"{ext_id}.{escape_kv_segment(session_name)}.{name}")
    return tenant_kv_key(tenant, f"{ext_id}.{name}")


def _validate_config_value(item, value: Any) -> str:
    t = item.type
    if t == "string" and not isinstance(value, str):
        return f"expected string, got {type(value).__name__}"
    if t == "number" and not isinstance(value, (int, float)):
        return f"expected number, got {type(value).__name__}"
    if t == "boolean" and not isinstance(value, bool):
        return f"expected boolean, got {type(value).__name__}"
    if t == "enum":
        if not isinstance(value, str):
            return f"expected enum string, got {type(value).__name__}"
        if item.enum_values and value not in item.enum_values:
            return f'value "{value}" not in the declared enum values'
    if t == "json":
        return ""
    return ""


def _lifecycle_kind_enum(kind: str) -> int:
    return {"created": 1, "forked": 2, "renamed": 3, "deleted": 4}.get(kind, 0)
