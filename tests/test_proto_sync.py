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


def test_every_field_in_the_proto_exists_in_the_bindings() -> None:
    """Field-level, not just message-level.

    The message-level check above passes as soon as the message exists, which is why a
    proto that gained `requires`, `grants` or the permission/channel messages could still
    ship stale bindings: those messages were new, so "missing" was empty for the OLD ones
    while the new fields simply were not there. A field this SDK does not know is DROPPED on
    the wire — a tool that declares `requires` would be sent without it and therefore never
    permission-gated, with nothing failing anywhere.
    """
    root = Path(__file__).resolve().parents[1]
    text = (root / "proto/easybus/v1/protocol.proto").read_text()

    # Parse `message X { ... field = N; ... }` well enough to compare field names. The proto
    # here is simple by construction (no nested message-in-message declarations), so a brace
    # counter is sufficient and avoids adding a protobuf parser as a test dependency.
    current: str | None = None
    depth = 0
    missing: list[str] = []
    for raw in text.splitlines():
        line = raw.split("//", 1)[0].strip()
        if not line:
            continue
        if line.startswith("message ") and line.endswith("{"):
            current = line[len("message ") : -1].strip()
            depth = 1
            continue
        if current is None:
            continue
        if line.endswith("{"):
            depth += 1
            continue
        if line.startswith("}"):
            depth -= 1
            if depth == 0:
                current = None
            continue
        # A field declaration looks like: [repeated|optional] <type> <name> = <n>;
        if "=" not in line or not line.endswith(";"):
            continue
        lhs = line.split("=", 1)[0].strip()
        parts = lhs.split()
        if len(parts) < 2:
            continue
        fname = parts[-1]

        desc = protocol_pb2.DESCRIPTOR.message_types_by_name.get(current)
        if desc is None:
            missing.append(f"{current} (whole message)")
            continue
        if fname not in desc.fields_by_name:
            missing.append(f"{current}.{fname}")

    assert not missing, f"generated bindings are missing fields: {missing}"


def test_bindings_do_not_carry_fields_the_proto_removed() -> None:
    """The OTHER direction: generated code must not keep a field the proto dropped.

    The check above only asks "is everything in the proto present in the bindings". That is
    satisfied by a binding that has MORE than the proto — e.g. when a proto change is reverted
    but the bindings were not regenerated. The stale field still serialises, so the wire now
    carries something the contract no longer defines: a receiver that validates strictly
    rejects the message, and one that does not silently accepts an undefined field.
    """
    root = Path(__file__).resolve().parents[1]
    text = (root / "proto/easybus/v1/protocol.proto").read_text()

    declared: dict[str, set[str]] = {}
    current: str | None = None
    depth = 0
    for raw in text.splitlines():
        line = raw.split("//", 1)[0].strip()
        if not line:
            continue
        if line.startswith("message ") and line.endswith("{"):
            current = line[len("message ") : -1].strip()
            declared[current] = set()
            depth = 1
            continue
        if current is None:
            continue
        if line.endswith("{"):
            depth += 1
            continue
        if line.startswith("}"):
            depth -= 1
            if depth == 0:
                current = None
            continue
        if "=" not in line or not line.endswith(";"):
            continue
        parts = line.split("=", 1)[0].strip().split()
        if len(parts) >= 2:
            declared[current].add(parts[-1])

    extra: list[str] = []
    for name, fields in declared.items():
        desc = protocol_pb2.DESCRIPTOR.message_types_by_name.get(name)
        if desc is None:
            continue
        for f in desc.fields_by_name:
            if f not in fields:
                extra.append(f"{name}.{f}")
    assert not extra, f"generated bindings carry fields the proto no longer defines: {extra}"
