"""Backward-compatible imports for the Grafana tool package."""

from src.tool.grafana import _CAPABILITIES, GrafanaTool

__all__ = ["GrafanaTool", "_CAPABILITIES"]
