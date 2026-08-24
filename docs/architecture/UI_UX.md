# UI/UX architecture

## Operator mental model

The UI should make four states visually distinct:

1. model reasoning/output;
2. proposed tool action;
3. approval/authorization state;
4. execution/evidence result.

Never imply that model prose itself performed an action.

## Chat timeline

Render typed items:

- user message;
- assistant message;
- tool search/load;
- proposed action with capability/target/source/arguments safe summary;
- approval card;
- execution status;
- evidence/result card;
- terminal failure.

## Approval UX

An approval card must show the exact action scope the approval binds to. Changing scope requires a new approval. Cancel/deny performs no execution.

## Failure UX

Use specific deterministic states such as `permission_denied`, `approval_required`, `tool_not_exposed`, `invalid_arguments`, `executor_unavailable`, `no_progress`, and `model_failure`. Avoid generic healthy-looking answers after a failed action.

## Evidence UX

Users should be able to inspect evidence provenance and status without reading internal debug logs. Secret values and private model reasoning are never displayed.

## Settings

Model, target/source, permission, project, and security settings should expose semantic health and validation errors, not just connectivity flags.
