"""QA-only application composition with a per-process mutation execution guard."""

from __future__ import annotations

import os

from fastapi import FastAPI

from orion.api.app import create_app as create_http_app
from orion.bootstrap import build_application


def create_app() -> FastAPI:
    mutation_case_enabled = (
        os.getenv("ORION_QA_CASE_MUTATION") == "1" and os.getenv("ORION_QA_ALLOW_MUTATION") == "1"
    )
    blocked_operation_kinds = frozenset() if mutation_case_enabled else frozenset({"mutation"})
    return create_http_app(
        application=build_application(
            blocked_tool_operation_kinds=blocked_operation_kinds,
        )
    )
