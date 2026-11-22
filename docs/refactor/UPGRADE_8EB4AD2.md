# Nâng cấp Windows từ checkpoint 8eb4ad2

Kịch bản bảo trì hiện trỏ tới ứng viên sửa lỗi từ checkpoint `253dae0`.

- Bộ cài Windows x64 preview chưa ký tại `release-work/final-internet-batch/Orion_0.1.5_x64_final-preview-setup.exe`.
- SHA-256 `D617E63DD323199A9B454CA200C2F5A54967AC5C08F1C9257F5A9DD7EF018545`.
- Backup trực tuyến đã kiểm khôi phục tại `C:/Users/phamg/AppData/Local/OrionRecovery/before-upgrade-8eb4ad2-20261123-055027`. Kịch bản chụp lại một backup trong cửa sổ bảo trì trước cài.

Ứng viên đi cùng các bước [nghiệm thu Internet](INTERNET_ACCEPTANCE.md). Chi tiết benchmark và kiểm thử nằm trong [nhật ký](EXECUTION_LOG.md). Các backup trước được ghi ở các mục lịch sử của nhật ký.

## Cửa sổ bảo trì do chủ máy thực hiện

1. Chọn thời gian bảo trì, chờ request hoàn tất và dừng Host sạch bằng Orion. Xác nhận cả Orion và OrionBackend đã thoát. Đóng cửa sổ ứng dụng có thể để Host tiếp tục chạy.
2. Trong PowerShell dưới cùng Windows account, chạy lệnh dưới đây. Kịch bản kiểm cửa sổ bảo trì, tiến trình và cổng, checksum NSIS, tạo và kiểm backup mới, cài đè, rồi kiểm trước lần mở đầu.

```powershell
& F:/Orion/scripts/windows/upgrade-maintenance.ps1 -MaintenanceWindow
```

3. Khi kịch bản báo PASS, mở Orion. Kiểm tra Chat, Projects, model, lịch sử dài và vị trí cuộn. Chủ máy tự đăng nhập Owner trên Web qua URL tailnet và thử một chat mới giữa Desktop/Web. Kiểm tra Android/iOS sau enrollment trên thiết bị tương ứng. Các bước xác thực và nghiệm thu nền tảng này là `PENDING_MANUAL`.

Kịch bản dùng Python tại `F:/Orion-toolchains/refactor-python/Scripts/python.exe`. Có thể truyền `-Python` khi vị trí môi trường đã thay đổi. Kịch bản sử dụng payload đã giải nén tại `release-work/final-internet-batch/extracted` để đối chiếu các tệp được cài. Thao tác dừng Host do chủ máy thực hiện trước khi chạy kịch bản.

## Nghiệm thu tự động đã chuẩn bị

- `scripts/windows/upgrade_readiness.py --snapshot <thư-mục-cha>` chụp backup và diễn tập phục hồi vào thư mục mới. `--verify <backup>` kiểm hash, SQLite, dữ liệu Chat, Owner state và khả năng giải mã DPAPI.
- `scripts/windows/upgrade_acceptance.py --backup <backup-mới> --payload <payload>` đối chiếu các tệp ứng dụng, mọi hàng SQLite trước lần mở đầu, credential/blobs, cấu hình Host, autostart và Serve. Lệnh cần `PYTHONPATH=F:/Orion/backend/src`.
- Đã chạy bộ kiểm sau cài trên payload và SQLite sao chép vào thư mục cô lập. Ca đúng đạt, ca thay đổi Chat trên bản sao bị phát hiện. Đã kiểm guard khi thiếu `-MaintenanceWindow`. Các bài runtime, Chat UI, frozen smoke và benchmark còn bằng chứng hợp lệ tại nhật ký checkpoint trước.

Sau lần mở đầu, backend có thể ghi thêm trạng thái phiên hoặc dữ liệu. Bộ kiểm toàn bộ hàng dùng cho giai đoạn trước lần mở đầu, với snapshot vừa chụp trong cùng cửa sổ bảo trì.

## Rollback trong cửa sổ bảo trì

1. Dừng Host sạch. Giữ thêm snapshot hậu kiểm để bảo toàn dữ liệu phát sinh sau nâng cấp.
2. Khôi phục thư mục ứng dụng từ `installed` của backup bảo trì mới vào `%LOCALAPPDATA%/Orion`. Giữ nguyên backup và ứng dụng mới trong thư mục riêng nếu cần đối chiếu.
3. Nếu cần phục hồi SQLite, phục hồi cả thư mục dữ liệu từ `managed` của backup bảo trì mới khi toàn bộ tiến trình đã thoát. Di chuyển bộ DB/WAL/SHM hiện tại sang thư mục hậu kiểm trước khi đặt snapshot vào vị trí. Snapshot là SQLite độc lập, không ghép với WAL/SHM từ phiên cũ. Việc trở về snapshot làm mất các thay đổi sau thời điểm chụp trong dữ liệu đang dùng, vì vậy chủ máy cần xác nhận khi chọn bước này.
4. Khôi phục `desktop-host.reg` và đúng giá trị/type `OrionDesktopHost` từ `autostart.json` nếu chúng đã đổi. So sánh Serve với `tailscale-serve.json` và khôi phục mapping trong cửa sổ bảo trì nếu cần. Giữ Funnel tắt.
5. Mở lại ứng dụng và chủ máy tự kiểm tra đăng nhập Owner, model và lịch sử. Thực thi rollback trên hệ thống đang dùng mang trạng thái `PENDING_MANUAL`. Diễn tập hiện tại đã kiểm bản sao dữ liệu và credential.
