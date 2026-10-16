.PHONY: gen test
gen:
	python3 -m grpc_tools.protoc -I proto --python_out=src/easybus/gen --pyi_out=src/easybus/gen proto/easybus/v1/protocol.proto
test:
	PYTHONPATH=src python3 -m pytest tests -q
