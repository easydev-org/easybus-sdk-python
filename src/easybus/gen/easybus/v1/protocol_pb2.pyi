from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Code(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CODE_UNSPECIFIED: _ClassVar[Code]
    CODE_INVALID_ARGUMENT: _ClassVar[Code]
    CODE_NOT_FOUND: _ClassVar[Code]
    CODE_PERMISSION_DENIED: _ClassVar[Code]
    CODE_RETRYABLE: _ClassVar[Code]
    CODE_BUSINESS: _ClassVar[Code]
    CODE_INTERNAL: _ClassVar[Code]
CODE_UNSPECIFIED: Code
CODE_INVALID_ARGUMENT: Code
CODE_NOT_FOUND: Code
CODE_PERMISSION_DENIED: Code
CODE_RETRYABLE: Code
CODE_BUSINESS: Code
CODE_INTERNAL: Code

class Envelope(_message.Message):
    __slots__ = ("v", "ch", "tenant", "kind", "payload", "id", "reply_to", "session_name", "pending")
    class Kind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        KIND_UNSPECIFIED: _ClassVar[Envelope.Kind]
        KIND_REQ: _ClassVar[Envelope.Kind]
        KIND_PUB: _ClassVar[Envelope.Kind]
        KIND_QUEUE: _ClassVar[Envelope.Kind]
    KIND_UNSPECIFIED: Envelope.Kind
    KIND_REQ: Envelope.Kind
    KIND_PUB: Envelope.Kind
    KIND_QUEUE: Envelope.Kind
    V_FIELD_NUMBER: _ClassVar[int]
    CH_FIELD_NUMBER: _ClassVar[int]
    TENANT_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    REPLY_TO_FIELD_NUMBER: _ClassVar[int]
    SESSION_NAME_FIELD_NUMBER: _ClassVar[int]
    PENDING_FIELD_NUMBER: _ClassVar[int]
    v: int
    ch: str
    tenant: str
    kind: Envelope.Kind
    payload: _struct_pb2.Value
    id: str
    reply_to: str
    session_name: str
    pending: int
    def __init__(self, v: _Optional[int] = ..., ch: _Optional[str] = ..., tenant: _Optional[str] = ..., kind: _Optional[_Union[Envelope.Kind, str]] = ..., payload: _Optional[_Union[_struct_pb2.Value, _Mapping]] = ..., id: _Optional[str] = ..., reply_to: _Optional[str] = ..., session_name: _Optional[str] = ..., pending: _Optional[int] = ...) -> None: ...

class ErrorPayload(_message.Message):
    __slots__ = ("code", "message")
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    code: Code
    message: str
    def __init__(self, code: _Optional[_Union[Code, str]] = ..., message: _Optional[str] = ...) -> None: ...

class ObjectRef(_message.Message):
    __slots__ = ("id", "content_type")
    ID_FIELD_NUMBER: _ClassVar[int]
    CONTENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    id: str
    content_type: str
    def __init__(self, id: _Optional[str] = ..., content_type: _Optional[str] = ...) -> None: ...

class ToolCallEnvelope(_message.Message):
    __slots__ = ("call_id", "arguments", "grants")
    CALL_ID_FIELD_NUMBER: _ClassVar[int]
    ARGUMENTS_FIELD_NUMBER: _ClassVar[int]
    GRANTS_FIELD_NUMBER: _ClassVar[int]
    call_id: str
    arguments: _struct_pb2.Struct
    grants: _containers.RepeatedCompositeFieldContainer[Grant]
    def __init__(self, call_id: _Optional[str] = ..., arguments: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., grants: _Optional[_Iterable[_Union[Grant, _Mapping]]] = ...) -> None: ...

class ToolProgress(_message.Message):
    __slots__ = ("call_id", "progress", "phase", "text", "metadata")
    CALL_ID_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_FIELD_NUMBER: _ClassVar[int]
    PHASE_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    call_id: str
    progress: float
    phase: str
    text: str
    metadata: _struct_pb2.Value
    def __init__(self, call_id: _Optional[str] = ..., progress: _Optional[float] = ..., phase: _Optional[str] = ..., text: _Optional[str] = ..., metadata: _Optional[_Union[_struct_pb2.Value, _Mapping]] = ...) -> None: ...

class ToolResult(_message.Message):
    __slots__ = ("call_id", "tool", "content", "data", "metadata", "error", "object")
    CALL_ID_FIELD_NUMBER: _ClassVar[int]
    TOOL_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    OBJECT_FIELD_NUMBER: _ClassVar[int]
    call_id: str
    tool: str
    content: str
    data: _struct_pb2.Value
    metadata: _struct_pb2.Value
    error: ToolError
    object: ObjectRef
    def __init__(self, call_id: _Optional[str] = ..., tool: _Optional[str] = ..., content: _Optional[str] = ..., data: _Optional[_Union[_struct_pb2.Value, _Mapping]] = ..., metadata: _Optional[_Union[_struct_pb2.Value, _Mapping]] = ..., error: _Optional[_Union[ToolError, _Mapping]] = ..., object: _Optional[_Union[ObjectRef, _Mapping]] = ...) -> None: ...

class ToolError(_message.Message):
    __slots__ = ("code", "message")
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    code: Code
    message: str
    def __init__(self, code: _Optional[_Union[Code, str]] = ..., message: _Optional[str] = ...) -> None: ...

class ExtensionVariable(_message.Message):
    __slots__ = ("name", "description", "descriptions", "scope")
    class DescriptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTIONS_FIELD_NUMBER: _ClassVar[int]
    SCOPE_FIELD_NUMBER: _ClassVar[int]
    name: str
    description: str
    descriptions: _containers.ScalarMap[str, str]
    scope: str
    def __init__(self, name: _Optional[str] = ..., description: _Optional[str] = ..., descriptions: _Optional[_Mapping[str, str]] = ..., scope: _Optional[str] = ...) -> None: ...

class ExtensionVariableValue(_message.Message):
    __slots__ = ("name", "value")
    NAME_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    name: str
    value: str
    def __init__(self, name: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

class ExtensionConfigItem(_message.Message):
    __slots__ = ("name", "type", "kind", "scope", "description", "descriptions", "enum_values", "default", "capability", "fields", "item_type", "min_items", "max_items", "namespace", "format")
    class DescriptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    NAME_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    SCOPE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTIONS_FIELD_NUMBER: _ClassVar[int]
    ENUM_VALUES_FIELD_NUMBER: _ClassVar[int]
    DEFAULT_FIELD_NUMBER: _ClassVar[int]
    CAPABILITY_FIELD_NUMBER: _ClassVar[int]
    FIELDS_FIELD_NUMBER: _ClassVar[int]
    ITEM_TYPE_FIELD_NUMBER: _ClassVar[int]
    MIN_ITEMS_FIELD_NUMBER: _ClassVar[int]
    MAX_ITEMS_FIELD_NUMBER: _ClassVar[int]
    NAMESPACE_FIELD_NUMBER: _ClassVar[int]
    FORMAT_FIELD_NUMBER: _ClassVar[int]
    name: str
    type: str
    kind: str
    scope: str
    description: str
    descriptions: _containers.ScalarMap[str, str]
    enum_values: _containers.RepeatedScalarFieldContainer[str]
    default: _struct_pb2.Value
    capability: str
    fields: _containers.RepeatedCompositeFieldContainer[ConfigFieldSchema]
    item_type: str
    min_items: int
    max_items: int
    namespace: str
    format: str
    def __init__(self, name: _Optional[str] = ..., type: _Optional[str] = ..., kind: _Optional[str] = ..., scope: _Optional[str] = ..., description: _Optional[str] = ..., descriptions: _Optional[_Mapping[str, str]] = ..., enum_values: _Optional[_Iterable[str]] = ..., default: _Optional[_Union[_struct_pb2.Value, _Mapping]] = ..., capability: _Optional[str] = ..., fields: _Optional[_Iterable[_Union[ConfigFieldSchema, _Mapping]]] = ..., item_type: _Optional[str] = ..., min_items: _Optional[int] = ..., max_items: _Optional[int] = ..., namespace: _Optional[str] = ..., format: _Optional[str] = ...) -> None: ...

class ExtensionNamespace(_message.Message):
    __slots__ = ("name", "description", "descriptions")
    class DescriptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTIONS_FIELD_NUMBER: _ClassVar[int]
    name: str
    description: str
    descriptions: _containers.ScalarMap[str, str]
    def __init__(self, name: _Optional[str] = ..., description: _Optional[str] = ..., descriptions: _Optional[_Mapping[str, str]] = ...) -> None: ...

class ConfigFieldSchema(_message.Message):
    __slots__ = ("name", "type", "kind", "format", "enum_values", "default", "required", "description", "descriptions", "fields")
    class DescriptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    NAME_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    FORMAT_FIELD_NUMBER: _ClassVar[int]
    ENUM_VALUES_FIELD_NUMBER: _ClassVar[int]
    DEFAULT_FIELD_NUMBER: _ClassVar[int]
    REQUIRED_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTIONS_FIELD_NUMBER: _ClassVar[int]
    FIELDS_FIELD_NUMBER: _ClassVar[int]
    name: str
    type: str
    kind: str
    format: str
    enum_values: _containers.RepeatedScalarFieldContainer[str]
    default: _struct_pb2.Value
    required: bool
    description: str
    descriptions: _containers.ScalarMap[str, str]
    fields: _containers.RepeatedCompositeFieldContainer[ConfigFieldSchema]
    def __init__(self, name: _Optional[str] = ..., type: _Optional[str] = ..., kind: _Optional[str] = ..., format: _Optional[str] = ..., enum_values: _Optional[_Iterable[str]] = ..., default: _Optional[_Union[_struct_pb2.Value, _Mapping]] = ..., required: _Optional[bool] = ..., description: _Optional[str] = ..., descriptions: _Optional[_Mapping[str, str]] = ..., fields: _Optional[_Iterable[_Union[ConfigFieldSchema, _Mapping]]] = ...) -> None: ...

class ConfigSet(_message.Message):
    __slots__ = ("name", "scope", "revision", "value", "session_name", "tenant", "ack")
    NAME_FIELD_NUMBER: _ClassVar[int]
    SCOPE_FIELD_NUMBER: _ClassVar[int]
    REVISION_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    SESSION_NAME_FIELD_NUMBER: _ClassVar[int]
    TENANT_FIELD_NUMBER: _ClassVar[int]
    ACK_FIELD_NUMBER: _ClassVar[int]
    name: str
    scope: str
    revision: int
    value: _struct_pb2.Value
    session_name: str
    tenant: str
    ack: bool
    def __init__(self, name: _Optional[str] = ..., scope: _Optional[str] = ..., revision: _Optional[int] = ..., value: _Optional[_Union[_struct_pb2.Value, _Mapping]] = ..., session_name: _Optional[str] = ..., tenant: _Optional[str] = ..., ack: _Optional[bool] = ...) -> None: ...

class ConfigSnapshot(_message.Message):
    __slots__ = ("sessions",)
    class GlobalEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: _struct_pb2.Value
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[_struct_pb2.Value, _Mapping]] = ...) -> None: ...
    GLOBAL_FIELD_NUMBER: _ClassVar[int]
    SESSIONS_FIELD_NUMBER: _ClassVar[int]
    sessions: _struct_pb2.Value
    def __init__(self, sessions: _Optional[_Union[_struct_pb2.Value, _Mapping]] = ..., **kwargs) -> None: ...

class HookCall(_message.Message):
    __slots__ = ("hook", "session_name", "arguments")
    HOOK_FIELD_NUMBER: _ClassVar[int]
    SESSION_NAME_FIELD_NUMBER: _ClassVar[int]
    ARGUMENTS_FIELD_NUMBER: _ClassVar[int]
    hook: str
    session_name: str
    arguments: _struct_pb2.Struct
    def __init__(self, hook: _Optional[str] = ..., session_name: _Optional[str] = ..., arguments: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class HookEvent(_message.Message):
    __slots__ = ("hook", "session_name", "payload")
    HOOK_FIELD_NUMBER: _ClassVar[int]
    SESSION_NAME_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    hook: str
    session_name: str
    payload: _struct_pb2.Value
    def __init__(self, hook: _Optional[str] = ..., session_name: _Optional[str] = ..., payload: _Optional[_Union[_struct_pb2.Value, _Mapping]] = ...) -> None: ...

class HookResponse(_message.Message):
    __slots__ = ("ok", "data", "error")
    OK_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    ok: bool
    data: _struct_pb2.Value
    error: ToolError
    def __init__(self, ok: _Optional[bool] = ..., data: _Optional[_Union[_struct_pb2.Value, _Mapping]] = ..., error: _Optional[_Union[ToolError, _Mapping]] = ...) -> None: ...

class LifecycleEvent(_message.Message):
    __slots__ = ("kind", "session_name", "to", "parent", "id", "payload")
    class Kind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        KIND_UNSPECIFIED: _ClassVar[LifecycleEvent.Kind]
        KIND_CREATED: _ClassVar[LifecycleEvent.Kind]
        KIND_FORKED: _ClassVar[LifecycleEvent.Kind]
        KIND_RENAMED: _ClassVar[LifecycleEvent.Kind]
        KIND_DELETED: _ClassVar[LifecycleEvent.Kind]
    KIND_UNSPECIFIED: LifecycleEvent.Kind
    KIND_CREATED: LifecycleEvent.Kind
    KIND_FORKED: LifecycleEvent.Kind
    KIND_RENAMED: LifecycleEvent.Kind
    KIND_DELETED: LifecycleEvent.Kind
    KIND_FIELD_NUMBER: _ClassVar[int]
    SESSION_NAME_FIELD_NUMBER: _ClassVar[int]
    FROM_FIELD_NUMBER: _ClassVar[int]
    TO_FIELD_NUMBER: _ClassVar[int]
    PARENT_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    kind: LifecycleEvent.Kind
    session_name: str
    to: str
    parent: str
    id: str
    payload: _struct_pb2.Value
    def __init__(self, kind: _Optional[_Union[LifecycleEvent.Kind, str]] = ..., session_name: _Optional[str] = ..., to: _Optional[str] = ..., parent: _Optional[str] = ..., id: _Optional[str] = ..., payload: _Optional[_Union[_struct_pb2.Value, _Mapping]] = ..., **kwargs) -> None: ...

class MailboxMessage(_message.Message):
    __slots__ = ("id", "type", "source", "payload")
    ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    id: str
    type: str
    source: str
    payload: _struct_pb2.Value
    def __init__(self, id: _Optional[str] = ..., type: _Optional[str] = ..., source: _Optional[str] = ..., payload: _Optional[_Union[_struct_pb2.Value, _Mapping]] = ...) -> None: ...

class InterruptSignal(_message.Message):
    __slots__ = ("session_name", "reason")
    SESSION_NAME_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    session_name: str
    reason: str
    def __init__(self, session_name: _Optional[str] = ..., reason: _Optional[str] = ...) -> None: ...

class ExtensionTool(_message.Message):
    __slots__ = ("name", "description", "descriptions", "input_schema", "required_config", "namespace", "requires")
    class DescriptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTIONS_FIELD_NUMBER: _ClassVar[int]
    INPUT_SCHEMA_FIELD_NUMBER: _ClassVar[int]
    REQUIRED_CONFIG_FIELD_NUMBER: _ClassVar[int]
    NAMESPACE_FIELD_NUMBER: _ClassVar[int]
    REQUIRES_FIELD_NUMBER: _ClassVar[int]
    name: str
    description: str
    descriptions: _containers.ScalarMap[str, str]
    input_schema: _struct_pb2.Struct
    required_config: _containers.RepeatedScalarFieldContainer[str]
    namespace: str
    requires: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, name: _Optional[str] = ..., description: _Optional[str] = ..., descriptions: _Optional[_Mapping[str, str]] = ..., input_schema: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., required_config: _Optional[_Iterable[str]] = ..., namespace: _Optional[str] = ..., requires: _Optional[_Iterable[str]] = ...) -> None: ...

class PermissionDecl(_message.Message):
    __slots__ = ("key", "label", "descriptions", "risk", "params_fields")
    class DescriptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    KEY_FIELD_NUMBER: _ClassVar[int]
    LABEL_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTIONS_FIELD_NUMBER: _ClassVar[int]
    RISK_FIELD_NUMBER: _ClassVar[int]
    PARAMS_FIELDS_FIELD_NUMBER: _ClassVar[int]
    key: str
    label: str
    descriptions: _containers.ScalarMap[str, str]
    risk: str
    params_fields: _containers.RepeatedCompositeFieldContainer[ConfigFieldSchema]
    def __init__(self, key: _Optional[str] = ..., label: _Optional[str] = ..., descriptions: _Optional[_Mapping[str, str]] = ..., risk: _Optional[str] = ..., params_fields: _Optional[_Iterable[_Union[ConfigFieldSchema, _Mapping]]] = ...) -> None: ...

class Grant(_message.Message):
    __slots__ = ("key", "params")
    KEY_FIELD_NUMBER: _ClassVar[int]
    PARAMS_FIELD_NUMBER: _ClassVar[int]
    key: str
    params: _struct_pb2.Struct
    def __init__(self, key: _Optional[str] = ..., params: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class ExtensionManifest(_message.Message):
    __slots__ = ("id", "version", "capabilities", "features", "config", "tools", "prompt_variables", "namespaces", "lifecycle", "hooks", "permissions", "channels")
    ID_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    CAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    FEATURES_FIELD_NUMBER: _ClassVar[int]
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    TOOLS_FIELD_NUMBER: _ClassVar[int]
    PROMPT_VARIABLES_FIELD_NUMBER: _ClassVar[int]
    NAMESPACES_FIELD_NUMBER: _ClassVar[int]
    LIFECYCLE_FIELD_NUMBER: _ClassVar[int]
    HOOKS_FIELD_NUMBER: _ClassVar[int]
    PERMISSIONS_FIELD_NUMBER: _ClassVar[int]
    CHANNELS_FIELD_NUMBER: _ClassVar[int]
    id: str
    version: str
    capabilities: _containers.RepeatedScalarFieldContainer[str]
    features: _containers.RepeatedScalarFieldContainer[str]
    config: _containers.RepeatedCompositeFieldContainer[ExtensionConfigItem]
    tools: _containers.RepeatedCompositeFieldContainer[ExtensionTool]
    prompt_variables: _containers.RepeatedCompositeFieldContainer[ExtensionVariable]
    namespaces: _containers.RepeatedCompositeFieldContainer[ExtensionNamespace]
    lifecycle: _containers.RepeatedScalarFieldContainer[str]
    hooks: HookSpec
    permissions: _containers.RepeatedCompositeFieldContainer[PermissionDecl]
    channels: _containers.RepeatedCompositeFieldContainer[ExtensionChannel]
    def __init__(self, id: _Optional[str] = ..., version: _Optional[str] = ..., capabilities: _Optional[_Iterable[str]] = ..., features: _Optional[_Iterable[str]] = ..., config: _Optional[_Iterable[_Union[ExtensionConfigItem, _Mapping]]] = ..., tools: _Optional[_Iterable[_Union[ExtensionTool, _Mapping]]] = ..., prompt_variables: _Optional[_Iterable[_Union[ExtensionVariable, _Mapping]]] = ..., namespaces: _Optional[_Iterable[_Union[ExtensionNamespace, _Mapping]]] = ..., lifecycle: _Optional[_Iterable[str]] = ..., hooks: _Optional[_Union[HookSpec, _Mapping]] = ..., permissions: _Optional[_Iterable[_Union[PermissionDecl, _Mapping]]] = ..., channels: _Optional[_Iterable[_Union[ExtensionChannel, _Mapping]]] = ...) -> None: ...

class ExtensionChannel(_message.Message):
    __slots__ = ("name", "description", "descriptions", "topics")
    class DescriptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTIONS_FIELD_NUMBER: _ClassVar[int]
    TOPICS_FIELD_NUMBER: _ClassVar[int]
    name: str
    description: str
    descriptions: _containers.ScalarMap[str, str]
    topics: _containers.RepeatedCompositeFieldContainer[ChannelTopic]
    def __init__(self, name: _Optional[str] = ..., description: _Optional[str] = ..., descriptions: _Optional[_Mapping[str, str]] = ..., topics: _Optional[_Iterable[_Union[ChannelTopic, _Mapping]]] = ...) -> None: ...

class ChannelTopic(_message.Message):
    __slots__ = ("pattern", "description", "descriptions")
    class DescriptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    PATTERN_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTIONS_FIELD_NUMBER: _ClassVar[int]
    pattern: str
    description: str
    descriptions: _containers.ScalarMap[str, str]
    def __init__(self, pattern: _Optional[str] = ..., description: _Optional[str] = ..., descriptions: _Optional[_Mapping[str, str]] = ...) -> None: ...

class HookSpec(_message.Message):
    __slots__ = ("call", "event", "call_schemas", "event_schemas")
    class CallSchemasEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: _struct_pb2.Struct
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...
    class EventSchemasEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: _struct_pb2.Struct
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...
    CALL_FIELD_NUMBER: _ClassVar[int]
    EVENT_FIELD_NUMBER: _ClassVar[int]
    CALL_SCHEMAS_FIELD_NUMBER: _ClassVar[int]
    EVENT_SCHEMAS_FIELD_NUMBER: _ClassVar[int]
    call: _containers.RepeatedScalarFieldContainer[str]
    event: _containers.RepeatedScalarFieldContainer[str]
    call_schemas: _containers.MessageMap[str, _struct_pb2.Struct]
    event_schemas: _containers.MessageMap[str, _struct_pb2.Struct]
    def __init__(self, call: _Optional[_Iterable[str]] = ..., event: _Optional[_Iterable[str]] = ..., call_schemas: _Optional[_Mapping[str, _struct_pb2.Struct]] = ..., event_schemas: _Optional[_Mapping[str, _struct_pb2.Struct]] = ...) -> None: ...
