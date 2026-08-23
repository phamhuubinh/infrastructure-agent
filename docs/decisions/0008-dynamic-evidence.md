# ADR-0008 — Dynamic Evidence Is Time-Bound

**Status:** Accepted

## Decision

Operational and current-world observations retain observation time and are not
stored as timeless truth. Project documents and other comparatively static
material may be reused according to their lifecycle.

The model decides when another read is necessary; the harness preserves the
metadata needed to make that decision.

## Consequence

Chat memory can contain prior observations without falsely treating them as
current infrastructure state.
