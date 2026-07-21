"""Backward-compatible import path for :class:`src.tool.linux.LinuxTool`."""

from src.tool.linux import _CAPABILITIES, LinuxTool

__all__ = ["LinuxTool", "_CAPABILITIES"]
