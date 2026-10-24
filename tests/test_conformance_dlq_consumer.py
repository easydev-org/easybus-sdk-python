"""The consumer side of the DLQ.

The other DLQ cases prove a message ARRIVES in the dead-letter stream. This proves something can
pick it up — a queue nobody reads is a graveyard, and before ``consume_dlq`` existed that was the
only option in this SDK.
"""

from __future__ import annotations

import asyncio

import pytest

from easybus.agent import Agent
from easybus.bus import InboxPublishOpts
from easybus.transport.nats import connect

pytestmark = pytest.mark.integration

T = "t1"


async def test_dlq_consumer_delivers(nats_server):
    a = await connect(nats_server)
    try:
        seen: list[str] = []

        async def handler(m) -> bool:
            seen.append(m["type"])
            return True  # ack

        stop = await Agent(a).consume_dlq(handler)
        # The subscription is established asynchronously; give it a beat so the test fails on
        # DELIVERY rather than on a subscribe race.
        await asyncio.sleep(0.5)

        tag = "dlq-deliver-abc123"
        await a.inbox_publish(
            f"easybus.{T}.dlq.{tag}",
            {"id": tag, "type": tag, "payload": {"n": 1}},
            InboxPublishOpts(id=tag, tenant=T, session_name="sess-dlq2"),
        )

        for _ in range(150):
            if tag in seen:
                break
            await asyncio.sleep(0.1)
        assert tag in seen, f"consume_dlq never delivered {tag}; saw {seen}"
        stop()
    finally:
        await a.close()
