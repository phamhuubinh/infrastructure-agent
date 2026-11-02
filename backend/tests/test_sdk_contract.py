"""The generated owner SDK preserves authoritative shapes, streams and access classes."""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "sdk_generator", Path(__file__).parents[1] / "scripts/sdk.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def document():
    return {
        "components": {
            "schemas": {
                "Payload": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                    "additionalProperties": False,
                }
            }
        },
        "paths": {
            "/api/items/{id}": {
                "post": {
                    "operationId": "create_item",
                    "x-orion-auth": "owner",
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Payload"}}
                        },
                    },
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Payload"}
                                }
                            }
                        }
                    },
                },
                "get": {"operationId": "worker_only", "x-orion-auth": "worker"},
            }
        },
    }


def test_sdk_is_deterministic_preserves_required_inputs_and_excludes_worker_authority():
    schema = document()
    output = MODULE.render(schema)
    assert MODULE.render(schema) == output
    assert 'readonly "name": string' in output
    assert 'readonly path: { readonly "id": string }' in output
    assert 'readonly body: Schemas["Payload"]' in output
    assert "worker_only" not in output
    assert "schemaSha256" in output and "export type Operations" in output


def test_sdk_binary_request_and_stream_response_are_not_json():
    schema = document()
    operation = schema["paths"]["/api/items/{id}"]["post"]
    operation["requestBody"]["content"] = {
        "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
    }
    operation["responses"] = {
        "200": {
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            }
        }
    }
    output = MODULE.render(schema)
    assert '"body": "binary"' in output and "readonly body: Blob" in output
    assert '"response": "stream"' in output and "ReadableStream<Uint8Array>" in output
    operation["requestBody"]["content"] = {
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "contentMediaType": "application/octet-stream"}
                },
                "required": ["file"],
            }
        }
    }
    assert 'readonly "file": Blob' in MODULE.render(schema)


@pytest.mark.parametrize("ref", ["https://external.test/schema", "#/components/schemas/Missing"])
def test_sdk_rejects_remote_or_missing_references(ref):
    schema = document()
    schema["components"]["schemas"]["Payload"] = {"$ref": ref}
    with pytest.raises(ValueError, match="local schema"):
        MODULE.render(schema)


def test_sdk_rejects_unclassified_access_and_duplicate_operations():
    schema = document()
    schema["paths"]["/api/items/{id}"]["post"].pop("x-orion-auth")
    with pytest.raises(ValueError, match="classification"):
        MODULE.render(schema)
    schema = document()
    schema["paths"]["/other"] = {"post": schema["paths"]["/api/items/{id}"]["post"]}
    with pytest.raises(ValueError, match="Duplicate"):
        MODULE.render(schema)
