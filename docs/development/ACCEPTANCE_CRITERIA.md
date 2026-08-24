# Acceptance criteria

The target is acceptable when these product/runtime invariants are demonstrated.

## Chat

- User can create/resume a conversation.
- Plain conversational prompts can answer without unnecessary tools.
- All registered/configured tools are available automatically.
- There is no required tool picker.
- Model tool calls execute and results return to the same model loop.
- Multiple sequential tool calls work.

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

- Upload → parse → index → ready lifecycle is explicit.
- Session attachments are retrievable only in valid session scope.
- Project documents are retrievable only in active project scope.
- Exact document read works.
- Semantic retrieval works.
- Whole-document summarization is not limited to arbitrary top-k chunks.
- Cross-document comparison preserves source identity.
- Answers can surface document citations/source metadata.
- Deleted/tombstoned documents do not reappear in retrieval.

## Canonical contracts

- Provider responses normalize into one internal model-turn/tool-call contract.
- Every registered tool has one canonical name/schema/handler binding.
- Tool execution returns one canonical `ToolResult`/error shape.
- Session/project/attachment runtime scope is application-owned context.
- Document/source/retrieved-segment identities survive ingestion through citation.
- Provider-specific and tool-specific implementation objects do not leak into the core runtime.

## Tools

- Knowledge/RAG, calculator, Internet, Linux, Grafana, and Zabbix families can register through the same tool system.
- A new registered tool becomes model-visible without adding semantic router rules.
- Tool errors return explicitly to the model.
- Secrets do not appear in model-visible tool arguments/results unless intentionally processed as user data by a defined safe path.

## Models

- Provider-neutral runtime works with at least the primary configured OpenAI-compatible/local model path.
- Tool calling survives provider adapter normalization.
- No legacy ACTION/ACTION_DETAIL/OBSERVATION/FEEDBACK protocol is required.

## Operations

- `./install.sh` behavior documented under `docs/operations/` matches the actual script.
- Current Compose service names/ports documented under `docs/operations/` match `docker-compose.yml`.
- Local Docker install/start path works.
- Persistent project/session/document data survives normal container restart/rebuild according to current storage design.
- Logs make model → tool → result → model flow traceable.

## Documentation consistency

- Architecture/product docs may describe target state and must label it as such.
- Operations docs describing current commands/configuration must be checked against current scripts/Compose/config files.
- No stale current-state claim may be retained merely because it existed in an older deployment.
