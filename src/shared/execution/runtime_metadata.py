from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True, slots=True)
class RuntimeMetadata:
    """Metadata about the runtime execution period."""

    runtime_version: str
    started_at: datetime
    finished_at: datetime
    duration_ms: int
