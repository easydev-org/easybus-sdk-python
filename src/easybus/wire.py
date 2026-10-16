"""Wire types + the Go-compatible JSON codec.

The wire MESSAGES come from the protoc-generated module (src/easybus/gen). This
module re-exports them and provides the Go-compatible JSON codec: the Go SDK
marshals with `encoding/json` (NOT protojson) — snake_case field names, proto
enum values as INTEGERS, and the Envelope `kind` as a SHORT STRING
("req"/"pub"/"queue"). NOTHING here is hand-written.
"""

from __future__ import annotations

import json

from google.protobuf import json_format

from easybus.gen.easybus.v1 import protocol_pb2 as pb

# Re-export the generated message types (the single source of truth).
Envelope = pb.Envelope
ErrorPayload = pb.ErrorPayload
ObjectRef = pb.ObjectRef
ToolCallEnvelope = pb.ToolCallEnvelope
ToolProgress = pb.ToolProgress
ToolResult = pb.ToolResult
ToolError = pb.ToolError
ExtensionVariable = pb.ExtensionVariable
ExtensionVariableValue = pb.ExtensionVariableValue
ExtensionConfigItem = pb.ExtensionConfigItem
ConfigSet = pb.ConfigSet
ConfigSnapshot = pb.ConfigSnapshot
HookCall = pb.HookCall
HookEvent = pb.HookEvent
HookResponse = pb.HookResponse
HookSpec = pb.HookSpec
LifecycleEvent = pb.LifecycleEvent
MailboxMessage = pb.MailboxMessage
InterruptSignal = pb.InterruptSignal
ExtensionTool = pb.ExtensionTool
ExtensionManifest = pb.ExtensionManifest

Code = pb.Code
Envelope_Kind = pb.Envelope.Kind
LifecycleEvent_Kind = pb.LifecycleEvent.Kind

#: The wire kind string the Go side writes for each Envelope.Kind.
KIND_TO_STRING = {
    pb.Envelope.KIND_REQ: "req",
    pb.Envelope.KIND_PUB: "pub",
    pb.Envelope.KIND_QUEUE: "queue",
}
KIND_FROM_STRING = {v: k for k, v in KIND_TO_STRING.items()}


def encode_envelope(env: pb.Envelope) -> bytes:
    """Encode an Envelope to Go-compatible JSON bytes (snake_case, `kind` as a
    short string)."""
    d = json_format.MessageToDict(env, preserving_proto_field_name=True, use_integers_for_enums=True)
    d["kind"] = KIND_TO_STRING.get(env.kind, "pub")
    return json.dumps(d, separators=(",", ":")).encode("utf-8")


def decode_envelope(data: bytes) -> pb.Envelope:
    """Parse Go-compatible JSON bytes into an Envelope."""
    d = json.loads(data.decode("utf-8"))
    if isinstance(d.get("kind"), str):
        d["kind"] = KIND_FROM_STRING.get(d["kind"], pb.Envelope.KIND_PUB)
    return json_format.ParseDict(d, pb.Envelope(), ignore_unknown_fields=True)


def envelope_kind_string(env: pb.Envelope) -> str:
    return KIND_TO_STRING.get(env.kind, "pub")


def encode_message(msg) -> bytes:
    """Encode any generated message to Go-compatible JSON bytes (snake_case,
    integer enums)."""
    d = json_format.MessageToDict(msg, preserving_proto_field_name=True, use_integers_for_enums=True)
    return json.dumps(d, separators=(",", ":")).encode("utf-8")


def decode_message(msg_type, data: bytes):
    """Decode Go-compatible JSON bytes into a generated message."""
    d = json.loads(data.decode("utf-8"))
    return json_format.ParseDict(d, msg_type(), ignore_unknown_fields=True)


def to_value(payload) -> pb.Value:
    """Wrap a plain JSON value into a google.protobuf.Value."""
    return _to_value(payload)


def _to_value(payload) -> pb.Value:
    from google.protobuf import struct_pb2

    v = struct_pb2.Value()
    if payload is None:
        v.null_value = struct_pb2.NULL_VALUE
    elif isinstance(payload, bool):
        v.bool_value = payload
    elif isinstance(payload, (int, float)):
        v.number_value = float(payload)
    elif isinstance(payload, str):
        v.string_value = payload
    elif isinstance(payload, dict):
        v.struct_value.update(payload)
    elif isinstance(payload, (list, tuple)):
        v.list_value.extend(payload)
    else:
        v.string_value = str(payload)
    return v


def from_value(v: pb.Value):
    """Unwrap a google.protobuf.Value into a plain JSON value."""
    return _from_value(v)


def _from_value(v: pb.Value):
    from google.protobuf import struct_pb2

    which = v.WhichOneof("kind")
    if which == "null_value":
        return None
    if which == "number_value":
        return v.number_value
    if which == "string_value":
        return v.string_value
    if which == "bool_value":
        return v.bool_value
    if which == "struct_value":
        return json_format.MessageToDict(v.struct_value, preserving_proto_field_name=True)
    if which == "list_value":
        return [json_format.MessageToDict(x, preserving_proto_field_name=True).get("@value") for x in v.list_value.values]
    return None
