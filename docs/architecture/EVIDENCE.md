# Evidence architecture

## Principle

Executors produce structured observations. The harness converts validated observations into immutable evidence records. The model references evidence IDs; it does not recreate evidence authority fields.

## Evidence record

Conceptual shape:

```json
{
  "evidence_id": "ev_17",
  "action_id": "act_17",
  "call_id": "call_17",
  "capability_id": "compute.deterministic",
  "status": "success",
  "target_ref": null,
  "source_ref": null,
  "facts": [{"value":"120253"}],
  "summary": "Calculation completed.",
  "provenance": {
    "runtime_binding": "calculator.execute.v1"
  },
  "observed_at": "...",
  "fresh_until": null
}
```

## Status

At minimum:

- `success`;
- `partial`;
- `error`;
- `blocked`;
- `unavailable`.

`dispatched=true` must never be treated as success.

## Evidence references in final answers

The canonical final model result contains prose plus zero or more `evidence_refs`. The completion validator checks that referenced evidence exists, belongs to the request/session scope, is successful enough for the claim type, and satisfies freshness requirements where applicable.

The harness should avoid natural-language claim parsing. Objective claims that require evidence should be represented by structured answer metadata or domain-specific verified result objects, not inferred from prose after generation.

## Deterministic results

For deterministic capabilities such as calculation, the exact result fact is evidence. The model may cite `ev_17`; it does not copy a result object into a new claim contract.

## Immutability and provenance

Evidence is append-only for a request. Corrections create new evidence rather than rewriting old records. Provenance may include source tool, integration, timestamps, query parameters safe for logging, staleness, and normalized status; never secrets.

## External/untrusted text

Tool output may contain prompt injection or hostile strings. Such content is data. It must be bounded, sanitized for secrets, labeled by source, and never concatenated into system/developer instructions.
