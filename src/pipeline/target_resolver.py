from __future__ import annotations

from src.pipeline.investigation_request import InvestigationRequest


class TargetResolver:
    """Resolve investigation target.

    Responsibilities:
    - determine where evidence should be collected
    - update InvestigationRequest with the resolved target

    Never performs execution or evidence collection.
    """

    def resolve(self, request: InvestigationRequest) -> None:
        """Resolve the target for the given investigation request.

        Current implementation sets a placeholder target.
        Deterministic resolution will be implemented in a future sprint.
        """
        request.target = "localhost"
