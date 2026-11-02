"""Publish the same explicit access inventory consumed by middleware and typed clients."""

from typing import Any

from pydantic import BaseModel

from orion.access.remote import COOKIE_NAME


def request_body_schema(model: type[BaseModel], *, required: bool = True) -> dict[str, Any]:
    """Describe a manually bounded JSON body without changing its parsing boundary."""
    return {
        "requestBody": {
            "required": required,
            "content": {"application/json": {"schema": model.model_json_schema()}},
        }
    }


def annotate_access(
    schema: dict[str, Any],
    owner_routes: set[tuple[str, str]],
    worker_routes: set[tuple[str, str]],
) -> dict[str, Any]:
    schemes = schema.setdefault("components", {}).setdefault("securitySchemes", {})
    schemes.update(
        {
            "NativeOwner": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "opaque owner access",
            },
            "BrowserOwner": {"type": "apiKey", "in": "cookie", "name": COOKIE_NAME},
            "Worker": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "endpoint worker credential",
            },
        }
    )
    for path, operations in schema.get("paths", {}).items():
        for method, operation in operations.items():
            if not isinstance(operation, dict) or method.upper() not in {
                "GET",
                "POST",
                "PUT",
                "PATCH",
                "DELETE",
                "HEAD",
                "OPTIONS",
            }:
                continue
            identity = method.upper(), path
            if identity in owner_routes:
                operation["security"] = [{"NativeOwner": []}, {"BrowserOwner": []}]
                operation["x-orion-auth"] = "owner"
                operation["x-orion-local-loopback-owner"] = True
            elif identity in worker_routes:
                operation["security"] = [{"Worker": []}]
                operation["x-orion-auth"] = "worker"
            else:
                operation["security"] = []
                operation["x-orion-auth"] = "public"
    return schema
