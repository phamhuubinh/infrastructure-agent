# ADR 0019 · Capability theo request và Internet có xác nhận

Ngày 18/11/2026. Yêu cầu nghiệm thu mới cho phép lazy tool exposure, thay phần yêu cầu gửi mọi schema ngay từ lượt đầu trong ADR 0018 và hướng dẫn cũ.

Model nhận `tools.enable` cùng catalog capability ngắn. Hội thoại thông thường trả lời trực tiếp. Khi cần dữ liệu hoặc thao tác, model chọn capability rồi nhận schema chuẩn từ registry. Trạng thái mở schema tách theo request và được giải phóng khi request kết thúc. Việc ghép/revoke endpoint được kiểm tra lại theo scope ở mỗi lượt model. Registry, validation, read-only/confirm/auto và authorization vẫn áp dụng tại execution boundary. Kết quả mở schema chỉ là metadata. Retry cùng trạng thái không tiến triển dùng recovery tracker có giới hạn hiện có.

Các adapter/fixture kiểm tra wire protocol có thể chọn eager mode bằng `lazy_tools=False`. Mặc định ứng dụng dùng lazy mode. Benchmark dùng cả hai chế độ trên cùng composition root, profile và dữ liệu tổng hợp, ghi đủ usage, invocation và thời gian.

Windows Settings cung cấp bật/tắt truy cập Internet qua Funnel. Giá trị mới mặc định tắt. Chỉ native Desktop có RPC thay đổi mạng. Bật yêu cầu Host Mode, backend loopback đúng cổng, Owner MFA sẵn sàng, HTTPS/auth/Origin probe đạt, route Serve khớp chính xác và người dùng xác nhận công khai URL. Schema/tool loading không cấp quyền gọi RPC này.

Thao tác chỉ thay route HTTPS của Orion trên cổng được Funnel hỗ trợ. Cấu hình xung đột bị từ chối. Tắt Internet dùng Serve riêng tư trên cùng upstream, giữ các route khác. Khởi động ứng dụng chỉ kiểm tra trạng thái Funnel đã tồn tại, không tự gọi lệnh bật công khai. Lỗi sau mutation phải hiển thị và cho phép kiểm tra/tắt lại từ trạng thái thực.

TLS, public DNS và quyền Funnel do Tailscale cung cấp. Owner password/TOTP, cookie, exact Origin, native bearer/enrollment, Worker credential, mutation policy và Stop/revoke do Orion kiểm tra. Client chỉ dùng HTTPS/WSS và SDK thông thường. Máy cần thao tác trực tiếp chạy Worker có quyền riêng.

Các test tự động chỉ lập kế hoạch hoặc dùng fixture. Bật Funnel trên máy đang dùng, đăng nhập Owner thật và kiểm tra từ thiết bị ngoài tailnet là `PENDING_MANUAL`.

Tham khảo tài liệu chính thức [Tailscale Funnel](https://tailscale.com/docs/features/tailscale-funnel) và CLI `tailscale funnel --help` trên máy. CLI Serve/Funnel được kiểm tra ở chế độ đọc trong phiên triển khai.
