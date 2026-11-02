# Model backends

Current target: DeepSeek, Claude and OpenAI through provider-neutral adapters.
[Provider specification](../refactor/PROVIDERS.md) and
[ADR 0018](../decisions/0018-clean-slate-cross-platform-refactor.md) supersede the
earlier single OpenAI-compatible target.

## Core contract

The runtime sends normalized system/conversation/tool definitions and receives
normalized stream events/turns. Vendor wire messages, stream deltas, opaque
continuation state and SDK objects remain behind adapters. A provider may require
state to survive a tool loop; keep it adapter-owned and separate from public
conversation/reasoning/log data.

Model profiles declare vendor, protocol, endpoint, model ID, credential reference,
capabilities, option schema and transport/context bounds. No vendor/model-name
heuristic substitutes for declared capabilities. Unsupported features return
explicit errors; no silent provider switch or fake tool support.

DeepSeek has its own tested profile/options; Claude uses native Messages;
OpenAI uses native Responses with a separate Chat Completions-compatible path.
The shared conformance suite covers tool roundtrip, stream reconstruction,
cancellation, errors/usage/state and no tool-mutation replay.

## Current source gap

The inspected source ModelSettings accepts only openai_compatible and bootstrap
chooses one OpenAICompatibleBackend calling /chat/completions. These facts do not
satisfy the new three-vendor target. R03–R06 in
[WORK_PLAN.md](../refactor/WORK_PLAN.md) implement and verify the changes.
