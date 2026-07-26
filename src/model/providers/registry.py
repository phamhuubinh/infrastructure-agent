from __future__ import annotations

from dataclasses import dataclass, field

from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.providers.credential_pool import CredentialPool
from src.model.providers.fallback_chain import FallbackChain
from src.shared.logger import warning as _warning


@dataclass
class ProviderRegistry:
    """Registry of named AssessmentModelAdapter instances with fallback chain.

    Maps provider names (e.g. "sv1", "sv2", "anthropic-prod") to adapters.
    A fallback chain defines the order in which providers are tried when
    the primary provider is unavailable.
    """

    providers: dict[str, AssessmentModelAdapter] = field(default_factory=dict)
    fallback_chain: list[str] = field(default_factory=list)
    credential_pool: CredentialPool | None = None

    def get_adapter(self, name: str | None = None) -> AssessmentModelAdapter:
        """Return an adapter by name, or fall back through the chain.

        Args:
            name: Provider name to look up.  If None, the fallback chain
                  is tried in order.  If a name is given but the provider
                  is unhealthy, the remaining fallback chain is tried.

        Returns:
            The first healthy adapter found.

        Raises:
            RuntimeError: If no available provider is found.
        """
        # Named lookup — try it first, then fall through the chain.
        if name and name in self.providers:
            adapter = self.providers[name]
            if self._is_healthy(adapter, name):
                return adapter
            _warning(
                "provider",
                provider=name,
                message="Named provider unhealthy, falling back",
            )

        # Fallback: try each provider in the chain.
        start_idx = 0
        if name and name in self.fallback_chain:
            try:
                start_idx = self.fallback_chain.index(name)
            except ValueError:
                pass

        for provider_name in self.fallback_chain[start_idx:]:
            adapter = self.providers.get(provider_name)
            if adapter and self._is_healthy(adapter, provider_name):
                return adapter

        # Last resort: try any registered provider not in the chain.
        for pname, adapter in self.providers.items():
            if pname not in self.fallback_chain and self._is_healthy(adapter, pname):
                return adapter

        available = ", ".join(sorted(self.providers))
        raise RuntimeError(f"No available LLM provider. Registered: {available}")

    def get_fallback_chain(self) -> FallbackChain | None:
        """Build a FallbackChain from the registered adapters.

        Returns None if no fallback chain is configured.
        """
        ordered = []
        for name in self.fallback_chain:
            adapter = self.providers.get(name)
            if adapter is not None:
                ordered.append(adapter)
        if not ordered:
            return None
        return FallbackChain(ordered)

    def register(
        self,
        name: str,
        adapter: AssessmentModelAdapter,
    ) -> None:
        """Register a named adapter."""
        self.providers[name] = adapter

    @staticmethod
    def _is_healthy(adapter: AssessmentModelAdapter, name: str) -> bool:
        """Check if an adapter passes its health check.

        Returns True if healthy, False otherwise.  Does not raise.
        """
        try:
            return adapter.health_check(timeout=2.0)
        except Exception as exc:
            _warning(
                "provider",
                provider=name,
                error=str(exc)[:80],
                message="Health check failed",
            )
            return False
