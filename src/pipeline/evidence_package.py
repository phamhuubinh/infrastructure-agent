from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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

    def __post_init__(self) -> None:
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
        return self.status in (CapabilityStatus.VALID, CapabilityStatus.VALID_EMPTY)
