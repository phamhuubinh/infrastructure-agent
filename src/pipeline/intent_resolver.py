from __future__ import annotations

from enum import auto
from enum import Enum

from src.pipeline.investigation_request import InvestigationRequest


class Intent(Enum):
    MACHINE_ASSESSMENT = auto()
    APPLICATION_DISCOVERY = auto()
    SERVICE_ASSESSMENT = auto()
    MONITORING_ASSESSMENT = auto()
    SECURITY_ASSESSMENT = auto()
    PERFORMANCE_ASSESSMENT = auto()
    STORAGE_ASSESSMENT = auto()
    NETWORK_ASSESSMENT = auto()
    CONFIGURATION_ASSESSMENT = auto()
    TROUBLESHOOTING = auto()


class Confidence(Enum):
    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()


# ---------------------------------------------------------------------------
# Keyword-to-intent mapping
# ---------------------------------------------------------------------------
# Each intent has a list of keyword groups (tuples of synonyms).
# Matching any keyword in a group counts as one match.

_INTENT_KEYWORDS: dict[Intent, tuple[tuple[str, ...], ...]] = {
    Intent.MACHINE_ASSESSMENT: (
        ("health", "healthy"),
        ("machine",),
        ("server",),
        ("system",),
        ("assess", "assessment", "evaluate"),
        ("overview",),
        ("summary",),
        ("general",),
        ("state",),
        ("configuration", "cấu hình"),
        ("của",),
        ("kiểm tra",),
    ),
    Intent.APPLICATION_DISCOVERY: (
        ("installed", "install", "installation"),
        ("exist", "exists", "present", "available", "deployed"),
        ("version",),
        ("running",),
        ("graylog",),
        ("docker",),
        ("prometheus",),
        ("nginx",),
        ("apache", "httpd"),
        ("mysql", "mariadb"),
        ("redis",),
        ("elasticsearch", "elastic"),
        ("kafka",),
        ("postgresql", "postgres"),
        ("rabbitmq",),
        ("mongodb", "mongo"),
        ("application",),
        ("package", "packages"),
        ("container", "containers"),
        ("vmware",),
    ),
    Intent.SERVICE_ASSESSMENT: (
        ("service", "services"),
        ("systemctl",),
        ("daemon", "daemons"),
        ("running",),
        ("mysql", "mariadb"),
        ("enabled",),
        ("restart", "started", "stopped"),
        ("failed",),
    ),
    Intent.MONITORING_ASSESSMENT: (
        ("alert", "alerts"),
        ("problem", "problems"),
        ("trigger", "triggers"),
        ("critical",),
        ("zabbix",),
        ("grafana",),
        ("monitor", "monitoring"),
        ("health",),
        ("dashboard", "dashboards"),
        ("panel", "panels"),
        ("host", "hosts"),
        ("event", "events"),
        ("severity",),
        ("alarm", "alarms"),
        ("down",),
    ),
    Intent.SECURITY_ASSESSMENT: (
        ("ssh",),
        ("firewall", "iptables", "nftables", "ufw"),
        ("security", "secure"),
        ("hardening", "harden"),
        ("selinux",),
        ("apparmor",),
        ("login", "logins", "authentication", "auth"),
        ("certificate", "certificates", "cert"),
        ("encrypt", "encryption", "encrypted"),
        ("vulnerability", "vulnerabilities", "cve"),
        ("audit",),
        ("password", "passwords"),
        ("key", "keys", "keypair"),
    ),
    Intent.PERFORMANCE_ASSESSMENT: (
        ("slow", "slowness"),
        ("performance",),
        ("cpu",),
        ("memory", "ram"),
        ("load", "load average"),
        ("bottleneck", "bottlenecks"),
        ("iowait", "io wait"),
        ("throughput",),
        ("saturation",),
    ),
    Intent.STORAGE_ASSESSMENT: (
        ("disk", "disks"),
        ("filesystem", "filesystems"),
        ("storage",),
        ("swap",),
        ("mount", "mounted", "mounts", "mountpoint"),
        ("inode", "inodes"),
        ("partition", "partitions"),
        ("lvm",),
        ("raid",),
        ("smart",),
        ("iops",),
        ("volume", "volumes"),
        ("fsck",),
    ),
    Intent.NETWORK_ASSESSMENT: (
        ("network", "networking"),
        ("ip", "ip address", "ipv4", "ipv6"),
        ("interface", "interfaces", "nic"),
        ("gateway",),
        ("route", "routing"),
        ("dns",),
        ("port", "ports", "open port"),
        ("connectivity", "connect", "connection", "connected"),
        ("ping",),
        ("bandwidth",),
        ("latency",),
        ("vlan",),
    ),
    Intent.CONFIGURATION_ASSESSMENT: (
        ("config", "configuration", "configured"),
        ("setting", "settings"),
        ("parameter", "parameters"),
        ("option", "options"),
        ("property", "properties"),
        ("validate", "validation"),
        ("drift",),
        ("compliance", "compliant"),
    ),
    Intent.TROUBLESHOOTING: (
        ("why",),
        ("issue", "issues"),
        ("diagnose", "diagnosis", "diagnostic"),
        ("troubleshoot", "troubleshooting"),
        ("fail", "fails", "failure"),
        ("broken",),
        ("error", "errors"),
        ("crash", "crashed", "crashing"),
        ("down",),
        ("not working", "not responding", "unreachable"),
        ("investigate",),
    ),
}

# Priority override rules.
# When a request matches keywords from multiple intents, the intent with the
# highest priority value wins. Higher number = higher priority.
# Priorities are designed so that specific operational intents win over
# general intents (MACHINE_ASSESSMENT is the lowest-priority fallback).
_INTENT_PRIORITY: dict[Intent, int] = {
    Intent.CONFIGURATION_ASSESSMENT: 60,
    Intent.TROUBLESHOOTING: 50,
    Intent.SECURITY_ASSESSMENT: 45,
    Intent.SERVICE_ASSESSMENT: 35,
    Intent.STORAGE_ASSESSMENT: 28,
    Intent.PERFORMANCE_ASSESSMENT: 25,
    Intent.NETWORK_ASSESSMENT: 20,
    Intent.MACHINE_ASSESSMENT: 11,
    Intent.MONITORING_ASSESSMENT: 10,
    Intent.APPLICATION_DISCOVERY: 12,
}


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase tokens preserving multi-word phrases."""
    text = text.lower()
    tokens: list[str] = []
    words = text.split()
    skip_next = False
    for i, word in enumerate(words):
        if skip_next:
            skip_next = False
            continue
        if i + 1 < len(words):
            phrase = f"{word} {words[i + 1]}"
            if phrase in _PHRASES:
                tokens.append(phrase)
                skip_next = True
                continue
        cleaned = word.strip(",.!?;:'\"()[]{}<>")
        if cleaned:
            tokens.append(cleaned)
    return tokens


_PHRASES: frozenset[str] = frozenset({
    "not working",
    "not responding",
    "io wait",
    "load average",
    "ip address",
    "cấu hình",
    "open port",
    "open ports",
    "memory leak",
    "packet loss",
})


def _matched_groups(
    tokens: list[str],
    keyword_groups: tuple[tuple[str, ...], ...],
) -> tuple[str, ...]:
    """Return the first matching keyword from each group found in tokens."""
    matched: list[str] = []
    for group in keyword_groups:
        for keyword in group:
            if keyword in tokens:
                matched.append(keyword)
                break
    return tuple(matched)


def _resolve_intent(
    tokens: list[str],
) -> tuple[Intent, Confidence, tuple[str, ...]] | None:
    """Resolve intent from tokenized input using keyword matching.

    Returns (intent, confidence, matched_keywords) or None if nothing matched.
    """
    candidates: list[tuple[Intent, int, tuple[str, ...]]] = []

    for intent, groups in _INTENT_KEYWORDS.items():
        matched = _matched_groups(tokens, groups)
        if matched:
            candidates.append((intent, len(matched), matched))

    if not candidates:
        return None

    if len(candidates) == 1:
        intent, count, matched = candidates[0]
        return (intent, _confidence_from_count(count), matched)

    # Multiple intents matched.
    # Find the highest match count among candidates.
    max_count = max(c[1] for c in candidates)
    # Filter to candidates with that maximum count.
    top = [c for c in candidates if c[1] == max_count]
    if len(top) == 1:
        intent, count, matched = top[0]
    else:
        # Tie in match count: use priority as tiebreaker.
        top.sort(key=lambda item: _INTENT_PRIORITY[item[0]], reverse=True)
        intent, count, matched = top[0]
    return (intent, _confidence_from_count(count), matched)


def _confidence_from_count(match_count: int) -> Confidence:
    if match_count >= 3:
        return Confidence.HIGH
    if match_count >= 2:
        return Confidence.MEDIUM
    return Confidence.LOW


class IntentResolver:
    """Resolve user intent using deterministic keyword rules.

    Responsibilities:
    - classify user intent from natural language requests
    - normalize input (lowercase, tokenize)
    - populate InvestigationRequest with intent, confidence, and matched keywords

    Never performs execution or tool calls.
    Never uses AI, ML, embeddings, or vector search.
    """

    def resolve(self, user_request: str) -> InvestigationRequest:
        """Resolve a user request and return an InvestigationRequest.

        Args:
            user_request: The raw user input string.

        Returns:
            An InvestigationRequest with intent, confidence, and matched keywords.
            Falls back to MACHINE_ASSESSMENT with LOW confidence when no keywords match.
        """
        if not user_request or not user_request.strip():
            return InvestigationRequest(
                raw_request=user_request,
                intent=Intent.MACHINE_ASSESSMENT,
                confidence=Confidence.LOW,
                matched_keywords=(),
            )

        tokens = _tokenize(user_request)
        result = _resolve_intent(tokens)

        if result is not None:
            intent, confidence, keywords = result
            return InvestigationRequest(
                raw_request=user_request,
                intent=intent,
                confidence=confidence,
                matched_keywords=keywords,
            )

        return InvestigationRequest(
            raw_request=user_request,
            intent=Intent.MACHINE_ASSESSMENT,
            confidence=Confidence.LOW,
            matched_keywords=(),
        )
