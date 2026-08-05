from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.request_frame import RequestFrame
from src.pipeline.routing_decision import RoutingStatus

if TYPE_CHECKING:
    from src.shared.pipeline_state import PipelineState, StateUpdate


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


@dataclass(frozen=True, slots=True)
class IntentCandidate:
    intent: Intent
    score: float
    matched_keywords: tuple[str, ...] = ()
    compatible: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.intent.name,
            "score": round(self.score, 4),
            "matched_keywords": list(self.matched_keywords),
            "compatible": self.compatible,
        }


@dataclass(frozen=True, slots=True)
class IntentResolution:
    intent: Intent
    confidence: Confidence
    score: float
    candidates: tuple[IntentCandidate, ...]
    ambiguity_margin: float | None
    routing_status: RoutingStatus
    matched_keywords: tuple[str, ...] = ()
    reason: str | None = None


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
        ("uptime",),
        (
            "thời gian chạy",
            "thời gian hoạt động",
            "đã chạy bao lâu",
            "chạy được bao lâu",
            "chạy bao lâu",
        ),
    ),
    Intent.MEMORY_ASSESSMENT: (
        ("memory", "ram", "mem", "bộ nhớ"),
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
        (
            "danh sách container",
            "list container",
            "liệt kê container",
            "các container",
            "những container",
        ),
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


_CONCEPT_INTENTS: dict[str, tuple[Intent, ...]] = {
    "cpu": (Intent.CPU_ASSESSMENT, Intent.PERFORMANCE_ASSESSMENT),
    "memory": (Intent.MEMORY_ASSESSMENT, Intent.PERFORMANCE_ASSESSMENT),
    "disk": (
        Intent.DISK_ASSESSMENT,
        Intent.STORAGE_ASSESSMENT,
        Intent.FILESYSTEM_ASSESSMENT,
    ),
    "network": (Intent.NETWORK_ASSESSMENT_SINGLE, Intent.NETWORK_ASSESSMENT),
    "process": (Intent.PROCESS_ASSESSMENT,),
    "service": (Intent.SERVICE_ASSESSMENT, Intent.APPLICATION_DISCOVERY),
    "log": (Intent.TROUBLESHOOTING, Intent.SECURITY_ASSESSMENT),
    "package": (Intent.APPLICATION_DISCOVERY,),
    "container": (Intent.APPLICATION_DISCOVERY, Intent.SERVICE_ASSESSMENT),
    "alerts": (
        Intent.MONITORING_ASSESSMENT,
        Intent.NETWORK_ASSESSMENT,
        Intent.TROUBLESHOOTING,
    ),
    "dashboards": (Intent.MONITORING_ASSESSMENT,),
    "monitors": (Intent.MONITORING_ASSESSMENT,),
    "firewall": (Intent.SECURITY_ASSESSMENT, Intent.NETWORK_ASSESSMENT),
    "ssh": (Intent.SECURITY_ASSESSMENT,),
    "selinux": (Intent.SECURITY_ASSESSMENT,),
    "apparmor": (Intent.SECURITY_ASSESSMENT,),
    "performance": (Intent.PERFORMANCE_ASSESSMENT,),
    "machine": (Intent.MACHINE_ASSESSMENT,),
    "hostname": (Intent.MACHINE_ASSESSMENT,),
    "kernel": (Intent.MACHINE_ASSESSMENT,),
    "uptime": (Intent.CPU_ASSESSMENT, Intent.MACHINE_ASSESSMENT),
    "load": (Intent.CPU_ASSESSMENT, Intent.PERFORMANCE_ASSESSMENT),
}

_MULTI_RESOURCE_CONCEPTS = frozenset(
    {"cpu", "memory", "disk", "network", "process", "filesystem", "storage"}
)


def _intent_is_compatible(intent: Intent, frame: RequestFrame) -> bool:
    if frame.operation == "configure":
        return intent is Intent.CONFIGURATION_ASSESSMENT
    if intent in {Intent.CONFIGURATION_ASSESSMENT, Intent.TROUBLESHOOTING}:
        return True
    if frame.concepts == ("machine",):
        # Machine is the language fallback and must not veto a strong
        # domain-specific intent candidate.
        return True
    compatible = {
        candidate
        for concept in frame.concepts
        for candidate in _CONCEPT_INTENTS.get(concept, ())
    }
    if frame.operation == "diagnose":
        compatible.add(Intent.TROUBLESHOOTING)
    return not compatible or intent in compatible


def _rank_intent_candidates(
    tokens: list[str],
    frame: RequestFrame,
    selected: Intent,
) -> tuple[IntentCandidate, ...]:
    ranked: list[IntentCandidate] = []
    for intent, groups in _INTENT_KEYWORDS.items():
        matched = _matched_groups(tokens, groups)
        if not matched:
            continue
        compatible = _intent_is_compatible(intent, frame)
        score = min(0.99, 0.35 + 0.14 * len(matched) + (0.2 if compatible else 0.0))
        ranked.append(IntentCandidate(intent, score, matched, compatible))

    if not any(item.intent is selected for item in ranked):
        ranked.append(
            IntentCandidate(
                selected,
                max(0.5, frame.confidence),
                tuple(frame.matched_synonyms),
                True,
            )
        )

    ranked.sort(
        key=lambda item: (
            item.intent is not selected,
            -item.score,
            -_INTENT_PRIORITY[item.intent],
            item.intent.name,
        )
    )
    # Priority/compatibility tie-breaking is part of the score contract, so
    # the selected candidate must not appear numerically below runner-up.
    if len(ranked) > 1 and ranked[0].score <= ranked[1].score:
        ranked[0] = IntentCandidate(
            ranked[0].intent,
            min(1.0, ranked[1].score + 0.02),
            ranked[0].matched_keywords,
            ranked[0].compatible,
        )
    return tuple(ranked[:5])


class IntentResolver:
    """Resolve user intent using deterministic keyword rules.

    Responsibilities:
    - classify user intent from natural language requests
    - normalize input (lowercase, tokenize)
    - populate InvestigationRequest with intent, confidence, and matched keywords
    - return a StateUpdate dict for immutable state accumulation

    Never performs execution or tool calls.
    Never uses AI, ML, embeddings, or vector search.
    """

    # ------------------------------------------------------------------
    # Immutable pipeline state interface.
    # ------------------------------------------------------------------

    def resolve_state(self, state: PipelineState) -> StateUpdate:
        """Return an immutable StateUpdate with intent/confidence/keywords.

        Thin adapter that delegates to resolve() using state.user_request.
        """
        frame = state.request_frame
        if not isinstance(frame, RequestFrame):
            from src.pipeline.normalizer import Normalizer

            frame = Normalizer().normalize(state.user_request)
        result = self.resolve_frame(frame)
        enriched = frame.evolve(
            intent_candidates=result.candidates,
            routing_status=result.routing_status,
        )
        update: StateUpdate = {
            "request_frame": enriched,
            "semantic_request": enriched,
            "intent": result.intent,
            "confidence": result.confidence,
            "matched_keywords": result.matched_keywords,
            "intent_candidates": result.candidates,
            "intent_score": result.score,
            "intent_margin": result.ambiguity_margin,
            "routing_status": result.routing_status,
        }
        return update

    def resolve_frame(self, frame: RequestFrame) -> IntentResolution:
        """Resolve intent from an already-normalized canonical frame."""
        tokens = list(frame.lexical_tokens or frame.matched_synonyms)
        legacy = _resolve_intent(tokens)
        resource_concepts = _MULTI_RESOURCE_CONCEPTS.intersection(frame.concepts)

        if len(resource_concepts) >= 2:
            intent = Intent.PERFORMANCE_ASSESSMENT
            confidence = Confidence.MEDIUM
            keywords = tuple(frame.matched_synonyms)
        elif "ip address" in tokens:
            intent = Intent.NETWORK_ASSESSMENT
            confidence = Confidence.LOW
            keywords = ("ip address",)
        elif frame.operation == "configure":
            intent = Intent.CONFIGURATION_ASSESSMENT
            confidence = Confidence.MEDIUM
            keywords = tuple(frame.matched_synonyms)
        elif legacy is not None:
            intent, confidence, keywords = legacy
            if not _intent_is_compatible(intent, frame):
                compatible = tuple(
                    candidate
                    for concept in frame.concepts
                    for candidate in _CONCEPT_INTENTS.get(concept, ())
                )
                if compatible:
                    intent = compatible[0]
                    confidence = (
                        Confidence.MEDIUM
                        if frame.confidence >= 1.0
                        else Confidence.LOW
                    )
                    keywords = tuple(frame.matched_synonyms)
        else:
            compatible = tuple(
                candidate
                for concept in frame.concepts
                for candidate in _CONCEPT_INTENTS.get(concept, ())
            )
            intent = compatible[0] if compatible else Intent.MACHINE_ASSESSMENT
            confidence = (
                Confidence.MEDIUM if frame.confidence >= 1.0 else Confidence.LOW
            )
            keywords = tuple(frame.matched_synonyms)

        candidates = _rank_intent_candidates(tokens, frame, intent)
        score = candidates[0].score if candidates else frame.confidence
        margin = (
            score - candidates[1].score if len(candidates) > 1 else score
        )
        unresolved = bool(frame.ambiguity) or (
            not frame.matched_synonyms
            and frame.concepts == ("machine",)
            and frame.confidence == 0.0
        )
        return IntentResolution(
            intent=intent,
            confidence=confidence,
            score=score,
            candidates=candidates,
            ambiguity_margin=margin,
            routing_status=(
                RoutingStatus.CLARIFICATION_REQUIRED
                if unresolved
                else RoutingStatus.RESOLVED
            ),
            matched_keywords=keywords,
            reason="ambiguous concept or operation" if unresolved else None,
        )

    def resolve(self, user_request: str | RequestFrame) -> InvestigationRequest:
        """Resolve a user request and return an InvestigationRequest.

        Args:
            user_request: The raw user input string.

        Returns:
            An InvestigationRequest with intent, confidence, and matched keywords.
            Falls back to MACHINE_ASSESSMENT with LOW confidence when no keywords match.
        """
        if isinstance(user_request, RequestFrame):
            frame = user_request
        else:
            from src.pipeline.normalizer import Normalizer

            frame = Normalizer().normalize(user_request)
        result = self.resolve_frame(frame)
        enriched = frame.evolve(
            intent_candidates=result.candidates,
            routing_status=result.routing_status,
        )
        return InvestigationRequest(
            raw_request=frame.raw_request,
            intent=result.intent,
            confidence=result.confidence,
            matched_keywords=result.matched_keywords,
            request_frame=enriched,
            semantic_request=enriched,
            intent_candidates=result.candidates,
            intent_score=result.score,
            intent_margin=result.ambiguity_margin,
            routing_status=result.routing_status,
            extracted_params=enriched.parameters,
            answer_type=enriched.answer_type,
        )
