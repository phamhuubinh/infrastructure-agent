from __future__ import annotations

from enum import Enum, auto

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
    CPU_ASSESSMENT = auto()
    MEMORY_ASSESSMENT = auto()
    DISK_ASSESSMENT = auto()
    NETWORK_ASSESSMENT_SINGLE = auto()
    PROCESS_ASSESSMENT = auto()
    FILESYSTEM_ASSESSMENT = auto()
    KNOWLEDGE_ASSESSMENT = auto()


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
    Intent.CPU_ASSESSMENT: (
        ("cpu",),
        ("cpu usage", "cpu utilization", "cpu load"),
        ("processor", "bộ xử lý", "vi xử lý"),
        ("core", "cores"),
        ("cpu percent",),
    ),
    Intent.MEMORY_ASSESSMENT: (
        ("memory", "ram", "bộ nhớ"),
        ("memory usage", "memory utilization"),
        ("swap",),
        ("memory leak",),
    ),
    Intent.DISK_ASSESSMENT: (
        ("disk", "disks"),
        ("disk usage", "disk space"),
        ("ổ cứng", "ssd", "hdd", "đĩa", "ổ đĩa", "dung lượng"),
        ("filesystem", "filesystems"),
        ("storage",),
        ("iowait", "io wait"),
        ("iops",),
        ("fsck",),
    ),
    Intent.NETWORK_ASSESSMENT_SINGLE: (
        ("network", "networking", "mạng", "kết nối mạng"),
        ("network usage", "network traffic"),
        ("băng thông", "băng-thông"),
        ("bandwidth",),
        ("latency", "độ trễ"),
        ("ping",),
        ("ip",),
    ),
    Intent.PROCESS_ASSESSMENT: (
        ("process", "processes", "tiến trình"),
        ("process list",),
        ("top process",),
        ("ps",),
        ("running process",),
    ),
    Intent.FILESYSTEM_ASSESSMENT: (
        ("filesystem", "filesystems"),
        ("mount", "mounts", "mountpoint", "mounted"),
        ("inode", "inodes"),
        ("fsck",),
    ),
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
        ("vấn đề",),
        ("nghiêm trọng", "nghiêm-trọng"),
        ("phân tích",),
        ("máy",),
        (
            "cho tôi biết",
            "cho tôi",
        ),
    ),
    Intent.APPLICATION_DISCOVERY: (
        ("installed", "install", "installation", "cài đặt"),
        ("exist", "exists", "present", "available", "deployed"),
        ("version", "phiên bản"),
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
        ("application", "ứng dụng"),
        ("package", "packages"),
        ("container", "containers"),
    ),
    Intent.SERVICE_ASSESSMENT: (
        ("service", "services", "dịch vụ"),
        ("systemctl",),
        ("daemon", "daemons"),
        ("running", "đang chạy"),
        ("mysql", "mariadb"),
        ("enabled",),
        ("restart", "started", "stopped"),
        ("failed",),
        ("sshd", "ssh service"),
        ("nginx", "apache", "httpd"),
        ("docker",),
        ("postgresql", "postgres"),
        ("redis",),
        ("elasticsearch", "elastic"),
        ("kafka",),
        ("rabbitmq",),
        ("mongodb", "mongo"),
        ("trạng thái",),
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
        ("down", "downed"),
        ("priorit", "priority", "ưu tiên"),
        ("sự cố", "sự-cố"),
        ("vấn đề",),
        ("nghiêm trọng", "nghiêm-trọng"),
        ("trend", "history", "chart", "graph"),
        ("timeseries", "time series", "time-series"),
        ("metric", "metrics"),
        ("1h", "24h", "7d", "30d"),
        ("biểu đồ", "đồ thị"),
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
        ("memory leak",),
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
        ("network", "networking", "mạng", "kết nối mạng"),
        ("ip", "ip address", "ipv4", "ipv6"),
        ("interface", "interfaces", "nic"),
        ("gateway",),
        ("route", "routing"),
        ("dns",),
        ("port", "ports", "open port"),
        ("connectivity", "connect", "connection", "connected"),
        ("ping",),
        ("bandwidth", "băng thông", "băng-thông"),
        ("latency",),
        ("vlan",),
        ("packet loss",),
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
    Intent.KNOWLEDGE_ASSESSMENT: (
        ("kubernetes", "k8s"),
        ("what is", "what are"),
        ("how does", "how do", "how to"),
        ("explain", "define", "definition"),
        ("difference", "vs", "versus"),
        ("tutorial", "guide", "example"),
        ("best practice",),
        ("architecture", "architect"),
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
    Intent.CPU_ASSESSMENT: 32,
    Intent.MEMORY_ASSESSMENT: 31,
    Intent.DISK_ASSESSMENT: 30,
    Intent.PROCESS_ASSESSMENT: 29,
    Intent.FILESYSTEM_ASSESSMENT: 28,
    Intent.STORAGE_ASSESSMENT: 28,
    Intent.PERFORMANCE_ASSESSMENT: 27,
    Intent.NETWORK_ASSESSMENT: 20,
    Intent.NETWORK_ASSESSMENT_SINGLE: 21,
    Intent.MACHINE_ASSESSMENT: 11,
    Intent.MONITORING_ASSESSMENT: 10,
    Intent.APPLICATION_DISCOVERY: 12,
    Intent.KNOWLEDGE_ASSESSMENT: 5,
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


_PHRASES: frozenset[str] = frozenset(
    {
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
        "kết nối mạng",
        "băng thông",
        "sự cố",
        "vấn đề",
        "nghiêm trọng",
        "ưu tiên",
        "ssh service",
        "time series",
        "running process",
        "dịch vụ",
        "đang chạy",
        "ổ đĩa",
        "ổ cứng",
        "bộ nhớ",
        "bộ xử lý",
        "vi xử lý",
        "trạng thái",
        "phiên bản",
        "cài đặt",
        "ứng dụng",
        "độ trễ",
        "phân tích",
        "cho tôi biết",
        "cho tôi",
    }
)


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
    # Heuristic: if two or more specific sub-system intents (CPU, MEMORY,
    # DISK, NETWORK, PROCESS, FILESYSTEM, STORAGE) are tied, the user
    # likely wants a broader assessment (MACHINE, PERFORMANCE, etc.).
    # Promote to MACHINE_ASSESSMENT first if it has strong confidence,
    # then fall back to PERFORMANCE_ASSESSMENT.
    _specific = frozenset(
        {
            Intent.CPU_ASSESSMENT,
            Intent.MEMORY_ASSESSMENT,
            Intent.DISK_ASSESSMENT,
            Intent.NETWORK_ASSESSMENT_SINGLE,
            Intent.PROCESS_ASSESSMENT,
            Intent.FILESYSTEM_ASSESSMENT,
            Intent.STORAGE_ASSESSMENT,
        }
    )
    specific_candidates = [(i, c, m) for i, c, m in candidates if i in _specific]
    if len(specific_candidates) >= 2:
        # Prefer MACHINE_ASSESSMENT if it has HIGH confidence (match≥3).
        machine = next(
            ((i, c, m) for i, c, m in candidates if i == Intent.MACHINE_ASSESSMENT),
            None,
        )
        if machine is not None and machine[1] >= 3:
            return (machine[0], _confidence_from_count(machine[1]), machine[2])
        # Otherwise promote to PERFORMANCE_ASSESSMENT if it is a candidate.
        perf = next(
            ((i, c, m) for i, c, m in candidates if i == Intent.PERFORMANCE_ASSESSMENT),
            None,
        )
        if perf is not None and perf[1] >= 2:
            return (perf[0], _confidence_from_count(perf[1]), perf[2])

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
