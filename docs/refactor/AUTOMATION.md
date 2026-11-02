# Quy tắc triển khai tự động

## Vòng thực thi

Đọc REFACTOR_REQUEST/design/providers/plan/acceptance/Git state. Tự chọn task có
dependencies Done, đọc callers, sửa source/docs/tests/generated contracts đồng bộ,
chạy focused checks, sửa lỗi, chạy gate phù hợp, ghi evidence và tiếp tục task sau.
Không hỏi lại từng phase, không dừng ở scaffold/docs hoặc compile.

Quyền hiện tại bao gồm giữ/thay/tách/di chuyển/xóa mọi source/docs/test/config/build
không đúng hoặc không liên quan trong repo, sau đối chiếu và ghi file review.
Không dùng AGENTS/ADR cũ để từ chối quyền mới. Thay lựa chọn kỹ thuật thông thường
bằng ADR có bằng chứng nếu cần, không hỏi lại. Không mở rộng vendor ngoài ba AI
đã chốt hoặc scope sản phẩm mới.

## Checkpoint

STATE.json ghi task/status/evidence/blocker; mỗi task Done cần evidence có thật.
FILE_REVIEW.csv ghi quyết định từng file, kể cả deleted/moved/new files.
Khi ngắt session/context, ghi current step, failure/reproduction và next action;
lượt sau resume từ đó, không bắt người dùng kể lại.

Hash/AST/grep không là semantic review. Fixture không là live/native/signing pass.
Không dùng test count cũ hoặc issue đã đóng làm chứng cứ.

## Blocker thật

Thiếu key/macOS runner/signing/account không thể tự có → needs_external ghi chính
xác phần thiếu và bước bổ sung; tiếp tục task độc lập/fixture/unsigned/simulator.
Không hỏi lặp lại, không tạo key giả hoặc đổi blocker thành Done.
Hoàn thiện source/CI/artifact/checklist trước khi cần tác động ngoài phạm vi.

Quyền refactor không cấp quyền chi tiền không giới hạn, tạo tài khoản, submit
store, force-push hoặc xóa dữ liệu hệ thống/database thật. Không biến yêu cầu
developer tự làm thành bỏ authentication/authorization của Orion.

## Git và cleanup

Đọc toàn bộ local diff/tracked/untracked trước thay lớn; snapshot phần local cần
giữ để recover. Không reset/clean/discard mù quáng, không rewrite history.
Có thể xóa code/docs/test cũ theo scope được cấp; kiểm tra caller/replacement và
ledger trước. Không chạy lệnh format/phân vùng trong lịch sử chat.

Lượt lập yêu cầu chưa commit/push. Publication theo quyền thực tế của phiên
triển khai, không suy từ câu chữ issue cũ; thiếu quyền public không cản sửa/test/
đóng gói local.

## Automation cần hiện thực

Một interface bootstrap/doctor/check/build/package hoạt động Windows/Linux;
toolchain/dependency locks; generated API SDK; provider/MCP fixture servers;
native CI matrix/artifact smoke/update/uninstall; task/review coverage checker;
log đủ debug không lộ secrets/opaque private state. Không paid API trong mỗi vòng
test. Các entrypoint chưa implement phải ghi Todo, không thêm command giả vào docs.

Không tạo agent AI riêng trong sản phẩm. Skill là task guidance, job là lifecycle
thực thi cùng runtime. Auto command mode vẫn có scope/capability/OS boundary,
không phải quyền toàn hệ thống vì developer đã được phép refactor.
