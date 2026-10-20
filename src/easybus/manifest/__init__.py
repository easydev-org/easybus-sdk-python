"""The YAML manifest -> extension Config builder — the Python twin of the Go
`easybus-sdk/manifest` package.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import yaml

from easybus.extension import (
    Config,
    ConfigSpec,
    FieldSpec,
    NamespaceSpec,
    ToolSpec,
    VariableSpec,
)

#: Config knob kinds (kind is an open string; these are the special values).
CONFIG_KIND_VALUE = "value"
CONFIG_KIND_MODEL = "model"
#: A secret's value is never returned to a client (the agent withholds it and
#: reports only whether it is set).
CONFIG_KIND_SECRET = "secret"


@dataclass
class ManifestTool:
    name: str
    description: str = ""
    descriptions: dict[str, str] = field(default_factory=dict)
    input_schema: dict[str, Any] = field(default_factory=dict)
    required_config: list[str] = field(default_factory=list)
    #: Grouping of this tool (pvc, build, storage, ...). Organisational only: the
    #: tool keeps its name; it lets a client group the list.
    namespace: str = ""


@dataclass
class ManifestField:
    """One key of a structured config value (or of one list item's keys)."""

    name: str
    type: str = "string"
    kind: str = ""
    format: str = ""
    enum_values: list[str] = field(default_factory=list)
    default: Any = None
    required: bool = False
    description: str = ""
    descriptions: dict[str, str] = field(default_factory=dict)
    fields: list["ManifestField"] = field(default_factory=list)


@dataclass
class ManifestNamespace:
    """One declared grouping of an extension's tools and config."""

    name: str
    description: str = ""
    descriptions: dict[str, str] = field(default_factory=dict)


@dataclass
class ManifestVariable:
    name: str
    description: str = ""
    descriptions: dict[str, str] = field(default_factory=dict)
    scope: str = ""


@dataclass
class ManifestConfig:
    name: str
    type: str = "string"
    kind: str = ""
    capability: str = ""
    enum_values: list[str] = field(default_factory=list)
    default: Any = None
    description: str = ""
    descriptions: dict[str, str] = field(default_factory=dict)
    scope: str = ""
    #: The shape of a structured knob: the keys of an ``object``, or of each
    #: ``list`` item when ``item_type == "object"``. Empty means untyped — a
    #: ``json`` blob, the backward-compatible fallback.
    fields: list[ManifestField] = field(default_factory=list)
    #: Element type when ``type == "list"`` (object | string | number | boolean).
    item_type: str = ""
    min_items: int = 0
    max_items: int = 0
    #: Scopes this knob's STORED VALUE to one namespace of the extension.
    #: Empty = extension-level (shared by all its namespaces).
    namespace: str = ""


@dataclass
class Manifest:
    id: str
    version: str = ""
    tools: list[ManifestTool] = field(default_factory=list)
    variables: list[ManifestVariable] = field(default_factory=list)
    config: list[ManifestConfig] = field(default_factory=list)
    lifecycle: list[str] = field(default_factory=list)
    hooks: dict[str, Any] = field(default_factory=dict)
    #: Declared groupings (pvc, build, storage, ...), in the author's ORDER.
    namespaces: list[ManifestNamespace] = field(default_factory=list)


def parse_manifest(data: str | bytes) -> Manifest:
    """Parse YAML manifest text."""
    doc = yaml.safe_load(data) or {}
    if not doc.get("id"):
        raise ValueError("manifest: id is required")
    for c in doc.get("config", []):
        if c.get("kind") != CONFIG_KIND_SECRET:
            continue
        # A secret knob is a credential: its value is never returned to a
        # client, and a `default` would ride the (broadcast) manifest — so a
        # secret MUST be a string and MUST NOT declare a default.
        #
        # It MAY be structured (a list/object whose records each carry their own
        # per-field `kind: secret`), which is how a sandbox list declares a token
        # per sandbox: withholding the whole knob is then a second guard on top of
        # the per-field masking.
        t = c.get("type", "")
        if t and t not in ("string", "list", "object"):
            raise ValueError(
                f'manifest: config "{c.get("name")}": kind=secret requires type '
                f'string, list or object (got "{t}")'
            )
        d = c.get("default")
        if d is not None and d != "":
            raise ValueError(f'manifest: config "{c.get("name")}": kind=secret must not declare a default')
    return Manifest(
        id=doc["id"],
        version=doc.get("version", ""),
        tools=[_build_tool(t) for t in doc.get("tools", [])],
        variables=[ManifestVariable(**{k: v for k, v in v.items() if k in ManifestVariable.__dataclass_fields__}) for v in doc.get("variables", [])],
        config=[_build_config(c) for c in doc.get("config", [])],
        lifecycle=doc.get("lifecycle", []),
        hooks=doc.get("hooks", {}) or {},
        namespaces=[_build_namespace(n) for n in doc.get("namespaces", [])],
    )


def _known(cls: type, raw: dict[str, Any]) -> dict[str, Any]:
    """Keep only the keys a dataclass declares.

    A manifest may legitimately carry keys this SDK does not know (a newer
    extension against an older SDK), so unknown keys are dropped rather than
    raising — but every key this SDK DOES know must be declared above, or it is
    silently lost. That is exactly how `namespace` and `fields` went missing.
    """
    return {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}


def _build_field(raw: dict[str, Any]) -> ManifestField:
    data = _known(ManifestField, raw)
    data["fields"] = [_build_field(f) for f in raw.get("fields", []) or []]
    return ManifestField(**data)


def _build_tool(raw: dict[str, Any]) -> ManifestTool:
    return ManifestTool(**_known(ManifestTool, raw))


def _build_config(raw: dict[str, Any]) -> ManifestConfig:
    data = _known(ManifestConfig, raw)
    data["fields"] = [_build_field(f) for f in raw.get("fields", []) or []]
    return ManifestConfig(**data)


def _build_namespace(raw: dict[str, Any]) -> ManifestNamespace:
    return ManifestNamespace(**_known(ManifestNamespace, raw))


@dataclass
class Bindings:
    """Name-keyed handlers/resolvers used to build a Config."""

    handlers: dict[str, Callable]
    variables: dict[str, VariableSpec] = field(default_factory=dict)
    on_call_hook: Callable | None = None
    on_event_hook: Callable | None = None
    on_config_change: Callable | None = None
    on_lifecycle: Callable | None = None
    on_interrupt: Callable | None = None


def build_config(m: Manifest, b: Bindings) -> Config:
    """Build an extension.Config from the manifest + bindings."""
    tools: dict[str, ToolSpec] = {}
    for t in m.tools:
        handler = b.handlers.get(t.name)
        if handler is None:
            continue
        tools[t.name] = ToolSpec(
            description=t.description,
            descriptions=t.descriptions,
            input_schema=t.input_schema,
            required_config=t.required_config,
            namespace=t.namespace,
            execute=handler,
        )
    variables: dict[str, VariableSpec] = {}
    for v in m.variables:
        r = b.variables.get(v.name)
        variables[v.name] = VariableSpec(
            description=v.description,
            descriptions=v.descriptions,
            scope=v.scope or "global",
            resolve=r.resolve if r else None,
        )
    config: dict[str, ConfigSpec] = {}
    for c in m.config:
        config[c.name] = ConfigSpec(
            description=c.description,
            descriptions=c.descriptions,
            type=c.type,
            kind=c.kind or "value",
            capability=c.capability,
            enum_values=c.enum_values,
            default=c.default,
            scope=c.scope or "global",
            fields=[_to_field_spec(f) for f in c.fields],
            item_type=c.item_type,
            min_items=c.min_items,
            max_items=c.max_items,
            namespace=c.namespace,
        )
    namespaces = [
        NamespaceSpec(name=n.name, description=n.description, descriptions=n.descriptions)
        for n in m.namespaces
    ]
    hooks = m.hooks or {}
    return Config(
        id=m.id,
        version=m.version,
        tools=tools,
        variables=variables,
        config=config,
        namespaces=namespaces,
        call_hooks=hooks.get("call", []) or [],
        event_hooks=hooks.get("event", []) or [],
        lifecycle=m.lifecycle,
        hook_schemas={"call": hooks.get("call_schemas", {}) or {}, "event": hooks.get("event_schemas", {}) or {}},
        on_call_hook=b.on_call_hook,
        on_event_hook=b.on_event_hook,
        on_config_change=b.on_config_change,
        on_lifecycle=b.on_lifecycle,
        on_interrupt=b.on_interrupt,
    )


def _to_field_spec(f: ManifestField) -> FieldSpec:
    """Map a declared field onto the wire-facing spec (recursing one level)."""
    return FieldSpec(
        name=f.name,
        type=f.type,
        kind=f.kind,
        format=f.format,
        enum_values=f.enum_values,
        default=f.default,
        required=f.required,
        description=f.description,
        descriptions=f.descriptions,
        fields=[_to_field_spec(sub) for sub in f.fields],
    )
