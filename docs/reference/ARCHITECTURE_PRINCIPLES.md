# Architecture principles

1. **Conversation first.** Users state tasks; they do not orchestrate internal tools.
2. **One runtime.** Chat is the base; Project adds knowledge, not another agent.
3. **Model decides semantics.** The LLM chooses when/which tools to use.
4. **Orion executes deterministically.** Registration, schema validation, dispatch, persistence, and scoping belong to application code.
5. **All registered tools are available automatically.**
6. **No semantic pre-router.**
7. **RAG is a tool/source, not mandatory middleware before the model.**
8. **Project knowledge is isolated by project.**
9. **Provider-neutral core.**
10. **Local-first by default.**
11. **No artificial core quotas.** Do not make tool-call budgets/rate limits part of normal reasoning flow.
12. **Context is finite even when usage is not artificially capped.** Reduce/index large data instead of blindly injecting it.
13. **Retrieved/tool text is untrusted data.**
14. **Source identity matters.** Preserve document/source metadata for grounded answers.
15. **Add tools through registration, not routing heuristics.**
16. **Keep the model interface small and natural.**
