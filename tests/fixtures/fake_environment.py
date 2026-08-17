"""Deterministic fake target/source availability registry (#50).

Every fixture uses fake hosts, fake tokens, and local or never-contacted
backends. Nothing here touches real endpoints, credentials, or machine
configuration, and production runtime config is never read.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.pipeline.target_resolver import TargetResolver
from src.shared.execution.tool_result import ToolResult
from src.tool.errors import source_api_error
from src.tool.execution_backend import LocalExecutionBackend, SSHExecutionBackend
from src.tool.grafana_tool import GrafanaTool
from src.tool.internet_tool import (
    _CAPABILITIES as _INTERNET_CAPABILITIES,
)
from src.tool.internet_tool import (
    InternetTool as _BaseInternetTool,
)
from src.tool.internet_tool import (
    SearchProvider,
    SearchResponse,
    SearchResult,
)
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry
from src.tool.zabbix_tool import ZabbixTool

# The KnowledgeTool capability router reads ``_CAPABILITIES`` from the
# concrete tool class's module; re-export the production declarations so the
# scripted subclass keeps the same declared capability surface.
_CAPABILITIES = _INTERNET_CAPABILITIES

# TEST-NET-1 address: valid syntax, never contacted by fixtures or tests.
FAKE_SSH_HOST = "192.0.2.10"
FAKE_GRAFANA_URL = "https://grafana.invalid"
FAKE_ZABBIX_URL = "https://zabbix.invalid"
FAKE_TOOL_TOKEN = "fake-token"


class FakeSearchProvider(SearchProvider):
    """Queued deterministic search results with optional failure injection."""

    def __init__(
        self,
        responses: list[SearchResponse | Exception],
        name: str = "fake-search",
    ) -> None:
        self._responses = list(responses)
        self._name = name
        self.queries: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    def search(
        self,
        query: str,
        *,
        locale: str | None = None,
        max_results: int = 5,
        timeout: int = 10,
    ) -> SearchResponse:
        self.queries.append(query)
        if not self._responses:
            return SearchResponse(query=query, status="empty", provider=self._name)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def search_response(query: str, *urls: str) -> SearchResponse:
    """Build a deterministic ok response with one result per URL."""

    return SearchResponse(
        query=query,
        results=tuple(
            SearchResult(
                title=f"result-{index}",
                url=url,
                snippet=f"snippet for {url}",
                rank=index,
                provider="fake-search",
            )
            for index, url in enumerate(urls, start=1)
        ),
        status="ok",
        provider="fake-search",
    )


def raw_search_payload(*urls: str) -> dict[str, object]:
    """Build the raw search payload shape the external executor parses."""

    return {
        "status": "ok",
        "provider": "fake-search",
        "results": [
            {"title": f"result-{index}", "url": url, "snippet": f"snippet {url}"}
            for index, url in enumerate(urls, start=1)
        ],
    }


class InternetTool(_BaseInternetTool):
    """Scripted internet source compatible with the real KnowledgeTool.

    The class keeps the production name so ``KnowledgeTool.source_kind``
    reports ``"internet"``. Search and fetch return queued deterministic
    payloads; unknown URLs and drained queues fail closed like an
    unavailable provider.
    """

    def __init__(
        self,
        *,
        search_payloads: list[dict[str, object]] | None = None,
        fetch_payloads: dict[str, dict[str, object]] | None = None,
        search_error: Exception | None = None,
    ) -> None:
        super().__init__()
        self._search_payloads = list(search_payloads or [])
        self._fetch_payloads = dict(fetch_payloads or {})
        self._search_error = search_error
        self.search_calls: list[dict[str, object]] = []
        self.fetch_calls: list[dict[str, object]] = []

    def execute(self, arguments: dict[str, object]) -> ToolResult:
        # KnowledgeTool dispatches with "action"; direct executor callers
        # use "resource". Accept either key.
        resource = arguments.get("resource") or arguments.get("action")
        if resource == "web_search":
            self.search_calls.append(dict(arguments))
            if self._search_error is not None:
                message = str(self._search_error)
                return ToolResult(
                    success=False,
                    error=message,
                    capability_error=source_api_error(message),
                )
            if not self._search_payloads:
                return ToolResult(
                    success=True,
                    data={"status": "ok", "provider": "fake-search", "results": []},
                )
            return ToolResult(success=True, data=self._search_payloads.pop(0))
        if resource == "web_fetch":
            url = str(arguments.get("url"))
            if _is_private_literal_hostname(url):
                message = f"Access to private address is not allowed: {url}"
                return ToolResult(
                    success=False,
                    error=message,
                    capability_error=source_api_error(message),
                )
            self.fetch_calls.append(dict(arguments))
            payload = self._fetch_payloads.get(url)
            if payload is None:
                message = f"blocked or unavailable: {url}"
                return ToolResult(
                    success=False,
                    error=message,
                    capability_error=source_api_error(message),
                )
            return ToolResult(success=True, data=dict(payload))
        return super().execute(arguments)


def _is_private_literal_hostname(url: str) -> bool:
    """Mimic the production SSRF boundary for IP-literal URLs.

    The real InternetTool resolves hostnames and rejects private addresses
    before opening a socket; this fixture never resolves, so it checks the
    literal form directly.
    """

    from ipaddress import ip_address
    from urllib.parse import urlsplit

    try:
        hostname = urlsplit(url).hostname
        if hostname is None:
            return False
        address = ip_address(hostname)
    except ValueError:
        return False
    return not address.is_global


def build_fake_registry(
    *,
    localhost: bool = True,
    monitor: bool = False,
    ssh: bool = False,
    grafana: bool = False,
    zabbix: bool = False,
    internet: bool = False,
    internet_provider: SearchProvider | None = None,
    internet_tool: _BaseInternetTool | None = None,
) -> TargetRegistry:
    """Build a TargetRegistry with exactly the requested availability states.

    A source or target that is not enabled is simply absent from the
    registry, so constrained-source and unknown-target paths fail closed
    exactly like an unconfigured production environment.
    """

    registry = TargetRegistry()
    if localhost:
        registry.add("localhost")
    if monitor:
        registry.add("monitor", backend=LocalExecutionBackend())
    if ssh:
        registry.add(
            "remote-1",
            backend=SSHExecutionBackend(
                host=FAKE_SSH_HOST,
                identity_file=None,
                strict_host_key_checking=True,
            ),
        )
    if grafana:
        registry.register_tool(
            "grafana",
            GrafanaTool(url=FAKE_GRAFANA_URL, token=FAKE_TOOL_TOKEN),
        )
    if zabbix:
        registry.register_tool(
            "zabbix",
            ZabbixTool(url=FAKE_ZABBIX_URL, token=FAKE_TOOL_TOKEN),
        )
    if internet or internet_tool is not None:
        registry.register_tool(
            "internet",
            internet_tool
            or _BaseInternetTool(
                provider=internet_provider
                or FakeSearchProvider([search_response("query")]),
            ),
        )
    return registry


@dataclass(frozen=True, slots=True)
class FakeEnvironment:
    """Registry plus the resolver/knowledge-tool pair agents are built from."""

    registry: TargetRegistry
    knowledge_tool: KnowledgeTool
    target_resolver: TargetResolver


def fake_environment(**flags: object) -> FakeEnvironment:
    """Build a fake environment with per-test availability flags."""

    registry = build_fake_registry(**flags)  # type: ignore[arg-type]
    return FakeEnvironment(
        registry=registry,
        knowledge_tool=KnowledgeTool(registry),
        target_resolver=TargetResolver(registry),
    )


__all__ = [
    "FAKE_GRAFANA_URL",
    "FAKE_SSH_HOST",
    "FAKE_TOOL_TOKEN",
    "FAKE_ZABBIX_URL",
    "FakeEnvironment",
    "FakeSearchProvider",
    "InternetTool",
    "build_fake_registry",
    "fake_environment",
    "raw_search_payload",
    "search_response",
]
