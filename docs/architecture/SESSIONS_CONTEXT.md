# Sessions and context

## Session

A session is a persistent conversation timeline plus safe runtime metadata. A request/turn is an execution unit inside a session.

## Persisted items

Persist typed public items such as:

- user messages;
- assistant final/clarification/refusal messages;
- tool-call proposals;
- approval requests/resolutions;
- tool results;
- evidence references;
- request terminal state;
- selected project/document references;
- bounded conversation summaries.

Do not persist private model reasoning or credentials.

## Context assembly

Order of priority:

1. system/security policy;
2. complete current request;
3. active approvals/pending state;
4. relevant recent tool results/evidence summaries;
5. project retrieval selected for this request;
6. bounded recent conversation;
7. older conversation summary.

## Concurrency

Request execution within one session should be serialized unless a future design explicitly supports concurrent turns. Delete/clean operations must coordinate with in-flight work so deleted sessions cannot be resurrected by late writes.

## Resume

Resume reconstructs public timeline and runtime-safe state, not hidden model state. Pending approval may be resumed only if its exact action fingerprint and expiry remain valid.
