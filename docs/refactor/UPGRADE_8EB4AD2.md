# Nâng cấp Windows từ checkpoint 8eb4ad2

Quy trình hiện hành nằm ở mục [Preview và Stable](#preview-và-stable). Chỉ dùng bộ cài đã ký từ quy trình phát hành để cài bootstrap. Các đường dẫn checkpoint `5a9e1aa` dưới đây là bằng chứng nghiệm thu lịch sử.

- Bộ cài Windows x64 preview chưa ký tại `release-work/mobile-runtime-5a9e1aa/Orion_0.1.5_x64_mobile-runtime-preview-setup.exe`.
- SHA-256 `8E753FD7182142039CBAC474DBECAECAC14C9D94E444F286F917794AE6635982`.
- Backup trực tuyến đã kiểm khôi phục tại `C:/Users/phamg/AppData/Local/OrionRecovery/before-upgrade-8eb4ad2-20261123-205410`. Kịch bản chụp lại một backup trong cửa sổ bảo trì trước cài.

Ứng viên đi cùng các bước [nghiệm thu Internet](INTERNET_ACCEPTANCE.md). Chi tiết benchmark và kiểm thử nằm trong [nhật ký](EXECUTION_LOG.md). Các backup trước được ghi ở các mục lịch sử của nhật ký.

## Nghiệm thu tại cửa sổ bảo trì

1. Chọn thời gian bảo trì, đợi các request hoàn tất và ghi nhận cấu hình Serve/Funnel. Với bootstrap, tạo và xác minh backup mới dưới cùng Windows account, dừng Host sạch, sau đó chạy bộ cài đã ký trong môi trường đã kiểm. Đóng cửa sổ ứng dụng có thể để Host tiếp tục chạy.
2. Sau khi cập nhật, mở Orion và kiểm tra Chat, Projects, model, lịch sử dài và vị trí cuộn. Chủ máy tự đăng nhập Owner trên Web qua URL đang dùng, thử tạo Chat hai chiều, rồi mở phiên cũ và xác nhận thứ tự Gần đây. Kiểm tra menu, lịch sử, bảng hoạt động và composer trên Chrome Android và Safari iPhone. Chạy chẩn đoán PowerShell chỉ đọc ở chế độ Confirm, xác nhận một lần và đối chiếu kết quả. Các bước trên Host thật là `PENDING_MANUAL`.

## Nghiệm thu tự động đã chuẩn bị

- `scripts/windows/upgrade_readiness.py --snapshot <thư-mục-cha>` chụp backup và diễn tập phục hồi vào thư mục mới. `--verify <backup>` kiểm hash, SQLite, dữ liệu Chat, Owner state và khả năng giải mã DPAPI.
- Khi chỉ sao lưu trực tuyến, thêm `--online-only` để ghi nhận cấu hình Serve/Funnel đang chạy. Kịch bản cài bảo trì dùng chế độ mặc định.
- `scripts/windows/upgrade_acceptance.py --backup <backup-mới> --payload <payload>` đối chiếu các tệp ứng dụng, mọi hàng SQLite trước lần mở đầu, credential/blobs, cấu hình Host, autostart và Serve. Lệnh cần `PYTHONPATH=F:/Orion/backend/src`.
- Đã chạy bộ kiểm sau cài trên payload và SQLite sao chép vào thư mục cô lập. Ca đúng đạt, ca thay đổi Chat trên bản sao bị phát hiện. Đã kiểm guard khi thiếu `-MaintenanceWindow`. Các bài runtime, Chat UI, frozen smoke và benchmark còn bằng chứng hợp lệ tại nhật ký checkpoint trước.

Sau lần mở đầu, backend có thể ghi thêm trạng thái phiên hoặc dữ liệu. Bộ kiểm toàn bộ hàng dùng cho giai đoạn trước lần mở đầu, với snapshot vừa chụp trong cùng cửa sổ bảo trì.

## Rollback trong cửa sổ bảo trì

1. Dừng Host sạch. Giữ thêm snapshot hậu kiểm để bảo toàn dữ liệu phát sinh sau nâng cấp.
2. Khôi phục thư mục ứng dụng từ `installed` của backup bảo trì mới vào `%LOCALAPPDATA%/Orion`. Giữ nguyên backup và ứng dụng mới trong thư mục riêng nếu cần đối chiếu.
3. Nếu cần phục hồi SQLite, phục hồi cả thư mục dữ liệu từ `managed` của backup bảo trì mới khi toàn bộ tiến trình đã thoát. Di chuyển bộ DB/WAL/SHM hiện tại sang thư mục hậu kiểm trước khi đặt snapshot vào vị trí. Snapshot là SQLite độc lập, không ghép với WAL/SHM từ phiên cũ. Việc trở về snapshot làm mất các thay đổi sau thời điểm chụp trong dữ liệu đang dùng, vì vậy chủ máy cần xác nhận khi chọn bước này.
4. Khôi phục `desktop-host.reg` và đúng giá trị/type `OrionDesktopHost` từ `autostart.json` nếu chúng đã đổi. So sánh Serve/Funnel với `tailscale-serve.json` và giữ cấu hình ghi trong backup bảo trì.
5. Mở lại ứng dụng và chủ máy tự kiểm tra đăng nhập Owner, model và lịch sử. Thực thi rollback trên hệ thống đang dùng mang trạng thái `PENDING_MANUAL`. Diễn tập hiện tại đã kiểm bản sao dữ liệu và credential.

## Preview và Stable

- Preview dùng [quy trình phát hành local](PREVIEW_SIGNING.md) và tag `orion-preview-vX.Y.Z`. Stable dùng workflow thủ công từ `main` và tag `vX.Y.Z`. Hai kênh dùng chung thứ tự tăng phiên bản.
- Preview phải qua Authenticode, SHA-256, phiên bản và cả hai ca cài/khôi phục trong Windows cô lập trước khi đăng Release. Chứng chỉ Preview là chứng chỉ đã thiết lập. Stable vẫn dùng môi trường ký riêng.

## Cập nhật ngay và khôi phục

Windows Desktop tự kiểm kênh đã chọn. Chủ máy bấm **Cập nhật ngay** trên thông báo hoặc trong Cài đặt và xác nhận hộp thoại bảo trì. Web và Mobile nhận thông báo bản Host qua API dùng chung. Updater tự cài cho bản Windows cài ở vị trí mặc định `%LOCALAPPDATA%/Orion`.

Orion xác minh chữ ký, digest và phiên bản NSIS trước khi dừng. Host bận sẽ từ chối. Sau khi xác nhận và đóng sidecar sạch, updater sao lưu, kiểm lại snapshot và cài. Bản mới khởi động trong chế độ bảo trì, chỉ cho phép kiểm tra sức khỏe qua kết nối cục bộ riêng. Sau khi sidecar và WebView2 sẵn sàng, updater mở quyền truy cập. Nếu cài hoặc kiểm tra thất bại, updater khôi phục bản cài và SQLite/DPAPI từ snapshot đã kiểm chứng trước khi mở lại Orion.

Nếu gặp `Manual recovery required` tại `%LOCALAPPDATA%/io.orion.desktop/update-*/outcome.txt`, dùng `snapshot.json` bên cạnh để xác định bản sao trong `OrionRecovery`. Giữ Host dừng sạch, khôi phục theo mục Rollback và giữ các thư mục `.failed-update-*` để đối chiếu. Chỉ gỡ dấu `%LOCALAPPDATA%/io.orion.desktop/update-active.txt` sau khi xác nhận dữ liệu và bản cài đã phục hồi. Updater giữ nguyên cấu hình Host/Funnel.
