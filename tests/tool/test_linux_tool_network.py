from __future__ import annotations

from src.tool.linux import LinuxTool

PROC_DEV = """Inter-| Receive | Transmit
 face |bytes packets errs drop fifo frame compressed multicast|bytes packets errs drop fifo colls carrier compressed
  lo: 100 2 0 0 0 0 0 0 100 2 0 0 0 0 0 0
eth0: 2048 8 0 1 0 0 0 0 4096 9 0 0 0 0 0 0
"""

PROC_ROUTE = """Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT
eth0 00000000 0101A8C0 0003 0 0 0 00000000 0 0 0
"""


def test_network_uses_proc_and_sys_fallback_when_ip_is_missing() -> None:
    def run(command, timeout=15):
        if command[0] == "ip":
            return False, ""
        if command == ["cat", "/proc/net/dev"]:
            return True, PROC_DEV
        if command == ["cat", "/proc/net/route"]:
            return True, PROC_ROUTE
        if command[-1].endswith("/address"):
            return True, "00:11:22:33:44:55"
        if command[-1].endswith("/operstate"):
            return True, "up"
        return False, ""

    tool = LinuxTool()
    tool._run = run
    result = tool.execute({"action": "get_network"})

    assert result.success is True
    assert result.data["interface_count"] == 2
    assert result.data["interfaces"][1]["statistics"]["rx_bytes"] == 2048
    assert result.data["routes"] == ["default via 192.168.1.1 dev eth0"]
    assert result.data["collection_sources"]["interfaces"] == "proc_net_dev+sysfs"


def test_interface_stats_are_numeric_with_proc_provenance() -> None:
    def run(command, timeout=15):
        if command[0] == "ip":
            return False, ""
        if command == ["cat", "/proc/net/dev"]:
            return True, PROC_DEV
        return False, ""

    tool = LinuxTool()
    tool._run = run
    result = tool.execute({"action": "get_interface_stats"})

    assert result.success is True
    assert result.data["collection_strategy"] == "proc_net_dev"
    assert isinstance(result.data["interface_stats"][0]["rx_bytes"], int)


def test_network_failure_does_not_claim_no_interfaces() -> None:
    tool = LinuxTool()
    tool._run = lambda command, timeout=15: (False, "")

    result = tool.execute({"action": "get_network"})

    assert result.success is False
    assert result.data is None
