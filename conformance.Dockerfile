# Runs the conformance suite against a REAL broker.
#
# Same shape as the other three SDKs' images, so a failure means the IMPLEMENTATION
# differs rather than the environment. The broker version matches the one pinned in
# docker-compose.yml.
#
# Build context is the repository root.
FROM python:3.13-slim AS base

# nats-server is required by the pytest fixture that starts one per test module; the
# compose broker covers the shared case but the fixture still needs the binary.
#
# Downloaded with Python rather than curl+apt: the image already has an interpreter,
# and adding a package manager round-trip means the build depends on an apt mirror
# being reachable — which is exactly what broke first, and for a tool we then delete.
ARG NATS_VERSION=2.15.1
# ARG values are only visible to RUN as build-time variables when promoted to ENV;
# without this the heredoc sees an empty string and downloads the wrong URL.
ENV NATS_VERSION=${NATS_VERSION}
RUN python - <<'PY'
import io, os, tarfile, urllib.request
v = os.environ.get("NATS_VERSION", "2.15.1")
url = f"https://github.com/nats-io/nats-server/releases/download/v{v}/nats-server-v{v}-linux-amd64.tar.gz"
data = urllib.request.urlopen(url, timeout=120).read()
with tarfile.open(fileobj=io.BytesIO(data)) as tf:
    member = tf.getmember(f"nats-server-v{v}-linux-amd64/nats-server")
    member.name = "nats-server"
    tf.extract(member, "/usr/local/bin")
os.chmod("/usr/local/bin/nats-server", 0o755)
PY

WORKDIR /src

# Dependency layer first: pyproject.toml changes far less often than src/.
COPY pyproject.toml pytest.ini ./
COPY src ./src
RUN pip install --no-cache-dir -e . && pip install --no-cache-dir pytest pytest-asyncio

COPY tests ./tests
COPY conformance-cases ./conformance-cases

RUN useradd -m -u 10001 runner && chown -R runner /src
USER runner

# ONLY the shared cases and the module-level fixtures they need.
#
# The full `tests/` suite includes cases that assume they own the broker (event hooks,
# presence timeouts) and cases that inspect the checkout (`test_proto_sync` reads
# `proto/`). Neither belongs in an image whose purpose is "do four implementations
# agree about config" — and running them here would fail for reasons that say nothing
# about this SDK. They run in the `test` job, which has its own broker and the full
# source tree.
#
# `-p no:cacheprovider` keeps the run reproducible: no .pytest_cache to leak between
# invocations of a reused container.
ENTRYPOINT ["python", "-m", "pytest", "tests/test_shared_cases.py", "-v", "-p", "no:cacheprovider"]
