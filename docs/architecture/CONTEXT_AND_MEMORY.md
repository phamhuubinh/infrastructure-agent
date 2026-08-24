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
