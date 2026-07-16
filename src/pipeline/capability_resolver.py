from __future__ import annotations

from src.pipeline.capability_library import lookup
from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.evidence_requirement import EvidenceRequirement
from src.pipeline.investigation_request import InvestigationRequest


class CapabilityResolver:
    """Map Evidence Requirements to operational Capability References.

    Responsibilities:
    - look up capability names from the Capability Library
    - deduplicate when multiple evidence items map to the same capability
    - populate InvestigationRequest with capability references

    Owns lookup behaviour only — the capability library is the single
    source of truth for evidence-to-capability mappings.

    Never performs execution.
    Never references tools, providers, or infrastructure.
    """

    def resolve(self, request: InvestigationRequest) -> None:
        """Resolve evidence requirements to capability references.

        Reads required_evidence and optional_evidence from the request.
        Produces a single deduplicated list of capability references
        stored on request.capability_references.

        Args:
            request: The InvestigationRequest. Must have evidence requirements
                     populated. Mutates capability_references.
        """
        all_evidence: list[EvidenceRequirement] = []
        all_evidence.extend(request.required_evidence)
        all_evidence.extend(request.optional_evidence)

        result: list[CapabilityReference] = []
        seen: set[str] = set()

        for evidence in all_evidence:
            cap_name = lookup(evidence.name)
            if cap_name is None:
                continue
            if cap_name in seen:
                continue
            seen.add(cap_name)
            result.append(
                CapabilityReference(
                    name=cap_name,
                    evidence_name=evidence.name,
                )
            )

        request.capability_references = result
