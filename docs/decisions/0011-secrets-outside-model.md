# ADR-0011: Secrets remain outside model context

Status: Accepted

## Decision

Credentials are resolved by executors after authorization from trusted configuration. They are not tool arguments, model context, evidence facts, or normal event payloads.
