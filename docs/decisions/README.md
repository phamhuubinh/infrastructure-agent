# Architecture decisions

[ADR 0018](0018-clean-slate-cross-platform-refactor.md) defines the current
clean-slate/multiplatform/three-provider refactor. Prior decisions remain inputs
only where compatible with the master request.

[ADR 0016](0016-single-runtime-redesign.md) consolidates the product boundary;
[ADR 0017](0017-windows-linux-command-focus.md) amends OS scope to Windows/Linux
commands and retires dedicated monitoring adapters.
Compatible earlier decisions remain authoritative for their detailed contracts.

| ADR | Decision |
| --- | --- |
| [0001](0001-local-first.md) | Local-first |
| [0002](0002-chat-project-one-runtime.md) | One Chat/Project runtime, extended to Device Chat by 0015/0016 |
| [0003](0003-model-driven-auto-tools.md) | Model-driven automatic tools |
| [0004](0004-project-adds-rag-source.md) | Project adds a scoped knowledge source |
| [0005](0005-no-manual-tool-picker.md) | No manual tool picker |
| [0006](0006-no-semantic-pre-router.md) | No semantic pre-router |
| [0007](0007-all-registered-tools-available.md) | All registered schemas from the first model turn; supersedes former progressive exposure |
| [0008](0008-provider-neutral-model-backend.md) | Provider-neutral backend |
| [0009](0009-canonical-runtime-contracts.md) | Canonical runtime contracts |
| [0010](0010-project-scope-is-runtime-bound.md) | Server-owned Project scope |
| [0011](0011-infrastructure-mutation-contracts.md) | Historical monitoring/no-shell scope superseded by 0017; compatible target/mutation lifecycle retained |
| [0012](0012-request-deadline-progress-terminal-semantics.md) | Deadlines, progress and terminal semantics |
| [0013](0013-production-mutation-authorization.md) | Server mutation ceiling; absent-allowlist rule superseded by 0014 |
| [0014](0014-conversation-mutation-permissions.md) | Conversation read_only/confirm/auto, exact-call approval |
| [0015](0015-paired-endpoint-execution.md) | Outbound model-free portable/remembered workers and endpoint-bound Device Chat |
| [0016](0016-single-runtime-redesign.md) | Single-runtime redesign, tool/skill distinction and backlog reset |
| [0017](0017-windows-linux-command-focus.md) | Windows/Linux commands, no dedicated monitoring adapters; replaces generic-shell ban |
| [0018](0018-clean-slate-cross-platform-refactor.md) | Clean-slate whole-repo refactor, DeepSeek/Claude/OpenAI and cross-platform apps |

Do not interpret historical superseded paragraphs as current requirements. Do not
turn issue closure into verification evidence. A change to these principles should
be explicit rather than introduced indirectly through implementation convenience.
