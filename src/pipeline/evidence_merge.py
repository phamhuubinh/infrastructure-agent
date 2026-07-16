from __future__ import annotations

from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.investigation_request import InvestigationRequest
from src.shared.execution.tool_result import ToolResult


class EvidenceMerge:
    """Merge collected evidence into normalized EvidencePackages.

    Responsibilities:
    - combine individual capability results
    - normalize results into EvidencePackage objects
    - detect missing or failed evidence
    - store merged evidence on the InvestigationRequest

    Never performs assessment or reasoning.
    """

    def merge(
        self,
        request: InvestigationRequest,
        results: dict[str, ToolResult],
    ) -> None:
        """Merge capability results into normalized evidence packages.

        Each ToolResult is wrapped in an EvidencePackage with the
        capability name and evidence name preserved.

        Failed results are included with success=False and error set.
        Normalization of data content is minimal — raw tool output
        is preserved for assessment consumption.

        Args:
            request: The InvestigationRequest with capability_references
                     populated. Mutates evidence.
            results: Raw capability_name → ToolResult mapping from Runtime.
        """
        packages: list[EvidencePackage] = []
        seen: set[str] = set()

        # Build evidence name lookup from capability references.
        ev_name_by_cap: dict[str, str] = {}
        for ref in request.capability_references:
            ev_name_by_cap[ref.name] = ref.evidence_name

        for cap_name, result in results.items():
            if cap_name in seen:
                continue
            seen.add(cap_name)

            ev_name = ev_name_by_cap.get(cap_name, cap_name)
            packages.append(
                EvidencePackage(
                    capability_name=cap_name,
                    evidence_name=ev_name,
                    data=result.data if result.success else None,
                    success=result.success,
                    error=result.error if not result.success else None,
                )
            )

        request.evidence = packages
