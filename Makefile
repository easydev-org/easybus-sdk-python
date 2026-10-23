.PHONY: gen gen-grpc-tools test

# buf, like the Go and TypeScript SDKs.
#
# It used grpc_tools directly, which made "regenerate the bindings" a different command from
# every other SDK — and a difference like that is how one of them gets forgotten. buf also
# removes a build dependency: the Python plugin runs on the Buf Schema Registry, so CI no
# longer installs grpcio-tools just to regenerate.
gen:
	cd proto && buf generate --template buf.gen.yaml

# Kept for one release as an escape hatch: if the BSR plugin turns out to differ from
# grpc_tools in some way this project depends on, this regenerates the previous way and the
# diff says exactly what changed. Delete it once a release has shipped on buf.
gen-grpc-tools:
	python3 -m grpc_tools.protoc -I proto --python_out=src/easybus/gen --pyi_out=src/easybus/gen proto/easybus/v1/protocol.proto

test:
	PYTHONPATH=src python3 -m pytest tests -q
