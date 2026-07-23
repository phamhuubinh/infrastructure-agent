from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CapabilityReference:
    """Abstract identifier representing an operational investigation capability.

    A capability answers exactly one operational question. The name
    describes the investigation objective rather than an implementation
    action, so it remains stable even if the underlying tool or command
    changes.

    Examples: "CPU Information", "Package Discovery", "Firewall Inspection"

    It does not describe:
    - which tool implements the capability
    - how the capability is executed
    - what infrastructure it accesses

    Attributes:
        name: The operational capability identifier.
        evidence_name: The evidence requirement this capability fulfills.
        description: Optional human-readable description.
        supported_targets: Target types this capability supports.
        parameters: Parameter names accepted by this capability.
        estimated_cost: Estimated execution cost (0.0 = free).
    """

    name: str
    evidence_name: str
    required: bool = False
    description: str = ""
    supported_targets: tuple[str, ...] = ()
    parameters: tuple[str, ...] = ()
    estimated_cost: float = 0.0
