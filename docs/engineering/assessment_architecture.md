# Assessment Architecture

## Design Principles

1. **Single Responsibility** — LLM Client does HTTP only. Adapter orchestrates. PromptBuilder builds prompts. No overlap.
2. **Stateless** — Assessment has no memory. Every call is independent.
3. **Deterministic Pipeline** — Assessment never modifies the investigation pipeline.
4. **Fail Isolated** — Assessment failures never affect collected evidence.
5. **Configurable** — Model selection is configuration-driven, not code-driven.

## Component Responsibilities

| Component | Responsibility | Never |
|---|---|---|
| `LLMClient` | HTTP communication with OpenAI-compatible API | Prompt logic, parsing, assessment logic |
| `LLMAssessmentAdapter` | Orchestrate prompt → LLM → result | Investigation, tool execution |
| `PromptBuilderV2` | Build prompt from AssessmentRequest | HTTP calls, model selection |
| `AssessmentResult` | Typed output from assessment | Investigation data |
| `MockAssessmentAdapter` | Deterministic summary for tests | LLM calls, real assessment |

## Data Flow

```
AssessmentRequest
  │
  ▼
PromptBuilderV2.build_assessment_prompt()
  │
  ▼
JSON string (prompt)
  │
  ▼
LLMClient.generate(prompt)
  │
  ▼
Raw response string
  │
  ▼
LLMAssessmentAdapter
  └── wrap in AssessmentResult
  │
  ▼
AssessmentResult { content, model, tokens, latency }
```

## Dependency Graph

```
LLMAssessmentAdapter
  ├── AssessmentModelAdapter (implements)
  ├── LLMClient (calls)
  └── PromptBuilderV2 (calls for prompt construction)

LLMClient
  └── urllib.request (stdlib, no external deps)

RuntimeFactory
  ├── LLMAssessmentAdapter (when configured)
  └── MockAssessmentAdapter (default / when not configured)

CLI
  └── RuntimeFactory (never constructs adapters directly)
```

## Configuration

Configuration is loaded from `servers.json`:

```json
{
  "active_server": "default",
  "servers": {
    "default": {
      "provider": "openai",
      "base_url": "http://localhost:8000",
      "model": "gpt-4",
      "api_key": null
    }
  }
}
```

The CLI passes `--server` name to select a configuration.
RuntimeFactory reads the config and constructs the appropriate adapter.
