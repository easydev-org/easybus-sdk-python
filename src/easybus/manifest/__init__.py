"""The YAML manifest -> extension Config builder — the Python twin of the Go
`easybus-sdk/manifest` package.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import yaml

from easybus.extension import Config, ConfigSpec, ToolSpec, VariableSpec

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


@dataclass
class Manifest:
    id: str
    version: str = ""
    tools: list[ManifestTool] = field(default_factory=list)
    variables: list[ManifestVariable] = field(default_factory=list)
    config: list[ManifestConfig] = field(default_factory=list)
    lifecycle: list[str] = field(default_factory=list)
    hooks: dict[str, Any] = field(default_factory=dict)


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
        t = c.get("type", "")
        if t and t != "string":
            raise ValueError(f'manifest: config "{c.get("name")}": kind=secret requires type=string (got "{t}")')
        d = c.get("default")
        if d is not None and d != "":
            raise ValueError(f'manifest: config "{c.get("name")}": kind=secret must not declare a default')
    return Manifest(
        id=doc["id"],
        version=doc.get("version", ""),
        tools=[ManifestTool(**{k: v for k, v in t.items() if k in ManifestTool.__dataclass_fields__}) for t in doc.get("tools", [])],
        variables=[ManifestVariable(**{k: v for k, v in v.items() if k in ManifestVariable.__dataclass_fields__}) for v in doc.get("variables", [])],
        config=[ManifestConfig(**{k: v for k, v in c.items() if k in ManifestConfig.__dataclass_fields__}) for c in doc.get("config", [])],
        lifecycle=doc.get("lifecycle", []),
        hooks=doc.get("hooks", {}) or {},
    )


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
        )
    hooks = m.hooks or {}
    return Config(
        id=m.id,
        version=m.version,
        tools=tools,
        variables=variables,
        config=config,
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
