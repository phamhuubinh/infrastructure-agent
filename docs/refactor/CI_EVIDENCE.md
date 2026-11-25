# Kiểm thử và phát hành Local-first

Kiểm `git diff` với mốc đã nghiệm thu để chọn những thành phần bị ảnh hưởng. Mã dùng chung cần kiểm thử contract và một luồng tích hợp qua các consumer bị ảnh hưởng. Ghi commit, lệnh và kết quả local trước khi phát hành.

| Phạm vi thay đổi | Kiểm thử local |
| --- | --- |
| Backend hoặc Worker | Pytest theo module và một luồng runtime hoặc kết nối Worker tương ứng |
| React UI, API hoặc SDK dùng chung | Vitest theo component, TypeScript, kiểm OpenAPI/SDK, rồi smoke UI và backend cùng nhau |
| Native Android, iOS hoặc Windows | Build và smoke trên nền tảng bị ảnh hưởng |
| Quy trình phát hành Preview | Parse PowerShell/YAML, regression cập nhật và chạy đúng NSIS đã ký trên Windows cô lập |
| Tài liệu | Kiểm link, lệnh mẫu và đối chiếu các bước với script |

`CI`, `Windows CI` và `Release bundles` chỉ chạy khi được yêu cầu thủ công. Có thể dùng **Actions → Run workflow** cho các bộ kiểm hosted cần thiết. Preview dùng [quy trình build, ký và nghiệm thu local](PREVIEW_SIGNING.md). Stable vẫn dùng workflow phát hành thủ công trên `main`, với hai workflow CI thủ công đã đạt trên chính commit Stable.
