# ADR-0005 — Unified Event and Trace System

**Status:** Accepted

## Decision

Agent activity UI, request traces, and `orion log` are backed by the same
structured event system.

The UI shows human-readable activity. CLI/debug views expose richer filtering
and safe metadata. Raw private chain-of-thought and secrets are not logged.

## Consequence

A failure can be traced consistently from the UI and command line without
maintaining separate instrumentation semantics.
