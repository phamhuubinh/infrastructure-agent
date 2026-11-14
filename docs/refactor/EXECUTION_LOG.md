# Nhật ký thực thi Orion

## 2026-11-13 · R21–R29 · Windows

- Kiểm tra working tree sạch, fetch `origin` và tạo `codex/orion-windows-acceptance` từ `3f2b624`. Giữ nhánh R27 tại `2828337` và checkpoint `ba6f7b2`.
- Graphify AST cục bộ cập nhật thành công và báo không có thay đổi. Đối chiếu kết quả với smoke desktop, workflow iOS và ma trận nghiệm thu.
- R26 và R27 giữ trạng thái Done. Đối chiếu log R27 hiện có tại `F:/Orion-toolchains/r16-android/r27-whpx-smoke-retry.log` với các bước enrollment, khôi phục route và Stop, resume SSE đúng cursor, DocumentsUI và thu hồi phiên khi đăng xuất.
- R22–R24 cần cấu hình live từ chủ sở hữu. R25 cần installer desktop đã phát hành trước đó. GitHub Releases API trả về v0.1.2 với archive máy chủ Linux, archive máy chủ Windows và checksums. R28 cần macOS/Xcode để chạy các luồng iOS còn thiếu. R29 cần credential ký và ứng viên đã ký để xác minh.
- R21: `python scripts/refactor/inventory.py --check --require-final` đạt tại baseline với 635 tệp. Backend Ruff và build wheel đạt. Lệnh mypy mặc định chọn package cài sẵn và báo thiếu `py.typed`. Chạy lại trong `backend` với `MYPYPATH=src` và `python -m mypy src/orion` đạt trên 135 tệp.
- UI: `npm run lint`, `tsc --noEmit`, `npm test -- --run` (125/125) và `npm run build` đều đạt. Vite cảnh báo một số chunk vượt 500 kB sau minify.
- Backend: `python -m pytest backend/tests -q` thoát mã 0. Bộ test có các ca skip theo môi trường và cảnh báo ZIP trùng tên từ fixture kiểm thử archive.
- Log local: `release-work/windows-acceptance-python.log`, `release-work/windows-acceptance-pytest.log`, `release-work/windows-acceptance-ui.log`.
- Checkpoint `b49644fc4e1d41df2043cdc4a0badd5ccffea5fd` đã push lên `origin/codex/orion-windows-acceptance`. `git ls-remote` xác nhận SHA. Lần commit đầu thiếu Git author nên đã dùng danh tính Codex của checkpoint trước qua cấu hình chỉ áp dụng cho lệnh commit.
- `plan.py --next` trả về danh sách sẵn sàng rỗng. R21 tiếp tục sau khi các điều kiện bên ngoài được đáp ứng.

## 2026-11-13 · R25 · Windows dùng cá nhân

- Build từ checkpoint `b220d42`. UI Vite và Tauri debug x64 đạt. Dùng Rust 1.99.1 GNU với `rust-lld` và `RUSTFLAGS=-Clink-self-contained=yes` để dùng CRT đồng bộ. Các lần trộn LLVM MinGW và CRT của Rust thiếu symbol khi link.
- Python 3.12.14 đi kèm runtime Codex tạo được EXE nhưng worker lỗi `FileNotFoundError` khi pairing và backend lỗi khi chat. Đóng gói lại bằng CPython 3.12.16 độc lập do uv quản lý. `test_headless_cli.py -k managed_serve` đạt 1 test và `portable_smoke.py` đạt pairing, file, command, cancel, disconnect, reconnect và revoke khi PATH/PYTHONPATH/PYTHONHOME trống.
- Bộ cài dùng cá nhân `release-work/r25-personal/Orion_0.1.3_x64-setup.exe`, SHA-256 `aab16883228655b7186ee85f786825c7ac678da765adc2096a8b037f6002bbbb`. Portable desktop nằm trong `release-work/r25-personal/desktop-portable`. Worker đã kiểm nằm trong `release-work/r25-personal/worker-standard`.
- Smoke trên bản cài candidate thực đạt WebView2, backend xác thực, chat fixture, Stop, đăng nhập/đăng xuất bằng mã, Credential Manager và đóng sạch. Log `release-work/r25-personal-desktop-candidate-smoke.log`.
- Kiểm thử nâng cấp giữa bản tự build R15 0.1.3 và NSIS 0.1.4 tạo cục bộ từ binary candidate. 0.1.4 là phiên bản của installer thử nghiệm. Kiểm tra phiên bản đăng ký, hash sidecar đã cài, giữ nguyên SQLite khi nâng cấp và gỡ, và mở lại với request completed/cancelled còn nguyên. Dữ liệu có sẵn được chuyển tạm rồi khôi phục. Log `release-work/r25-personal-desktop-install-smoke.log`.
- 45 test endpoint/SSH đạt. Worker WebSocketDisconnect lịch sử liên quan fixture ping timing. R27 giữ bằng chứng native về ADB và SSE cursor; lần lỗi đầu do fixture delta bị buffer, đã sửa ở `2828337`.
- Tiếp theo dùng provider profile và thiết bị do chủ sở hữu cấu hình. iOS, signing và nâng cấp từ release công khai được ghi riêng trong nghiệm thu toàn scope.

## 2026-11-14 · Windows Desktop 0.1.4 và Local System Tools

- Tái hiện trên 0.1.3 đã cài từ Start Menu và Desktop. Trace thấy Orion.exe CUI tạo conhost, Windows Terminal mở cửa sổ Orion, và sidecar có conhost riêng. 0.1.4 dùng GUI subsystem kể cả debug, giữ pipe và CREATE_NO_WINDOW cho sidecar, ghi stderr và lỗi startup vào desktop-backend.log.
- Windows managed backend đăng ký local:windows qua executor và CommandService hiện có. Quyền Read-only / Confirm / Auto và scope giữ nguyên. Tiến trình shell nền dùng Job Object và môi trường OS chọn lọc.
- Build Tauri và sidecar CPython 3.12.16, đóng gói một NSIS 0.1.4. SHA-256 F35FF8938236202CF2A1597826E8A4188B4A76D8854C1452DF840B7B8DC0F309. Nâng cấp tại chỗ từ 0.1.3, không gọi uninstaller. Backup dữ liệu và bản cài ở F:/Orion-recovery/desktop-before-0.1.4-20261114-074812.
- SQLite integrity_check đạt, hash DB không đổi trong installer. Sau chạy app, so khớp 2 cấu hình model gồm credential reference, 1 session, 4 requests và 14 timeline items gốc. Hồ sơ ban đầu có 0 Projects.
- Shortcut Start Menu và Desktop mở cửa sổ Orion, không ghi nhận Windows Terminal/OpenConsole. Sidecar có conhost không hiển thị trong trace Start Menu và thoát sạch cùng host. Chưa thử đăng xuất/đăng nhập lại Windows.
- AI live trên bản đã nâng cấp yêu cầu đúng lệnh PowerShell hostname tại local:windows, chờ xác nhận và trả kết quả khớp OS. Không pairing. Backend regression 48 pass, local executor 3 pass, frozen managed smoke 1 pass, UI 17 pass, mypy và TypeScript đạt. Log trong release-work/desktop-local-014, trace 0.1.3 trong release-work/orion-shortcut-trace.

- Kiểm tra live bổ sung trên 0.1.4: duyệt đúng script PowerShell để lấy hostname, phiên bản Windows, IPv4, DNS và gateway. Kết quả hostname và mạng khớp dữ liệu OS và phản hồi có phiên bản Windows. Sửa đường dẫn PowerShell trong script đối chiếu sau lần đầu lỗi harness. Log `release-work/desktop-local-014/live-network-retry.log`. Checkpoint mã `b70d121` đã được xác minh trên remote.
