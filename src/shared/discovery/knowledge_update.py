from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KnowledgeUpdate:
    """
    Immutable structured knowledge update.
    """

    data: object
