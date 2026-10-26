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
from easybus.protocol.errors import is_absent_key, is_consumer_gone, is_lost_race
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


def _cases_of_kind(kind: str):
    """Cases of one kind, for parametrisation.

    Split by KIND rather than filtered inside a single test: a `constant` case asserts
    a protocol value and needs no broker, so it must run in the unit job — which has
    none. Marking every case `integration` would have quietly dropped it from that job
    for a reason that does not apply to it.
    """
    out = []
    for p in _cases():
        case = json.loads(p.read_text())
        if case.get("kind") == kind:
            out.append(pytest.param(p, id=p.stem))
    return out


@pytest.mark.parametrize("path", _cases_of_kind("constant"))
def test_shared_constant_case(path):
    _run_constant(json.loads(path.read_text()))


@pytest.mark.parametrize("path", _cases_of_kind("permission-matching"))
def test_shared_permission_matching_case(path):
    """The grant-matching rules, from the shared table.

    Pure computation, so no broker: this runs in the unit job, which means a rule that drifts in
    this SDK fails immediately rather than at the next integration run.

    These rules are the security boundary of every extension, implemented once per language. Two
    SDKs that disagree do not fail loudly — they authorise different things for the same grant,
    depending on which language the extension happens to be written in.
    """
    from easybus.extension import matches

    case = json.loads(path.read_text())
    cases = case.get("cases") or []
    assert cases, f"{case['id']}: no cases"
    for i, mc in enumerate(cases):
        assert matches(mc["grant"], mc["target"]) is mc["want"], f"{case['id']} case {i}: {mc['why']}"


@pytest.mark.integration
@pytest.mark.parametrize("path", _cases_of_kind("kv"))
def test_shared_kv_case(path, nats_server):
    # Prefer the broker the environment provides (docker-compose.yml), falling back to
    # the fixture's private one. Using the shared broker is the POINT of the container:
    # it is the pinned version every other SDK tests against.
    _run_kv(json.loads(path.read_text()), os.environ.get("EASYBUS_NATS_URL") or nats_server)


@pytest.mark.parametrize("path", _cases_of_kind("error-classification"))
def test_shared_error_classification_case(path):
    """Pin how a transport error is CATEGORISED.

    The shared half of the KV fix. Every SDK used to collapse every failure into a zero value
    (``except Exception: return 0``), which made a lost race and a broken connection
    indistinguishable. The zero value is CORRECT for a lost race and catastrophic for anything
    else, so the category is the contract.

    No broker: this is pure text matching, so it runs in the unit job.
    """
    case = json.loads(path.read_text())
    entries = case.get("cases") or []
    assert entries, f"{case['id']}: no cases"

    for i, mc in enumerate(entries):
        msg = mc.get("err") or ""
        # An empty message means "no error at all".
        err = None if msg == "" else RuntimeError(msg)

        assert is_lost_race(err) is bool(mc.get("lostRace")), (
            f"{case['id']} {i} is_lost_race({msg!r}): {mc.get('why')}"
        )
        assert is_absent_key(err) is bool(mc.get("absent")), (
            f"{case['id']} {i} is_absent_key({msg!r}): {mc.get('why')}"
        )
        assert is_consumer_gone(err) is bool(mc.get("consumerGone")), (
            f"{case['id']} {i} is_consumer_gone({msg!r}): {mc.get('why')}"
        )

        # The categories must be mutually exclusive: a fault belonging to two would make
        # behaviour depend on clause order rather than on the fault.
        hits = sum(
            [is_lost_race(err), is_absent_key(err), is_consumer_gone(err)]
        )
        assert hits <= 1, f"{case['id']} {i} ({msg!r}): matches {hits} categories"


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
