from __future__ import annotations

import pytest

from src.pipeline.intent_resolver import (
    Confidence,
    Intent,
    IntentResolver,
)
from src.pipeline.investigation_request import InvestigationRequest


@pytest.fixture
def resolver() -> IntentResolver:
    return IntentResolver()


# ---------------------------------------------------------------------------
# Each supported intent (from 05_INTENT_LIBRARY.md)
# ---------------------------------------------------------------------------


class TestMachineAssessment:
    @pytest.mark.parametrize(
        "request_text",
        [
            "Assess this machine",
            "Evaluate server health",
            "Is this machine healthy?",
            "Review system status",
            "check server",
            "system overview",
            "general assessment",
            "machine state",
            "health check",
            "system summary",
        ],
    )
    def test_matches(self, resolver: IntentResolver, request_text: str) -> None:
        result = resolver.resolve(request_text)
        assert result.intent == Intent.MACHINE_ASSESSMENT
        assert result.matched_keywords


class TestApplicationDiscovery:
    @pytest.mark.parametrize(
        "request_text",
        [
            "Is Graylog installed?",
            "Does this server have Docker?",
            "Is Prometheus running?",
            "Is Nginx installed?",
            "check if redis is installed",
            "is elasticsearch deployed",
            "available packages",
            "application version",
            "check package exist",
            "is kafka present",
            "is postgresql installed",
            "is rabbitmq deployed",
            "mongodb version",
        ],
    )
    def test_matches(self, resolver: IntentResolver, request_text: str) -> None:
        result = resolver.resolve(request_text)
        assert result.intent == Intent.APPLICATION_DISCOVERY
        assert result.matched_keywords


class TestServiceAssessment:
    @pytest.mark.parametrize(
        "request_text",
        [
            "Check Docker service",
            "Is MySQL healthy?",
            "Review system services",
            "check service status",
            "is systemctl running",
            "daemon status",
            "list services",
            "service failed",
            "restart service",
        ],
    )
    def test_matches(self, resolver: IntentResolver, request_text: str) -> None:
        result = resolver.resolve(request_text)
        assert result.intent == Intent.SERVICE_ASSESSMENT
        assert result.matched_keywords


class TestMonitoringAssessment:
    @pytest.mark.parametrize(
        "request_text",
        [
            "Are there any problems?",
            "Show monitoring status",
            "Is anything critical?",
            "Review alerts",
            "check zabbix triggers",
            "grafana dashboards",
            "check host status",
            "recent events",
            "alarm severity",
            "monitoring health",
        ],
    )
    def test_matches(self, resolver: IntentResolver, request_text: str) -> None:
        result = resolver.resolve(request_text)
        assert result.intent == Intent.MONITORING_ASSESSMENT
        assert result.matched_keywords


class TestSecurityAssessment:
    @pytest.mark.parametrize(
        "request_text",
        [
            "Is SSH secure?",
            "Evaluate hardening",
            "check firewall rules",
            "security audit",
            "selinux status",
            "apparmor status",
            "check certificates",
            "recent logins",
            "check authentication",
            "password policy",
            "vulnerability scan",
        ],
    )
    def test_matches(self, resolver: IntentResolver, request_text: str) -> None:
        result = resolver.resolve(request_text)
        assert result.intent == Intent.SECURITY_ASSESSMENT
        assert result.matched_keywords


class TestPerformanceAssessment:
    @pytest.mark.parametrize(
        "request_text",
        [
            "Check CPU usage",
            "Check memory usage",
            "Review performance",
            "server is slow",
            "system load",
            "memory bottleneck",
            "cpu utilization",
            "iowait high",
            "check throughput",
            "system saturation",
        ],
    )
    def test_matches(self, resolver: IntentResolver, request_text: str) -> None:
        result = resolver.resolve(request_text)
        assert result.intent == Intent.PERFORMANCE_ASSESSMENT
        assert result.matched_keywords


class TestStorageAssessment:
    @pytest.mark.parametrize(
        "request_text",
        [
            "Check disk usage",
            "Review filesystem",
            "Is storage healthy?",
            "Any storage problems?",
            "check mount points",
            "disk partition",
            "inode usage",
            "lvm status",
            "raid health",
            "smart status",
            "volume group",
        ],
    )
    def test_matches(self, resolver: IntentResolver, request_text: str) -> None:
        result = resolver.resolve(request_text)
        assert result.intent == Intent.STORAGE_ASSESSMENT
        assert result.matched_keywords


class TestNetworkAssessment:
    @pytest.mark.parametrize(
        "request_text",
        [
            "Check networking",
            "Review interfaces",
            "Are there connection problems?",
            "Review ports",
            "ip address",
            "check gateway",
            "dns resolution",
            "network latency",
            "ping test",
            "bandwidth check",
            "vlan info",
        ],
    )
    def test_matches(self, resolver: IntentResolver, request_text: str) -> None:
        result = resolver.resolve(request_text)
        assert result.intent == Intent.NETWORK_ASSESSMENT
        assert result.matched_keywords


class TestConfigurationAssessment:
    @pytest.mark.parametrize(
        "request_text",
        [
            "Review SSH configuration",
            "Check Docker configuration",
            "Validate configuration",
            "Inspect system settings",
            "check config parameters",
            "review options",
            "configuration drift",
            "compliance check",
            "validate settings",
            "inspect properties",
        ],
    )
    def test_matches(self, resolver: IntentResolver, request_text: str) -> None:
        result = resolver.resolve(request_text)
        assert result.intent == Intent.CONFIGURATION_ASSESSMENT
        assert result.matched_keywords


class TestTroubleshooting:
    @pytest.mark.parametrize(
        "request_text",
        [
            "Why isnt this working?",
            "Find the issue",
            "Diagnose the problem",
            "Help troubleshoot",
            "why did the service fail",
            "investigate the error",
            "server is down",
            "app crashed",
            "broken service",
            "diagnose connection issue",
            "not working",
            "not responding",
            "unreachable host",
        ],
    )
    def test_matches(self, resolver: IntentResolver, request_text: str) -> None:
        result = resolver.resolve(request_text)
        assert result.intent == Intent.TROUBLESHOOTING
        assert result.matched_keywords


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_request(self, resolver: IntentResolver) -> None:
        result = resolver.resolve("")
        assert result.intent == Intent.MACHINE_ASSESSMENT
        assert result.confidence == Confidence.LOW
        assert result.matched_keywords == ()

    def test_whitespace_request(self, resolver: IntentResolver) -> None:
        result = resolver.resolve("   ")
        assert result.intent == Intent.MACHINE_ASSESSMENT
        assert result.confidence == Confidence.LOW

    def test_unknown_request_falls_back(self, resolver: IntentResolver) -> None:
        result = resolver.resolve("foo bar baz qux")
        assert result.intent == Intent.MACHINE_ASSESSMENT
        assert result.confidence == Confidence.LOW
        assert result.matched_keywords == ()


# ---------------------------------------------------------------------------
# Priority rules
# ---------------------------------------------------------------------------


class TestPriorityRules:
    """When multiple intents match, priority rules ensure the correct one wins."""

    def test_troubleshooting_overrides_generic(
        self, resolver: IntentResolver
    ) -> None:
        # "why" + generic keywords -> troubleshooting wins
        result = resolver.resolve("why is the system slow")
        assert result.intent == Intent.TROUBLESHOOTING

    def test_configuration_overrides_security(
        self, resolver: IntentResolver
    ) -> None:
        # When "configuration" is mentioned explicitly, configuration intent wins
        result = resolver.resolve("review ssh configuration")
        assert result.intent == Intent.CONFIGURATION_ASSESSMENT

    def test_specific_trumps_generic_on_match_count(
        self, resolver: IntentResolver
    ) -> None:
        # "storage healthy" -> storage (1 match) vs machine (1 match, healthy)
        # storage priority (28) < machine (5), so storage wins on priority
        result = resolver.resolve("Is storage healthy?")
        assert result.intent == Intent.STORAGE_ASSESSMENT

    def test_application_discovery_for_app_name(
        self, resolver: IntentResolver
    ) -> None:
        # "Is Prometheus running?" -> app discovery has 2 matches
        # (prometheus, running) vs service has 1 (running)
        result = resolver.resolve("Is Prometheus running?")
        assert result.intent == Intent.APPLICATION_DISCOVERY

    def test_monitoring_wins_over_troubleshooting_for_problems(
        self, resolver: IntentResolver
    ) -> None:
        # "Are there any problems?" -> monitoring wins (problems is in monitoring)
        result = resolver.resolve("Are there any problems?")
        assert result.intent == Intent.MONITORING_ASSESSMENT

    def test_service_wins_for_service_keyword(
        self, resolver: IntentResolver
    ) -> None:
        # "check docker service" -> service keyword wins
        result = resolver.resolve("check docker service")
        assert result.intent == Intent.SERVICE_ASSESSMENT


# ---------------------------------------------------------------------------
# InvestigationRequest properties
# ---------------------------------------------------------------------------


class TestInvestigationRequest:
    def test_raw_request_preserved(self, resolver: IntentResolver) -> None:
        result = resolver.resolve("Is the server healthy?")
        assert result.raw_request == "Is the server healthy?"

    def target_unset_after_resolver(self, resolver: IntentResolver) -> None:
        result = resolver.resolve("check disk")
        assert result.target is None

    def evidence_empty_after_resolver(self, resolver: IntentResolver) -> None:
        result = resolver.resolve("check disk")
        assert result.evidence == {}

    def execution_plan_unset_after_resolver(
        self, resolver: IntentResolver
    ) -> None:
        result = resolver.resolve("check disk")
        assert result.execution_plan is None

    def execution_graph_unset_after_resolver(
        self, resolver: IntentResolver
    ) -> None:
        result = resolver.resolve("check disk")
        assert result.execution_graph is None

    def capability_references_empty(self, resolver: IntentResolver) -> None:
        result = resolver.resolve("check disk")
        assert result.capability_references == []

    def required_evidence_empty(self, resolver: IntentResolver) -> None:
        result = resolver.resolve("check disk")
        assert result.required_evidence == []

    def optional_evidence_empty(self, resolver: IntentResolver) -> None:
        result = resolver.resolve("check disk")
        assert result.optional_evidence == []


# ---------------------------------------------------------------------------
# Confidence levels
# ---------------------------------------------------------------------------


class TestConfidence:
    def test_high_for_three_or_more_keywords(self, resolver: IntentResolver) -> None:
        result = resolver.resolve("review ssh firewall security hardening")
        assert result.confidence == Confidence.HIGH

    def test_medium_for_two_keywords(self, resolver: IntentResolver) -> None:
        result = resolver.resolve("check disk storage")
        assert result.confidence == Confidence.MEDIUM

    def test_low_for_one_keyword(self, resolver: IntentResolver) -> None:
        result = resolver.resolve("server")
        assert result.confidence == Confidence.LOW
