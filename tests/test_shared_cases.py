"""Run the shared, language-neutral conformance cases.

The cases live in conformance-cases/ and describe behaviour every SDK must
implement identically. Reading the same files in every SDK is what stops four
hand-written test suites from drifting apart: the CONFIG decoder had the same
defect in all four languages, each suite passed, and nothing compared them.

The copy is pinned by cases.lock. A mismatch means this SDK has not been refreshed
after the contract changed — which would otherwise keep passing while asserting an
older behaviour.
"""
import hashlib
import json
import os
import pathlib

import pytest

from easybus.extension import Config, ConfigSpec, Extension
from easybus.protocol import CONFIG_KV_BUCKET
from easybus.transport.nats import connect

CASES_DIR = pathlib.Path(__file__).resolve().parent.parent / "conformance-cases"


def _cases():
    return sorted(CASES_DIR.glob("*.json"))


def _digest() -> str:
    h = hashlib.sha256()
    for p in _cases():
        h.update(p.read_bytes())
    return h.hexdigest()


def test_shared_cases_are_current():
    want = (CASES_DIR / "cases.lock").read_text().strip()
    assert _digest() == want, (
        "conformance-cases/ does not match cases.lock — run "
        "conformance/cases/gen-lock.sh in the SDK repo that owns the change, then "
        "copy conformance-cases/ into this one"
    )


def test_shared_cases_exist():
    assert _cases(), "no shared cases found"


@pytest.mark.integration
@pytest.mark.parametrize("path", _cases(), ids=lambda p: p.stem)
def test_shared_case(path, nats_server):
    case = json.loads(path.read_text())
    kind = case["kind"]
    if kind == "constant":
        _run_constant(case)
    elif kind == "kv":
        _run_kv(case, nats_server)
    else:
        pytest.fail(f"unknown case kind {kind!r}")


@pytest.mark.integration
def test_nats_binary_is_available():
    """The shared config cases must not pass by skipping.

    The `nats_server` fixture SKIPS when no broker binary is present, which turns a
    missing dependency into a green run — and the KV recovery path it guards (the only
    way a restarted extension learns its configuration, and where every config defect
    in this SDK was found) is exactly what would go untested.

    This asserts the BINARY exists without using the fixture, so it fails instead of
    skipping. It is marked `integration` so the unit-test job — which deliberately has
    no broker — excludes it; the broker-dependent job (and the compose image) include
    it, and there the absence of a broker is a real failure rather than a green skip.
    """
    import shutil

    bin_ = os.environ.get("EASYBUS_NATS_SERVER_BIN", "nats-server")
    assert shutil.which(bin_) is not None, (
        "nats-server not found — the shared config cases need a real broker and would "
        "otherwise skip. Run `docker compose up --build --exit-code-from conformance`, "
        "or set EASYBUS_NATS_SERVER_BIN to the binary."
    )


def _run_constant(case):
    c = case["constant"]
    if c["name"] == "configKVBucket":
        assert CONFIG_KV_BUCKET == c["value"], case["why"]
    else:
        pytest.fail(f"unknown constant {c['name']!r}")


def _run_kv(case, url):
    """Seed one bucket key, start an extension, assert the knob resolves."""
    import asyncio

    async def run():
        tenant, ext_id = "shared-t1", "shared-ext"
        key = case["kv"]["key"].replace("{tenant}", tenant).replace("{ext}", ext_id)
        specs = {name: ConfigSpec(type=k["type"]) for name, k in case["knobs"].items()}
        conf = Config(id=ext_id, version="1", config=specs)
        a = await connect(url)
        e = await connect(url)
        try:
            await a.kv_put(CONFIG_KV_BUCKET, key, case["kv"]["value"], 0)
            ext = Extension(e, conf)
            await ext.serve()
            try:
                want = case["expect"]["value"]
                vt = case["expect"]["valueType"]
                for _ in range(100):
                    if _matches(ext.get_config(tenant, case["expect"]["knob"], ""), want, vt):
                        return
                    await asyncio.sleep(0.05)
                got = ext.get_config(tenant, case["expect"]["knob"], "")
                pytest.fail(f"{case['expect']['knob']} = {got!r}, want {want!r} ({vt}). {case['why']}")
            finally:
                await ext.close()
        finally:
            await a.close()

    asyncio.run(run())


def _matches(got, want, value_type):
    """Compare by the TYPE the case declares, not the language's representation."""
    if value_type == "string":
        return isinstance(got, str) and got == want
    if value_type == "number":
        return isinstance(got, (int, float)) and not isinstance(got, bool) and float(got) == float(want)
    if value_type == "bool":
        return isinstance(got, bool) and got is want
    if value_type == "null":
        return got is None
    return False
