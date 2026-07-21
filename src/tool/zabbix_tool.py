"""Backward-compatible imports for the Zabbix tool package."""

from src.tool.zabbix import _CAPABILITIES, ZabbixTool

__all__ = ["ZabbixTool", "_CAPABILITIES"]
