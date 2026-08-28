# Context and memory

## Context builder

Orion assembles context from deterministic application state plus model-driven tool results.

Recommended priority:

1. stable system instructions;
2. complete current user message;
3. explicit current attachment metadata/content;
4. active project metadata/instructions;
5. recent conversation;
6. older conversation summary;
7. tool results already produced in the current turn.

RAG results are normally added through tool calls rather than automatically injected for every message.

## Conversation memory

Persist public conversation state:

- user messages;
- assistant messages;
- tool-call items;
- tool results;
- attachments;
- active project relation;
- safe summaries.

Do not persist private hidden reasoning.

## Summaries

Long conversations may be summarized to fit the model's context window.

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
