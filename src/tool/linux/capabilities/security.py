from __future__ import annotations

import ipaddress
import re

from .common import CommandRunner

_SSH_CONTEXT_USER = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,31}\Z")
_SSH_CONTEXT_HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}\Z")
_PERMIT_ROOT_LOGIN_VALUES = frozenset(
    {"yes", "no", "prohibit-password", "forced-commands-only"}
)


def _get_ssh(
    run: CommandRunner,
    *,
    user: str | None = None,
    host: str | None = None,
    addr: str | None = None,
) -> dict[str, object]:
    """
    Subsystem: SSH server configuration summary (no keys, no secrets).

    Prefers safe read-only effective inspection via ``sshd -T`` so Includes,
    Match blocks and defaults are applied (GA2-G08).  Falls back to raw
    ``/etc/ssh/sshd_config`` parsing only when ``sshd -T`` is unavailable.
    The effective value never reports ``no`` merely because a directive is
    absent — an absent directive is resolved by effective inspection or
    reported UNKNOWN rather than guessed.
    """
    _SSHD_DEFAULTS = {
        "port": "22",
        "permitrootlogin": "prohibit-password",
        "passwordauthentication": "yes",
    }

    supplied_context = (user, host, addr)
    has_context = any(value is not None for value in supplied_context)
    if has_context:
        if not all(isinstance(value, str) and value for value in supplied_context):
            raise ValueError("SSH context requires user, host, and addr together.")
        if not _SSH_CONTEXT_USER.fullmatch(user):
            raise ValueError("SSH context user is invalid.")
        if not _SSH_CONTEXT_HOST.fullmatch(host) or ".." in host:
            raise ValueError("SSH context host is invalid.")
        try:
            ipaddress.ip_address(addr)
        except ValueError as exc:
            raise ValueError("SSH context addr must be an IP address.") from exc
        effective = run(["sshd", "-T", "-C", f"user={user},host={host},addr={addr}"])
        source = "effective_sshd_config_context"
    else:
        effective = run(["sshd", "-T"])
        source = "effective_sshd_config"

    def _parse_effective(output: str) -> dict[str, str]:
        values: dict[str, str] = {}
        for line in output.splitlines():
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            values[parts[0].lower()] = parts[1].strip().split()[0]
        return values

    def _has_active_match(output: str) -> bool:
        return any(
            re.match(r"^\s*match\b", line, re.IGNORECASE)
            for line in output.splitlines()
            if not line.lstrip().startswith("#")
        )

    if effective.success:
        effective_values = _parse_effective(effective.stdout)
        # Effective inspection resolves Includes/Match/defaults.  An absent
        # directive here is the real OpenSSH default, not a guess.
        prl_raw = (
            effective_values.get("permitrootlogin") or _SSHD_DEFAULTS["permitrootlogin"]
        )
        port_raw = effective_values.get("port") or _SSHD_DEFAULTS["port"]
        password_raw = (
            effective_values.get("passwordauthentication")
            or _SSHD_DEFAULTS["passwordauthentication"]
        )
        # ``sshd -T`` without ``-C`` is global effective state.  A top-level
        # Match block can change PermitRootLogin for individual connections,
        # so never present that global value as universal when context is absent.
        if not has_context:
            config_result = run(["cat", "/etc/ssh/sshd_config"])
            if config_result.success and _has_active_match(config_result.stdout):
                prl_raw = "UNKNOWN"
                source = "context_specific_unknown"
    else:
        source = "raw_config_fallback"
        port = None
        permit_root_login = None
        password_authentication = None
        has_match = False
        config_result = run(["cat", "/etc/ssh/sshd_config"])
        if config_result.success:
            for line in config_result.stdout.splitlines():
                line = line.strip()
                parts = line.split(None, 1)
                if len(parts) < 2:
                    continue
                is_commented = line.startswith("#")
                if is_commented:
                    line = line.lstrip("#").strip()
                    parts = line.split(None, 1)
                    if len(parts) < 2:
                        continue
                key = parts[0].lower()
                value = parts[1].strip().split()[0]
                if not is_commented:
                    if key == "match":
                        has_match = True
                    if key == "port":
                        port = value
                    elif key == "permitrootlogin":
                        permit_root_login = value
                    elif key == "passwordauthentication":
                        password_authentication = value
        # Raw fallback cannot resolve Includes/Match recursively; an absent
        # directive is reported as UNKNOWN rather than a guessed default.
        prl_raw = permit_root_login if permit_root_login is not None else "UNKNOWN"
        port_raw = port if port is not None else "UNKNOWN"
        password_raw = (
            password_authentication
            if password_authentication is not None
            else "UNKNOWN"
        )
        if has_match:
            prl_raw = "UNKNOWN"
            source = "context_specific_unknown"

    prl = (prl_raw or "UNKNOWN").casefold()
    if prl not in _PERMIT_ROOT_LOGIN_VALUES:
        prl = "UNKNOWN"
    port_str = port_raw or _SSHD_DEFAULTS["port"]
    pa = (
        password_raw
        if password_raw is not None
        else _SSHD_DEFAULTS["passwordauthentication"]
    )

    active = "unknown"
    for service_name in ("ssh", "sshd"):
        status_result = run(["systemctl", "is-active", service_name])
        if status_result.success:
            active = status_result.stdout.strip()
            break

    return {
        "port": port_str,
        "permit_root_login": prl,
        "password_authentication": pa,
        "active": active,
        "source": source,
        "has_config": True,
    }


def _get_secureboot(run: CommandRunner) -> dict[str, object]:
    """
    Subsystem: Secure Boot state.
    """
    result = run(["mokutil", "--sb-state"])

    if not result.success:
        return {"enabled": "unknown"}
    return {"enabled": "enabled" in result.stdout.lower()}


def _get_apparmor(run: CommandRunner) -> dict[str, object]:
    """
    Subsystem: AppArmor enabled state.
    """
    result = run(["cat", "/sys/module/apparmor/parameters/enabled"])

    if not result.success:
        return {"enabled": "unknown"}
    return {"enabled": result.stdout.strip() == "Y"}


def _get_selinux(run: CommandRunner) -> dict[str, object]:
    """
    Subsystem: SELinux enforcement mode.

    Detects whether SELinux is installed and reports its status.
    Returns "not installed" when SELinux is absent (e.g., Debian/Ubuntu).
    """
    # Try sestatus first for full status.
    result = run(["sestatus"])
    if result.success:
        status_line = ""
        mode = "unknown"
        for line in result.stdout.splitlines():
            line_lower = line.lower().strip()
            if "selinux status" in line_lower:
                status_line = line.strip()
            if "current mode" in line_lower:
                mode = line.split(":")[-1].strip()
        return {"status": status_line or "enabled", "mode": mode, "installed": True}

    # Fallback: getenforce.
    result = run(["getenforce"])
    if result.success:
        return {"status": result.stdout.strip(), "installed": True}

    # Check if config file exists (SELinux not running but may be installed).
    result = run(["cat", "/etc/selinux/config"])
    if result.success:
        return {"status": "disabled", "installed": True}

    return {"status": "not installed", "installed": False}


def _get_firewall(run: CommandRunner) -> dict[str, object]:
    """
    Subsystem: firewall status with rules.

    Priority: ufw → iptables → nft.
    Always tries iptables for rule details even if ufw succeeds,
    because ufw may report 'inactive' while iptables has active rules.
    """
    ufw_result = None
    result = run(["ufw", "status", "verbose"])
    if result.success:
        lines = result.stdout.splitlines()
        active = False
        default_policy = ""
        ufw_rules: list[str] = []
        in_rules = False
        saw_status = False
        for line in lines:
            lower = line.lower().strip()
            if not saw_status and lower.startswith("status:"):
                active = "active" in lower and "inactive" not in lower
                saw_status = True
            if lower.startswith("default:"):
                default_policy = line.strip()
            if in_rules and line.strip():
                ufw_rules.append(line.strip())
            if not in_rules and ("----" in line or "action" in lower):
                in_rules = True
        ufw_result = {
            "backend": "ufw",
            "active": active,
            "default_policy": default_policy,
            "rules": ufw_rules,
            "rule_count": len(ufw_rules),
        }
        # If ufw is active with rules, return immediately.
        if active and ufw_rules:
            return ufw_result

    # Try iptables — always attempt this, even if ufw was 'inactive'.
    # iptables rules may exist independently of ufw.
    result = run(["iptables", "-L", "-n", "-v", "--line-numbers"])
    if result.success:
        iptables_rules: list[str] = []
        in_rules = False
        chain = "unknown"
        policy = "unknown"
        chains_seen: list[str] = []
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("Chain "):
                parts = stripped.split()
                if len(parts) >= 2:
                    chain = parts[1]
                    chains_seen.append(chain)
                if "policy" in stripped.lower():
                    policy = stripped.split("policy")[-1].strip().split()[0]
                in_rules = True
                continue
            if in_rules and stripped:
                iptables_rules.append(f"[{chain}] {stripped}")
        iptables_result = {
            "backend": "iptables",
            "active": True,
            "rules": iptables_rules,
            "rule_count": len(iptables_rules),
            "chains": chains_seen,
            "default_policy": f"{chain}: {policy}",
        }
        # If ufw returned inactive, combine: report ufw as frontend but show iptables rules.
        if ufw_result is not None and not ufw_result["active"]:
            return {
                "backend": "ufw (inactive) + iptables",
                "active": bool(iptables_rules),
                "ufw_status": ufw_result,
                "iptables_rules": iptables_rules,
                "iptables_rule_count": len(iptables_rules),
                "rules": iptables_rules,
                "rule_count": len(iptables_rules),
            }
        return iptables_result

    # If ufw was active but had no iptables visibility, return ufw result.
    if ufw_result is not None:
        return ufw_result

    # Try nft as final fallback.
    result = run(["nft", "list", "ruleset"])
    if result.success:
        nft_rules = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
        return {
            "backend": "nftables",
            "active": bool(nft_rules),
            "rules": nft_rules,
            "rule_count": len(nft_rules),
        }

    return {"backend": "unknown", "active": False}


def _get_certificate(run: CommandRunner) -> dict[str, object]:
    """
    Subsystem: installed CA certificate filenames (not their content).
    """
    result = run(["ls", "/etc/ssl/certs"])

    certificates = (
        [line for line in result.stdout.splitlines() if line.strip()]
        if result.success
        else []
    )

    return {"certificates": certificates}
