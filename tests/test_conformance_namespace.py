"""Conformance: a manifest's structured config and namespaces reach the WIRE.

Each of these asserts the same three hops the Go reference does:

    YAML manifest  ->  parsed types  ->  build_config  ->  Extension._build_manifest

Testing only the first hop is what let this ship broken: the fields existed on the
dataclass and were still dropped on the way out, so a Python extension could
declare a typed config knob and the world would never see it.
"""

from __future__ import annotations

from typing import Any

from easybus.extension import Extension
from easybus.manifest import Bindings, build_config, parse_manifest

OPS_MANIFEST = """
id: ops
version: "1"
namespaces:
  - name: services
    description: Deploy workloads
  - name: build
    description: Image builds
config:
  - name: easyops-url
    type: string
  - name: buildkit-addr
    type: string
    namespace: build
  - name: sandboxes
    type: list
    kind: secret
    item_type: object
    min_items: 1
    fields:
      - name: name
        type: string
        required: true
      - name: url
        type: string
        format: uri
        required: true
      - name: token
        type: string
        kind: secret
        required: true
      - name: os
        type: enum
        enum_values: [linux, windows, macos, android]
        default: linux
tools:
  - name: create-pvc
    description: Create a PVC
    namespace: storage
  - name: build-image
    description: Build an image
    namespace: build
"""


def _wire_manifest() -> Any:
    """Parse -> build_config -> the manifest the extension publishes."""
    m = parse_manifest(OPS_MANIFEST)
    cfg = build_config(
        m,
        Bindings(handlers={"create-pvc": _noop, "build-image": _noop}),
    )
    ext = Extension(None, cfg)  # the bus is unused by _build_manifest
    return ext._build_manifest()  # noqa: SLF001 - asserting the wire form


async def _noop(*_a: object, **_k: object) -> object:  # pragma: no cover
    return None


def test_declared_namespaces_reach_the_wire() -> None:
    wire = _wire_manifest()
    assert [n.name for n in wire.namespaces] == ["services", "build"], (
        "the author's ORDER must survive, or a client can only sort alphabetically"
    )
    assert wire.namespaces[0].description == "Deploy workloads"


def test_tool_namespace_reaches_the_wire() -> None:
    wire = _wire_manifest()
    by_name = {t.name: t for t in wire.tools}
    assert by_name["create-pvc"].namespace == "storage"
    assert by_name["build-image"].namespace == "build"
    # The tool keeps its name: the namespace is organisational only.
    assert by_name["create-pvc"].name == "create-pvc"


def test_structured_config_shape_reaches_the_wire() -> None:
    wire = _wire_manifest()
    knob = {c.name: c for c in wire.config}["sandboxes"]
    assert knob.type == "list"
    assert knob.item_type == "object"
    assert knob.min_items == 1

    fields = {f.name: f for f in knob.fields}
    assert set(fields) == {"name", "url", "token", "os"}
    assert fields["url"].format == "uri"
    assert fields["token"].kind == "secret"
    assert fields["os"].type == "enum"
    assert list(fields["os"].enum_values) == ["linux", "windows", "macos", "android"]
    assert fields["name"].required is True


def test_extension_level_knob_has_no_namespace() -> None:
    """An empty namespace means extension-level: shared by all its namespaces."""
    wire = _wire_manifest()
    by_name = {c.name: c for c in wire.config}
    assert by_name["easyops-url"].namespace == ""
    assert by_name["buildkit-addr"].namespace == "build"
