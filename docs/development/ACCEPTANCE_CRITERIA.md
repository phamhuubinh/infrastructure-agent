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
- Whole-document summarization is not limited to arbitrary top-k chunks.
- Cross-document comparison preserves source identity.
- PDF page, DOCX section/paragraph/table, and XLSX sheet/row provenance can survive to citations/source metadata where available.
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
- A new registered tool becomes discoverable/model-visible without adding semantic router rules.
- Progressive exact-name exposure remains a model-context optimization over the canonical registry rather than an authorization or semantic-routing layer.
- Tool errors return explicitly to the model.
- Repeated recoverable failures terminate only after an unchanged normalized failure state demonstrates no progress; corrected arguments may continue.
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
- Accepted ADRs, architecture rules, current-state docs, and executable behavior must not contradict the progressive exposure contract.
- Operations docs describing current commands/configuration must be checked against current scripts/config files.
- No stale current-state claim may be retained merely because it existed in an older deployment.
