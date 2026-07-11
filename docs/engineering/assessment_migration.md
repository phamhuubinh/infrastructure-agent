# Assessment Migration Guide

## Current State

- MockAssessmentAdapter is the default
- LLMAssessmentAdapter is available when `--server` is provided
- DeterministicAgent works with both

## Migrating from Mock to LLM

### Step 1: Configure servers.json

Ensure `servers.json` exists with your model endpoint.

### Step 2: Test with --server

```bash
python -m src.cli --server sv1
```

The CLI uses LLMAssessmentAdapter when `--server` is specified,
falling back to MockAssessmentAdapter when it is not.

### Step 3: Make LLM the Default

To change the default, update `runtime_factory.py`:

```python
# Change this condition in create_deterministic_agent():
if assessment_adapter is None:
    if server_name or model:
        # Use LLM
        ...
    else:
        # Use Mock (default)
        assessment_adapter = MockAssessmentAdapter()
```

To make LLM the default:

```python
if assessment_adapter is None:
    # Always try server config, fall back to mock
    try:
        assessment_adapter = _build_assessment_adapter(server_name, model)
    except (RuntimeError, FileNotFoundError):
        assessment_adapter = MockAssessmentAdapter()
```

## Backward Compatibility

- MockAssessmentAdapter remains available
- All existing tests continue to use Mock
- No investigation pipeline changes needed
- No EvidencePackage changes needed
