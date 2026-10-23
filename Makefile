.PHONY: gen test

# buf, like the Go and TypeScript SDKs.
#
# It used grpc_tools directly, which made "regenerate the bindings" a different command from
# every other SDK — and a difference like that is how one of them gets forgotten. buf also
# removes a build dependency: the Python plugin runs on the Buf Schema Registry, so CI no
# longer installs grpcio-tools just to regenerate.
gen:
	cd proto && buf generate --template buf.gen.yaml

test:
	PYTHONPATH=src python3 -m pytest tests -q
