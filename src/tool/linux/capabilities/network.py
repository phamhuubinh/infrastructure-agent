from __future__ import annotations

import ipaddress
from collections.abc import Callable


def _get_network(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: networking (interfaces, addresses, routes).
    """
    interfaces: list[dict[str, object]] = []
    interface_names: set[str] = set()

    ok, output = run(["ip", "-o", "addr", "show"])

    result: dict[str, object] = {}
    sources: dict[str, str] = {}
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
        result["interfaces"] = interfaces
        result["interface_count"] = len(interface_names)
        sources["interfaces"] = "ip_addr"

    # Kernel fallback remains available in minimal containers where iproute2
    # is absent.  It reports link identity/statistics only and never invents
    # an IP address.
    if not interfaces:
        proc_ok, proc_output = run(["cat", "/proc/net/dev"])
        if proc_ok:
            stats = _parse_proc_net_dev(proc_output)
            for item in stats:
                name = str(item["name"])
                interface: dict[str, object] = {
                    "name": name,
                    "family": "link",
                    "statistics": {k: v for k, v in item.items() if k != "name"},
                }
                address_ok, address = run(["cat", f"/sys/class/net/{name}/address"])
                if address_ok and address.strip():
                    interface["address"] = address.strip()
                interfaces.append(interface)
                interface_names.add(name)
            result["interfaces"] = interfaces
            result["interface_count"] = len(interface_names)
            sources["interfaces"] = "proc_net_dev+sysfs"

    routes: list[str] = []
    ok, output = run(["ip", "route"])
    if ok:
        routes = [line.strip() for line in output.splitlines() if line.strip()]
        result["routes"] = routes
        sources["routes"] = "ip_route"
    else:
        route_ok, route_output = run(["cat", "/proc/net/route"])
        if route_ok:
            routes = _parse_proc_net_route(route_output)
            result["routes"] = routes
            sources["routes"] = "proc_net_route"

    ok2, link_output = run(["ip", "-o", "link", "show"])
    active_interfaces = 0
    if ok2:
        for line in link_output.splitlines():
            if "state UP" in line or "state UNKNOWN" in line:
                ifname2 = line.split(":")[1].strip() if ":" in line else ""
                if ifname2:
                    active_interfaces += 1
        result["active_interfaces"] = active_interfaces
        sources["link_state"] = "ip_link"
    elif interface_names:
        active_interfaces = 0
        state_collected = False
        for name in sorted(interface_names):
            state_ok, state = run(["cat", f"/sys/class/net/{name}/operstate"])
            if state_ok:
                state_collected = True
                if state.strip() in {"up", "unknown"}:
                    active_interfaces += 1
        if state_collected:
            result["active_interfaces"] = active_interfaces
            sources["link_state"] = "sysfs_operstate"

    if result:
        result["collection_sources"] = sources

    return result


def _parse_proc_net_route(output: str) -> list[str]:
    routes: list[str] = []
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 8:
            continue
        iface, destination_hex, gateway_hex, flags_hex = parts[:4]
        try:
            flags = int(flags_hex, 16)
            destination = str(
                ipaddress.IPv4Address(int(destination_hex, 16).to_bytes(4, "little"))
            )
            gateway = str(
                ipaddress.IPv4Address(int(gateway_hex, 16).to_bytes(4, "little"))
            )
        except (ValueError, OverflowError):
            continue
        if not flags & 0x1:
            continue
        if destination == "0.0.0.0":
            routes.append(f"default via {gateway} dev {iface}")
        else:
            routes.append(f"{destination} dev {iface}")
    return routes


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
    return {}


def _get_interface_stats(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """Subsystem: per-interface traffic statistics (bytes/packets/errors/drops)."""
    interfaces: list[dict[str, object]] = []
    strategy = "ip_link"
    ok, output = run(["ip", "-s", "link"])
    if ok:
        current_iface: dict[str, object] = {}
        pending_direction: str | None = None
        for line in output.splitlines():
            line = line.strip()
            # New interface block starts with a digit+colon (e.g., "1: lo:")
            if line and line[0].isdigit() and ":" in line:
                if current_iface:
                    interfaces.append(current_iface)
                current_iface = {}
                parts = line.split(":", 2)
                if len(parts) >= 2:
                    current_iface["name"] = parts[1].strip()
                pending_direction = None
            elif "RX:" in line and current_iface:
                pending_direction = "rx"
            elif "TX:" in line and current_iface:
                pending_direction = "tx"
            elif pending_direction and current_iface:
                values = line.split()
                if len(values) >= 4:
                    try:
                        for index, key in enumerate(
                            ("bytes", "packets", "errors", "dropped")
                        ):
                            current_iface[f"{pending_direction}_{key}"] = int(
                                values[index]
                            )
                    except ValueError:
                        pass
                pending_direction = None
        if current_iface:
            interfaces.append(current_iface)

    # Fallback: /proc/net/dev
    if not interfaces:
        ok2, dev_output = run(["cat", "/proc/net/dev"])
        if ok2:
            interfaces = _parse_proc_net_dev(dev_output)
            strategy = "proc_net_dev"

    if interfaces:
        return {
            "interface_stats": interfaces,
            "interface_stat_count": len(interfaces),
            "collection_strategy": strategy,
        }
    if ok or ok2:
        return {
            "interface_stats": [],
            "interface_stat_count": 0,
            "collection_strategy": strategy,
        }
    return {}


def _parse_ip_stats_line(line: str) -> dict[str, object]:
    """Parse 'RX: bytes packets errors dropped ...' style line from ip -s link."""
    result: dict[str, object] = {}
    parts = line.split()
    if len(parts) < 2:
        return result
    direction = parts[0].rstrip(":").lower()  # "RX" or "TX"
    prefix = f"{direction}_"
    for i, key in enumerate(("bytes", "packets", "errors", "dropped")):
        if i + 1 < len(parts):
            try:
                result[f"{prefix}{key}"] = int(parts[i + 1])
            except ValueError:
                continue
    return result


def _parse_proc_net_dev(output: str) -> list[dict[str, object]]:
    """Parse /proc/net/dev into interface stats list."""
    interfaces: list[dict[str, object]] = []
    for line in output.splitlines()[2:]:  # skip header lines
        if ":" not in line:
            continue
        name, stats = line.split(":", 1)
        name = name.strip()
        values = stats.split()
        if len(values) >= 10:
            try:
                interfaces.append(
                    {
                        "name": name,
                        "rx_bytes": int(values[0]),
                        "rx_packets": int(values[1]),
                        "rx_errors": int(values[2]),
                        "rx_dropped": int(values[3]),
                        "tx_bytes": int(values[8]),
                        "tx_packets": int(values[9]),
                        "tx_errors": int(values[10]) if len(values) > 10 else 0,
                        "tx_dropped": int(values[11]) if len(values) > 11 else 0,
                    }
                )
            except ValueError:
                continue
    return interfaces


def _get_ping_latency(
    run: Callable[..., tuple[bool, str]],
    target: str = "",
    count: int = 4,
) -> dict[str, object]:
    """Subsystem: ping latency to a specific target.

    Only runs when explicitly asked — never auto-ping on vague queries.
    """
    if not target:
        return {"latency": None, "error": "No target specified"}

    # Safety: validate target is not an injection attempt.
    import re as _re

    if not _re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,253}$", target):
        return {"latency": None, "error": f"Invalid target: {target}"}

    # Limit count to prevent abuse.
    count = max(1, min(count, 10))
    ok, output = run(["ping", "-c", str(count), "-W", "2", target])

    if not ok:
        return {"latency": None, "error": output.strip() or "Ping failed"}

    # Parse ping statistics.
    rtt_values: list[float] = []
    for line in output.splitlines():
        if "time=" in line:
            # Extract time=N.NN ms
            import re as _re2

            m = _re2.search(r"time=(\d+\.?\d*)\s*ms", line)
            if m:
                rtt_values.append(float(m.group(1)))

    if not rtt_values:
        return {"latency": None, "error": "No RTT data in ping output"}

    avg = sum(rtt_values) / len(rtt_values)
    min_rtt = min(rtt_values)
    max_rtt = max(rtt_values)

    # Parse loss percentage from summary line.
    loss_pct = 0.0
    for line in output.splitlines():
        if "packet loss" in line:
            import re as _re3

            m = _re3.search(r"(\d+(?:\.\d+)?)%", line)
            if m:
                loss_pct = float(m.group(1))
                break

    return {
        "target": target,
        "latency_ms": round(avg, 2),
        "latency_min_ms": round(min_rtt, 2),
        "latency_max_ms": round(max_rtt, 2),
        "packet_loss_pct": loss_pct,
        "samples": len(rtt_values),
    }


def _get_bandwidth(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """Subsystem: current bandwidth usage via sar.

    Falls back gracefully if sysstat is not installed.
    """
    ok, output = run(["sar", "-n", "DEV", "1", "1"])

    if not ok:
        # Check if sar is missing vs. just no data.
        ok2, _ = run(["which", "sar"])
        if not ok2:
            return {
                "bandwidth": None,
                "error": "sysstat not installed (sar unavailable)",
                "hint": "Install sysstat: apt install sysstat",
            }
        return {"bandwidth": None, "error": "sar failed"}

    interfaces: list[dict[str, object]] = []
    # Parse sar -n DEV output: skip header, parse IFACE rxpck/s txpck/s rxkB/s txkB/s
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("Linux") or line.startswith("Average"):
            continue
        if "IFACE" in line:
            continue
        parts = line.split()
        if len(parts) >= 6 and parts[0] != "Average:":
            try:
                interfaces.append(
                    {
                        "name": parts[0],
                        "rx_packets_per_sec": float(parts[1]),
                        "tx_packets_per_sec": float(parts[2]),
                        "rx_kbps": float(parts[3]),
                        "tx_kbps": float(parts[4]),
                    }
                )
            except (ValueError, IndexError):
                continue

    return {
        "bandwidth": interfaces,
        "interface_count": len(interfaces),
    }


def _get_listening_ports(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    ports: list[dict[str, object]] = []
    succeeded = False

    for proto in ("tcp", "udp"):
        ok, output = run(["ss", f"-l{proto[0]}np"])
        if ok:
            succeeded = True
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
                                "port_number": int(port_str) if port_str.isdigit() else None,
                                "protocol": proto,
                                "process": process,
                            }
                        )
    if not succeeded:
        proc_succeeded = False
        for proto, path in (
            ("tcp", "/proc/net/tcp"),
            ("tcp", "/proc/net/tcp6"),
            ("udp", "/proc/net/udp"),
            ("udp", "/proc/net/udp6"),
        ):
            proc_ok, proc_output = run(["cat", path])
            if not proc_ok:
                continue
            proc_succeeded = True
            ports.extend(_parse_proc_sockets(proc_output, proto))
        if not proc_succeeded:
            return {}
        return {
            "ports": ports,
            "port_count": len(ports),
            "collection_strategy": "proc_net_sockets",
            "process_attribution": "unavailable",
        }
    return {
        "ports": ports,
        "port_count": len(ports),
        "collection_strategy": "ss",
    }


def _parse_proc_sockets(output: str, protocol: str) -> list[dict[str, object]]:
    ports: list[dict[str, object]] = []
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 4 or ":" not in parts[1]:
            continue
        _, port_hex = parts[1].rsplit(":", 1)
        state = parts[3]
        # TCP 0A is LISTEN. UDP sockets have no LISTEN state and are retained
        # when bound because /proc provides no process-health guarantee.
        if protocol == "tcp" and state != "0A":
            continue
        try:
            port = int(port_hex, 16)
        except ValueError:
            continue
        ports.append(
            {
                "address": parts[1],
                "port": str(port),
                "port_number": port,
                "protocol": protocol,
                "process": "",
            }
        )
    return ports
