# Context and memory

## Context builder

Orion assembles context from deterministic application state plus model-driven tool results.

Recommended priority:

1. stable system instructions;
2. complete current user message;
3. explicit current attachment metadata/content;
4. active project metadata/instructions;
5. recent complete user/assistant conversation turns within the deterministic byte bound;
6. ToolResults already produced in the current request.

RAG results are normally added through tool calls rather than automatically injected for every message.

## Conversation memory

Persist canonical public conversation state:

- user messages;
- assistant messages;
- tool-call items;
- tool results;
- attachments;
- active project relation;
- session-scoped derived checkpoints.

Do not persist private hidden reasoning.

## Summaries

The synchronous request path never invokes an LLM conversation summarizer. Legacy checkpoint
rows remain for persistence compatibility but are not read or retried by `ChatRuntime`; bounded
continuity comes from deterministic recent complete user/assistant turns. The current user
message is always retained in full or the request fails before a provider call.

The current user request must never be silently truncated into a different request.

## Canonical timeline and model projection

The persisted/API timeline is the complete audit and UI record. Model input is a
separate byte-proxy-bounded projection of that record:

- the complete current user turn is retained when the request can fit the local model-context safety bound;
- history reads begin only at user-turn boundaries and load at most the 64 newest
  complete prior turns plus the complete current turn;
- prior turns are considered newest-first, and any complete turn that does not fit is
  skipped so an older complete turn may still be retained;
- assistant tool calls are included only with every matching tool result;
- duplicate provider tool-call IDs are rejected before persistence;
- every current-turn ToolResult receives the same deterministic cap; Orion finds the
  largest shared cap whose complete current protocol sequence fits the conversation
  byte proxy, so no result is privileged merely for executing last;
- prior-request raw ToolResults are not normal model context; only current-request results are
  evidence for a current-state claim;
- oversized ToolResults are reduced structurally, never by cutting serialized JSON;
- status, errors, correlation fields, infrastructure target/change/verification
  metadata, collection counts, and exact `SourceRef` objects remain visible;
- explicit projection metadata reports omitted keys, items, string characters, and
  the number of omission records hidden by the metadata cap;
- checkpoint state plus its recent raw history share the same conversation byte
  budget; a checkpoint never creates an additional unbounded history allowance.

Projection never mutates the canonical `ToolResult`. Assistant/tool protocol envelopes,
errors, and exact sources remain structurally valid. Orion does not silently truncate the
current user message: if the complete current request plus irreducible protocol/system
context cannot fit Orion's local safety bound, the request fails explicitly before the
provider call with a context-safety error. This local byte proxy is deterministic context
engineering, not an exact tokenizer count or a guarantee that a particular provider window
is large enough.

## Project memory

Project documents/metadata are not conversation memory. They are durable project knowledge and should be queried through the project source when needed.

## Context window pressure

"Remove limits" means Orion should not impose arbitrary product quotas on tool use. The model still has a finite context window.

Therefore large tool/document outputs must use:

- pagination;
- structured reduction;
- summarization;
- references;
- selective read;
- retrieval.

This is context engineering, not a user-facing usage quota.
