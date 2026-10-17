"""A secret config knob must be a string with no default (a default would ride
the broadcast manifest)."""
import pytest

from easybus.manifest import CONFIG_KIND_SECRET, parse_manifest


def test_accepts_string_secret_no_default():
    m = parse_manifest(
        """
id: x
version: "1"
config:
  - name: gh-token
    type: string
    kind: secret
"""
    )
    assert m.config[0].kind == CONFIG_KIND_SECRET


def test_rejects_non_string_secret():
    with pytest.raises(ValueError, match="type=string"):
        parse_manifest(
            """
id: x
version: "1"
config:
  - name: gh-token
    type: number
    kind: secret
"""
        )


def test_rejects_secret_with_default():
    with pytest.raises(ValueError, match="must not declare a default"):
        parse_manifest(
            """
id: x
version: "1"
config:
  - name: gh-token
    type: string
    kind: secret
    default: ghp_leaked
"""
        )


def test_ordinary_knob_unaffected():
    m = parse_manifest(
        """
id: x
version: "1"
config:
  - name: region
    type: string
    default: us
"""
    )
    assert m.config[0].default == "us"
