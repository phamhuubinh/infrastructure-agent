"""DR1-704: Action hallucination guard and ActionReceipt contract.

Orion is currently read-only: no capability performs a mutation. This module
defines the (future-compatible) ActionReceipt contract that a write
capability would need to produce before the model is allowed to claim an
action happened, and a guard that blocks/downgrades any response claiming
Orion already performed a mutating action when no such receipt exists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ActionReceipt:
    """Proof that a mutating action actually executed.

    Orion has no write capability today, so no code path currently
    constructs one of these — every guarded claim must therefore be
    rejected. The contract exists so a future write capability has a
    well-defined shape to satisfy before action claims become legal.
    """

    action_id: str
    capability: str
    target: str
    status: str
    started_at: datetime
    completed_at: datetime
    exit_code: int | None
    verified: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "capability": self.capability,
            "target": self.target,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "exit_code": self.exit_code,
            "verified": self.verified,
        }


_REFUSAL_VI = (
    "Orion chưa thực hiện hành động nào trên hệ thống — Orion chỉ đọc và đề "
    "xuất. Bất kỳ hành động khắc phục nào cũng cần được thực hiện thủ công."
)
_REFUSAL_EN = (
    "Orion has not performed any action on the system — Orion is read-only "
    "and can only recommend. Any remediation must be carried out manually."
)

# Completion-claim patterns: actor ("tôi"/"Orion"/"I"/"I've") + a mutating
# verb in the past/perfect tense. Deliberately narrow to actor-attributed
# claims so describing existing system state (e.g. "dịch vụ đã dừng") does
# not false-positive.
_ACTION_PATTERNS_VI = re.compile(
    r"\b(?:tôi|orion|hệ thống đã tự động|đã tự động)\s+(?:đã\s+)?"
    r"(?:xóa|sửa|khởi động lại|restart|deploy|gỡ|cài đặt|dừng|tắt|khởi động)\b",
    re.IGNORECASE,
)
_ACTION_PATTERNS_EN = re.compile(
    r"\b(?:i|i've|i have|orion has|orion)\s+(?:already\s+)?"
    r"(?:deleted|fixed|restarted|deployed|removed|installed|stopped|started|killed)\b",
    re.IGNORECASE,
)
_DIRECT_COMPLETION_VI = re.compile(
    r"\bđã\s+(?:tiến hành\s+)?(?:xóa|sửa|khởi động lại|restart|deploy|gỡ bỏ)\b"
    r"(?:\s+(?:file|thư mục|dịch vụ|service|tiến trình|process))",
    re.IGNORECASE,
)


def contains_action_claim(text: str) -> bool:
    """Detect Orion-attributed claims of having performed a mutating action."""

    return bool(
        _ACTION_PATTERNS_VI.search(text)
        or _ACTION_PATTERNS_EN.search(text)
        or _DIRECT_COMPLETION_VI.search(text)
    )


def guard_action_claims(
    text: str,
    action_receipts: tuple[ActionReceipt, ...] = (),
    *,
    lang: str = "vi",
) -> str:
    """Fail-closed: replace responses claiming an unverified action.

    If ``action_receipts`` contains a verified receipt, the claim is
    considered legitimate and the text passes through unchanged. Today no
    write capability exists, so ``action_receipts`` is always empty and any
    detected action claim is replaced with a safe refusal.
    """

    if not contains_action_claim(text):
        return text
    if any(receipt.verified for receipt in action_receipts):
        return text
    return _REFUSAL_VI if lang == "vi" else _REFUSAL_EN
