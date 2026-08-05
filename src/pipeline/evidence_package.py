from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from src.pipeline.fact import Fact, FactFreshness
from src.pipeline.provenance import claim_source_links
from src.shared.execution.command_result import CommandResult
from src.tool.capability_result import CapabilityStatus
from src.tool.errors import CapabilityError, capability_error_from_status


@dataclass(frozen=True, slots=True)
class EvidencePackage:
    """Typed contract between Runtime and Assessment.

    An EvidencePackage represents one collected piece of operational
    evidence, normalized and ready for assessment.

    It is the output of EvidenceMerge and the input to Assessment.

    Attributes:
        capability_name: The operational capability that produced this evidence.
        evidence_name: The evidence requirement name this capability fulfills.
        data: Normalized operational evidence (structured dict or list).
        success: True if evidence was collected successfully.
        error: Error message if collection failed.
    """

    capability_name: str
    evidence_name: str
    data: Any = None
    success: bool = True
    error: str | None = None
    source_tool: str | None = None
    status: CapabilityStatus | None = None
    command_results: tuple[CommandResult, ...] = ()
    warnings: tuple[str, ...] = ()
    produced_fact_names: tuple[str, ...] = ()
    collection_failures: tuple[str, ...] = ()
    capability_error: CapabilityError | None = None
    raw_data: Any = None
    facts: tuple[Fact, ...] = ()
    source: str | None = None
    resource: str | None = None
    parameters: tuple[tuple[str, object], ...] = ()
    timeframe: object | None = None
    schema_version: str = "1"
    stale: bool = False
    recovery_attempts: tuple[dict[str, object], ...] = ()
    recovered_by: str | None = None

    def __post_init__(self) -> None:
        if self.raw_data is None and self.data is not None:
            object.__setattr__(self, "raw_data", self.data)
        elif self.data is None and self.raw_data is not None:
            object.__setattr__(self, "data", self.raw_data)
        object.__setattr__(self, "facts", tuple(self.facts))
        object.__setattr__(
            self,
            "parameters",
            tuple(sorted((str(key), value) for key, value in self.parameters)),
        )
        status = self.status
        if status is None:
            if self.success:
                status = (
                    CapabilityStatus.VALID_EMPTY
                    if self.data is None or self.data in ({}, [], (), "")
                    else CapabilityStatus.VALID
                )
            else:
                status = CapabilityStatus.COLLECTION_FAILED
            object.__setattr__(self, "status", status)

        object.__setattr__(
            self,
            "success",
            status in (CapabilityStatus.VALID, CapabilityStatus.VALID_EMPTY),
        )
        if not self.success and not self.collection_failures and self.error:
            object.__setattr__(self, "collection_failures", (self.error,))
        if not self.success and self.capability_error is None:
            object.__setattr__(
                self,
                "capability_error",
                capability_error_from_status(
                    status.value,
                    command_results=self.command_results,
                    message=self.error,
                ),
            )

    @property
    def valid_for_requirements(self) -> bool:
        return (
            not self.stale
            and self.status in (CapabilityStatus.VALID, CapabilityStatus.VALID_EMPTY)
            and not any(fact.freshness is FactFreshness.STALE for fact in self.facts)
        )

    @property
    def capability_status(self) -> CapabilityStatus:
        assert self.status is not None
        return self.status

    @property
    def source_links(self) -> tuple[dict[str, str | None], ...]:
        return tuple(link.to_dict() for link in claim_source_links(self.facts))

    def to_dict(
        self,
        *,
        include_raw: bool = False,
        raw_limit_bytes: int = 8192,
    ) -> dict[str, Any]:
        """Serialize audit metadata; raw evidence is opt-in and bounded."""

        result: dict[str, Any] = {
            "capability_name": self.capability_name,
            "evidence_name": self.evidence_name,
            "success": self.success,
            "error": self.error,
            "source_tool": self.source_tool,
            "source": self.source,
            "resource": self.resource,
            "capability_status": self.capability_status.value,
            "warnings": list(self.warnings),
            "collection_failures": list(self.collection_failures),
            "schema_version": self.schema_version,
            "stale": self.stale,
            "recovery_attempts": list(self.recovery_attempts),
            "recovered_by": self.recovered_by,
            "facts": [fact.to_dict() for fact in self.facts],
            "source_links": list(self.source_links),
        }
        if include_raw:
            result["raw_data"] = self._bounded_raw(self.raw_data, raw_limit_bytes)
        return result

    @staticmethod
    def _bounded_raw(value: Any, limit: int) -> Any:
        limit = max(int(limit), 0)
        try:
            serialized = json.dumps(value, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            serialized = repr(value)
        encoded = serialized.encode("utf-8")
        if len(encoded) <= limit:
            return json.loads(serialized)
        preview = encoded[:limit].decode("utf-8", errors="ignore")
        return {
            "truncated": True,
            "original_bytes": len(encoded),
            "preview": preview,
        }
