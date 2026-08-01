from __future__ import annotations

from collections.abc import Callable


def _get_ssh(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: SSH server configuration summary (no keys, no secrets).

    Reads /etc/ssh/sshd_config and reports actual values or OpenSSH defaults
    when the directive is commented/missing.
    """
    port = None
    permit_root_login = None
    password_authentication = None
    has_config = False

    # OpenSSH defaults (for directives not explicitly set).
    # Source: man sshd_config (OpenSSH 8.9+).
    _SSHD_DEFAULTS = {
        "port": "22",
        "permitrootlogin": "prohibit-password",
        "passwordauthentication": "yes",
    }

    ok, output = run(["cat", "/etc/ssh/sshd_config"])

    if ok:
        has_config = True
        for line in output.splitlines():
            line = line.strip()
            parts = line.split(None, 1)

            # Check if this line has a real directive (even if commented).
            # A commented line means no explicit setting → use default.
            if len(parts) < 2:
                continue

            is_commented = line.startswith("#")
            if is_commented:
                # Strip leading '#' and re-split.
                line = line.lstrip("#").strip()
                parts = line.split(None, 1)
                if len(parts) < 2:
                    continue

            key = parts[0].lower()
            value = parts[1].strip().split()[0]  # First token only

            if key == "port":
                if not is_commented:
                    port = value
            elif key == "permitrootlogin":
                if not is_commented:
                    permit_root_login = value
            elif key == "passwordauthentication":
                if not is_commented:
                    password_authentication = value

    # Apply defaults for unset values.
    port_str = port if port is not None else _SSHD_DEFAULTS["port"]
    prl = (
        permit_root_login
        if permit_root_login is not None
        else _SSHD_DEFAULTS["permitrootlogin"]
    )
    pa = (
        password_authentication
        if password_authentication is not None
        else _SSHD_DEFAULTS["passwordauthentication"]
    )

    # Annotate if value came from default vs. explicit config.
    if port is None:
        port_str = f"{port_str} (default, not set in sshd_config)"
    if permit_root_login is None:
        prl = f"{prl} (default, not set in sshd_config)"
    if password_authentication is None:
        pa = f"{pa} (default, not set in sshd_config)"

    active = "unknown"
    if has_config:
        for service_name in ("ssh", "sshd"):
            ok2, status_output = run(["systemctl", "is-active", service_name])
            if ok2:
                active = status_output.strip()
                break

    return {
        "port": port_str,
        "permit_root_login": prl,
        "password_authentication": pa,
        "active": active,
        "has_config": has_config,
    }


def _get_secureboot(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: Secure Boot state.
    """
    ok, output = run(["mokutil", "--sb-state"])

    if not ok:
        return {"enabled": "unknown"}
    return {"enabled": "enabled" in output.lower()}


def _get_apparmor(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: AppArmor enabled state.
    """
    ok, output = run(["cat", "/sys/module/apparmor/parameters/enabled"])

    if not ok:
        return {"enabled": "unknown"}
    return {"enabled": output.strip() == "Y"}


def _get_selinux(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: SELinux enforcement mode.

    Detects whether SELinux is installed and reports its status.
    Returns "not installed" when SELinux is absent (e.g., Debian/Ubuntu).
    """
    # Try sestatus first for full status.
    ok, output = run(["sestatus"])
    if ok:
        status_line = ""
        mode = "unknown"
        for line in output.splitlines():
            line_lower = line.lower().strip()
            if "selinux status" in line_lower:
                status_line = line.strip()
            if "current mode" in line_lower:
                mode = line.split(":")[-1].strip()
        return {"status": status_line or "enabled", "mode": mode, "installed": True}

    # Fallback: getenforce.
    ok, output = run(["getenforce"])
    if ok:
        return {"status": output.strip(), "installed": True}

    # Check if config file exists (SELinux not running but may be installed).
    ok, _ = run(["cat", "/etc/selinux/config"])
    if ok:
        return {"status": "disabled", "installed": True}

    return {"status": "not installed", "installed": False}


def _get_firewall(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: firewall status with rules.

    Priority: ufw → iptables → nft.
    Always tries iptables for rule details even if ufw succeeds,
    because ufw may report 'inactive' while iptables has active rules.
    """
    ufw_result = None
    ok, output = run(["ufw", "status", "verbose"])
    if ok:
        lines = output.splitlines()
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
    ok, output = run(["iptables", "-L", "-n", "-v", "--line-numbers"])
    if ok:
        iptables_rules: list[str] = []
        in_rules = False
        chain = "unknown"
        policy = "unknown"
        chains_seen: list[str] = []
        for line in output.splitlines():
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
    ok, output = run(["nft", "list", "ruleset"])
    if ok:
        nft_rules = [ln.strip() for ln in output.splitlines() if ln.strip()]
        return {
            "backend": "nftables",
            "active": bool(nft_rules),
            "rules": nft_rules,
            "rule_count": len(nft_rules),
        }

    return {"backend": "unknown", "active": False}


def _get_certificate(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: installed CA certificate filenames (not their content).
    """
    ok, output = run(["ls", "/etc/ssl/certs"])

    certificates = [line for line in output.splitlines() if line.strip()] if ok else []

    return {"certificates": certificates}
