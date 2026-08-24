# Cleanup targets

This file records categories that conflict with the target architecture. It is not an instruction to delete them automatically.

When implementation migration is explicitly requested and complete, remove code whose only purpose is:

- model-visible ACTION/ACTION_DETAIL/OBSERVATION/FEEDBACK workflow;
- semantic pre-routing/tool selection before the model;
- keyword/alias intent maps used to choose tools;
- per-chat manual tool selection;
- dynamic capability search/exposure;
- artificial per-request tool-call quota/budget orchestration;
- duplicate Chat and Project runtimes;
- provider-specific types inside core runtime;
- RAG automatically run before every model request;
- stale docs/tests that assert those behaviors.

Keep reusable parsers, RAG components, integration clients, tool implementations, stores, UI components, and tests when they fit the new contracts.
