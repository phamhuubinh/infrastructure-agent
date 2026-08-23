"""Canonical READ/WRITE permission contracts."""

from __future__ import annotations

from enum import Enum


class EffectClass(str, Enum):
    READ = "read"
    WRITE = "write"


class PermissionMode(str, Enum):
    READ = "read"
    RW_ASK = "rw_ask"
    RW_FULL = "rw_full"

    def allows(self, effect: EffectClass) -> bool:
        if not isinstance(effect, EffectClass):
            raise TypeError("effect must be EffectClass.")
        if effect is EffectClass.READ:
            return True
        return self is not PermissionMode.READ

    def requires_approval(self, effect: EffectClass) -> bool:
        if not isinstance(effect, EffectClass):
            raise TypeError("effect must be EffectClass.")
        return effect is EffectClass.WRITE and self is PermissionMode.RW_ASK
