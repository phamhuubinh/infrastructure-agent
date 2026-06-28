from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """Context for an execution, containing ID, parameters, and metadata."""
    execution_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
