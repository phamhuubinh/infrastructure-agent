# Thiết kế đích — Orion refactor

## 1. Phạm vi và lựa chọn mặc định

Một runtime chính với provider DeepSeek, Claude và OpenAI; các client dùng chung
API và dữ liệu. Windows/Linux là máy đích thực thi lệnh. Android/iOS là client
điều khiển, không được mô tả như worker OS hoặc nơi chạy Python/model inference.

Mặc định: Python service/core/worker, SQLite + blob storage, React/TypeScript SPA,
Tauri 2 shell cho Windows/Android/iOS, Linux CLI gọi application service hoặc API.
Đây là lựa chọn của thiết kế mới dựa trên tài nguyên hiện có, không phải nghĩa vụ
giữ code cũ. Thay lựa chọn chỉ khi có ADR/bằng chứng về packaging, bảo trì hoặc
khả năng đáp ứng nghiệm thu; không cần hỏi lại việc kỹ thuật thông thường.

## 2. Kiến trúc

```text
Windows app         Web SPA          Android/iOS app       Linux CLI
(local/remote)          │                 (remote)          (local/remote)
       └────────────────┴───────────────────┴──────────────────┘
                                  │
                     typed API / auth / event protocol
                                  │
                         application services
                                  │
                             ChatRuntime
                ┌─────────────────┼────────────────────┐
                │                 │                    │
          Context + scope    Provider adapter     ToolRunner / registry
          Project/history    DeepSeek            ├── Knowledge/RAG / web / calculator
          skill guidance     Claude              ├── skill resource lifecycle
          provenance         OpenAI              ├── MCP proxies
                                                 └── system.command.*
                                                          │
                                             worker / configured SSH
                                                          │
                                                   Windows / Linux
```

Không có runtime riêng cho Project/device/provider; model profile chọn adapter
cho request. Không tạo semantic pre-router hay AI agent cho từng máy/công việc.
Schema đến từ canonical registry, quyền thực thi được kiểm tra riêng.

## 3. Ranh giới module

- Domain/contracts: Session, Project, Device, RuntimeScope, Request, ModelTurn,
  ToolDefinition, ToolCall/Result, SourceRef, SkillPackage, ModelProfile, Command.
- Runtime: model loop, context/provenance, cancellation, terminal state/recovery.
- Providers: map wire protocol/stream/tool-call/continuation state, không lộ SDK
  object hoặc vendor condition vào runtime.
- Tools: registry/schema/dispatch/permissions, read/mutation metadata.
- Skills: package/catalog/loader/resources/version/trust; không cấp quyền mới.
- MCP: connection/auth/discovery/schema/lifecycle, tools vào registry chung.
- Targets/commands: machine identity, worker/SSH transport, process lifecycle.
- Data: repository interfaces, SQLite/blob/index, migrations/export/retention.
- API: DTO/events/auth/resources, shared generated client SDK.
- Clients: shared UI/API client và platform bridge mỏng; không chứa logic model
  hoặc tự thực thi shell trên phone/WebView.
- Operations: doctor/bootstrap/verify/build/package, một nguồn version/config.

Có thể đổi physical layout nhưng không đổi trách nhiệm hoặc nhân đôi semantics.
Chọn một package manager cho TS; lock dependencies reproducibly.

## 4. Sản phẩm và dữ liệu

Điều hướng Chat | Projects | Remote Control, thêm Settings cho provider/server/
skill/MCP/connection ở cấp cấu hình, không biến thành tool picker mỗi câu hỏi.

Chat có history/attachment riêng. Project bổ sung instructions/docs/history theo
scope. Device Chat có history/mutation mode riêng và endpoint binding server-owned,
không kế thừa tài liệu Project hoặc Chat khác. Remote workspace ưu tiên Chat,
Commands, Connection; view desktop/files/process/browser cũ chỉ giữ khi còn giá trị
và không làm chậm đường command chính.

Scope chứa principal/workspace/session/project/endpoint/attachment khi hợp lệ.
Model hoặc client payload không tự đổi authority. Hiển thị tên thân thiện nhưng
server resolve opaque ID. Secrets ở backend/OS keystore, không ở prompt, URL,
ordinary log hoặc localStorage.

## 5. Provider và context

Ba provider bắt buộc theo [PROVIDERS.md](PROVIDERS.md). Profile gồm provider/
protocol/base URL/model ID/credential reference/capabilities/timeout và các option
có schema. Không ép tất cả qua Chat Completions, không hardcode model alias/giá.

Một normalized model turn/event protocol dùng cho mọi client. Phân biệt output
hiển thị, tool arguments, usage, stop/error, provider continuation/opaque state.
Giữ state vendor bắt buộc qua tool loop trong adapter-owned envelope; không lấy
private reasoning làm public chat/diagnostic hay lời giải thích của Orion.

Context luôn giữ đúng yêu cầu người dùng, scope metadata, history hợp lệ và current
ToolResults. RAG được truy xuất qua tool khi cần, không pipeline bắt buộc trước
mọi request. Không thêm lượt model tóm tắt/planner không cần thiết.
Capability không hỗ trợ phải báo rõ, không gửi tham số không hợp lệ hoặc tự đổi
provider/model để làm được tác vụ.

## 6. Windows/Linux commands

Dùng [system.command.run/status/cancel](../architecture/SYSTEM_COMMANDS.md) làm
contract chung. Windows: PowerShell/cmd; Linux: sh/bash, worker hoặc SSH đã cấu
hình. Command payload gồm máy đích, shell, command/script, cwd, timeout/output
bound; có stdout/stderr/exit state/duration/truncation.

Generic run là mutation. read_only/scheduler chặn; confirm bind exact payload;
auto chịu explicit capability và OS rights. Không phân loại read-only bằng regex/
model tự khai, không bắt allowlist từng chuỗi lệnh. cwd/root filter không phải
sandbox cho arbitrary shell. Không tự nâng quyền.

Server tạo command handle trước dispatch, bind scope; timeout/Stop xử lý process
tree và báo trạng thái quan sát được. Disconnect sau dispatch là outcome_unknown
nếu chưa xác định; không replay command. Partial output không được hiểu là zero/
empty/success. Audit giữ metadata/hash an toàn; raw output/script theo retention
rõ, mặc định transient hiện tại.

## 7. Skill thực sự

Viết loader/validator/catalog, không chỉ tạo SKILL.md rồi báo xong. Format package:
SKILL.md với name/description, metadata version/scope/required capabilities; optional
references/scripts/assets. Ràng buộc paths/resources/symlink/size/dependency rõ.

Bundled skills do repo quản lý; user/project skills là nguồn được cấu hình rõ.
Explicit invocation hoặc model lựa chọn từ catalog bounded; không thêm AI planner.
Không tự coi webpage/upload/MCP prompt là skill trusted. Project skill không chui
vào Device Chat. Script trong skill phải đi qua command/tool authorization.

Đợt đầu có windows-linux-ops, project-research và mcp-workflows cùng fixture/tests.
Skill cài/update/disable/remove, version pin và unknown capability có error rõ.
Development skill orion-refactor thuộc quy trình làm repo, không tự đưa vào
product catalog. Các package mẫu chưa chứng minh loader đã chạy.

## 8. MCP

Orion là MCP client/host: stdio và Streamable HTTP, cấu hình server/tools/
credential references, lifecycle startup/shutdown/failed connection, schema và
protocol negotiation theo revisions hỗ trợ có fixture. Không hứa mọi revision.

Map tool vào cùng registry/read-mutation policy. Reconnect không replay mutation.
Catalog refresh phải tạo snapshot/version nhất quán, không thay registry giữa
request. Không đưa server instructions/prompts vào system authority mặc định.
Resource retrieval nếu thực hiện phải qua scoped tool với provenance.

Có doctor/list/connect/disconnect/test tools và fake stdio/HTTP servers cho CI.
Không bắt triển khai Orion như MCP server hoặc hỗ trợ mọi SaaS connector trong
đợt này; chỉ thêm khi có mục đích rõ được yêu cầu.

## 9. Clients và xác thực

| Client | Runtime placement | Giao hàng |
| --- | --- | --- |
| Windows | Managed local backend hoặc server remote | App thật, self-contained runtime, installer/portable và lifecycle sạch |
| Linux | Service headless và CLI | serve/chat/run/profile/project/skill/mcp/target/command/doctor |
| Android | Remote client | Adaptive UI, APK debug + AAB release path |
| iOS | Remote client | Adaptive UI, simulator build/test + signed archive path |
| Web | Remote/local browser client | Static SPA dùng chung typed SDK/events |

Windows shell chỉ load trusted bundled UI; backend sidecar có token/IPC/loopback
auth và clean shutdown, không duplicate service hoặc zombie process.
Browser dùng cookie/Origin/CSRF đúng boundary. Native client có enrollment/login,
short-lived access/refresh, revoke/logout/expiry, token ở OS secure storage.
Không mở wildcard CORS, bỏ Origin check hoặc nhét provider key vào mobile bundle.

Mobile xử lý safe area/keyboard/file picker, foreground/background, đổi mạng,
reconnect/resume/read status và accessibility; không replay mutation. Offline
state rõ; không giả chạy inference khi mất server. Push notification không bắt
buộc để hoàn tất scope hiện tại.

Linux CLI thật, không chỉ launcher mở browser: stdin/prompt-file, streaming,
--json, exit codes, stdout/stderr, SIGINT, status/cancel và no-display install.
CLI/server không cần Node/WebView hoặc embedding model nếu chưa dùng feature đó.

## 10. Data, dependencies và cleanup

Thiết kế migration/import/export/backup trước schema breaking. Không tự xóa dữ
liệu người dùng để test xanh. Optional RAG/embedding không thành prerequisite của
mọi app/client/CLI. Tách optional dependency/features cần thiết; build artifacts
không mang secret/cache/profile/screenshot/test reports.

Xóa executable monitoring registration/adapters/config/credential examples/
dependency/tests không liên quan, nhưng không xóa SSH nằm chung file trước khi
tách callers. Rà telemetry/vendor hooks, dead modules, duplicate lockfiles và
generated artifacts. Mỗi file phải có disposition và verification.

## 11. Build và vận hành tự động

Một bootstrap/doctor/check/build interface chạy trên Windows/Linux; setup repo-local
toolchain/dependency, generate contracts, run gates, build artifacts có source SHA/
version/checksum và smoke cài-chạy-update-gỡ. CI matrix Windows/Linux/macOS/Android/
iOS không dùng live paid API cho test thường xuyên.

Windows end user không cài Python/Node. Linux headless không phụ thuộc display.
iOS build cần macOS/Xcode; Android cần SDK/NDK/JDK. Missing runner/signing/account
phải ghi needs_external chứ không giả nghiệm thu nền tảng. Hoàn thiện source/CI/
simulator/debug artifact độc lập trước khi chờ secret phát hành.

## 12. Nguồn kiểm chứng lựa chọn nền tảng

Tauri yêu cầu frontend static thay vì SSR: [frontend](https://v2.tauri.app/start/frontend/).
Điều kiện native toolchain và iOS macOS/Xcode:
[prerequisites](https://v2.tauri.app/start/prerequisites/).
Desktop backend sidecar:
[external binaries](https://v2.tauri.app/develop/sidecar/).
Các ràng buộc trên là giới hạn nền tảng, không phải lý do bỏ mobile khỏi kế hoạch.
