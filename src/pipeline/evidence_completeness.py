from __future__ import annotations

from src.pipeline.investigation_request import InvestigationRequest


class EvidenceCompleteness:
    """Determine whether required evidence has been collected.

    Responsibilities:
    - compare collected evidence against evidence requirements
    - identify missing required evidence
    - report completeness status

    Never involves AI.
    Never performs assessment or reasoning.
    """

    def check(self, request: InvestigationRequest) -> None:
        """Check evidence completeness and store results on the request.

        Reads required_evidence and optional_evidence from the request.
        Compares against collected evidence.
        Sets evidence_complete and missing_evidence fields.

        Args:
            request: The InvestigationRequest. Must have evidence requirements
                     and collected evidence populated. Mutates
                     evidence_complete and missing_evidence.
        """
        collected_names: set[str] = set()
        for pkg in request.evidence:
            if pkg.success:
                collected_names.add(pkg.evidence_name)

        missing: list[str] = []

        for req in request.required_evidence:
            if req.name not in collected_names:
                missing.append(req.name)

        request.evidence_complete = len(missing) == 0
        request.missing_evidence = tuple(missing)
