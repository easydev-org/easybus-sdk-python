"""The NATS transport — the Python twin of the Go `easybus-sdk/transport/nats`
package. The wire envelope is Go-compatible JSON (snake_case, `kind` a short
string). Stream topology (mailbox/events/dlq) and the object/KV buckets match
the Go side.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Callable

import nats
from nats.aio.client import Client as NatsClient
from nats.aio.msg import Msg
from nats.js import JetStreamContext
from nats.js.api import StreamConfig
from nats.js.errors import NotFoundError

from easybus.bus import (
    InboxConsumeOpts,
    InboxPublishOpts,
    KvEvent,
    PublishOpts,
    RequestOpts,
    SubscribeOpts,
)
from easybus.identity import Fields as IdFields, Identity, auth_header, verify
from easybus.protocol import subject_tenant, tenant_prefix, session_token
from easybus.protocol.errors import is_absent_key, is_already_exists, is_lost_race
from easybus.wire import (
    Envelope,
    KIND_TO_STRING,
    decode_envelope,
    encode_envelope,
    envelope_kind_string,
)

STREAM_MAILBOX = "EASYBUS_MAILBOX"
STREAM_EVENTS = "EASYBUS_EVENTS"
STREAM_DLQ = "EASYBUS_DLQ"
INBOX_WILDCARD = "easybus.*.mailbox.>"
EVENTS_WILDCARD = "easybus.*.session.events.>"
LIFECYCLE_WILDCARD = "easybus.*.session.lifecycle.>"
CHANGED_WILDCARD = "easybus.*.session.changed"
DLQ_WILDCARD = "easybus.*.dlq.>"
DURABLE_CONSUMER = "easybus-mailbox-push"
OBJECT_BUCKET = "EASYBUS_TOOL"
# There is deliberately NO durable object bucket constant: persistent bytes live in an
# S3-compatible backend and nowhere else. A NATS bucket for them made "a persistent file" mean S3
# in one deployment and a broker stream in another, with identical code.


def _build_envelope(kind: str, ch: str, payload: Any, tenant: str, id: str = "", session_name: str = "", reply_to: str = "") -> bytes:
    from easybus.wire import to_value

    env = Envelope(v=2, ch=ch, tenant=tenant, kind={"req": Envelope.KIND_REQ, "pub": Envelope.KIND_PUB, "queue": Envelope.KIND_QUEUE}[kind])
    if id:
        env.id = id
    if session_name:
        env.session_name = session_name
    if reply_to:
        env.reply_to = reply_to
    if payload is not None:
        env.payload.CopyFrom(to_value(payload))
    return encode_envelope(env)


def _tenant_of(ch: str, explicit: str = "") -> str:
    return explicit if explicit else subject_tenant(ch)


def _stream_for(subject: str) -> str:
    seg = subject.split(".")
    if len(seg) > 3 and seg[2] == "session" and seg[3] in ("events", "lifecycle", "changed"):
        return STREAM_EVENTS
    if len(seg) > 2 and seg[2] == "dlq":
        return STREAM_DLQ
    return STREAM_MAILBOX


def _dlq_subject_for(subject: str) -> str:
    token = subject.rsplit(".", 1)[-1]
    tenant = subject_tenant(subject)
    return f"{tenant_prefix(tenant)}dlq.{token}" if tenant else f"easybus.dlq.{token}"


async def _ensure_streams(js: JetStreamContext, opts: "Options") -> None:
    # nats-py StreamConfig.max_age is in SECONDS (the server parses it as a
    # time.Duration); the Go SDK passes 24h.
    max_age = (opts.max_age_ns / 1_000_000_000) if opts.max_age_ns > 0 else 24 * 3600
    specs = [
        (STREAM_MAILBOX, [INBOX_WILDCARD]),
        (STREAM_EVENTS, [EVENTS_WILDCARD, LIFECYCLE_WILDCARD, CHANGED_WILDCARD]),
        (STREAM_DLQ, [DLQ_WILDCARD]),
    ]
    for name, subjects in specs:
        try:
            info = await js.stream_info(name)
            existing = set(info.config.subjects or [])
            if existing != set(subjects):
                await js.update_stream(config=StreamConfig(name=name, subjects=subjects, max_age=max_age))
        except NotFoundError:
            await js.add_stream(config=StreamConfig(name=name, subjects=subjects, max_age=max_age))


class NoDurableObjectStoreError(RuntimeError):
    """Raised when persistent file bytes are requested without an S3-compatible backend.

    A fallback to the NATS object store would be a silent change of meaning, not a degradation:
    the bytes would still be stored, in a place the operator did not choose. Refusing is the only
    answer that gives "persistent" one meaning across deployments.
    """


class Options:
    def __init__(self, max_age_ns: int = 0, replicas: int = 0, identity: Identity | None = None) -> None:
        self.max_age_ns = max_age_ns
        self.replicas = replicas
        self.identity = identity


class NatsBus:
    def __init__(
        self,
        nc: NatsClient,
        js: JetStreamContext,
        identity: Identity | None = None,
        durable: Any = None,
    ) -> None:
        self._nc = nc
        self._js = js
        self._idn = identity
        # durable owns the PERSISTENT object path. None means "not configured", and the persistent
        # methods refuse rather than quietly using the broker.
        self._durable = durable

    # ---- auth helpers ------------------------------------------------------

    def _sign(self, headers: dict, ch: str, kind: str, id: str, payload: Any) -> None:
        if self._idn is None:
            return
        h = auth_header(self._idn, IdFields(ch=ch, kind=kind, id=id, payload=payload))
        headers["easybus-id"] = h.id
        headers["easybus-sig"] = h.sig

    def _verify(self, headers: dict, tenant: str, ch: str, kind: str, id: str, payload: Any) -> bool:
        if self._idn is None:
            return True
        sig = (headers or {}).get("easybus-sig", "")
        if not sig:
            return False
        return verify((headers or {}).get("easybus-id", ""), self._idn.secret, IdFields(tenant=tenant, ch=ch, kind=kind, id=id, payload=payload), sig)

    # ---- request / publish / subscribe -------------------------------------

    async def request(self, ch: str, payload: Any, opts: RequestOpts | None = None) -> Envelope | None:
        o = opts or RequestOpts()
        data = _build_envelope("req", ch, payload, _tenant_of(ch, o.tenant), session_name=o.session_name)
        timeout = (o.timeout_ms / 1000.0) if o.timeout_ms > 0 else None
        try:
            msg = await self._nc.request(ch, data, timeout=timeout)
        except Exception:
            return None
        return self._decode_msg(msg)

    async def request_many(self, ch: str, payload: Any, opts: RequestOpts | None = None) -> list[Envelope]:
        o = opts or RequestOpts()
        data = _build_envelope("req", ch, payload, _tenant_of(ch, o.tenant))
        max_wait = (o.max_wait_ms / 1000.0) if o.max_wait_ms > 0 else 0.5
        out: list[Envelope] = []
        inbox = self._nc.new_inbox()
        sub = await self._nc.subscribe(inbox)
        try:
            await self._nc.flush()
            await self._nc.publish(ch, data, reply=inbox)
            deadline = asyncio.get_event_loop().time() + max_wait
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    break
                try:
                    msg = await sub.next_msg(timeout=remaining)
                except Exception:
                    break
                env = self._decode_msg(msg)
                if env is not None:
                    out.append(env)
        finally:
            await sub.unsubscribe()
        return out

    async def publish(self, ch: str, payload: Any, opts: PublishOpts | None = None) -> None:
        o = opts or PublishOpts()
        data = _build_envelope("pub", ch, payload, _tenant_of(ch, o.tenant), reply_to=o.reply_to)
        headers: dict = {}
        self._sign(headers, ch, "pub", "", payload)
        if o.reply_to:
            await self._nc.publish(ch, data, reply=o.reply_to, headers=headers or None)
        else:
            await self._nc.publish(ch, data, headers=headers or None)

    async def subscribe(self, ch: str, opts: SubscribeOpts | None = None) -> "NatsSub":
        o = opts or SubscribeOpts()
        sub = await self._nc.subscribe(ch, queue=o.queue or None)
        await self._nc.flush()
        return NatsSub(sub, self)

    async def inbox_publish(self, ch: str, payload: Any, opts: InboxPublishOpts) -> None:
        data = _build_envelope("queue", ch, payload, _tenant_of(ch, opts.tenant), id=opts.id, session_name=opts.session_name)
        await self._js.publish(ch, data, headers={"Nats-Msg-Id": opts.id})

    async def inbox_consume(self, opts: InboxConsumeOpts) -> "NatsInboxSub":
        subject = opts.subject or INBOX_WILDCARD
        durable = DURABLE_CONSUMER if subject == INBOX_WILDCARD else f"{DURABLE_CONSUMER}-{session_token(subject)}"
        sub = await self._js.pull_subscribe(subject, durable=durable)
        return NatsInboxSub(sub, self)

    async def replay(self, ch: str) -> list[Envelope]:
        out: list[Envelope] = []
        for name in (STREAM_EVENTS, STREAM_MAILBOX, STREAM_DLQ):
            try:
                info = await self._js.stream_info(name)
            except NotFoundError:
                continue
            subjects = info.config.subjects or []
            if not any(s == ch or (("*" in s or ">" in s) and _subject_match(s, ch)) for s in subjects):
                continue
            try:
                from nats.js.api import ConsumerConfig, DeliverPolicy

                # A pull consumer (fetch works on it, unlike a push subscription).
                sub = await self._js.pull_subscribe(
                    ch,
                    stream=name,
                    config=ConsumerConfig(deliver_policy=DeliverPolicy.ALL),
                )
                # A fresh ephemeral consumer; drain the retained window.
                for _ in range(10):
                    msgs = await sub.fetch(1000, timeout=1)
                    if not msgs:
                        break
                    for m in msgs:
                        env = self._decode_msg(m)
                        if env is not None:
                            out.append(env)
            except Exception:
                pass
            break
        return out

    # ---- object store ------------------------------------------------------

    async def _object_store(self, bucket: str, create: bool):
        try:
            return await self._js.object_store(bucket)
        except NotFoundError:
            if create:
                return await self._js.create_object_store(bucket)
            return None

    async def object_put(self, name: str, data: bytes) -> None:
        os = await self._object_store(OBJECT_BUCKET, True)
        await os.put(name, data)

    async def object_get(self, name: str) -> bytes | None:
        os = await self._object_store(OBJECT_BUCKET, False)
        if os is None:
            return None
        try:
            res = await os.get(name)
            return res.data
        except Exception:
            return None

    async def object_put_persistent(self, name: str, data: bytes) -> None:
        """Persistent bytes have exactly ONE backend, and it is not NATS.

        There used to be an OBJECT_BUCKET_DUR fallback here. That is not a degradation but a
        silent change of meaning: the bytes were still stored (so nothing errored), in a place the
        operator did not choose, under the broker's retention rules instead of S3's durability.
        Two deployments running identical code answered "where is this file" differently, and only
        the config said which.

        The TRANSIENT bucket is untouched: those bytes are in-flight hand-off with a 24h TTL, so
        the broker is their correct home.
        """
        if self._durable is None:
            raise NoDurableObjectStoreError(
                "no durable object store configured: persistent files require an "
                "S3-compatible backend"
            )
        await self._durable.object_put_persistent(name, data)

    async def object_get_persistent(self, name: str) -> bytes | None:
        if self._durable is None:
            raise NoDurableObjectStoreError(
                "no durable object store configured: persistent files require an "
                "S3-compatible backend"
            )
        return await self._durable.object_get_persistent(name)

    # ---- KV ----------------------------------------------------------------

    async def _kv(self, bucket: str, ttl_ms: int = 0):
        try:
            return await self._js.key_value(bucket)
        except NotFoundError:
            from nats.js.api import KeyValueConfig

            ttl = (ttl_ms / 1000.0) if ttl_ms > 0 else None
            return await self._js.create_key_value(KeyValueConfig(bucket=bucket, ttl=ttl))

    async def kv_watch(self, bucket: str, keys: str) -> tuple[AsyncIterator[KvEvent], Callable[[], None]]:
        kv = await self._kv(bucket)
        # `watchall` ignores a key filter; `watch` takes it. Use `watch` so the
        # `t.*.<ext>.>` filter actually applies.
        watcher = await kv.watch(keys=keys)
        state = {"snapshots_left": None, "done_emitted": False}
        # Prime the snapshot count by a status query.
        try:
            status = await kv.status()
            state["snapshots_left"] = status.values
        except Exception:
            state["snapshots_left"] = 0

        async def gen() -> AsyncIterator[KvEvent]:
            # nats-py delivers the initial snapshot first (is_update False), then
            # a synthetic "done" marker (entry is None), then live updates.
            while True:
                try:
                    entry = await watcher.updates(timeout=2)
                except asyncio.TimeoutError:
                    return
                # nats-py yields a StopIterSentinel when the watcher ends.
                if entry is None or entry.__class__.__name__ == "StopIterSentinel":
                    yield KvEvent(done=True)
                    continue
                if not hasattr(entry, "key"):
                    continue
                yield KvEvent(
                    key=entry.key,
                    value=entry.value.decode("utf-8") if entry.value else "",
                    revision=entry.revision,
                    deleted=_is_deleted(entry.operation),
                    is_update=True,
                    done=False,
                )

        return gen(), watcher.stop

    async def kv_create(self, bucket: str, key: str, value: str, ttl_ms: int) -> int:
        kv = await self._kv(bucket, ttl_ms)
        try:
            return await kv.create(key, value.encode("utf-8"))
        except Exception as e:
            # "already exists" is the normal LOSING side of a claim race: the caller reads 0 as
            # "somebody else has it" and backs off. Every OTHER error is raised — swallowing them
            # made a broken bucket indistinguishable from a lost race, so a replica that could not
            # reach the broker believed another replica owned the session and never ran the turn.
            if is_already_exists(e):
                return 0
            raise

    async def kv_put(self, bucket: str, key: str, value: str, ttl_ms: int) -> None:
        kv = await self._kv(bucket, ttl_ms)
        await kv.put(key, value.encode("utf-8"))

    async def kv_get(self, bucket: str, key: str) -> str:
        try:
            kv = await self._kv(bucket)
            e = await kv.get(key)
            return e.value.decode("utf-8") if e.value else ""
        except Exception as e:
            # A MISS, not a failure: the key is absent (deleted, or expired under a short TTL —
            # the server reports "no message found" for that). Callers already treat "" as
            # absent.
            #
            # Any OTHER error is raised. Swallowing everything made a dead connection or a
            # missing bucket look exactly like "the key is not set", so a caller took its default
            # branch and never retried.
            if is_absent_key(e):
                return ""
            raise

    async def kv_cas(self, bucket: str, key: str, value: str, revision: int) -> int:
        try:
            kv = await self._kv(bucket)
            return await kv.update(key, value.encode("utf-8"), last=revision)
        except Exception as e:
            # A lost CAS is a normal outcome: 0 with NO error. Anything else is a real failure,
            # and collapsing the two is what let a network blip abort a healthy in-flight turn —
            # the caller reads 0 as "the lease was LOST".
            if is_lost_race(e):
                return 0
            raise

    async def kv_delete(self, bucket: str, key: str) -> None:
        kv = await self._kv(bucket)
        try:
            await kv.delete(key)
        except Exception:
            pass

    async def close(self) -> None:
        await self._nc.drain()

    # ---- decode ------------------------------------------------------------

    def _decode_msg(self, msg: Msg) -> Envelope | None:
        try:
            env = decode_envelope(msg.data)
        except Exception:
            return None
        if not self._verify(msg.headers or {}, env.tenant, msg.subject, envelope_kind_string(env), env.id, None):
            return None
        if not env.reply_to and msg.reply:
            env.reply_to = msg.reply
        return env


class NatsSub:
    def __init__(self, sub, bus: NatsBus) -> None:
        self._sub = sub
        self._bus = bus

    async def next(self) -> Envelope | None:
        try:
            msg = await self._sub.next_msg(timeout=2)
        except asyncio.TimeoutError:
            return None
        return self._bus._decode_msg(msg)

    async def close(self) -> None:
        await self._sub.unsubscribe()


class NatsInboxSub:
    def __init__(self, sub, bus: NatsBus) -> None:
        self._sub = sub
        self._bus = bus

    async def next(self):
        try:
            msgs = await self._sub.fetch(1, timeout=2)
        except asyncio.TimeoutError:
            return None
        if not msgs:
            return None
        m = msgs[0]
        env = self._bus._decode_msg(m)
        if env is None:
            return None
        _b = self._bus

        class _Msg:
            envelope = env

            def ack(self) -> None:
                asyncio.create_task(m.ack())

            def nak(self, delay_ms: int = 0) -> None:
                asyncio.create_task(m.nak(delay=delay_ms / 1000.0))

            def term(self) -> None:
                async def _t():
                    try:
                        await _b._js.publish(_dlq_subject_for(m.subject), m.data, headers={"Nats-Msg-Id": env.id} if env.id else None)
                    except Exception as e:  # noqa: BLE001
                        import sys

                        print("[easybus] dlq publish failed:", e, file=sys.stderr, flush=True)
                    await m.term()

                asyncio.create_task(_t())

            def term_no_dlq(self) -> None:
                asyncio.create_task(m.term())

        return _Msg()

    async def close(self) -> None:
        pass


def _is_deleted(op) -> bool:
    """The KV entry operation is a KV_OP enum (or a string); treat DEL/PURGE as
    deleted."""
    if op is None:
        return False
    name = getattr(op, "name", None) or str(op)
    return name in ("DEL", "PURGE")


def _subject_match(pattern: str, subject: str) -> bool:
    p = pattern.split(".")
    s = subject.split(".")
    pi = 0
    for si in range(len(s)):
        if pi >= len(p):
            return False
        pt = p[pi]
        if pt == ">":
            return True
        if pt == "*":
            pi += 1
            continue
        if pt != s[si]:
            return False
        pi += 1
    return pi == len(p)


async def connect(url: str = "nats://127.0.0.1:4222", opts: Options | None = None) -> NatsBus:
    """Connect a NATS bus with the default stream topology."""
    o = opts or Options()
    nc = await nats.connect(url)
    js = nc.jetstream()
    await _ensure_streams(js, o)
    return NatsBus(nc, js, o.identity)
