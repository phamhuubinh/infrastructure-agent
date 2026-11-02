# Orion — yêu cầu refactor toàn bộ từ thiết kế trắng

Ngày: 29/10/2026. Đây là **yêu cầu triển khai**, không phải đề xuất để hỏi duyệt
từng bước. Bản này hợp nhất yêu cầu người dùng và thay thế các ràng buộc lịch sử
mâu thuẫn. Tài liệu hiện hữu/source là tư liệu để đánh giá, không phải thứ bắt
buộc phải giữ.

## 1. Kết quả cần giao

Làm lại Orion thành trợ lý kỹ thuật dùng được thực tế, một model/runtime chính,
gọi tool, skill và MCP; thao tác Windows/Linux bằng lệnh. Hoàn thành thiết kế
trước, sau đó sửa toàn bộ code, test, cấu hình, dữ liệu mẫu, CLI/UI, app, build,
release và tài liệu theo thiết kế đó.

Bắt buộc có:

1. Ba nhà cung cấp AI: **DeepSeek, Claude, OpenAI**; adapter tách biệt khỏi core.
2. Windows app thực sự; hỗ trợ backend local được quản lý và kết nối server từ xa.
3. Linux server/CLI headless; dùng chat/lệnh/quản trị bằng terminal, không bắt mở web.
4. Android và iOS app làm client tới cùng runtime; giao diện dùng được trên điện thoại.
5. Web client tiếp tục dùng cùng API; Chat, Projects, Remote Control là các scope
   sản phẩm, không phải các agent AI khác nhau.
6. Windows/Linux command runner thật: PowerShell/cmd/sh/bash qua worker/SSH.
7. Skill loader/catalog và skill thực tế, MCP client và công cụ quản trị tương ứng.
8. CI, đóng gói, cài đặt, update, kiểm thử và hướng dẫn khớp artifact thực tế.

Không làm adapter chuyên biệt Grafana/Zabbix hay mở thêm dự án monitoring.
Không mở rộng đợt này sang Gemini/Ollama hoặc “mọi API trên thế giới”.
Tính mở rộng là hợp đồng adapter có kiểm thử; không phải tuyên bố tương thích
mọi protocol/model/tính năng.

## 2. Tinh thần thiết kế trắng và quyền sửa/xóa

Phạm vi là **mọi file trong repo**: source, test, docs, scripts, manifests,
lockfiles, workflow, fixture, generated schema, assets và cấu hình mẫu.
Không chỉ sửa một vài module hay giữ test cũ vì chúng đang xanh.

Được phép tự quyết định giữ, viết lại, tách, di chuyển, thay thế hoặc xóa phần
không đúng thiết kế, thừa, không liên quan hoặc không còn caller. Không cần xin
phép lại cho việc xóa code/tài liệu/test cũ trong phạm vi refactor này.
Phải kiểm tra caller/import/entry point/generated references và ghi quyết định
vào bảng kiểm kê từng file trước khi loại bỏ. Không xóa chỉ dựa vào tên file.

“Tờ giấy trắng” áp dụng cho quyết định kiến trúc, không yêu cầu vứt bỏ implementation
đúng hoặc tái viết cơ học. Tái sử dụng chỉ khi có lý do và nghiệm thu mới.
Không mặc định giữ Python, framework, layout hay schema cũ vì lịch sử; các lựa
chọn mặc định trong thiết kế mới là quyết định thực dụng, có thể thay bằng ADR
có bằng chứng khi triển khai.

Không coi .git, credential thật, dữ liệu người dùng hoặc hệ điều hành máy host là
code thừa. Bảo toàn/migrate dữ liệu thực trước thay đổi; snapshot local changes
cần thiết trước khi thay thế. Không chạy lại lệnh format/phân vùng trong transcript.

## 3. Bộ tài liệu có thẩm quyền

Đọc theo thứ tự:

1. File yêu cầu này.
2. [Thiết kế đích](docs/refactor/DESIGN.md).
3. [Nhà cung cấp/API](docs/refactor/PROVIDERS.md).
4. [Công việc và phụ thuộc](docs/refactor/WORK_PLAN.md).
5. [Tiêu chí nghiệm thu](docs/refactor/ACCEPTANCE.md).
6. [Quy tắc tự triển khai](docs/refactor/AUTOMATION.md).
7. [Trạng thái máy đọc](docs/refactor/STATE.json) và
   [bảng duyệt từng file](docs/refactor/audit/FILE_REVIEW.csv).

Các ADR cũ chỉ còn hiệu lực ở phần không mâu thuẫn với bộ yêu cầu này. Khi sửa,
đồng bộ Product, architecture, operations, quickstart, AGENTS, example config và
test; không chồng thêm notice lên tài liệu trái ngược rồi coi là xong.

## 4. Quy trình bắt buộc

**Docs → contracts → implementation → verification → packaging → cleanup.**

- Kiểm kê toàn repo và kiểm tra từng file: vai trò, caller, đúng/sai thiết kế,
  quyết định giữ/sửa/xóa, nơi thay thế và bằng chứng.
- Viết xong thiết kế, contract, dependency/lifecycle và tiêu chí hoàn tất trước
  khi sửa runtime lớn; tự chốt lựa chọn thông thường, không chờ người dùng duyệt.
- Thực hiện các work item theo phụ thuộc; sau mỗi phần chạy kiểm tra có ý nghĩa,
  sửa lỗi và cập nhật trạng thái. Không dừng khi mới có scaffold/docs hoặc compile.
- Rà lại mọi file sau implementation, bao gồm dependency/lockfile/schema/workflow,
  import chết, code duplicate, telemetry/vendor hook, config/test không còn dùng.
- Build và smoke artifact đúng nền tảng; báo rõ phần nào chỉ có fixture, simulator,
  native runner, live API hoặc signing thật.

Kiểm kê hash/AST không đồng nghĩa đọc hiểu và kiểm toán ngữ nghĩa từng file.
R00 không được đánh dấu toàn bộ audit đã xong; R01/R19 phải đóng đủ mọi hàng
trong FILE_REVIEW.csv và chứng minh không sót file mới.

## 5. Tự động hóa tối đa

Khi thực hiện yêu cầu này, tự đọc tài liệu, chọn việc sẵn sàng, sửa, chạy kiểm tra,
chẩn đoán lỗi, sửa tiếp và nghiệm thu. Không hỏi lại các quyết định đã nằm trong
phạm vi: đổi cấu trúc repo, thay dependency, sửa schema/API/client, viết skill,
MCP, test, build, hoặc xóa phần cũ đã đối chiếu.

Không dùng “có thể làm tiếp”, “cần xác nhận kế hoạch” hay báo xong sau mỗi phase
để thay thế triển khai. Ghi checkpoint và tiếp tục phần còn làm được. Chỉ ghi
needs_external khi thật sự thiếu secret/tài khoản/hardware/runner không thể tự
cung cấp; tiếp tục mọi việc độc lập, không giả pass hoặc hỏi đi hỏi lại.

Quyền tự sửa repo không tự cấp quyền dùng tiền không giới hạn, tạo tài khoản,
phát hành store, force-push hay xóa dữ liệu hệ thống. Tách rõ tự động hóa phát triển
với quyền thực thi lệnh của sản phẩm Orion; không bỏ authentication/authorization
để làm demo chạy.

## 6. Định nghĩa hoàn tất

Chỉ kết luận refactor hoàn tất khi:

- mọi work item bắt buộc đã có bằng chứng Done, không che needs_external bằng Done;
- mọi file trong scope đã được duyệt/đối chiếu và không còn active path sai thiết kế;
- ba provider đi được cùng vòng model → tool → result → model;
- Windows app, Linux CLI/service, Android/iOS client build/smoke theo ma trận;
- command runner, skill loader/skills, MCP và các scope dữ liệu được kiểm thử;
- không còn executable Grafana/Zabbix path/dependency/config/test bắt buộc;
- artifact, version/source hash/checksum và tài liệu vận hành khớp thực tế;
- báo cáo cuối có diff phạm vi, task evidence, test/build results, artifact paths,
  dữ liệu đã migrate, giới hạn còn lại và trạng thái Git.

Việc viết bộ yêu cầu này không có nghĩa các app/adapter/runner đã triển khai.
Trạng thái thực tế phải đọc từ STATE.json và bằng chứng kiểm chứng, không suy
từ một mô tả hay issue đã đóng.
