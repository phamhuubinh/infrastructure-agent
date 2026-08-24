# Acceptance criteria

The target is acceptable when these product invariants are demonstrated.

## Chat

- User can create/resume a conversation.
- Plain conversational prompts can answer without unnecessary tools.
- All registered tools are available automatically.
- There is no required tool picker.
- Model tool calls execute and results return to the same model loop.
- Multiple sequential tool calls work.

## Project

- Project conversation uses the same runtime as Chat.
- Active project metadata is present deterministically.
- Project documents form an additional project-scoped RAG source.
- Project A retrieval never leaks Project B data.
- All non-RAG tools remain available inside Project.
- There is no Project-specific tool picker.

## RAG/documents

- Upload → parse → index → ready lifecycle is explicit.
- Session attachments are retrievable in session scope.
- Project documents are retrievable in project scope.
- Exact document read works.
- Semantic retrieval works.
- Whole-document summarization is not limited to arbitrary top-k chunks.
- Cross-document comparison preserves source identity.
- Answers can surface document citations/source metadata.

## Tools

- Knowledge/RAG, calculator, Internet, Linux, Grafana, and Zabbix families can register through the same tool system.
- A new registered tool becomes model-visible without adding semantic router rules.
- Tool errors return explicitly to the model.
- Secrets do not appear in model-visible tool arguments/results unless the tool's legitimate output itself is non-secret data.

## Models

- Provider-neutral runtime works with at least the primary configured OpenAI-compatible/local model path.
- Tool calling survives provider adapter normalization.
- No legacy ACTION/ACTION_DETAIL/OBSERVATION/FEEDBACK protocol is required.

## Operations

- Local Docker install/start path works.
- Persistent project/session/document data survives normal container restart/rebuild.
- Logs make model → tool → result → model flow traceable.
