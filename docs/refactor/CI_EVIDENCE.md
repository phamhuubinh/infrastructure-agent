# Chọn bài kiểm thử và xác minh kết quả phát hành

CI so sánh Git tree với các push đã hoàn tất trên cùng nhánh. Chỉ kế thừa một job đã thật sự chạy và thành công trong 24 giờ gần nhất. Commit so sánh phải là tổ tiên của SHA mới và diff phải chứng minh không có thay đổi trong đầu vào liên quan. Một job tương đương vừa thất bại buộc chạy lại. Kết quả `skipped` không được dùng làm nguồn bằng chứng.

| Thay đổi đã phân loại | Kiểm thử |
| --- | --- |
| Native Android hoặc cấu hình Android | Android |
| Kịch bản Android | Android và backend, vì backend chạy regression cho smoke script |
| Native iOS hoặc cấu hình iOS | iOS |
| Fixture cập nhật Windows | Windows và backend |
| Các tài liệu nâng cấp và sổ kiểm kê được liệt kê trong mã | Acceptance extra |
| Mã dùng chung, lockfile, cấu hình CI, hoặc đường dẫn chưa được phân loại | Toàn bộ |

Job `plan` ghi SHA và job ID của nguồn bằng chứng. PR từ nhánh có push CI dùng lại kết quả push khi Git tree của merge result trùng toàn bộ với head, đồng thời chờ cùng bộ kiểm đạt. Nếu Git tree khác hoặc không so sánh được, PR chạy các job riêng. `main` luôn chạy đủ bộ.

Preview xác minh riêng nhóm Windows/backend/Worker/UI/acceptance và nhóm Android/iOS. Mỗi job vẫn cần kết quả push thành công trên SHA phát hành hoặc bằng chứng tương thích được gate kiểm lại qua GitHub API. Job hiện tại thất bại sẽ chặn phát hành. Preview chỉ tạo NSIS mới khi Windows có đầu vào thay đổi so với Preview đã phát hành hoặc khi thiếu mốc có thể xác minh. Stable yêu cầu toàn bộ job push thành công trên đúng SHA và giữ các bài nghiệm thu release riêng.

Bằng chứng này xác minh đầu vào được quản lý bằng Git. Runner và dịch vụ bên ngoài vẫn có thể thay đổi. Giới hạn thời gian và đường dẫn mặc định chạy toàn bộ giúp tránh dùng lại kết quả quá cũ. Khi sửa cấu hình job hoặc công cụ build, commit đó sẽ chạy lại các job. Quy trình ký, xác minh đúng NSIS, sao lưu và rollback vẫn bắt buộc mỗi khi đóng gói.
