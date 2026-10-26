"""Classifying a transport error is a PROTOCOL concern, not a transport detail.

Four SDKs talk to the same broker, and each has to answer the same question when a KV call fails:
is this an expected outcome (a lost race, an absent key) or a real failure? Getting it wrong is
silent in both directions:

  - a lost CAS reported as a failure -> the lease is renewed against a revision it no longer owns,
    or a healthy turn is aborted because a network blip looked like a takeover;
  - a network failure reported as "the key is absent" -> an extension starts with no configuration
    and reports itself unconfigured, while the config is plainly set.

Every SDK had the second shape (``except Exception: return 0``). The classification lives here
once, and the shared conformance table pins it for all four implementations.
"""

from __future__ import annotations


def _message_of(err: object) -> str:
    """Lower-cased text of an error, whatever shape it arrived in.

    The nats-py client raises its own exception types, but a wrapper may surface a plain
    ``Exception`` or a string. Matching on ``str(err)`` alone loses nothing for the first two, but
    a bare non-string would become its repr, so the message attribute is preferred when present.
    """
    msg = getattr(err, "message", None)
    if isinstance(msg, str):
        return msg.lower()
    return str(err).lower()


def is_lost_race(err: object) -> bool:
    """The server's rejection of a CAS that lost a race (10071 "wrong last sequence")."""
    if err is None:
        return False
    # Two phrasings exist in the wild, with and without the ``stream`` prefix; the shared
    # substring covers both, so a server-version difference cannot silently reclassify a normal
    # outcome.
    return "wrong last sequence" in _message_of(err)


def is_already_exists(err: object) -> bool:
    """A create() that found the key already present.

    The other losing side of a claim race, and equally normal: the caller reads revision 0 as
    "somebody else holds it".
    """
    if err is None:
        return False
    return "already exists" in _message_of(err)


def is_absent_key(err: object) -> bool:
    """An absent key: deleted, or expired under a short TTL.

    "no message found" (10037) is what get() raises once the value expired between being listed
    and being read. It is a MISS — treating it as an error makes the caller take its error path
    when the correct behaviour is the default one.
    """
    if err is None:
        return False
    m = _message_of(err)
    return "no message found" in m or "key not found" in m


def is_consumer_gone(err: object) -> bool:
    """A JetStream consumer that no longer exists.

    A durable consumer can be deleted underneath a long-lived subscription: operator cleanup, a
    stream reset, or the server reclaiming it. A pull Fetch then fails IMMEDIATELY with "no
    responders", which one deployment read as "nothing to read" — 2,814,600 empty pulls, no
    delivery, no log. The fix is to rebuild, not to keep asking.
    """
    if err is None:
        return False
    m = _message_of(err)
    return (
        "consumer not found" in m
        or "consumer deleted" in m
        or "no responders" in m
    )
