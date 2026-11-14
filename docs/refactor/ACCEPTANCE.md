# Ma trận nghiệm thu refactor

Done cần evidence đúng cấp: docs/source/fixture/live/simulator/native/signed không
thay thế lẫn nhau. Needs_external còn là gate chưa hoàn tất.

| Gate | Bằng chứng tối thiểu |
| --- | --- |
| Whole-repo review | Mọi current/deleted/moved/new file có disposition/reason/callers/replacement/verification, inventory không stale |
| Core | Một runtime, normalized turns/events, scope/cancellation/terminal/data lifecycle |
| Providers | DeepSeek/Claude/OpenAI cùng conformance tool loop/stream/errors/continuation/cancel |
| Data/RAG | Scope isolation, migration/restart/export/retention và optional embeddings |
| Commands | Windows/Linux native + SSH lifecycle, exact target, process/output bounds/no replay |
| Skills | Loader/catalog/lifecycle/trust/resources/scopes và bundled workflows chạy thật |
| MCP | stdio/HTTP negotiation/schema/auth/lifecycle/error/permissions/reconnect |
| Clients | Shared SDK/UI, browser/native auth, scopes/stream/reconnect/commands |
| Cleanup | Không active monitoring/dead vendor hooks/config/import/dependency, generated/locks đúng |
| Operations | Reproducible build/version/source hash/checksum, install/update/uninstall và docs khớp artifact |

## Providers

Với từng vendor: direct/stream/tool-call-result-answer, multiple/interleaved/
fragmented arguments, Unicode, invalid JSON, stop/usage, provider state, schema
projection, unsupported option/capability, errors/auth/timeout/drop/cancel.
Không sớm dispatch partial arguments hoặc replay tool mutation do provider retry.
Private protocol state/key không ra public answer/log. Responses parser riêng,
Claude native Messages, DeepSeek thinking/tool continuation có test theo docs.

Small live smoke khi có key; thiếu key không chặn fixtures/adapter/client work
nhưng live gate giữ needs_external. Không hardcode một model cũ để gọi hỗ trợ vendor.

## Commands

Exact machine/shell/cwd, paths có spaces, pipes/redirection, Unicode/stdout/stderr/
nonzero exit/duration/truncation/slow processes. read_only/scheduler deny raw run;
confirm bind full payload, auto chịu capability/OS rights. Không keyword/model
classifier và không fake shell sandbox bằng cwd/roots.

Handle trước dispatch, scoped status/cancel, process-tree cleanup/timeout,
disconnect uncertainty và no replay qua reconnect/restart. SSH text không chạy
trên local control-plane shell. Exit 0 không chứng minh task nghiệp vụ hoàn tất.
Portable temporary lease/exit dọn own state, không xóa security telemetry.

## Skills và MCP

Package metadata/version/trusted catalog/path/symlink/size/missing capability,
Project/device scope, lifecycle update/remove, scripts qua policy.
windows-linux-ops/project-research/mcp-workflows có workflow tests; development
skill không tự vào product catalog.

MCP fake stdio/HTTP có discovery/call/schema/error/auth/timeout/cancel/failed startup/
close/reconnect, locally assigned read/mutation kind, bounded output, versioned
registry snapshot. Remote prompt/resource không tự thành authority. Protocol
revision mismatch phải báo đúng.

## Nghiệm thu sử dụng cá nhân

Orion phục vụ Helpdesk, System Administration và hỗ trợ từ xa trên thiết bị
thuộc quyền sở hữu hoặc được cấp quyền quản trị. Nghiệm thu sử dụng cá nhân
ưu tiên Windows, Linux và truy cập bằng trình duyệt hoặc Android. Giữ đầy đủ
yêu cầu về quyền, bảo mật, chức năng và kiểm thử trong các luồng này.

Bằng chứng gồm cài đặt và vận hành ứng dụng thật, AI runtime, đăng nhập và
kết nối, command/Stop, SSH, worker, khởi động lại và bảo toàn dữ liệu khi
nâng cấp/gỡ. Có thể dùng installer unsigned hoặc portable. Khi chưa có
installer desktop công khai đời trước, ghi rõ nguồn và phiên bản của hai
bản tự build dùng để kiểm tra nâng cấp. Kiểm thử bằng fixture được ghi
riêng với kết quả provider live.

iOS native, store và signing thương mại thuộc các gate riêng. R21 tiếp tục
theo dõi nghiệm thu toàn scope và bằng chứng còn thiếu.

## Native delivery

| Target | Build/smoke bắt buộc | Gate thêm |
| --- | --- | --- |
| Windows app | Native package install/start/local+remote, bundled backend lifecycle/auth, command/Stop, update/uninstall | Signing khi có credential |
| Linux CLI/service | Headless clean install, serve/chat/run JSON/stdin, SIGINT/status/cancel, no display/Node baseline | Package lifecycle theo docs |
| Windows/Linux worker | Self-contained portable pair/command/exit, process cleanup/OS rights | Exact version/source/checksum |
| Android | Debug APK + emulator smoke auth/stream/files/keyboard/background/reconnect | Signed AAB path |
| iOS | macOS/Xcode simulator build/tests, lifecycle/auth/reconnect | Signed archive/IPA path |
| Web | Static build/browser auth/Origin/CSRF/responsive shared scopes | Served bundle/API compatibility |

Mobile không bundle Python/OS worker/provider keys; token ở secure storage.
Windows trusted UI bridge không cấp native shell cho trang web ngoài.
Client đổi server/logout không rò history/credentials/command handles.

## Test/build integrity

CI pin toolchains/dependencies và không phụ thuộc paid API. Backend/client/CLI/
worker/provider/skill/MCP/data/package checks phù hợp đều chạy; ghi rõ native/live
checks không chạy được và lý do. Không skip test bắt buộc hoặc sửa expectation
chỉ để xanh. Có thể xóa/rewrite test cũ vì contract bị thay, phải thay bằng evidence
của intended behavior; không yêu cầu giữ test count lịch sử.

Không dùng text-match docs làm behavioral test. Audit all files là điều kiện bổ
sung, không thay quality/security/performance nghiệm thu.

## Báo cáo cuối

Task states/evidence, file review coverage, removed/moved paths/callers, test/build/
native/live results, artifact/version/hash, migration/user-data status, Git diff/
status và needs_external còn lại. Chỉ full Done khi các gate bắt buộc có evidence;
còn thiếu báo partial chính xác.
