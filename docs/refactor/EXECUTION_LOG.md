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

## 2026-11-14 · Desktop Host Mode

- Host Mode opt-in dùng một backend managed và SQLite hiện có. Upstream cố định 127.0.0.1:61888, yêu cầu cấu hình origin HTTPS và Argon2id. Native Desktop giữ owner pipe, browser giữ cookie Secure và exact Origin, native remote giữ bearer enrollment/refresh/logout.
- Đóng cửa sổ giữ host chạy, mở shortcut hiện lại cửa sổ. Settings hiển thị origin và có Stop, tạo mã enrollment, liệt kê/thu hồi native sessions. Web bundle là resource NSIS.
- Backend 76 test đạt, sau đó bài Host Mode bổ sung enroll/refresh/logout cũng đạt. Windows cargo check và UI TypeScript đạt. Log backend/Rust tại release-work/desktop-host-backend.log và release-work/desktop-host-rust.log.
- Bản đang cài vẫn là 0.1.4. Còn kiểm thử native host lifecycle và HTTPS qua proxy thật, cấu hình bật/tắt và autostart trong UI, tunnel status, đóng gói worker xác minh, và nghiệm thu trước nâng cấp.

### Windows Host Settings và gói Worker 0.1.5

- Host Mode lưu cấu hình theo tài khoản Windows, tùy chọn chạy khi đăng nhập và áp dụng bằng khởi động lại ứng dụng. Backend vẫn do một tiến trình Desktop quản lý và dùng thư mục dữ liệu hiện có.
- Thêm phân phối Worker local qua route owner, xác minh hash trước khi gửi. Công cụ staging yêu cầu cùng phiên bản và commit nguồn sạch.
- Tailscale Serve phù hợp với truy cập cá nhân qua tailnet. Máy hiện chưa có Tailscale hoặc cloudflared được kết nối. Serve trên Windows cần phiên Administrator và tailnet bật HTTPS. Cloudflare published application cần tài khoản và domain. Chưa xác minh truy cập từ ngoài máy.

- Checkpoint 26cdc21 đồng bộ phiên bản Worker và Desktop 0.1.5. Backend 21 test của nhóm artifact/managed/local commands đạt. Edge qua TLS loopback xác minh login, cookie Secure/HttpOnly/Strict, Origin, session dùng chung, native enroll/refresh/revoke, logout trả 204 và tài nguyên đã được bảo vệ lại. Harness phải reload để xác nhận màn hình đăng nhập. Log release-work/desktop-host-qa/loopback-https-probe.log.
- Build native 0.1.5 đạt. Gói sidecar và Worker Windows được build lại từ cùng commit sau khi phát hiện Worker có version riêng. Chưa có bản Linux cùng commit. Windows hiện chưa có đăng nhập tailnet hay Cloudflare Tunnel; nghiệm thu Internet và Android từ thiết bị ngoài máy còn mở.

### 2026-11-15 · Windows 0.1.5 tại chỗ

- NSIS SHA-256 56D739B4DCA8EC705C33286F4E0A6A93290E8965C186E4B849162CEA61C483D1. Cài đè 0.1.4, hash SQLite không đổi trong quá trình cài. Sao lưu bản cài, registry uninstall và hồ sơ tại F:/Orion-recovery/desktop-before-0.1.5-20261114-190731.
- Trên bản cài, Host Mode kiểm thử bằng cấu hình tiến trình: health hoạt động sau khi đóng cửa sổ, chạy lại mở ứng dụng, Stop Host thoát. Shortcut Start Menu/Desktop không ghi nhận Windows Terminal/OpenConsole. Chưa thử tự chạy sau khi đăng nhập Windows.
- Frozen host phục vụ web shell, bảo vệ tài nguyên cần đăng nhập, công bố local:windows và tải Worker Windows 0.1.5 với SHA-256 khớp. Worker portable qua pairing/command/cancel/Exit/forget/reconnect. DeepSeek chạy PowerShell local có xác nhận sau nâng cấp. Log tại release-work/desktop-host-015-matched.
- Chưa có endpoint HTTPS ngoài máy: Tailscale/cloudflared chưa được cấu hình, phiên Windows không có quyền Administrator cho Serve và ADB không thấy thiết bị. Có kết quả TLS loopback ở bước trước. Bản Linux portable cùng phiên bản chưa đóng gói.

### 2026-11-15 · Tailscale Serve

- Settings Windows lấy upstream từ readiness của ManagedBackend, đối chiếu hostname, cổng HTTPS và root proxy từ Tailscale CLI, phân biệt cấu hình Funnel và kiểm tra JSON health qua TLS. Đo trên Orion 0.1.5 bản đã cài với Host Mode tắt: OrionBackend lắng nghe 127.0.0.1:63440 trong phiên thử. Cổng đó chỉ là quan sát của phiên.
- Windows Rust: 1 test phân biệt upstream chính xác, upstream sai và Funnel. TypeScript và 13 test UI đạt. Log release-work/tailscale/native-test.log và ui-test.log.
- Winget tải MSI Tailscale 1.104.7 từ nhà phát hành, xác minh checksum và Authenticode hợp lệ. Máy chưa có Tailscale, phiên không elevated. Đã chuyển bước UAC và đăng nhập tailnet cho chủ máy. Chưa chạy Serve thật, chưa bật Funnel, chưa đóng gói NSIS hay thay bản cài 0.1.5.

### 2026-11-15 · Owner Auth và QR Android

- Xác minh checkpoint 7a247af và sao lưu 25 file WIP ngoài repo, kiểm tra SHA-256 từng file.
- Windows Host Mode dùng Owner với Argon2id, TOTP chống tái sử dụng và recovery codes dạng hash. Thiết lập, đổi mật khẩu, thay 2FA và thu hồi phiên qua kênh Desktop xác thực. Luồng browser giữ exact Origin và cookie Secure. Chặn phiên native cũ trước khi 2FA được xác minh.
- QR Authenticator và QR ghép đôi Android có payload riêng. Mã enrollment hết hạn sau 5 phút, dùng một lần và yêu cầu mật khẩu cùng mã xác thực Owner khi redeem. Java scanner biên dịch được với Gradle x86_64 Debug. ADB chưa thấy thiết bị để thử camera, Keystore và reconnect.
- Các suite backend tập trung Auth/API/SSE/endpoints đạt, hai fixture native opt-in bị skip. UI 134 test đạt, TypeScript, ESLint, mypy, Ruff và Vite production build đạt. OpenAPI và SDK đã regen.
- Serve trỏ tới managed upstream và kiểm tra Owner trước khi kích hoạt trong Settings. CLI báo No serve config và phiên này không có quyền Administrator. Chưa bật Serve/Funnel hay nâng cấp bản cài Windows 0.1.5. Cần Windows build/smoke, Owner thao tác Authenticator và Android quét QR thật trước khi chốt nghiệm thu.

- Kiểm thử bản d75b258: 103 backend pass, 2 native opt-in skip, 134 UI pass. Windows Cargo check và Rust test chọn upstream/nhận diện Funnel đạt. Sidecar frozen và Edge qua HTTPS loopback đạt đăng nhập MFA, Secure cookie, native enrollment và revoke. Dùng hồ sơ SQLite thử nghiệm tách riêng. Log release-work/owner-auth-d75b258/owner-edge-smoke.log.
- Ứng viên NSIS Windows x64 chưa ký, SHA-256 61761ccbe6894c9e8b7a4926463985e6a717f33f85961aa7c903f000a0b63e50. Giải nén installer và đối chiếu 844 hash của sidecar, gồm Worker Windows cùng source SHA. Web shell khớp build Vite.
- APK Android ARM64 debug, SHA-256 72969755c93d115e83c3aae181715d656c2190d0637e6101988dc6988341db96. Gradle assemble thành công, apksigner xác minh chữ ký v2, manifest có CAMERA và ABI arm64-v8a. Chưa có thiết bị ADB để nghiệm thu camera, Keystore và reconnect. Hai gói và checksums tại release-work/owner-auth-d75b258. Bản cài 0.1.5 vẫn nguyên, Serve/Funnel chưa cấu hình. Cần Owner thiết lập thật, quyền Administrator cho Serve, và kiểm thử Android trước khi chốt nâng cấp.

### 2026-11-15 · Nghiệm thu preview trên Windows

- Xác minh SHA-256 NSIS và APK của d75b258. Sao lưu 924 file của bản cài và profile khi Orion dừng, đối chiếu từng hash và SQLite integrity_check. Backup có ACL riêng trong LocalAppData/OrionRecovery; giữ thông tin rollback registry của bản cài nếu key tồn tại.
- Diễn tập migration và phục hồi SQLite trên bản sao offline. Cài đè NSIS preview cùng phiên bản 0.1.5, exit 0. Hash SQLite giữ nguyên trước lần mở đầu. Orion.exe, sidecar và web shell khớp payload. Sau khi khởi động, bảng desktop_owner được tạo, SQLite qua integrity_check, và dòng trong sessions, timeline, model_configs, projects, request_events và document_ingestion_events khớp backup. Lịch sử chat hiển thị trên app đã cài.
- Mở Cài đặt > Kết nối server > Tài khoản & Bảo mật. Bàn giao biểu mẫu cho chủ máy tự tạo mật khẩu, quét Authenticator và lưu mã khôi phục. Backend chỉ lắng nghe loopback, Serve/Funnel chưa có cấu hình. ADB chưa thấy thiết bị. Web/DeepSeek/Local System Tools qua Serve và Android thật vẫn chờ nghiệm thu.

### 2026-11-15 · Remote Host từ Settings

- Trên preview 942721e, Tailscale Serve 443 có mapping tailnet-only tới 127.0.0.1:61888. HTTPS health 200, protected sessions 401, auth/session xác nhận MFA. POST rỗng/lỗi cú pháp với Origin đúng trả 400 và thiếu Origin trả 403. Lỗi hiển thị cũ không phân biệt HTTP và lỗi vận chuyển. Chưa tái hiện nguyên nhân thời điểm báo lỗi.
- Nút bật/tắt lưu Host Mode, origin và autostart sau khi Owner sẵn sàng. Cài Serve nền qua CLI và có UAC cho thao tác bị từ chối quyền. Mapping có trước không được nhận là của Orion. Khi tắt chỉ gỡ mapping Orion tạo nếu còn khớp. Funnel không tự bật.
- TypeScript, ESLint và 14 test UI tập trung đạt. 3 Rust tests đạt, gồm probe HTTPS trực tiếp trên Serve đang chạy và guard mapping xung đột. NSIS preview build lại Desktop/web và tái sử dụng backend/Worker d75b258.

- NSIS preview 464ee75 kiểm tra archive 926 file OK, SHA-256 dfa20bce5ddfbe19e4b5089c3e2ea7b1ace375264a85d5eb1084f0068e9684cb. Sao lưu 930 file khi Host dừng. Cài đè 0.1.5 exit 0, EXE khớp payload NSIS, backend binary giữ nguyên. SQLite hash giữ nguyên qua cài, integrity_check và nội dung hàng chat/model/Owner khớp backup sau restart.
- Nghiệm thu UI bản cài: Settings báo Online, Owner MFA. Bật từ Settings lưu autostart. Đóng cửa sổ giữ HTTPS 200, mở lại hiện cửa sổ. Tắt từ Settings khởi động lại chế độ local, HTTPS 502. Bật lại từ local tự khởi động Host Mode, HTTPS 200 và protected API 401. JSON Serve khớp trước và sau, tailnet-only; Orion không nhận mapping thủ công là của mình. Đã kiểm tra entry autostart; chưa reboot Windows.
- Đang chờ Owner đăng nhập thật từ trình duyệt ẩn danh tại URL tailnet. Kiểm tra login readiness không nhập hay ghi nhận bí mật. Chưa thử UAC hay tạo mới Serve trên cổng trống, vì máy đang có mapping của người dùng. Không bật Funnel, không phát hành stable.

### 2026-11-17 · DeepSeek credential DPAPI

- Profile DeepSeek đang active trỏ tới api.deepseek.com với model deepseek-flash; tham chiếu env:ORION_PROVIDER_KEY. Windows User có biến này. Chỉ ghi nhận hiện diện.
- Route cập nhật credential giới hạn Windows Desktop qua managed token. Nhập key từ HKCU Environment, mã hoá DPAPI, giải mã/so sánh rồi cập nhật credential_ref bằng CAS. Giữ biến User, model ID, endpoint, reasoning và các thuộc tính khác. Settings có nút nhập và ô API key mới cho hồ sơ typed.
- Trên fixture chạy từ source, Windows trusted route trả 204, xác minh DPAPI đạt, và DeepSeek live streaming hoàn tất. EXE đang cài tái hiện request.failed trên fixture đã có credential DPAPI. Log cũ chỉ ghi lỗi chung. Thêm phân loại thiếu credential, HTTP, timeout, transport/stream, và loại/vị trí exception nội bộ. Đóng gói sidecar bằng Python 3.12 độc lập để kiểm tra đúng PHIÊN BẢN EXE trước khi cài.
- Backend tập trung 73 pass, 1 skip. TypeScript/ESLint, 19 test bridge/SDK, OpenAPI và SDK validation đạt. Cần xác minh gói nội bộ và Desktop/Web sau cài đè.

- SHA Python DLL của sidecar cũ khớp Python bundled Codex. Sidecar mới build bằng CPython 3.12 độc lập; frozen fixture mới pass 204 import, DPAPI và DeepSeek chat streaming, khi biến key không có trong process test. Log release-work/deepseek-dpapi/frozen-deepseek.log. Fixture Web HTTPS loopback dùng Edge, MFA thử nghiệm và chat DeepSeek mới pass. Teardown Windows khoá SQLite tạm thời, dữ liệu fixture đã dọn sau khi process thoát.
- NSIS preview 2427f8b, SHA-256 c091283d4cef47a1132f00c73ba018e2ff79ee5c1d976f89d733788728765b9c, archive 926 file OK. Backup 931 file với ACL riêng; cài đè và xác minh hash sidecar mới, SQLite không đổi qua installer.
- Nhập key từ nút Settings trong app đã cài. Tham chiếu profile DeepSeek active đã đổi env sang secret; đối chiếu mọi field còn lại với backup. DPAPI giải mã và khớp giá trị User, giữ nguyên biến gốc. Owner và lịch sử cũ khớp backup. Hội thoại mới Desktop trả ORION-DESKTOP-DPAPI. HTTPS tailnet trả 200, mapping Serve không đổi, Funnel tắt. Web thật qua tailnet chờ Owner xác thực.
- Cộng 25 test UI (19 bridge/SDK và 6 Settings) pass, 73 backend pass, 1 skip.
