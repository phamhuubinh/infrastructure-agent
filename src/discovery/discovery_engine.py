from __future__ import annotations


class DiscoveryEngine:
    """
    Coordinates the discovery workflow.

    Discovery Engine performs no planning,
    reasoning, execution, or runtime management.
    """

    def discover(
        self,
        observations: object,
    ) -> object:
        """
        Execute one discovery cycle.

        Implementation is intentionally omitted.
        """
        raise NotImplementedError
