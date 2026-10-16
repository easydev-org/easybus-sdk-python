"""The transport-agnostic message bus — the Python twin of the Go
`easybus-sdk/bus` package. The wire envelope is the GENERATED
`easybus.v1.Envelope` (see `easybus.wire`); nothing here is hand-written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Protocol

from easybus.wire import Envelope


@dataclass
class RequestOpts:
    timeout_ms: int = 0
    max_wait_ms: int = 0
    session_name: str = ""
    tenant: str = ""


@dataclass
class SubscribeOpts:
    queue: str = ""


@dataclass
class PublishOpts:
    reply_to: str = ""
    tenant: str = ""


@dataclass
class InboxPublishOpts:
    id: str
    session_name: str = ""
    tenant: str = ""


@dataclass
class InboxConsumeOpts:
    subject: str = ""


@dataclass
class KvEvent:
    key: str = ""
    value: str = ""
    revision: int = 0
    deleted: bool = False
    is_update: bool = False
    done: bool = False


class Subscription(Protocol):
    async def next(self) -> Envelope | None: ...
    async def close(self) -> None: ...


class InboxMsg(Protocol):
    envelope: Envelope

    def ack(self) -> None: ...
    def nak(self, delay_ms: int = 0) -> None: ...
    def term(self) -> None: ...
    def term_no_dlq(self) -> None: ...


class InboxSubscription(Protocol):
    async def next(self) -> InboxMsg | None: ...
    async def close(self) -> None: ...


class Bus(Protocol):
    async def request(self, ch: str, payload: Any, opts: RequestOpts | None = None) -> Envelope | None: ...
    async def request_many(self, ch: str, payload: Any, opts: RequestOpts | None = None) -> list[Envelope]: ...
    async def publish(self, ch: str, payload: Any, opts: PublishOpts | None = None) -> None: ...
    async def subscribe(self, ch: str, opts: SubscribeOpts | None = None) -> Subscription: ...

    async def inbox_publish(self, ch: str, payload: Any, opts: InboxPublishOpts) -> None: ...
    async def inbox_consume(self, opts: InboxConsumeOpts) -> InboxSubscription: ...

    async def replay(self, ch: str) -> list[Envelope]: ...

    async def object_put(self, name: str, data: bytes) -> None: ...
    async def object_get(self, name: str) -> bytes | None: ...
    async def object_put_persistent(self, name: str, data: bytes) -> None: ...
    async def object_get_persistent(self, name: str) -> bytes | None: ...

    async def kv_watch(self, bucket: str, keys: str) -> tuple[AsyncIterator[KvEvent], Callable[[], None]]: ...
    async def kv_create(self, bucket: str, key: str, value: str, ttl_ms: int) -> int: ...
    async def kv_put(self, bucket: str, key: str, value: str, ttl_ms: int) -> None: ...
    async def kv_get(self, bucket: str, key: str) -> str: ...
    async def kv_cas(self, bucket: str, key: str, value: str, revision: int) -> int: ...
    async def kv_delete(self, bucket: str, key: str) -> None: ...

    async def close(self) -> None: ...
