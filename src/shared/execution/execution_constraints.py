from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class ExecutionConstraints:
    timeout_seconds: int
    cancellable: bool
    retry_limit: int
