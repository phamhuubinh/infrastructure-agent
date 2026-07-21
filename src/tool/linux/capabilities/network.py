from __future__ import annotations

from collections.abc import Callable


def _get_network(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: networking (interfaces, addresses, routes).
    """
    interfaces: list[dict[str, object]] = []
    interface_names: set[str] = set()

    ok, output = run(["ip", "-o", "addr", "show"])

    if ok:
        for line in output.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            ifname = parts[1]
            interface_names.add(ifname)
            interfaces.append(
                {
                    "name": ifname,
                    "family": parts[2],
                    "address": parts[3],
                }
            )

    routes: list[str] = []
    ok, output = run(["ip", "route"])
    if ok:
        routes = [line.strip() for line in output.splitlines() if line.strip()]

    ok2, link_output = run(["ip", "-o", "link", "show"])
    active_interfaces = 0
    if ok2:
        for line in link_output.splitlines():
            if "state UP" in line or "state UNKNOWN" in line:
                ifname2 = line.split(":")[1].strip() if ":" in line else ""
                if ifname2:
                    active_interfaces += 1

    return {
        "interfaces": interfaces,
        "interface_count": len(interface_names),
        "active_interfaces": active_interfaces,
        "routes": routes,
    }


def _get_dns(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: DNS resolver configuration.
    """
    ok, output = run(["cat", "/etc/resolv.conf"])

    nameservers: list[str] = []

    if ok:
        for line in output.splitlines():
            line = line.strip()

            if not line.startswith("nameserver"):
                continue

            parts = line.split()

            if len(parts) >= 2:
                nameservers.append(parts[1])

    return {"nameservers": nameservers}


def _get_listening_ports(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    ports: list[dict[str, object]] = []

    for proto in ("tcp", "udp"):
        ok, output = run(["ss", f"-l{proto[0]}np"])
        if ok:
            for line in output.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 4:
                    addr = parts[3]
                    if ":" in addr:
                        port_str = addr.rsplit(":", 1)[-1]
                        process = ""
                        if len(parts) >= 6:
                            proc_part = parts[5] if len(parts) > 5 else ""
                            if "users:" in proc_part:
                                import re as _re

                                m = _re.search(r'"([^"]*)"', proc_part)
                                if m:
                                    process = m.group(1)
                        ports.append(
                            {
                                "address": addr,
                                "port": port_str,
                                "protocol": proto,
                                "process": process,
                            }
                        )
    return {"ports": ports, "port_count": len(ports)}
