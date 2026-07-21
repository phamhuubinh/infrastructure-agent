from __future__ import annotations

from collections.abc import Callable


def _get_ssh(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: SSH server configuration summary (no keys, no secrets).
    """
    port = "unknown"
    permit_root_login = "unknown"
    password_authentication = "unknown"

    ok, output = run(["cat", "/etc/ssh/sshd_config"])

    if ok:
        for line in output.splitlines():
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            parts = line.split(None, 1)

            if len(parts) < 2:
                continue

            key, value = parts[0].lower(), parts[1].strip()

            if key == "port":
                port = value
            elif key == "permitrootlogin":
                permit_root_login = value
            elif key == "passwordauthentication":
                password_authentication = value

    active = "unknown"

    for service_name in ("ssh", "sshd"):
        ok, status_output = run(["systemctl", "is-active", service_name])

        if ok:
            active = status_output.strip()
            break

    return {
        "port": port,
        "permit_root_login": permit_root_login,
        "password_authentication": password_authentication,
        "active": active,
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
    """
    ok, output = run(["getenforce"])

    return {"status": output if ok else "unknown"}


def _get_firewall(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: firewall status (ufw preferred, iptables fallback).
    """
    ok, output = run(["ufw", "status"])

    if ok:
        words = output.lower().split()
        active = "active" in words
        return {"backend": "ufw", "active": active}

    ok, output = run(["iptables", "-L", "-n"])

    if ok:
        return {"backend": "iptables", "active": True}

    return {"backend": "unknown", "active": None}


def _get_certificate(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: installed CA certificate filenames (not their content).
    """
    ok, output = run(["ls", "/etc/ssl/certs"])

    certificates = [line for line in output.splitlines() if line.strip()] if ok else []

    return {"certificates": certificates}
