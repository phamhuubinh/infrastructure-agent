# Engineering rules

## Runtime

- One Chat runtime serves ordinary Chat and Project conversations.
- Project adds project context/source; it does not fork runtime logic.
- The model makes semantic tool decisions.
- Do not introduce a pre-model intent/tool router.
- Do not introduce an Orion-specific model-visible workflow FSM.

## Tools

- One registry is the source of model-visible tool definitions.
- Every registered tool is available automatically.
- Tool descriptions/schemas must be provider-serializable.
- Tool results must be explicit successes or errors.
- Integration credentials stay outside model arguments where possible.
- Adding a tool must not require editing keyword intent maps.

## RAG

- RAG is a tool/source.
- Session and Project scopes are explicit.
- Project retrieval cannot leak across projects.
- Preserve document/page/section/chunk provenance.
- Whole-document tasks need more than naive top-k chunk search.

## Models

- Keep provider specifics behind adapters.
- Prefer native tool calling where reliable.
- A JSON fallback must stay small and tool-native.
- Never fix a weak provider by rebuilding a multi-stage Orion state protocol.

## Local-first

- Prefer local persistence/services.
- External integrations are optional.
- No product-level quota/rate-limit/tool-call-budget layer in the core architecture.
- Operational timeouts are allowed for hung-process recovery.

## Changes

- Keep changes cohesive.
- Delete superseded paths when cutover is complete rather than maintaining two semantic runtimes.
- Add tests at the contract boundary changed.
