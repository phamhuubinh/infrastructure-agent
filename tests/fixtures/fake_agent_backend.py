from __future__ import annotations


class ScriptedAgentBackend:
    """Minimal deterministic backend for canonical-agent tests."""

    def __init__(
        self,
        responses: str | list[str],
    ) -> None:
        self._responses = (
            [responses]
            if isinstance(responses, str)
            else list(responses)
        )
        self.prompts: list[str] = []

    def complete(
        self,
        prompt: str,
    ) -> str:
        self.prompts.append(prompt)

        if not self._responses:
            raise RuntimeError(
                "script exhausted"
            )

        return self._responses.pop(0)

    def health_check(
        self,
        timeout: float = 5.0,
    ) -> bool:
        del timeout
        return True
