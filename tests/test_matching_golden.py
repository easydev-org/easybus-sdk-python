"""The shared matching table, from conformance-cases/permission-matching.json.

WHY a shared file rather than a test written once here: the rules are implemented four times, and
they are the security boundary of every extension. Two SDKs that disagree do not fail loudly — they
authorise different things for the same grant, silently, depending on which language the extension
happens to be written in. Every SDK reads this same table.
"""

import json
from pathlib import Path

import pytest

from easybus.extension import matches

_TABLE = json.loads(
    (Path(__file__).resolve().parents[1] / "conformance-cases" / "permission-matching.json").read_text()
)


def test_table_has_cases() -> None:
    assert _TABLE["cases"], "the shared table is empty"


@pytest.mark.parametrize("case", _TABLE["cases"], ids=lambda c: c["why"])
def test_shared_matching_case(case: dict) -> None:
    assert matches(case["grant"], case["target"]) is case["want"]
