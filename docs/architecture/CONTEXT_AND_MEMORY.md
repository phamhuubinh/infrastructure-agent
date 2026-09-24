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
- retained current-turn ToolResults share a deterministic cap. Under strict budget
  pressure, Orion selects complete tool-call/result blocks and recomputes that cap
  from their canonical results; discarded retry blocks do not consume the retained
  evidence budget;
- compaction reserves usable successful source-bearing evidence that fits with the
  complete user message and system context, then considers the latest failed tool
  block for recovery and other evidence. A later failure does not automatically
  replace an earlier success. Selected blocks stay in chronological order, with
  exact sources and call/result pairings; their original data remains persisted;
- a non-null projected `data` object is not proof that evidence survived: it may
  contain document metadata after all segment text was removed. Any reduction of
  successful source-bearing data triggers reconsideration of the strict-budget
  allocation. Its best standalone projection is protected before adding discovery
  results and retry history, which may be compacted or dropped to preserve text;
- prior-request raw ToolResults are not normal model context; only current-request results are
  evidence for a current-state claim;
- oversized ToolResults are reduced structurally, never by cutting serialized JSON;
- status, errors, correlation fields, infrastructure target/change/verification
  metadata, collection counts, and exact source reference IDs remain visible;
- when a ToolResult exceeds its model projection budget, source metadata is reduced
  to `source_ref_id` plus non-null `label` and `url` before reducing evidence data.
  Every source ID is preserved; `sources_compacted` reports this reduction. The
  canonical timeline and runtime visibility/authorization retain full `SourceRef`
  objects, including document/project identity and retrieval metadata;
- explicit projection metadata reports omitted keys, items, string characters, and
  the number of omission records hidden by the metadata cap;
- checkpoint state plus its recent raw history share the same conversation byte
  budget; a checkpoint never creates an additional unbounded history allowance.

Projection never mutates the canonical `ToolResult`. Assistant/tool protocol envelopes,
errors, and source identities remain structurally valid. The Orion-owned
`untrusted_external_content` trust label on current tool-result provenance survives data
compaction. Embedded instructions are retained as untrusted data, so a user can explicitly
ask to quote or analyze them; they are not removed using keyword rules. Source-only compaction leaves
`data_state=complete` and `source_data_state=upstream_nonempty_complete` when all nonempty
evidence data fits. Orion does not silently truncate the
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
