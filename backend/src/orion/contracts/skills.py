"""Product skill catalog descriptors; guidance never grants tool authority."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from orion.contracts import CanonicalModel, RuntimeScope


class SkillDescriptor(CanonicalModel):
    schema_version: Literal[1] = 1
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    description: str = Field(min_length=1, max_length=2048)
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9.-]+)?$")
    audience: Literal["product"] = "product"
    source: Literal["bundled", "user", "project"]
    project_id: str | None = Field(default=None, min_length=1, max_length=128)
    required_capabilities: tuple[
        Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,127}$")], ...
    ] = Field(default=(), max_length=64)
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    enabled: bool = True
    scopes: tuple[Literal["chat", "project", "device"], ...] = ("chat", "project", "device")

    @model_validator(mode="after")
    def coherent_scope(self) -> SkillDescriptor:
        if (self.source == "project") != (self.project_id is not None):
            raise ValueError("only project skills require a bound project")
        if len(set(self.required_capabilities)) != len(self.required_capabilities):
            raise ValueError("duplicate required skill capability")
        if any(not item or len(item) > 128 for item in self.required_capabilities):
            raise ValueError("invalid required skill capability")
        if not self.scopes or len(set(self.scopes)) != len(self.scopes):
            raise ValueError("invalid or duplicate skill scope")
        return self

    def applies_to(self, scope: RuntimeScope) -> bool:
        if not self.enabled:
            return False
        surface = (
            "device" if scope.endpoint_id is not None else "project" if scope.project_id else "chat"
        )
        if surface not in self.scopes:
            return False
        if self.source == "project":
            return scope.endpoint_id is None and scope.project_id == self.project_id
        return True
