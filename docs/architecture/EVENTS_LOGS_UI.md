# Events, Logs, Metrics, and Agent Activity

One structured event/trace system is the target source for UI activity, request traces, CLI/debug diagnostics, and operational counters.

Keep event fields such as timestamp/request/chat/project/component/type/status/model/capability/tool/target/source/duration/error/safe message.

Metrics distinguish model calls, discovery, proposed/validated/rejected actions, dispatched execution, successful evidence, failed/blocked/unavailable observations, and accurately measurable active sessions.

`/api/metrics` projects a bounded, redacted production `AgentEvent` stream.
It counts dispatches from `tool.started`, successful tool/evidence outcomes only
from successful `tool.completed`/`evidence.created`, and failures separately.
It must never reconstruct events from trace summary counters.

Packaged Compose log following is an operator transport surface; it does not by itself satisfy unified structured-event semantics.

The request/session/runtime path emits correlated request, model, discovery,
authority, execution, evidence, and terminal events. See resolved F-15 in
`docs/development/IMPLEMENTATION_GAPS.md`.
