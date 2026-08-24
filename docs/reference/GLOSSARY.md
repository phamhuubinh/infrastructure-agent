# Glossary

**Chat** — Orion's base conversational workspace/runtime.

**Project** — Chat plus persistent project metadata and a project-scoped knowledge/RAG source.

**Session** — persisted conversation identity and timeline.

**Attachment** — file associated with a session/current message.

**Project document** — durable document owned by a project.

**Knowledge source** — a retrieval scope such as a session or project.

**RAG** — retrieval-augmented generation; in Orion it is a model-usable knowledge tool/source, not an always-on pre-model stage.

**Tool** — model-visible callable capability with a name, description, input schema, and Orion handler.

**Registered tool** — a successfully registered/configured tool that is available automatically to the model.

**ToolCall** — model request to execute a registered tool.

**ToolResult** — structured success/error returned by Orion to the model after a ToolCall.

**Tool registry** — source of truth for model-visible tools.

**Tool runner** — dispatches validated ToolCalls to handlers.

**ModelBackend** — provider-neutral model invocation interface.

**Provider adapter** — converts Orion messages/tools to/from provider-native formats.

**Context builder** — assembles deterministic session/project/current context for a model call.

**Semantic pre-router** — a forbidden target pattern where Orion tries to decide user intent/tool before the model using heuristics/classifiers.

**Local-first** — Orion's application services and data are designed to run locally by default; external model/tool integrations are optional.

**Automatic tool use** — no user tool picker; model selects the tool, Orion executes it.

**Project source** — RAG source containing only one project's documents.

**Session source** — RAG source containing session/chat attachments.
