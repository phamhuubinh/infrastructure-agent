# GA1 verification evidence

Date: 2026-08-08

This record distinguishes deterministic repository verification from an
operator-specific remote search-provider run. No provider credential or model
endpoint is stored in this repository, so a live Internet benchmark must be
performed after deployment configuration; it is not represented here as a
false pass.

## Baseline captured before GA1 implementation

- The pre-GA1 targeted deterministic suite completed successfully with 171
  tests. The initial working tree was already dirty with the human-reviewed
  revised 193-question datasets; those changes were preserved.
- DR1 contracts remain protected by the pipeline/agent/tool/model/QA suite;
  unknown-target handling, read-only inspection, canonical evidence, and
  SSRF tests remain in that scope.

## Repository verification after implementation

The following completed successfully in the repository environment:

```bash
make typecheck
PYTHONPATH=. .venv/bin/pytest -q \
  tests/pipeline tests/agent tests/tool tests/model tests/qa \
  tests/backend tests/security tests/cli
git diff --check
.venv/bin/python scripts/qa/build_golden.py
```

Golden validation reports 45 curated cases (44 agent-scorable), including the
new stable/general, current/external, explicit URL, constrained-source, and
generation/mutation route expectations.

## Acceptance evidence by gate

| Gate | Evidence |
|---|---|
| Stable general knowledge does not collect tools | `tests/agent/test_deterministic_agent.py`, `tests/pipeline/test_request_semantics.py` |
| Current external request requires a bounded provider flow | `tests/pipeline/test_external_verification.py`, `tests/tool/test_internet_tool.py` |
| Explicit URL and SSRF protection fail closed | `tests/pipeline/test_external_verification.py`, `tests/tool/test_internet_tool.py` |
| Source constraints do not broaden | `tests/pipeline/test_source_constraints.py` |
| Unknown target has no localhost fallback | `tests/qa/test_transcript_regression.py` and existing target-resolver coverage |
| Generation allowed; mutation refused | `tests/agent/test_deterministic_agent.py`, `tests/pipeline/test_request_semantics.py` |
| Query/page failure is not presented as verified current data | `tests/pipeline/test_external_verification.py`, `tests/agent/test_deterministic_agent.py` |
| QA datasets and stage schema are preserved | `tests/qa/test_general_agent_question_sets.py`, `tests/qa/test_golden_schema.py` |

## Deployment follow-up

Before claiming a production external-information benchmark, configure the
provider documented in `docs/tools/internet.md`, run the revised DEFAULT 193
and the four session-preserving text suites against the deployed API, and save
the resulting credential-safe transcripts under ignored `artifacts/qa/`.
