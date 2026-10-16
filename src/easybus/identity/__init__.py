"""Static pre-shared identity signing (HMAC-SHA256) — the Python twin of the Go
`easybus-sdk/identity` package. A message carries the sender's `easybus-id`
plus an HMAC (`easybus-sig`) over canonical fields.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    id: str
    secret: str


@dataclass(frozen=True)
class Fields:
    ch: str
    kind: str
    tenant: str = ""
    id: str = ""
    payload: object = None


@dataclass(frozen=True)
class Header:
    id: str
    sig: str


def _canonical(identity_id: str, f: Fields) -> str:
    payload = ""
    if f.payload is not None:
        try:
            payload = json.dumps(f.payload, separators=(",", ":"), sort_keys=False)
        except (TypeError, ValueError):
            payload = ""
    return f"{identity_id}\n{f.tenant}\n{f.ch}\n{f.kind}\n{f.id}\n{payload}"


def _sign(identity: Identity, f: Fields) -> str:
    mac = hmac.new(identity.secret.encode("utf-8"), _canonical(identity.id, f).encode("utf-8"), hashlib.sha256)
    return base64.urlsafe_b64encode(mac.digest()).decode("ascii").rstrip("=")


def auth_header(identity: Identity, f: Fields) -> Header:
    """Build the sender-side auth header."""
    return Header(id=identity.id, sig=_sign(identity, f))


def verify(claimed_id: str, secret: str, f: Fields, provided: str) -> bool:
    """Check an HMAC against a known secret, constant-time."""
    want = _sign(Identity(id=claimed_id, secret=secret), f)
    return hmac.compare_digest(want, provided)
