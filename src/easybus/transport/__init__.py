"""Transport wiring. There is exactly ONE transport — NATS — mirroring the Go
SDK."""

from . import nats as nats  # noqa: F401

__all__ = ["nats"]
