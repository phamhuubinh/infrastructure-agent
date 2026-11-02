# Architecture principles

1. **Conversation first.** Users state tasks; they do not orchestrate internal tools.
2. **One runtime.** Chat is the base; Project adds knowledge, Device Chat adds a bound endpoint, neither adds an AI agent.
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
17. **Worker is an executor.** Outbound model-free device connections enforce independent local policy; portable temporary mode is primary.
18. **Skill is guidance.** Reusable instructions use existing tools and never create authority or another runtime.
19. **Job is scheduling.** Background execution uses the same runtime with explicit scope and read-only scheduler policy.
20. **Evidence of implementation is separate.** Source presence, target documentation and closed issues do not establish a current test/release pass.
21. **Windows/Linux command focus.** Use the shared command contract instead of dedicated monitoring adapters; a shell requires explicit target capability and OS rights.
