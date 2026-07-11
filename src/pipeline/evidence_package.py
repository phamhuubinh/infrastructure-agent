from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
