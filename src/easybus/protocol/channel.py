"""Channel subjects and matching.

A channel is a PUBLISH/SUBSCRIBE topic, distinct from the mailbox, which is a point-to-point
command queue for one session. Keeping them separate matters: a mailbox message drives one
session, while a channel message may interest none or many.

    easybus.<tenant>.channel.<channel>.<topic...>

The tenant segment is not optional and not caller-supplied: publishers name a channel, never a
tenant. That is what makes cross-tenant delivery structurally impossible rather than merely
forbidden by a check.
"""

from __future__ import annotations

import re

#: The KV bucket holding channel subscriptions.
CHANNEL_KV_BUCKET = "subs"

#: Matches every channel message in every tenant (the agent's fan-in consumer uses this).
CH_CHANNEL_ALL = "easybus.*.channel.>"

_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def ch_channel(tenant: str, channel: str, topic: str) -> str:
    """Builds the subject for one channel message.

    Channel and topic are validated rather than escaped: a caller that smuggles a wildcard into
    either would turn one publish into a broadcast.
    """
    for v in (channel, topic):
        if not v or not _SEGMENT_RE.match(v) or v.startswith(".") or v.endswith("."):
            raise ValueError(f"channel and topic must be literal subject segments: {v!r}")
    return f"easybus.{tenant}.channel.{channel}.{topic}"


def parse_channel_subject(subject: str) -> tuple[str, str, str] | None:
    """Splits a channel subject into (tenant, channel, topic), or None.

    The consumer derives the tenant from the SUBJECT rather than the payload: a publisher that
    lied in its payload must not be able to deliver into another tenant's channel. The subject
    is the one thing a publisher cannot forge, because the broker routes on it.
    """
    prefix = "easybus."
    if not subject.startswith(prefix):
        return None
    rest = subject[len(prefix) :]
    i = rest.find(".")
    if i <= 0:
        return None
    tenant = rest[:i]
    tail = rest[i + 1 :]
    if not tail.startswith("channel."):
        return None
    tail = tail[len("channel.") :]
    j = tail.find(".")
    if j <= 0 or j == len(tail) - 1:
        return None
    return tenant, tail[:j], tail[j + 1 :]


def match_subject(pattern: str, topic: str) -> bool:
    """Reports whether a topic matches a subscription pattern, with NATS subject semantics.

    ``*`` matches exactly one segment; ``>`` matches the rest and must be last, covering at least
    one segment. The ``>`` rule was verified against a real broker rather than assumed:
    subscribing to ``tag.>`` delivers ``tag.v1`` but NOT ``tag``.
    """
    if not pattern:
        return False
    p = pattern.split(".")
    t = topic.split(".")
    for i, seg in enumerate(p):
        if seg == ">":
            return len(t) > i
        if i >= len(t):
            return False
        if seg != "*" and seg != t[i]:
            return False
    return len(p) == len(t)
