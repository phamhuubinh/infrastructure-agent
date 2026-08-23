# ADR-0007 — Secrets Stay Outside Model Context

**Status:** Accepted

## Decision

The model never receives API keys, passwords, SSH private keys, bearer tokens,
or equivalent credentials.

Tools/runtime resolve logical connection references to local secret material.

## Consequence

Provider changes and prompt/trace handling cannot expose credentials that were
never placed in model context.
