# Acceptance criteria

The target is acceptable when these product/runtime invariants are demonstrated.

## Chat

- User can create/resume a conversation.
- Plain conversational prompts can answer without unnecessary tools.
- All registered/configured tools are available automatically through the registry-derived exposure contract.
- There is no required tool picker.
- Model tool calls execute and results return to the same model loop.
- Multiple sequential tool calls work without a fixed successful-call quota.

## Project

- Project conversation uses the same runtime as Chat.
- Active project metadata is present deterministically.
- Project documents form an additional project-scoped RAG source.
- Project A retrieval never leaks Project B data.
- Project scope comes from Orion session/project state, not an arbitrary model-supplied `project_id`.
- A knowledge tool receives the active project through application-owned `RuntimeScope` or an equivalent deterministic mechanism.
- All non-RAG registered tools remain available inside Project.
- There is no Project-specific tool picker.

## RAG/documents

- Binary-safe upload accepts supported text/Markdown, PDF, DOCX, and XLSX files.
- Upload → parse → index → ready lifecycle is explicit; malformed or unsafe input reaches an explicit failed state.
- Raw upload size and Office archive-expansion safety limits are bounded independently.
- Session attachments are retrievable only in valid session scope.
- Project documents are retrievable only in active project scope.
- Exact document read works.
- Semantic retrieval works.
- Document-grounded factual/topic/quote answers retrieve current content evidence before synthesis.
- `knowledge.search` is the default discovery path when no exact target document is visible or
  retrieval spans knowledge sources; a visible exact session attachment may be read directly.
- Document metadata listing is not required as a content-QA preflight.
- Whole-document summarization is not limited to arbitrary top-k chunks.
- Cross-document comparison preserves source identity.
- PDF page, DOCX section/paragraph/table, and XLSX sheet/row provenance can survive to citations/source metadata where available.
- Model answers grounded in ToolResults preserve record/field associations: dates, statuses, versions, labels, retrieval times, and other attributes must not be transferred to neighboring records or renamed into unsupported claims; ancillary metadata is omitted when it is not explicitly tied to the requested record.
- Deleted/tombstoned documents do not reappear in retrieval.
- Incomplete persisted ingestion can reconcile after a normal restart.

## Canonical contracts

- Provider responses normalize into one internal model-turn/tool-call contract.
- Every registered tool has one canonical name/schema/handler binding.
- Tool execution returns one canonical `ToolResult`/error shape.
- Session/project/attachment runtime scope is application-owned context.
- Document/source/retrieved-segment identities survive ingestion through citation.
- Provider-specific and tool-specific implementation objects do not leak into the core runtime.

## Tools

- Knowledge/RAG, calculator, Internet, Linux, Grafana, and Zabbix families can register through the same tool system.
- Internet search rows are discovery-only; citable web evidence comes from `internet.fetch`.
- For an explicit citation request, a non-empty discovery-only `internet.search` result cannot terminate as an uncited answer; Orion resumes the model so it can fetch citable web evidence.
- Exact latest/current web claims use authoritative fetched evidence; search-result rank or an
  incidental snippet mention alone does not establish the requested current state.
- A new registered tool becomes discoverable/model-visible without adding semantic router rules.
- All registered model-callable schemas are visible on the first turn; schema visibility never grants mutation authorization.
- Tool errors return explicitly to the model.
- Repeated recoverable failures terminate only after an unchanged normalized failure state demonstrates no progress; corrected arguments may continue.
- When citation recovery obtains new citable evidence through a successful tool call, Orion permits one bounded follow-up citation repair from that new evidence; the allowance cannot reopen repeatedly.
- Citation recovery prefers already-visible supporting `evidence_ref` aliases and does not broaden into unrelated tool calls merely to repair a missing citation.
- Under model-context pressure, retrieved knowledge segment text and segment identity are retained ahead of expendable result metadata so a visible hit does not degrade into metadata-only pseudo-evidence.
- During citation recovery, discovery-only `internet.search` rows with no fetched web `evidence_ref` require an `internet.fetch` call before terminal answer prose.
- Discovery-only tool results may request generic model continuation without becoming provider-visible control metadata; all registered tools remain available and the model still selects the follow-up action.
- A successful ToolResult that explicitly requires model continuation receives request-local system/user guidance that it is not answer-bearing evidence and that the model must select an exposed follow-up read tool from returned locators/identifiers; the runtime does not select that tool for the model.
- A model-continuation obligation is sticky across assistant-only drafts and citation repair turns; it clears only after the model emits a tool step whose results do not renew the continuation requirement.
- Model-visible `internet.search` discovery rows contain only selection metadata (title, URL, retrieval time), not claim-bearing snippets; factual web evidence comes from `internet.fetch`.
- While discovery-only Internet citation evidence is pending, terminal drafts remain ineligible even after a prior citation-correction draft fails; request-local correction continues subject to the bounded invalid-draft recovery limit and the existing request deadline. The runtime does not select or execute the follow-up tool for the model.
- Repeated invalid terminal drafts while discovery-only Internet citation evidence is pending are bounded; Orion fails the citation contract instead of spinning until the request deadline.
- Secrets do not appear in model-visible tool arguments/results unless intentionally processed as user data by a defined safe path.

## Models

- Provider-neutral runtime works with at least the primary configured OpenAI-compatible/local model path.
- Tool calling survives provider adapter normalization.
- Oversized current user input is never silently truncated; an irreducible request outside the configured local safety bound fails explicitly.
- No legacy ACTION/ACTION_DETAIL/OBSERVATION/FEEDBACK protocol is required.

## Operations

- `./install.sh` behavior documented under `docs/operations/` matches the actual script.
- The current packaged local install/start path works without requiring Docker.
- SQLite/session/project/document persistence survives a normal Orion process restart according to the current storage design.
- Operations lifecycle checks exercise the current local process/package behavior.
- Logs make model → tool → result → model flow traceable.
- Docker/Compose behavior is an acceptance requirement only if/when a Docker deployment path is implemented and documented as current.

## Documentation consistency

- Architecture/product docs may describe target state and must label future behavior as such.
- Accepted ADRs, architecture rules, current-state docs, and executable behavior must not contradict the direct first-turn registry contract.
- Operations docs describing current commands/configuration must be checked against current scripts/config files.
- No stale current-state claim may be retained merely because it existed in an older deployment.
- `knowledge.search.document_ids` is an optional narrowing filter, not a discovery prerequisite: the model must omit it unless exact visible document IDs are available; an out-of-scope filter remains source-free and returns recoverable feedback so the model can retry with valid visible IDs or, when the user did not require a specific document, search the current scope without the filter.
