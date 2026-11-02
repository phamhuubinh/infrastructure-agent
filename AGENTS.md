# Orion — hướng dẫn thực hiện trong repo

## Yêu cầu hiện hành và điểm vào

Giao tiếp tiếng Việt. Đọc theo thứ tự:

1. REFACTOR_REQUEST.md — yêu cầu refactor toàn bộ và quyền sửa/xóa.
2. docs/refactor/DESIGN.md và PROVIDERS.md — thiết kế, ba provider AI.
3. docs/refactor/WORK_PLAN.md, AUTOMATION.md, ACCEPTANCE.md và STATE.json.
4. docs/refactor/audit/FILE_REVIEW.csv và source/callers của task đang làm.

ADR 0018 xác lập bộ yêu cầu mới; spec này thay yêu cầu cũ ở phần mâu thuẫn.
Không giữ kiến trúc/test/file chỉ vì chúng đã tồn tại. Khi chỉ được yêu cầu viết/
review bộ yêu cầu, giao đặc tả và trạng thái thật; không đánh dấu implementation
Done. Khi triển khai, thực hiện tới nghiệm thu, không dừng xin duyệt từng phase.

## Quyền refactor và trách nhiệm

Người dùng đã cho phép làm lại từ thiết kế trắng, kiểm tra mọi file, tự thay/tách/
di chuyển/xóa source/docs/test/config/build không đúng hoặc không liên quan.
Không cần hỏi lại cleanup/thiết kế kỹ thuật thông thường trong phạm vi này.
Trước xóa, kiểm tra callers/entrypoints/generated references, ghi reason/
replacement/verification. Bảo toàn record cho file đã xóa và local changes cần
recover. Không reset/clean/rewrite history để che diff.

Quyền trên không biến .git/credentials/dữ liệu thật/hệ điều hành thành code thừa.
Không chạy lại lệnh format/phân vùng trong transcript. Không tự phát hành public,
submit store hoặc chi tiền không giới hạn. Chưa có yêu cầu commit/push trong lượt
lập bộ đặc tả; publication theo quyền thực tế của phiên triển khai.

## Thiết kế đích

- Một ChatRuntime chính, Projects là context/docs/history, máy đích là worker/
  connection, không agent AI riêng.
- DeepSeek, Claude, OpenAI; provider-neutral adapters/capabilities/state, không ép
  mọi API thành OpenAI-compatible. Model ID từ cấu hình.
- Tool definitions từ canonical registry; expose valid schemas on the first model turn
  khi capability/profile hỗ trợ, không semantic pre-router/tool picker.
  Không giả hỗ trợ feature provider không có; schema visibility không cấp quyền.
- Windows app, Linux headless CLI/service, web, Android/iOS clients dùng chung
  API/SDK/runtime; mobile không là Python backend hay OS shell worker.
- PowerShell/cmd/sh/bash qua system.command.run/status/cancel. Run mutation-capable,
  không keyword/model read-only classifier. Scope/capability/OS rights vẫn kiểm tra;
  confirm bind payload, auto không vượt policy; scheduler read_only.
- Skill loader/catalog/lifecycle và bundled skills phải được triển khai, không
  gọi SKILL.md tồn tại là runtime đã hỗ trợ. Skill không cấp quyền.
- MCP stdio/HTTP là external tool adapter cùng authorization/scope/registry.
- Bỏ dedicated monitoring adapters/code/config/test không còn liên quan.
- Current evidence/provenance, data isolation, private state/secret redaction,
  process-tree timeout/cancel, outcome_unknown và no mutation replay.

## Tự triển khai và kiểm chứng

Dùng scripts/refactor/inventory.py và plan.py để coverage/next work; chúng không
tự thực thi task. Development skill: skills/development/orion-refactor/SKILL.md.
Không đưa skill này vào product catalog; product skills ở skills/builtin.

Đọc toàn bộ file/callers, sửa đồng bộ code/docs/tests/generated artifacts, chạy
checks có ý nghĩa, ghi evidence/next action và tiếp tục. Thiếu key/runner/signing
thật → needs_external rõ và làm việc độc lập khác; không hỏi lặp hoặc giả pass.
Hash/AST không thay semantic review, fixture không là live/native/signing proof.
Không giữ test count cũ hoặc skip gate để báo xanh.

Tài liệu source operations cũ mô tả implementation trước refactor; dùng làm evidence
để migrate, không lấy nó phủ quyết yêu cầu mới.
