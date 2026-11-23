# Nghiệm thu Internet của Orion

Funnel mặc định tắt. Trong đợt triển khai, các thao tác trên Tailscale thật chỉ đọc trạng thái và trợ giúp CLI. Chủ máy cần thực hiện các bước mang trạng thái `PENDING_MANUAL` bên dưới sau khi nâng cấp trong cửa sổ bảo trì.

1. Sao lưu và kiểm rollback bằng kịch bản nâng cấp đã chuẩn bị. Chủ máy dừng Host sạch và cài ứng viên cuối cùng. Mở lại cùng Windows account để DPAPI tiếp tục giải mã được.
2. Trong Settings, xác nhận Host Mode và Serve riêng tư hoạt động, Owner đã có password và TOTP. Từ đây không cần PowerShell cho bật/tắt thông thường. Tailscale trên server cần được cài và đăng nhập sẵn, có HTTPS và quyền Funnel trong tailnet. Những bước thiết lập tài khoản/UAC phải do chủ máy thực hiện.
3. Đánh dấu xác nhận công khai URL, bấm “Bật truy cập qua Internet”. Lưu URL HTTPS được hiển thị. Trạng thái phải là Internet/Funnel và probe HTTPS/auth đạt. Kiểm tra từ mạng ngoài tailnet bằng Chrome/Edge trên máy không cài Tailscale. Chỉ health/login shell được truy cập trước xác thực; Chat, Projects, Models, Commands, pairing và Remote Control phải bị chặn.
4. Chủ máy tự đăng nhập với password và TOTP. Dùng một chat thử để kiểm tạo/đổi tên/xóa một lần giữa Web và Desktop, chat dài, thứ tự “Gần đây”, hai vị trí cuộn độc lập và draft cục bộ. Kiểm tra reconnect, offline rồi online và khởi động lại Host khi không có request đang chạy.
5. Trong chat thử, kiểm read-only chặn lệnh, confirm chỉ thực thi đúng payload đã duyệt, Stop dừng đúng request. Kiểm streaming/SSE qua Internet, logout rồi API bị chặn, revoke phiên native khiến refresh/stream reconnect bị từ chối. TOTP cũ không được tái sử dụng. Giữ recovery codes ở nơi riêng tư.
6. Android/iOS chỉ cài Orion, thêm cùng URL HTTPS, enrollment bằng Owner theo UI và kiểm SSE/reconnect/Stop trên thiết bị thật. Máy được điều khiển chỉ chạy Worker và ghép endpoint. Worker không có bản SQLite của Host. Linux Web/CLI dùng cùng API; nghiệm thu Linux trên máy tương ứng vẫn cần thực hiện.
7. Bấm “Tắt truy cập qua Internet”. Kiểm cấu hình về Serve riêng tư với cùng loopback upstream và các route khác còn nguyên. Máy ngoài tailnet phải mất khả năng kết nối, còn client trong tailnet tiếp tục dùng Serve. Kiểm lại sau khi đóng/mở ứng dụng để xác nhận không tự bật Funnel.

Các ca lỗi cần kiểm khi có môi trường thích hợp gồm mất kết nối Tailscale, quyền Funnel bị từ chối, HTTPS chưa sẵn sàng, UAC bị hủy, route khác chiếm cổng và Host chưa bật MFA. Orion phải báo lỗi, từ chối mutation xung đột và giữ dữ liệu ứng dụng.

Chưa có bằng chứng từ thiết bị thật ngoài tailnet thì public reachability, native mobile và chức năng trên bản đã cài tiếp tục là `PENDING_MANUAL`. Các test fixture về cookie/Origin/bearer/rate-limit/Worker và native command planning được ghi riêng trong `EXECUTION_LOG.md`.
