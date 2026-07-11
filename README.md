# Infrastructure Investigation Agent

A deterministic infrastructure investigation platform.

Evidence-driven investigation with AI-powered assessment.

## Architecture

```
User Request
    ↓
Intent Resolution (deterministic)
    ↓
Target Resolution (deterministic)
    ↓
Evidence Planning (deterministic)
    ↓
Capability Resolution (deterministic)
    ↓
Execution Planning (deterministic)
    ↓
Execution Graph (deterministic)
    ↓
Execution Runtime → KnowledgeTool → Child Tools
    ↓
Evidence Collection
    ↓
Assessment (AI)
    ↓
Response
```

The investigation pipeline is fully deterministic.
AI is used only for assessment.

## CLI Usage

```
python -m src.cli
```

## Documentation

The `docs/` directory is the **Source of Truth** for architectural and design documentation.
