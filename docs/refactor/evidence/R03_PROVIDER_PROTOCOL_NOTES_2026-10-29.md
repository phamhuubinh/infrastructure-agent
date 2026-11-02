# Official protocol checks for the upcoming provider work

Read official pages on 2026-10-29. This records protocol constraints for R03–R06,
not implemented adapters, conformance passes, live access or fixed model aliases.

- [OpenAI Responses migration](https://developers.openai.com/api/docs/guides/migrate-to-responses)
  and [function calling](https://developers.openai.com/api/docs/guides/function-calling):
  Responses function definitions differ from Chat Completions; outputs are typed
  items correlated by call_id. Retain reasoning/function-call/function-output
  items when replaying stateless context. Choose an explicit supported strictness
  strategy rather than treating Chat Completions schemas as native Responses.
- [DeepSeek thinking](https://api-docs.deepseek.com/guides/thinking_mode/): requests
  carrying tools require reasoning_content replay in subsequent requests,
  including earlier turns in the current documented example. R02's request-local
  envelope alone does not establish correctness for a later user request with
  historical tool exchanges. R04 must implement a legal history/state strategy
  with privacy/retention tests; do not blindly drop required fields or claim a
  successful multi-request thinking conversation. Thinking option support is
  model/profile-specific; do not infer it from a model-name regex.
- [Claude streaming](https://platform.claude.com/docs/en/build-with-claude/streaming):
  native message/block start/delta/stop lifecycle differs from Chat Completions.
  Preserve thinking-block signatures as adapter-owned protocol state. Handle ping,
  errors, usage and partial JSON blocks without dispatching incomplete arguments.

Use raw HTTP/SSE fixtures with configured fake model IDs and sanitized state.
Real vendor model selection/credentials and small live smoke are separate gates.
