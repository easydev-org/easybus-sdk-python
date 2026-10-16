import asyncio
import os
import socket
import subprocess
import tempfile
import time

import pytest


def _wait_port(port, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.05)
    return False


@pytest.fixture
def nats_server():
    """A real nats-server (memory JetStream). Skips when the binary is absent."""
    bin_ = os.environ.get("EASYBUS_NATS_SERVER_BIN", "nats-server")
    port = 15200 + int.from_bytes(os.urandom(2), "big") % 1000
    d = tempfile.mkdtemp(prefix="easybus-py-")
    try:
        proc = subprocess.Popen([bin_, "-p", str(port), "-sd", d, "-js"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pytest.skip("no nats-server available (set EASYBUS_NATS_SERVER_BIN)")
    if not _wait_port(port):
        proc.kill()
        pytest.skip("nats-server did not start")
    try:
        yield f"nats://127.0.0.1:{port}"
    finally:
        proc.kill()
