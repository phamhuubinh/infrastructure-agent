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

Default mode (deterministic pipeline):

```
python -m src.cli
```

Legacy ReAct mode (optional):

```
python -m src.cli --legacy
```

## Documentation

The `docs/` directory is the **Source of Truth** for architectural and design documentation.
