# Công việc triển khai Orion refactor

Đọc [yêu cầu](../../REFACTOR_REQUEST.md), [thiết kế](DESIGN.md),
[providers](PROVIDERS.md), [automation](AUTOMATION.md) và [acceptance](ACCEPTANCE.md).
Task chỉ Done khi có bằng chứng; STATE.json giữ dependencies/status/evidence.
R00 là đầu ra của lượt lập yêu cầu hiện tại. Các task implementation còn Todo,
không được đổi Done vì chỉ có scaffold/docs.

## R00 — Đặc tả và kiểm kê nền

Master request, design/providers/automation/acceptance, task graph, skill packages,
scanner và điểm vào AGENTS/README/context. Validate spec/skills/links/inventory.
Không coi đây là hoàn tất refactor.

## R01 — Audit ngữ nghĩa từng file

Đọc mọi source/docs/config/test/build/fixture/generated/asset trong inventory.
Ghi disposition/reason/callers/replacement/verification cho từng FILE_REVIEW.csv row.
Hash/grep/AST không thay semantic review. Bao gồm tracked/untracked/ignored/new files.
Private data chỉ metadata; .git không là code để xóa. R19 phải đối chiếu lại sau sửa.

Điểm đã thấy cần xử lý: provider_type khóa openai_compatible; fixed executors;
policy family hardcode; UI endpoint build-time; native apps chưa có; E5 installer
bắt provision; bun/npm lock trùng; lovable hook; CONTRIBUTING nói Docker không có.

## R02 — Core contracts và skeleton kiến trúc mới

Từ thiết kế chọn domain/module boundaries; schema DTO/events/ModelTurn/provider
state/tool scope/command/skill/MCP/version/config. Tách API khỏi core, sửa assumption
và architecture checks lỗi thời. Smoke cùng runtime model giả → tool → kết quả →
answer. Không chuyển nguyên kiến trúc lỗi vào folder mới rồi gọi refactor.

## R03 — Provider registry và adapter conformance

Profiles/capabilities/options/credential references; bỏ regex provider đơn.
Fixture HTTP/SSE cho stream/tools/errors/cancel/opaque state/no mutation replay.
Chỉ DeepSeek/Claude/OpenAI bắt buộc.

## R04 — DeepSeek

Adapter/profile/protocol và thinking/continuation đúng tài liệu. Stream/multi-tool
roundtrip, malformed/unsupported fields, usage/error. Live smoke thuộc R22,
không có key không cản Done phần implementation/conformance.

## R05 — Claude

Native Messages serialization/parser, blocks/tool_use/tool_result, argument deltas,
stop/usage/state. Không ép thành OpenAI Chat Completions.

## R06 — OpenAI

Native Responses typed events/function output; Chat Completions-compatible là path
riêng. Fixtures state/calls/cancel/schema/capability. Model ID theo config. Live smoke ba vendor tách R22–R24, không là
prerequisite của Done phần adapter khi fixture/conformance đã đạt.

## R07 — Data, scope, RAG và request lifecycle

Migrations/backup/export/import, history/Project/device isolation, retention/
credentials, context/provenance/citations/recovery. RAG/embeddings optional; không
ép mọi app/client tải E5. Không xóa dữ liệu thật để test xanh.

## R08 — Command service và portable worker

system.command.run/status/cancel, explicit capability, handle trước dispatch,
stdout/stderr/Unicode/cwd/pipes/exit state/output bound, process-tree timeout/Stop,
outcome_unknown/no replay. Temporary pairing/lease/cleanup/OS rights; native
Windows/Linux test fixtures và contract tests. Native artifact proof tách R25/R26;
R08 Done không tự chứng minh artifact/native execution đã đạt.

## R09 — SSH command transport

Tách SSH cần dùng khỏi mixed legacy infrastructure, cùng command contract/policy.
Server credentials/exact target/quoting, không chạy nhầm trên local control plane.
Remote termination không xác minh được phải báo unknown, không claim success.

## R10 — Skill loader/catalog và bundled workflows

Package/metadata/resources/version/trust, discovery/load/install/update/disable/
remove, bounded context/scopes, unavailable tool error. Viết/test windows-linux-ops,
project-research và mcp-workflows. Script qua policy. Development orion-refactor
không vào catalog sản phẩm. SKILL.md tồn tại chưa đủ Done.

## R11 — MCP

stdio/Streamable HTTP config/auth/revision negotiation/schema/discovery/call/error/
close/failed startup/reconnect, fake servers và permission tests. Snapshot version
không thay registry giữa request; reconnect không replay mutation. Không mặc định
đưa server prompts thành authority; ghi revisions thực sự hỗ trợ.

## R12 — API, native auth và shared generated SDK

Chat/projects/documents/profiles/skills/MCP/targets/commands/jobs/version/doctor
resources, normalized events, native access/refresh/enrollment/revoke và browser
cookie/CSRF/Origin. Không wildcard CORS/bỏ auth. Resume không duplicate mutation.

## R13 — Shared UI

Static React/TS, runtime server profiles, generated SDK, Chat/Projects/Remote
Control/Commands/Settings, sources/errors/approval/Stop/status, responsive/a11y.
Loại SSR/state duplicate/vendor hooks thừa. Không nhân đôi model/tool semantics.

## R14 — Linux CLI/service

Headless serve/chat/run --prompt-file/--json, stdin/stdout/stderr/exit codes/SIGINT,
profile/project/skill/mcp/target/command/status/cancel/doctor, local/remote.
Không bắt display/browser/Node/embedding nếu chưa dùng; clean install lifecycle.
R14 giao implementation/recipe/tests; native package gate tách R26.

## R15 — Windows app

Tauri trusted UI, managed bundled backend hoặc remote, single instance/readiness/
ports/auth/secure storage/clean shutdown, installer/portable/update/uninstall.
End user không cài Python/Node. R15 giao source/recipe/tests; native artifact
smoke là R25, không coi vite dev là app hoặc báo native pass từ code.

## R16 — Android

Shared client/SDK, secure auth/token/server profiles, file picker/keyboard/safe area/
background/network/reconnect/cancel. R16 giao source/recipe/tests; debug APK/emulator smoke tách R27 và signing R29.
Không bundle Python backend/OS shell worker hoặc provider key.

## R17 — iOS

R17 giao iOS source/config/client behavior và test definitions. macOS/Xcode
simulator build/test tách R28; signing tách R29. Thiếu Mac không cản Done
phần source/fixture nếu đúng hợp đồng, nhưng R28 vẫn needs_external và toàn scope
chưa hoàn tất; không dùng web build thay native nghiệm thu.

## R18 — Automation, CI, packaging và operation docs

Bootstrap/doctor/check/build entrypoints Windows/Linux, repo-local pinned toolchain,
generate SDK/schema, native matrix, mock providers/MCP thay live paid API trong CI,
version/source SHA/checksum, install/update/uninstall. Signing qua CI secrets.
Quickstart/config/troubleshooting dựa artifact thật, không mô tả flow chưa có.

## R19 — Cleanup và audit cuối

Loại monitoring adapters/registration/config/credentials/dependencies/tests/QA chuyên
biệt; giữ/tách SSH cần thiết trước khi xóa mixed module. Dead imports/entrypoints,
telemetry/vendor hooks, duplicate locks/docs/generated assets. Mọi current/deleted/
moved file có reason/replacement/verification; không mất ledger. Không legacy chạy
ngầm chỉ vì docs đã thêm banner.

## R20 — Core E2E/offline regression

Checks không cần external key/runner cho core/provider/tool/scope/data/command/
skill/MCP/API/clients/CLI, cùng các native checks đang khả dụng. Native delivery
proof bắt buộc tách R25–R28; R20 Done không giả các gate đó đã pass.
Sửa failure do refactor; không skip gate hoặc sửa expectation
chỉ để xanh. Verify startup/stream/long output hợp lý, ghi môi trường không chạy được.

## R21 — Báo cáo cuối và nghiệm thu toàn scope

Small live smoke ba provider, native/signing trên runner/secret thật khi có.
Không suy fixture thành live pass. Needs_external còn là chưa xong gate tương ứng.
Báo task/file coverage/tests/artifacts/migration/removed paths/Git state; chỉ full
Done khi mọi gate bắt buộc có evidence. Không tự public store submit ngoài quyền có.

## R22–R24 — Live API gates riêng

R22 DeepSeek, R23 Claude, R24 OpenAI: smoke nhỏ có key thật, model/tool loop/stream
và profile được ghi lại. Thiếu key chỉ chặn gate tương ứng, không chặn adapter
fixtures hoặc công việc khác. Không suy conformance thành live pass.

## R25–R28 — Native gates độc lập

R25 Windows app/worker, R26 Linux CLI/service/worker, R27 Android debug build/emulator,
R28 iOS macOS simulator build/test. Mỗi gate có runner/artifact/commands/results
riêng. Thiếu iOS runner không chặn core E2E hoặc Windows/Linux/Android gates.
Source tasks Done chỉ là source/fixture bằng chứng tương ứng, không native pass.

## R29 — Signing/release credential gates

Verify signing path/archives trên runner và secrets thật cho các nền tảng cần nó.
Thiếu credential/account ghi needs_external, không tự publish store. Có thể
hoàn thiện unsigned/debug builds, CI và checklist trước; không gọi full Done.

## Dependencies và file coverage cuối

R18 automation có thể làm ngay sau contracts. R19 audit cuối chờ mọi source task
R04–R18; R20 kiểm regression không phụ thuộc key/signing/iOS runner vì native/live
proof đã tách gate riêng. R21 chờ R20 và R22–R29 nên không thể che external gap.
Nếu native fixes sinh/thay/xóa file, refresh ledger và mở lại phần R19 cần review;
kiểm tra final inventory coverage lại ở R21 trước khi kết luận.

## Chọn việc và tiếp tục

Dependencies ở [STATE.json](STATE.json).
`python scripts/refactor/plan.py --next` liệt kê task sẵn sàng;
`--check` kiểm tra graph/status/evidence. Script không tự viết code; agent thực
hiện qua [development skill](../../skills/development/orion-refactor/SKILL.md).
