"""Guards the committed protobuf bindings against drifting from the .proto.

Python COMMITS its generated *_pb2.py/_pb2.pyi (unlike Rust, whose build.rs
regenerates at compile time), so nothing forces them to match. When they drift,
Python consumers silently get a wire format that is missing fields the Go SDK
already sends — which is exactly what happened: the proto copy here was 64 lines
behind and had no `namespace` or structured-config fields at all.
"""

from pathlib import Path

from easybus.gen.easybus.v1 import protocol_pb2


def test_proto_file_matches_the_generated_bindings() -> None:
    root = Path(__file__).resolve().parents[1]
    proto = root / "proto/easybus/v1/protocol.proto"
    assert proto.is_file(), f"missing proto at {proto}"

    text = proto.read_text()

    # Every message declared in the .proto must exist in the compiled bindings,
    # otherwise the committed *_pb2.py is stale.
    missing = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("message "):
            continue
        name = line.split()[1]
        if not name.replace(".", "") or not name[:1].isupper():
            continue
        if name not in protocol_pb2.DESCRIPTOR.message_types_by_name:
            missing.append(name)
    assert not missing, f"generated bindings are stale; missing: {missing}"


def test_structured_config_and_namespace_fields_exist() -> None:
    """The two additions that matter for typed config and per-extension keys."""
    item = protocol_pb2.ExtensionConfigItem.DESCRIPTOR
    for field in ("fields", "item_type", "namespace"):
        assert field in item.fields_by_name, f"ExtensionConfigItem.{field} missing"

    tool = protocol_pb2.ExtensionTool.DESCRIPTOR
    assert "namespace" in tool.fields_by_name, "ExtensionTool.namespace missing"

    manifest = protocol_pb2.ExtensionManifest.DESCRIPTOR
    assert "namespaces" in manifest.fields_by_name, "ExtensionManifest.namespaces missing"
