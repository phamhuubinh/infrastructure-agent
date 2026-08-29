# Context and memory

## Context builder

Orion assembles context from deterministic application state plus model-driven tool results.

Recommended priority:

1. stable system instructions;
2. complete current user message;
3. explicit current attachment metadata/content;
4. active project metadata/instructions;
5. one bounded session-scoped conversation-state checkpoint when needed;
6. recent complete conversation turns not covered by that checkpoint;
7. tool results already produced in the current turn.

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

Long conversations may create one rolling checkpoint to fit the model's context window.
The checkpoint is a derived cache, not canonical truth: the complete timeline remains
authoritative and sufficient to regenerate it. A checkpoint covers a stable timeline
item boundary; covered raw turns are not replayed beside its state. It is refreshed
in bounded complete-turn batches, with a recent raw tail retained verbatim.

Current deterministic maintenance limits are an 8,000-byte unsummarized-history
watermark, one 4,000-byte complete-turn source batch, a 2,400-byte replacement
state, and a 4,400-byte recent raw-history allowance. Only one summary attempt is
made for a user request. These are model-context byte proxies, not product quotas.

Checkpoint text is untrusted conversation data, not a source of instructions or
citations. It is session-scoped, bounded, and removed with its Session (including
when a Project deletion removes that Session).

The current user request must never be silently truncated into a different request.

## Canonical timeline and model projection

The persisted/API timeline is the complete audit and UI record. Model input is a
separate byte-proxy-bounded projection of that record:

- the complete current user turn is retained;
- history reads begin only at user-turn boundaries and load at most the 64 newest
  complete prior turns plus the complete current turn;
- prior turns are considered newest-first, and any complete turn that does not fit is
  skipped so an older complete turn may still be retained;
- assistant tool calls are included only with every matching tool result;
- duplicate provider tool-call IDs are rejected before persistence;
- every current-turn ToolResult receives the same deterministic cap; Orion finds the
  largest shared cap whose complete current protocol sequence fits the conversation
  byte proxy, so no result is privileged merely for executing last;
- recent historical tool results receive more model-visible space than old results;
- oversized ToolResults are reduced structurally, never by cutting serialized JSON;
- status, errors, correlation fields, infrastructure target/change/verification
  metadata, collection counts, and exact `SourceRef` objects remain visible;
- explicit projection metadata reports omitted keys, items, string characters, and
  the number of omission records hidden by the metadata cap.
- checkpoint state plus its recent raw history share the same conversation byte
  budget; a checkpoint never creates an additional unbounded history allowance.

Projection never mutates the canonical `ToolResult`. The complete current user message,
assistant/tool protocol envelopes, errors, and exact sources are irreducible; if those
alone exceed the proxy, Orion retains them and treats the byte bound as soft rather than
creating malformed history. The byte proxy is deterministic context engineering, not
an exact tokenizer count or a guarantee that a particular model context window fits.

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
