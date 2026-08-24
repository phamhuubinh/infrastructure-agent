# ADR 0006 — No semantic pre-router

## Decision

Orion does not classify the prompt into an intent/tool route before the primary model.

Do not maintain synonym lists, bilingual keyword rules, regex routers, or a separate LLM intent classifier whose job is to choose the tool.

The model sees the user request and tool schemas directly.
