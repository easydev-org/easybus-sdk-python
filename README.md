# easybus-sdk-python

The **Python** implementation of the easybus protocol SDK — a multi-tenant
message bus between an agent and its extensions.

## Source of truth

The wire contract is `proto/easybus/v1/protocol.proto`, **copied** from the Go
reference (`easydev-org/easybus-sdk`); `grpc_tools.protoc` (or `buf generate`)
produces `src/easybus/gen`. Runtime conventions (subject layout
`easybus.<tenant>.<...>`, KV-key escaping, golden derivations) live in
`src/easybus/protocol/` and MUST match Go/TypeScript byte-for-byte.

## Layout (mirrors the Go SDK)

```
proto/easybus/v1/protocol.proto   the wire contract (copied, never edited here)
src/easybus/gen/                  generated messages (grpc_tools / buf)
src/easybus/protocol/             subjects, KV keys, escaping, golden
src/easybus/identity/             HMAC pre-shared identity
src/easybus/bus/                  transport-agnostic Bus
src/easybus/transport/nats/       the NATS transport
src/easybus/manifest/             YAML manifest -> extension Config
src/easybus/extension/            the extension role
src/easybus/agent/                the agent role
```
