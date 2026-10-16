"""The extension role — the Python twin of the Go `easybus-sdk/extension`
package. An Extension registers on the bus (discovery + tool/variable/config/
hook/lifecycle/interrupt channels), heartbeats a per-replica presence key, and
executes tool calls.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from easybus.bus import (
    InboxPublishOpts,
    PublishOpts,
    RequestOpts,
    SubscribeOpts,
)
from easybus.protocol import (
    CONFIG_KV_BUCKET,
    GLOBAL_TENANT,
    LIFECYCLE_WILDCARD,
    CH_DISCOVER,
    VARS_BUCKET,
    ch_mailbox,
    ch_session_events,
    ch_tool_progress,
    new_id,
    session_var_key,
    subject_tenant,
    tenant_object_name,
    var_key,
)
from easybus.wire import (
    ErrorPayload,
    ExtensionConfigItem,
    ExtensionManifest,
    ExtensionTool,
    ExtensionVariable,
    HookResponse,
    LifecycleEvent,
    ToolError,
    ToolResult,
    from_value,
    to_value,
)

MAX_TOOL_CONTENT_BYTES = 128 * 1024
PRESENCE_BUCKET = "easybus-presence"
PRESENCE_TTL = 15_000
PRESENCE_INTERVAL = 5.0

_CODE_INVALID_ARGUMENT = 1
_CODE_NOT_FOUND = 2
_CODE_RETRYABLE = 4
_CODE_INTERNAL = 6

EASYBUS_FEATURES = ["dlq", "config-kv", "presence", "kv-escaping", "interrupt-abort", "progress", "multitenant"]


class TypedError(Exception):
    """Carries a standard protocol error code from a tool execution."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ToolResultData:
    content: str = ""
    data: Any = None
    object: dict | None = None  # {"id": ..., "content_type": ...}


@dataclass
class ToolSpec:
    execute: Callable[..., Awaitable[ToolResultData]]
    description: str = ""
    descriptions: dict[str, str] = field(default_factory=dict)
    input_schema: dict[str, Any] = field(default_factory=dict)
    required_config: list[str] = field(default_factory=list)


@dataclass
class VariableSpec:
    resolve: Callable[..., Awaitable[str]] | None = None
    description: str = ""
    descriptions: dict[str, str] = field(default_factory=dict)
    scope: str = "global"


@dataclass
class ConfigSpec:
    type: str = "string"
    kind: str = "value"
    capability: str = ""
    enum_values: list[str] = field(default_factory=list)
    default: Any = None
    description: str = ""
    descriptions: dict[str, str] = field(default_factory=dict)
    scope: str = "global"


@dataclass
class Config:
    id: str
    version: str = ""
    replica_id: str = ""
    tools: dict[str, ToolSpec] = field(default_factory=dict)
    variables: dict[str, VariableSpec] = field(default_factory=dict)
    config: dict[str, ConfigSpec] = field(default_factory=dict)
    call_hooks: list[str] = field(default_factory=list)
    event_hooks: list[str] = field(default_factory=list)
    lifecycle: list[str] = field(default_factory=list)
    hook_schemas: dict[str, dict] = field(default_factory=dict)
    on_call_hook: Callable | None = None
    on_event_hook: Callable | None = None
    on_config_change: Callable | None = None
    on_lifecycle: Callable | None = None
    on_interrupt: Callable | None = None


async def _invoke_execute(fn, args, call_id, session_name, tenant, cancel):
    """Call a tool handler. Handlers may take 4 args (args, call_id, session,
    tenant) or 5 (…, cancel) — the cancel event lets a handler abort early."""
    import inspect

    try:
        n = len(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        n = 4
    if n >= 5:
        return await fn(args, call_id, session_name, tenant, cancel)
    return await fn(args, call_id, session_name, tenant)


def _sanitize_replica_id(id_: str) -> str:
    out = "".join(c if (c.isalnum() or c in "-_") else "-" for c in id_)
    return out or str(uuid.uuid4())


def _resolve_replica_id(explicit: str) -> str:
    rid = explicit or os.environ.get("EASYBUS_REPLICA_ID", "") or os.environ.get("POD_NAME", "") or str(uuid.uuid4())
    return _sanitize_replica_id(rid)


def validate_hook_schema(schema: dict | None, value: Any, path: str) -> str:
    """The small declarative JSON-schema subset (returns '' when valid)."""
    if not schema:
        return ""
    t = schema.get("type")
    if t == "string" and not isinstance(value, str):
        return f"{path}: expected string, got {type(value).__name__}"
    if t == "number" and not isinstance(value, (int, float)):
        return f"{path}: expected number, got {type(value).__name__}"
    if t == "boolean" and not isinstance(value, bool):
        return f"{path}: expected boolean, got {type(value).__name__}"
    if t == "object":
        if not isinstance(value, dict):
            return f"{path}: expected object"
        for r in schema.get("required", []) or []:
            if r not in value:
                return f'{path}: missing required field "{r}"'
        for name, p in (schema.get("properties", {}) or {}).items():
            if name in value:
                msg = validate_hook_schema(p, value[name], f"{path}.{name}")
                if msg:
                    return msg
    enum_vals = schema.get("enum")
    if isinstance(enum_vals, list) and not any(str(e) == str(value) for e in enum_vals):
        return f"{path}: value not in the declared enum"
    return ""


class ConfigStore:
    """Applied config values per tenant: global set + per-session overrides."""

    def __init__(self) -> None:
        self.global_: dict[str, dict[str, Any]] = {}
        self.session: dict[str, dict[str, dict[str, Any]]] = {}

    def get(self, specs: dict[str, ConfigSpec], tenant: str, name: str, session_name: str) -> Any:
        if session_name:
            v = self.session.get(tenant, {}).get(session_name, {}).get(name)
            if v is not None:
                return v
        v = self.global_.get(tenant, {}).get(name)
        if v is not None:
            return v
        spec = specs.get(name)
        return spec.default if spec else None

    def apply_set(self, tenant: str, name: str, value: Any, session_name: str | None) -> None:
        if session_name:
            self.session.setdefault(tenant, {}).setdefault(session_name, {})[name] = value
            return
        self.global_.setdefault(tenant, {})[name] = value

    def rollback(self, tenant: str, name: str, session_name: str | None) -> None:
        if session_name:
            self.session.get(tenant, {}).get(session_name, {}).pop(name, None)
            return
        self.global_.get(tenant, {}).pop(name, None)

    def set_global(self, tenant: str, name: str, value: Any, deleted: bool) -> None:
        m = self.global_.setdefault(tenant, {})
        if deleted:
            m.pop(name, None)
        else:
            m[name] = value

    def set_session(self, tenant: str, session_name: str, name: str, value: Any, deleted: bool) -> None:
        m = self.session.setdefault(tenant, {}).setdefault(session_name, {})
        if deleted:
            m.pop(name, None)
        else:
            m[name] = value


class Extension:
    """The extension-side role."""

    def __init__(self, bus, cfg: Config) -> None:
        self._b = bus
        self._cfg = cfg
        self.replica_id = _resolve_replica_id(cfg.replica_id)
        self.config_store = ConfigStore()
        self.manifest = self._build_manifest()
        self._subs: list = []
        self._inflight: dict[str, dict[str, asyncio.Event]] = {}
        self._tasks: list[asyncio.Task] = []
        self._stopped = False

    def _build_manifest(self) -> ExtensionManifest:
        m = ExtensionManifest(id=self._cfg.id, version=self._cfg.version, features=EASYBUS_FEATURES)
        caps: list[str] = []
        for name, spec in self._cfg.tools.items():
            m.tools.append(
                ExtensionTool(
                    name=name,
                    description=spec.description,
                    descriptions=spec.descriptions,
                    required_config=spec.required_config,
                )
            )
        if self._cfg.tools:
            caps.append("tools")
        for name, spec in self._cfg.variables.items():
            m.prompt_variables.append(ExtensionVariable(name=name, description=spec.description, descriptions=spec.descriptions, scope=spec.scope or "global"))
        if self._cfg.variables:
            caps.append("prompt")
        for name, spec in self._cfg.config.items():
            item = ExtensionConfigItem(name=name, type=spec.type, kind=spec.kind or "value", scope=spec.scope or "global")
            if spec.capability:
                item.capability = spec.capability
            if spec.description:
                item.description = spec.description
            item.descriptions.update(spec.descriptions)
            item.enum_values.extend(spec.enum_values)
            if spec.default is not None:
                item.default.CopyFrom(to_value(spec.default))
            m.config.append(item)
        m.lifecycle.extend(self._cfg.lifecycle)
        m.capabilities.extend(caps)
        if self._cfg.call_hooks or self._cfg.event_hooks:
            m.hooks.call.extend(self._cfg.call_hooks)
            m.hooks.event.extend(self._cfg.event_hooks)
            for k, v in (self._cfg.hook_schemas.get("call", {}) or {}).items():
                m.hooks.call_schemas[k].update(v)
            for k, v in (self._cfg.hook_schemas.get("event", {}) or {}).items():
                m.hooks.event_schemas[k].update(v)
        return m

    async def serve(self) -> None:
        self._stopped = False
        await self._start_presence()
        await self._serve_discovery()
        await self._serve_config()
        await self._serve_tools()
        await self._serve_variables()
        await self._serve_call_hooks()
        await self._serve_event_hooks()
        await self._serve_lifecycle()
        await self._serve_interrupt()

    async def close(self) -> None:
        self._stopped = True
        for s in self._subs:
            try:
                await s.close()
            except Exception:
                pass
        self._subs = []
        for t in self._tasks:
            t.cancel()
        self._tasks = []
        try:
            await self._b.kv_delete(PRESENCE_BUCKET, self._presence_key())
        except Exception:
            pass
        await self._b.close()

    def _presence_key(self) -> str:
        return f"{self._cfg.id}.{self.replica_id}"

    async def _start_presence(self) -> None:
        async def put() -> None:
            try:
                from easybus.wire import encode_message

                await self._b.kv_put(PRESENCE_BUCKET, self._presence_key(), encode_message(self.manifest).decode("utf-8"), PRESENCE_TTL)
            except Exception:
                pass

        await put()

        async def loop() -> None:
            while not self._stopped:
                await asyncio.sleep(PRESENCE_INTERVAL)
                await put()

        self._tasks.append(asyncio.create_task(loop()))

    async def report_progress(self, tenant: str, call_id: str, progress: dict) -> None:
        await self._b.publish(ch_tool_progress(tenant, call_id), {"call_id": call_id, **progress}, PublishOpts(tenant=tenant))

    async def _serve_discovery(self) -> None:
        sub = await self._b.subscribe(CH_DISCOVER, SubscribeOpts(queue=self._cfg.id))
        self._subs.append(sub)

        async def loop() -> None:
            from easybus.wire import encode_message

            while not self._stopped:
                env = await sub.next()
                if env is None:
                    continue
                if env.reply_to:
                    await self._b.publish(env.reply_to, json.loads(encode_message(self.manifest).decode("utf-8")), PublishOpts(tenant=GLOBAL_TENANT))

        self._tasks.append(asyncio.create_task(loop()))

    async def _serve_tools(self) -> None:
        for name, spec in self._cfg.tools.items():
            sub = await self._b.subscribe(f"easybus.*.tool.call.{self._cfg.id}.{name}", SubscribeOpts(queue=self._cfg.id))
            self._subs.append(sub)
            self._tasks.append(asyncio.create_task(self._tool_loop(name, spec, sub)))

    async def _tool_loop(self, name: str, spec: ToolSpec, sub) -> None:
        while not self._stopped:
            env = await sub.next()
            if env is None or not env.reply_to:
                continue
            asyncio.create_task(self._handle_tool_call(name, spec, env))

    async def _handle_tool_call(self, name: str, spec: ToolSpec, env) -> None:
        reply_to = env.reply_to
        call = from_value(env.payload)
        if not isinstance(call, dict) or not reply_to:
            return
        session_name = env.session_name or ""
        tenant = env.tenant or subject_tenant(env.ch)
        call_id = call.get("call_id", "")
        # A per-call cancellation event: an interrupt sets it, and a tool that
        # observes it (via the 5th execute arg) can abort early.
        cancel = asyncio.Event()
        if session_name:
            self.track_inflight(tenant, session_name, call_id, cancel)
        res = ToolResult(call_id=call_id, tool=name)
        try:
            data = await _invoke_execute(spec.execute, call.get("arguments", {}) or {}, call_id, session_name, tenant, cancel)
            if data.content and len(data.content.encode("utf-8")) > MAX_TOOL_CONTENT_BYTES:
                res.error.CopyFrom(ToolError(code=_CODE_INVALID_ARGUMENT, message=f"tool '{name}' returned {len(data.content.encode('utf-8'))} bytes of text, over the {MAX_TOOL_CONTENT_BYTES}-byte limit; return large data as a file (data.files) instead"))
            elif data.content:
                res.content = data.content
            if not res.HasField("error") and data.data is not None:
                res.data.CopyFrom(to_value(data.data))
            if not res.HasField("error") and data.object is not None:
                res.object.id = data.object["id"]
                if data.object.get("content_type"):
                    res.object.content_type = data.object["content_type"]
        except TypedError as e:
            res.error.CopyFrom(ToolError(code=_code_from_name(e.code), message=e.message))
        except asyncio.CancelledError:
            res.error.CopyFrom(ToolError(code=_CODE_RETRYABLE, message="interrupted"))
        except Exception as e:  # noqa: BLE001
            res.error.CopyFrom(ToolError(code=_CODE_INTERNAL, message=str(e)))
        finally:
            self.untrack_inflight(tenant, session_name, call_id)
        from easybus.wire import encode_message

        await self._b.publish(reply_to, json.loads(encode_message(res).decode("utf-8")), PublishOpts(tenant=tenant))

    async def _serve_variables(self) -> None:
        for name, spec in self._cfg.variables.items():
            sub = await self._b.subscribe(f"easybus.*.var.{self._cfg.id}.{name}", SubscribeOpts(queue=self._cfg.id))
            self._subs.append(sub)
            self._tasks.append(asyncio.create_task(self._var_loop(name, spec, sub)))

    async def _var_loop(self, name: str, spec: VariableSpec, sub) -> None:
        while not self._stopped:
            env = await sub.next()
            if env is None or not env.reply_to or spec.resolve is None:
                continue
            tenant = env.tenant or subject_tenant(env.ch)
            try:
                v = await spec.resolve(env.session_name or "", tenant)
            except Exception:
                v = ""
            await self._b.publish(env.reply_to, {"name": name, "value": v}, PublishOpts(tenant=tenant))

    async def _serve_call_hooks(self) -> None:
        for hook in self._cfg.call_hooks:
            sub = await self._b.subscribe(f"easybus.*.hook.call.{self._cfg.id}.{hook}", SubscribeOpts(queue=self._cfg.id))
            self._subs.append(sub)
            self._tasks.append(asyncio.create_task(self._call_hook_loop(hook, sub)))

    async def _call_hook_loop(self, hook: str, sub) -> None:
        while not self._stopped:
            env = await sub.next()
            if env is None or not env.reply_to:
                continue
            call = from_value(env.payload) or {}
            session_name = call.get("session_name") or env.session_name or ""
            tenant = env.tenant or subject_tenant(env.ch)
            args = call.get("arguments", {}) or {}
            msg = validate_hook_schema(self._cfg.hook_schemas.get("call", {}).get(hook), args, "arguments")
            if msg:
                res = {"ok": False, "error": {"code": _CODE_INVALID_ARGUMENT, "message": msg}}
            elif self._cfg.on_call_hook is None:
                res = {"ok": False, "error": {"code": _CODE_NOT_FOUND, "message": f"no handler for hook {hook}"}}
            else:
                try:
                    res = await self._cfg.on_call_hook(hook, session_name, args, tenant)
                except Exception as e:  # noqa: BLE001
                    res = {"ok": False, "error": {"code": _CODE_INTERNAL, "message": str(e)}}
            await self._b.publish(env.reply_to, res, PublishOpts(tenant=tenant))

    async def _serve_event_hooks(self) -> None:
        for hook in self._cfg.event_hooks:
            sub = await self._b.subscribe(f"easybus.*.hook.event.{hook}", SubscribeOpts(queue=self._cfg.id))
            self._subs.append(sub)
            self._tasks.append(asyncio.create_task(self._event_hook_loop(hook, sub)))

    async def _event_hook_loop(self, hook: str, sub) -> None:
        while not self._stopped:
            env = await sub.next()
            if env is None:
                continue
            ev = from_value(env.payload) or {}
            session_name = ev.get("session_name") or env.session_name or ""
            tenant = env.tenant or subject_tenant(env.ch)
            if validate_hook_schema(self._cfg.hook_schemas.get("event", {}).get(hook), ev.get("payload"), "payload"):
                continue
            if self._cfg.on_event_hook is not None:
                try:
                    await self._cfg.on_event_hook(hook, session_name, ev.get("payload"), tenant)
                except Exception:
                    pass

    async def _serve_lifecycle(self) -> None:
        if not self._cfg.lifecycle or self._cfg.on_lifecycle is None:
            return
        wanted = set(self._cfg.lifecycle)
        sub = await self._b.subscribe(f"{LIFECYCLE_WILDCARD}>", SubscribeOpts(queue=self._cfg.id))
        self._subs.append(sub)

        async def loop() -> None:
            while not self._stopped:
                env = await sub.next()
                if env is None:
                    continue
                ev = from_value(env.payload) or {}
                kind = _lifecycle_kind_string(ev.get("kind"))
                tenant = env.tenant or subject_tenant(env.ch)
                if kind not in wanted:
                    continue
                if kind == "deleted":
                    await self.delete_session_variables(tenant, ev.get("session_name", ""))
                # The handler receives the event with its kind NORMALIZED to the
                # string form (the wire carries the enum number).
                ev["kind"] = kind
                try:
                    r = self._cfg.on_lifecycle(ev, tenant)
                    if asyncio.iscoroutine(r):
                        await r
                except Exception:
                    pass

        self._tasks.append(asyncio.create_task(loop()))

    async def _serve_interrupt(self) -> None:
        sub = await self._b.subscribe(f"easybus.*.ctl.interrupt.{self._cfg.id}", SubscribeOpts(queue=self._cfg.id))
        self._subs.append(sub)

        async def loop() -> None:
            while not self._stopped:
                env = await sub.next()
                if env is None:
                    continue
                sig = from_value(env.payload) or {}
                session_name = sig.get("session_name") or env.session_name or ""
                tenant = env.tenant or subject_tenant(env.ch)
                self._cancel_inflight(tenant, session_name)
                if self._cfg.on_interrupt is not None:
                    self._cfg.on_interrupt(session_name, sig.get("reason", ""), tenant)
                elif self._cfg.on_event_hook is not None:
                    try:
                        await self._cfg.on_event_hook("interrupt", session_name, sig.get("reason"), tenant)
                    except Exception:
                        pass

        self._tasks.append(asyncio.create_task(loop()))

    # ---- inflight tracking -------------------------------------------------

    def _inflight_key(self, tenant: str, session: str) -> str:
        return f"{tenant}\x00{session}"

    def track_inflight(self, tenant: str, session: str, call_id: str, ev: asyncio.Event) -> None:
        self._inflight.setdefault(self._inflight_key(tenant, session), {})[call_id] = ev

    def untrack_inflight(self, tenant: str, session: str, call_id: str) -> None:
        if not session:
            return
        m = self._inflight.get(self._inflight_key(tenant, session))
        if m:
            m.pop(call_id, None)
            if not m:
                self._inflight.pop(self._inflight_key(tenant, session), None)

    def _cancel_inflight(self, tenant: str, session: str) -> None:
        if session:
            m = self._inflight.pop(self._inflight_key(tenant, session), {})
            for ev in m.values():
                ev.set()
        elif tenant:
            for k in [k for k in self._inflight if k.startswith(f"{tenant}\x00")]:
                for ev in self._inflight.pop(k, {}).values():
                    ev.set()
        else:
            for m in self._inflight.values():
                for ev in m.values():
                    ev.set()
            self._inflight.clear()

    # ---- session-facing helpers -------------------------------------------

    async def publish_session_event(self, tenant: str, session_name: str, event: str, params: Any) -> None:
        id_ = new_id()
        await self._b.inbox_publish(ch_session_events(tenant, session_name), {"event": event, "params": params, "eid": id_}, InboxPublishOpts(id=id_, session_name=session_name, tenant=tenant))

    async def publish_mailbox_event(self, tenant: str, session_name: str, event_type: str, payload: Any, source: str = "") -> None:
        id_ = new_id()
        body = {"id": id_, "type": event_type or "event", "payload": payload}
        if source:
            body["source"] = source
        await self._b.inbox_publish(ch_mailbox(tenant, session_name), body, InboxPublishOpts(id=id_, session_name=session_name, tenant=tenant))

    async def put_object(self, tenant: str, name: str, data: bytes) -> None:
        await self._b.object_put(tenant_object_name(tenant, name), data)

    async def get_object(self, tenant: str, name: str) -> bytes | None:
        return await self._b.object_get(tenant_object_name(tenant, name))

    async def set_variable(self, tenant: str, name: str, value: str) -> None:
        await self._b.kv_put(VARS_BUCKET, var_key(tenant, self._cfg.id, name), value, 0)

    async def set_session_variable(self, tenant: str, session_name: str, name: str, value: str) -> None:
        await self._b.kv_put(VARS_BUCKET, session_var_key(tenant, self._cfg.id, session_name, name), value, 0)

    async def delete_session_variables(self, tenant: str, session_name: str) -> None:
        for name, spec in self._cfg.variables.items():
            if spec.scope != "session":
                continue
            try:
                await self._b.kv_delete(VARS_BUCKET, session_var_key(tenant, self._cfg.id, session_name, name))
            except Exception:
                pass

    async def get_session_variable(self, tenant: str, provider: str, session_name: str, name: str, fallback: str) -> str:
        if not session_name:
            return fallback
        try:
            v = await self._b.kv_get(VARS_BUCKET, session_var_key(tenant, provider, session_name, name))
        except Exception:
            v = ""
        return v or fallback

    def get_config(self, tenant: str, name: str, session_name: str) -> Any:
        return self.config_store.get(self._cfg.config, tenant, name, session_name)

    async def _serve_config(self) -> None:
        if not self._cfg.config:
            return
        try:
            events, stop = await self._b.kv_watch(CONFIG_KV_BUCKET, f"t.*.{self._cfg.id}.>")
            self._tasks.append(asyncio.create_task(self._config_kv_loop(events)))
            self._subs.append(_Stopper(stop))
        except Exception:
            pass
        sub = await self._b.subscribe(f"easybus.*.config.{self._cfg.id}", SubscribeOpts(queue=self._cfg.id))
        self._subs.append(sub)
        self._tasks.append(asyncio.create_task(self._config_loop(sub)))

    async def _config_kv_loop(self, events) -> None:
        async for ev in events:
            if ev.done:
                continue
            self._apply_config_kv(ev)

    async def _config_loop(self, sub) -> None:
        while not self._stopped:
            env = await sub.next()
            if env is None or not env.reply_to:
                continue
            raw = from_value(env.payload) or {}
            name = raw.get("name", "")
            scope = raw.get("scope", "global")
            session_name = raw.get("session_name") or env.session_name or ""
            value = raw.get("value")
            tenant = env.tenant or subject_tenant(env.ch)
            self.config_store.apply_set(tenant, name, value, session_name if scope == "session" else None)
            reject: Exception | None = None
            if self._cfg.on_config_change is not None:
                try:
                    res = self._cfg.on_config_change(name, value, session_name, lambda n, s: self.config_store.get(self._cfg.config, tenant, n, s))
                    if asyncio.iscoroutine(res):
                        await res
                except Exception as e:  # noqa: BLE001
                    reject = e
            if reject is not None:
                self.config_store.rollback(tenant, name, session_name if scope == "session" else None)
            if raw.get("ack"):
                res = {"ok": False, "error": {"code": _CODE_INTERNAL, "message": str(reject)}} if reject else {"ok": True}
                await self._b.publish(env.reply_to, res, PublishOpts(tenant=tenant))

    def _apply_config_kv(self, ev) -> None:
        segs = ev.key.split(".")
        if len(segs) < 3 or segs[0] != "t":
            return
        tenant = segs[1]
        rest = ".".join(segs[2:])
        if rest.startswith(f"{self._cfg.id}."):
            rest = rest[len(self._cfg.id) + 1:]
        parts = rest.split(".")
        value: Any = None
        if not ev.deleted:
            try:
                parsed = json.loads(ev.value)
                value = parsed.get("v") if isinstance(parsed, dict) and "v" in parsed else parsed
            except Exception:
                return
            if value is None:
                return
        from easybus.protocol import unescape_kv_segment

        if len(parts) == 1:
            self.config_store.set_global(tenant, parts[0], value, ev.deleted)
        elif len(parts) >= 2:
            # The session segment is KV-escaped in the key; unescape it.
            self.config_store.set_session(tenant, unescape_kv_segment(parts[0]), ".".join(parts[1:]), value, ev.deleted)


class _Stopper:
    def __init__(self, stop: Callable[[], None]) -> None:
        self._stop = stop

    async def close(self) -> None:
        self._stop()


_CODE_BY_NAME = {
    "CODE_UNSPECIFIED": 0,
    "CODE_INVALID_ARGUMENT": 1,
    "CODE_NOT_FOUND": 2,
    "CODE_PERMISSION_DENIED": 3,
    "CODE_RETRYABLE": 4,
    "CODE_BUSINESS": 5,
    "CODE_INTERNAL": 6,
}
_NAME_BY_CODE = {v: k for k, v in _CODE_BY_NAME.items()}


def _code_from_name(name: str | int) -> int:
    if isinstance(name, int):
        return name
    return _CODE_BY_NAME.get(name, 6)


def code_from_wire(code: int | float | str) -> str:
    # google.protobuf.Value carries numbers as float, so accept float too.
    if isinstance(code, bool):
        return code
    if isinstance(code, (int, float)):
        return _NAME_BY_CODE.get(int(code), "CODE_UNSPECIFIED")
    return code


def _lifecycle_kind_string(kind: int | float | str | None) -> str:
    mapping = {0: "", 1: "created", 2: "forked", 3: "renamed", 4: "deleted"}
    # google.protobuf.Value carries numbers as float, so accept float too.
    if isinstance(kind, bool):
        return ""
    if isinstance(kind, (int, float)):
        return mapping.get(int(kind), "")
    return kind or ""
