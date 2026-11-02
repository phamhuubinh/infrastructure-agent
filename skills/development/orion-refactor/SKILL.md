---
name: orion-refactor
description: Thực hiện yêu cầu refactor toàn bộ Orion theo bộ đặc tả và task graph trong repo; dùng khi triển khai hoặc tiếp tục đợt làm lại này, không tự mở rộng một yêu cầu sửa tính năng thông thường thành rebuild.
metadata:
  version: "1.0.0"
  audience: development
---

# Orion refactor

Tìm root bằng REFACTOR_REQUEST.md và Git checkout; không dựa vào tên thư mục cũ.
Đọc [master request](../../../REFACTOR_REQUEST.md),
[design](../../../docs/refactor/DESIGN.md),
[providers](../../../docs/refactor/PROVIDERS.md),
[work plan](../../../docs/refactor/WORK_PLAN.md),
[automation](../../../docs/refactor/AUTOMATION.md) và STATE.json.

Người dùng đã cấp quyền sửa/thay/xóa code/docs/test/config không còn đúng trong
repo, không phải quyền xóa credential/dữ liệu thật/hệ điều hành. Mọi file cần
disposition/reason/callers/replacement/verification; không dùng hash/grep như bằng
chứng semantic review hoàn tất. Giữ ledger của file đã xóa/di chuyển.

Khi được yêu cầu triển khai: chạy inventory --check và plan --next, chọn task có
prerequisite phù hợp, sửa đồng bộ, chạy checks thực tế, ghi evidence và tiếp tục.
Không dừng ở docs/scaffold; không hỏi lại routine choices/cleanup đã cho phép.
Nếu đang chỉ được yêu cầu viết/review đặc tả, giao đặc tả và giữ implementation
tasks Todo; không lặng lẽ bắt đầu một refactor khác.

Mốc sản phẩm: một runtime; DeepSeek/Claude/OpenAI; Windows app, Linux CLI/service,
Android/iOS clients; Windows/Linux commands; skills và MCP. Không phục hồi
monitoring adapters hay agent riêng theo Project/device.

Thiếu API key/macOS/signing thật → ghi needs_external và tiếp tục task/subtask
độc lập, không giả native/live pass. Tách quyền tự làm development khỏi mutation
mode/capability của Orion. Không tự publish/store submit hoặc rewrite Git history.

Dùng [acceptance](../../../docs/refactor/ACCEPTANCE.md) để chốt evidence. Sau thay
file refresh inventory, giữ record xóa; checkpoint state/failure/next action khi
ngắt turn/context. Báo kết quả theo task/file/tests/artifact/remaining gates.
