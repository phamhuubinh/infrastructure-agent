from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ExtractedParams:
    """Parameters extracted from a user request.

    All fields default to None when no parameter is detected.
    """

    service_name: str | None = None
    port: str | None = None
    process_name: str | None = None
    path: str | None = None
    time_range: str | None = None

    def __bool__(self) -> bool:
        return any(
            v is not None
            for v in (
                self.service_name,
                self.port,
                self.process_name,
                self.path,
                self.time_range,
            )
        )

    def to_dict(self) -> dict[str, str]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


class ParameterExtractor:
    """Extract structured parameters from user requests.

    Uses deterministic regex patterns to identify:
    - service_name: specific service the user is asking about
    - port: port number mentioned
    - process_name: specific process name
    - path: filesystem path mentioned
    - time_range: time expression like "1h", "today", etc.

    No AI — purely deterministic.
    """

    # Common service names used in infrastructure queries.
    _SERVICE_NAMES: re.Pattern = re.compile(
        r"\b(nginx|apache2?|httpd|sshd?|docker|postgres(ql)?|mysql|mariadb|"
        r"redis|mongod|kafka|rabbitmq|elasticsearch|haproxy|traefik|cron|"
        r"rsyslog|systemd-journald|ufw|iptables|fail2ban|apparmor|selinux|"
        r"containerd|grafana(?:-server)?|zabbix(?:-agent|-server)?|prometheus|"
        r"node_exporter|openvpn|bind9|named)\b",
        re.IGNORECASE,
    )

    # Port number patterns.
    _PORT: re.Pattern = re.compile(r"\b(?:port|cổng)\s+(\d{1,5})\b", re.IGNORECASE)
    _BARE_PORT: re.Pattern = re.compile(r"\b(?:on port|:)\s*(\d{1,5})\b", re.IGNORECASE)

    # Process name patterns.
    _PROCESS_NAME: re.Pattern = re.compile(
        r"\b(?:process|tiến trình|pid)\s+(\w+)\b", re.IGNORECASE
    )

    # Filesystem path patterns.
    _FILE_PATH: re.Pattern = re.compile(r"(/\w[\w./-]*)")

    # Time range patterns.
    _TIME_RANGE_VN: dict[str, str] = {
        "1 giờ": "1h",
        "một giờ": "1h",
        "1 tiếng": "1h",
        "24 giờ": "24h",
        "24h": "24h",
        "hôm nay": "today",
        "today": "today",
        "hôm qua": "yesterday",
        "yesterday": "yesterday",
        "tuần này": "7d",
        "this week": "7d",
        "tuần trước": "last_week",
        "last week": "last_week",
        "1 ngày": "1d",
        "1 day": "1d",
        "7 ngày": "7d",
        "7 days": "7d",
        "30 ngày": "30d",
        "30 days": "30d",
    }
    _TIME_RANGE_PATTERN: re.Pattern = re.compile(
        r"\b(\d+\s*(?:giờ|tiếng|ngày|days?|hours?|h|d|w|weeks?|months?))\b",
        re.IGNORECASE,
    )

    def extract(self, raw_request: str) -> ExtractedParams:
        """Extract all detectable parameters from a user request.

        Args:
            raw_request: The raw user request string.

        Returns:
            ExtractedParams with detected parameters.
        """
        lower = raw_request.lower()

        service_name = self._extract_service(lower)
        port = self._extract_port(lower)
        process_name = self._extract_process(lower)
        path = self._extract_path(lower)
        time_range = self._extract_time_range(lower)

        return ExtractedParams(
            service_name=service_name,
            port=port,
            process_name=process_name,
            path=path,
            time_range=time_range,
        )

    def _extract_service(self, text: str) -> str | None:
        """Look for specific service names like nginx, docker, sshd."""
        # Try "service X" or "dịch vụ X" patterns first.
        svc_pattern = re.compile(r"\b(?:service|dịch vụ)\s+(\w+)", re.IGNORECASE)
        m = svc_pattern.search(text)
        if m:
            candidate = m.group(1).lower()
            # Normalize common variants.
            if candidate in ("apache", "apache2"):
                return "apache2"
            if candidate in ("postgresql", "postgres"):
                return "postgresql"
            if candidate in ("sshd", "ssh"):
                return "sshd"
            return candidate

        # Try "trạng thái X" (Vietnamese: status of X).
        status_pattern = re.compile(
            r"\b(?:trạng thái|kiểm tra|check)\s+(\w+)", re.IGNORECASE
        )
        m = status_pattern.search(text)
        if m:
            candidate = m.group(1).lower()
            if candidate in ("sshd", "ssh"):
                return "sshd"
            if candidate in ("nginx",):
                return "nginx"
            if candidate in ("docker",):
                return "docker"

        # Fall back: look for known service names anywhere.
        m = self._SERVICE_NAMES.search(text)
        if m:
            name = m.group(1).lower()
            if name == "apache":
                return "apache2"
            if name.startswith("grafana"):
                return "grafana-server"
            if name.startswith("zabbix"):
                return "zabbix-server"
            return name
        return None

    def _extract_port(self, text: str) -> str | None:
        """Extract a port number from the request."""
        m = self._PORT.search(text)
        if m:
            return m.group(1)
        m = self._BARE_PORT.search(text)
        if m:
            return m.group(1)
        return None

    def _extract_process(self, text: str) -> str | None:
        """Extract a process name mentioned explicitly."""
        m = self._PROCESS_NAME.search(text)
        if m:
            return m.group(1)
        return None

    def _extract_path(self, text: str) -> str | None:
        """Extract a filesystem path from the request."""
        m = self._FILE_PATH.search(text)
        if m:
            return m.group(1)
        return None

    def _extract_time_range(self, text: str) -> str | None:
        """Extract time range expressions.

        Examples:
            "1 giờ" → "1h"
            "hôm nay" → "today"
            "7 ngày" → "7d"
        """
        # Check fixed expressions first.
        for phrase, value in self._TIME_RANGE_VN.items():
            if phrase in text:
                return value

        # Try numeric + unit patterns.
        m = self._TIME_RANGE_PATTERN.search(text)
        if m:
            return m.group(1).replace(" ", "")

        return None
