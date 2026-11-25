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

### 2026-11-17 · Đồng bộ từ Orion Host và đo token DeepSeek

- Phản hồi DELETE đến trễ từng ghi đè bản sao danh sách và lựa chọn Chat cũ. Store nay cập nhật theo trạng thái hiện tại sau khi Host xác nhận. Backend trả mã `active_request` và session tương ứng khi còn request đang chạy, giữ nguyên hàng dữ liệu. Xóa lặp sau khi client khác đã xóa được coi là hoàn tất. Bản nháp và thông báo lỗi gắn với hội thoại đang thao tác.
- Sidebar Chat kiểm tra snapshot từ SQLite qua ETag trong bộ nhớ. Client đọc lại khi nhận focus, quay về tab hoặc khôi phục kết nối. Chat đang mở đọc timeline và trạng thái request đã được Host xác nhận, gồm xếp hàng, đang chạy, chờ phê duyệt và yêu cầu dừng. Projects, danh sách model, Commands và endpoints làm mới qua API hiện có. Tắt ASGI của Host tự nhả SQLite và khóa runtime của ứng dụng để có thể mở lại.
- Kiểm thử tự động tập trung gồm 112 test backend và 46 test UI, TypeScript, Ruff, ESLint, OpenAPI và SDK. Bài tích hợp mở ba HTTP client trên cùng SQLite fixture, kiểm tra revision, tạo, đổi tên, xóa đồng thời với tạo mới, `409`, Projects và mở lại dữ liệu. Edge trên Windows dùng ba browser context độc lập vào web bundle thật với Host loopback và database tạm. Đã thấy rename sau reconnect, giữ bản nháp, cập nhật request/timeline/metrics và dừng request từ client khác, đồng bộ xóa và Project, rồi khởi động lại Host cùng database tạm.
- DeepSeek thật đọc hồ sơ `deepseek-flash` hiện có ở chế độ chỉ đọc và dùng credential DPAPI của Host. Mỗi phản hồi Chat mới lưu thời lượng và token theo từng lần model báo usage, cùng tổng khi đủ dữ liệu. Diagnostics bổ sung kích thước theo vai trò và phần continuation. System prompt ngắn hơn và giữ nguyên tool schemas cùng các giới hạn thực thi. Benchmark dùng dữ liệu tổng hợp trong SQLite tạm, cùng profile và bộ công cụ trước/sau. Input lần gọi đầu giảm 107 token ở mỗi kịch bản. Tổng mỗi lượt thay đổi theo số lần model tự gọi.

| Kịch bản DeepSeek | Lần gọi trước → sau | Input trước → sau | Output trước → sau |
| --- | ---: | ---: | ---: |
| Lời chào | 1 → 1 | 4.685 → 4.578 | 133 → 146 |
| Giải thích TCP/UDP | 1 → 1 | 4.688 → 4.581 | 1.099 → 910 |
| Đọc tài nguyên độc lập | 3 → 3 | 16.627 → 16.743 | 1.104 → 1.603 |
| Tiếp tục sau mười lượt | 1 → 1 | 5.393 → 5.286 | 245 → 289 |
| Một tác vụ đọc | 2 → 3 | 10.085 → 15.959 | 289 → 525 |
| Nhiều bước phụ thuộc | 4 → 3 | 23.235 → 17.266 | 1.474 → 1.779 |

- Đo thêm bốn kịch bản có tiêu chí đúng/sai từ cùng DeepSeek. Prompt trước lấy từ `61ba030`. PowerShell chạy một lệnh cố định không truy cập dữ liệu người dùng. RAG đọc tài liệu tổng hợp trong SQLite. Kịch bản nhiều bước dùng kết quả PowerShell làm đầu vào cho calculator. Cả bốn đạt kiểm tra nội dung và công cụ mong đợi ở hai lần đo.

| Kiểm tra có kết quả mong đợi | Số lần gọi trước → sau | Input trước → sau | Output trước → sau |
| --- | ---: | ---: | ---: |
| Trả đúng chuỗi | 1 → 1 | 2.337 → 2.230 | 91 → 56 |
| PowerShell cố định | 2 → 2 | 5.314 → 5.137 | 116 → 166 |
| RAG SQLite | 2 → 2 | 5.826 → 5.617 | 146 → 217 |
| PowerShell rồi tính toán | 3 → 3 | 8.451 → 8.113 | 185 → 172 |

- Trên bản đang cài, HTTPS Serve trả `200` cho health và `401` cho API danh sách Chat khi chưa đăng nhập. Chưa nghiệm thu lần đăng nhập Owner qua Serve cho mã nguồn mới. ADB chưa có thiết bị kết nối. Windows hiện tại không có WSL hay macOS/Xcode. Các cổng nghiệm thu nền tảng vẫn mở. Chưa build NSIS, cài đè, hay thay đổi Owner Auth, DPAPI, SQLite đang dùng, Serve hoặc Funnel.

### 2026-11-18 · Cuộn Chat, token và nghiệm thu Windows

- Checkpoint đầu phiên `55bbb49` trùng nhánh remote. Đã có NSIS unsigned 120.163.803 byte trong `release-work/sync-55bbb49` với SHA-256 `2A23DBB2B971805B73FA8C39E4DC52850C1ADB27805365F642B34E47F7286AB6`, kiểm tra 926 tệp và frozen smoke đạt. Thư mục đó chỉ có kịch bản nâng cấp, chưa có backup hay biên bản cài của ứng viên. Log thử Web thật bị dừng khi trình duyệt đóng. Giữ lại gói và backup của bản cài trước.
- Windows Desktop đang chạy sinh đúng tiến trình OrionBackend sở hữu listener `127.0.0.1:61888`. Serve HTTPS cùng proxy đó trả health 200 và danh sách Chat 401 khi chưa xác thực. Nguồn Desktop mở sidecar bằng thư mục local app data `managed`, và backend chọn `orion.db` trong thư mục ấy. SQLite đọc bằng `mode=ro` trả `quick_check=ok`; cả ba giá trị xuất hiện trong timeline và sự kiện SSE lưu bền. Hash sidecar đang cài khác sidecar ứng viên `55bbb49`, và bundle Web đang cài chưa có header `If-None-Match` cho snapshot. Bản cài cũ giữ snapshot sidebar giữa các thao tác, còn mã mới tại checkpoint thêm ETag, polling 5 giây khi đang hiển thị, refresh khi focus/reconnect và áp dụng kết quả xóa lên dữ liệu hiện tại. Dùng lại bằng chứng ba Edge context và một SQLite fixture của checkpoint.
- Chat lưu mốc tin nhắn và độ lệch trong localStorage theo client/server/hội thoại. Khôi phục khi timeline có dữ liệu, giữ mốc qua refresh và reflow. Chỉ theo đuôi khi có tin nhắn mới hoặc phần stream nối tiếp và người đọc đang gần cuối, đồng thời tôn trọng thao tác cuộn lên. Bài thử Windows Edge với bundle thật và SQLite tạm xác minh chat dài, focus refresh, hai vị trí riêng, đổi chiều rộng và reload. Bản nháp vẫn theo luồng cục bộ hiện có.
- Số liệu bên dưới lấy từ SQLite đang dùng. Đếm `model.started` và đối chiếu với `model.completed`. Hai lượt lớn nhất là lượt đầu của hội thoại. Lượt 39.920 có một lượt trước đó. Kho dữ liệu cũ chỉ có tổng token, số lần gọi, thời lượng và timeline, nên không khôi phục được token theo thành phần hoặc payload từng lần gọi. Trace hiện có trên fixture DeepSeek tại `55bbb49` đo phần system từ 5.053 lên 7.182 byte sau bước công cụ, 4.159 byte schemas gửi lại mỗi lần, và phần tool content từ 410 lên 767 byte qua hai lần tiếp tục. Đây là byte JSON của fixture, còn token trong bảng là số do provider báo.

| Lượt lịch sử | Input | Output | Lần gọi model | Vết công cụ |
| --- | ---: | ---: | ---: | --- |
| 39.920 | 39.920 | 1.098 | 3 | 1 run, 1 status |
| 105.410 | 105.410 | 5.274 | 8 | 6 công cụ, 4 thất bại, 2 lần liệt kê endpoint |
| 132.005 | 132.005 | 1.751 | 10 | 1 run, 8 status |

- Rút gọn phần hướng dẫn hệ thống và nhắc model chọn cùng lúc các lệnh đọc độc lập có đầu vào đã biết. Giữ cấu trúc schema, bước phụ thuộc, kiểm tra scope và các giới hạn dựa trên evidence. Với trang đầu của `system.command.status`, chờ monitor đang có tối đa 8 giây rồi lấy trạng thái bằng luồng hiện có. API trạng thái trực tiếp và truy xuất trang output theo byte offset vẫn trả theo luồng trước. Hủy chờ không hủy monitor và không chạy lại lệnh. Benchmark DeepSeek dùng hồ sơ hiện có ở chế độ chỉ đọc và SQLite tạm; so sánh prompt tại `55bbb49` với prompt mới, rồi tách riêng tác động của chế độ đợi trạng thái bằng một fixture chạy lệnh cố định 6 giây.

| DeepSeek fixture | Model trước → sau | Input trước → sau | Output trước → sau |
| --- | ---: | ---: | ---: |
| Chuỗi chính xác | 1 → 1 | 2.230 → 1.863 | 21 → 9 |
| PowerShell cố định | 2 → 2 | 5.124 → 4.396 | 144 → 171 |
| RAG SQLite | 2 → 2 | 5.601 → 4.881 | 169 → 171 |
| PowerShell rồi calculator | 3 → 3 | 8.152 → 7.040 | 202 → 209 |
| Trạng thái lệnh, trả ngay so với đợi | 8 → 3 | 25.777 → 6.511 | 1.054 → 473 |

- Bốn kịch bản prompt đạt tiêu chí fixture và giảm 12,9–16,5% input. Kịch bản trạng thái giảm 74,7% input, trả đúng stdout và có đúng một lần chạy lệnh ở hai chế độ. Input từng lần trạng thái trước là `1612, 2231, 2693, 3153, 3614, 4094, 4128, 4252`, sau là `1612, 2222, 2677`. Mỗi kịch bản là một cặp đo. Ba yêu cầu thật không được chạy lại vì có lịch sử thao tác trên máy và thiếu payload/token từng bước. Log đo `release-work/orion-followup/benchmark-final.log` và `benchmark-command.log`.
- Mã backend và Worker đóng gói từ `fdfcb15`. UI cuối tại `9391a52`. 132 test runtime/context/diagnostics, 26 test command/local/SSH, 20 test Chat UI, TypeScript, ESLint và Ruff tập trung đạt. Vite build đạt, còn cảnh báo chunk vượt 500 kB. Frozen sidecar qua smoke với port và SQLite tạm, không đụng Host đang chạy. Log trong `release-work/orion-followup` và `release-work/acceptance-fdfcb15`. Mypy toàn backend báo 4 lỗi kiểu hiện hữu trong `endpoints/artifacts.py`, tệp này khớp `55bbb49`.

- NSIS x64 debug preview chưa ký `release-work/acceptance-fdfcb15/Orion_0.1.5_x64_fdfcb15-preview-setup.exe`, 120.184.178 byte, SHA-256 `9B56E4FFDFB7606EE4F3FF437C91CBC647F61702D4666BDA5442C82DE9A2E24C`. 7-Zip kiểm tra 926 tệp. Giải nén và đối chiếu 844 hash sidecar/Worker với manifest và 72 hash web với build Vite. Đổi PATH của lần đóng gói lại để Tauri tìm thấy windres. Ứng viên đã sẵn sàng để nâng cấp theo checklist.

#### PENDING_MANUAL · Nâng cấp tại chỗ và kiểm tra thiết bị

1. Dùng cùng tài khoản Windows hiện tại. Chờ yêu cầu đang chạy hoàn tất. Ghi lại mapping Serve và xác nhận Funnel tắt, sau đó dừng Host sạch từ Orion. Xác nhận hai tiến trình Orion và OrionBackend đã thoát. Chỉ đóng cửa sổ sẽ để Host chạy nền.
2. Sao lưu riêng tư cả profile `%LOCALAPPDATA%\io.orion.desktop\managed`, bộ cài/ứng dụng cũ tại `%LOCALAPPDATA%\Orion`, cấu hình Host và mục autostart HKCU. Giữ cùng Windows account/máy để DPAPI còn giải mã được. Kiểm tra hash tệp, SQLite integrity, Owner record, tham chiếu model và ba lượt token trên bản sao. Lưu JSON Serve riêng cùng backup.
3. Kiểm SHA-256 ứng viên, cài đè NSIS theo cùng phạm vi và thư mục hiện tại. Đối chiếu hash SQLite trước lần mở đầu và hash backend mới với manifest. Mở Orion, xác nhận history, Projects, hồ sơ model và trạng thái Host. Đối chiếu Serve, giữ Funnel tắt. Chủ máy tự xác thực Owner và tự kiểm tra chat DeepSeek qua Desktop và Web tailnet.
4. Kiểm thử tạo, đổi tên, xóa một chat thử và dừng một request thử giữa các client trỏ đúng cùng URL Host. Thử reconnect, chat dài và vị trí cuộn riêng trên từng nền tảng. Android và iOS cần thiết bị thích hợp và Owner enrollment. Trên Linux, repo cung cấp headless và Web; launcher Tauri desktop hiện triển khai Windows, nên Linux native GUI còn thiếu.
5. Nếu phải rollback, dừng Host sạch và giữ thêm snapshot hậu kiểm trước khi hoàn nguyên. Khôi phục bộ ứng dụng và cấu hình cũ từ backup. Ưu tiên giữ SQLite hiện tại nếu bản cũ tương thích, và chỉ phục hồi snapshot trước nâng cấp khi cần phục hồi dữ liệu/schema. Việc thay snapshot có thể làm mất chat tạo sau nâng cấp, nên giữ snapshot hậu kiểm và xác nhận trước khi thực hiện. Kiểm tra lại health, SQLite và Serve trước khi thử tiếp.

- `PENDING_MANUAL` cho nâng cấp Windows và smoke Desktop bản cài, đăng nhập Web thật qua Serve, Android, iOS và Web trên Linux. Giữ Host đang chạy, Owner, credential, Serve và Funnel trong trạng thái trước phiên.

### 2026-11-18 · Xác minh gói 8eb4ad2 và chuẩn bị bảo trì

- Tiếp tục từ working tree sạch tại `8eb4ad2`. Bộ cài cuối vẫn là `release-work/acceptance-fdfcb15/Orion_0.1.5_x64_fdfcb15-preview-setup.exe`, 120.184.178 byte, SHA-256 `9B56E4FFDFB7606EE4F3FF437C91CBC647F61702D4666BDA5442C82DE9A2E24C`. Đối chiếu Git xác nhận backend/Worker tại `fdfcb15` khớp mã ứng dụng của `8eb4ad2`, UI tại `9391a52`. Build lại UI ở checkpoint hiện tại để so 72 tệp Web và tìm đủ 8 JS/CSS byte-for-byte trong Orion.exe. Kiểm 844 hash backend/Worker với manifest. Giữ gói đã xác minh. Bằng chứng tại `release-work/upgrade-8eb4ad2/package-verification.json` và `ui-reproduce.log`.
- Tạo backup trực tuyến tại `C:/Users/phamg/AppData/Local/OrionRecovery/before-upgrade-8eb4ad2-20261118-073941`, ACL chỉ tài khoản hiện tại và SYSTEM. Dùng SQLite Backup API trên giao dịch đọc WAL-consistent, kiểm hash mọi tệp và so dữ liệu mọi bảng với giao dịch nguồn. Backup chứa SQLite, blobs, credential DPAPI mã hóa, ứng dụng đang cài, registry Host/uninstall, autostart và Serve JSON. Có manifest và lệnh kiểm lại. Mọi giá trị bảo mật chỉ nằm trong bản sao riêng tư hoặc bộ nhớ.
- Diễn tập vào thư mục rollback mới dưới backup. Khởi tạo SQLite bằng mã ứng dụng, so khớp mọi bảng, integrity/foreign keys, hàng Owner gồm password hash/TOTP/recovery/replay counter, hồ sơ model, lịch sử Chat và ba lượt token. Credential DPAPI bản phục hồi giải mã được dưới cùng tài khoản và khớp bản gốc bằng so sánh trong bộ nhớ. Log chỉ ghi PASS/FAIL và đường dẫn. Backup trực tuyến được giữ làm checkpoint; kịch bản nâng cấp sẽ chụp snapshot mới khi Host đã dừng sạch.
- Thêm `scripts/windows/upgrade_readiness.py`, `upgrade_acceptance.py` và `upgrade-maintenance.ps1`. Bộ kiểm sau cài chạy thành công trên payload và SQLite sao chép cô lập, đồng thời phát hiện thay đổi Chat chủ động trên bản sao và chỉ báo lỗi cố định. Guard thiếu cửa sổ bảo trì đã được kiểm. Ruff/Python compile và PowerShell parse đạt. Các test runtime/UI/frozen/live đã đạt ở checkpoint trước được tái sử dụng vì mã ứng dụng giữ nguyên. Log tại `release-work/upgrade-8eb4ad2`.
- Quy trình và rollback tại `docs/refactor/UPGRADE_8EB4AD2.md`. Kịch bản cần chủ máy dừng Host sạch trong cửa sổ bảo trì, sau đó tự tạo/kiểm backup mới, kiểm checksum, cài và đối chiếu toàn bộ dữ liệu trước lần mở đầu. Rollback hệ thống thật và đăng nhập Owner cùng nghiệm thu Desktop/Web/Android/iOS vẫn `PENDING_MANUAL`.
- Host vẫn giữ listener `127.0.0.1:61888` bởi PID 17004. Kiểm lại Serve health 200 và API danh sách Chat 401 ở trạng thái chưa xác thực; Funnel có 0 mapping bật. Phiên chuẩn bị chỉ chụp dữ liệu và chạy diễn tập cô lập.

### 2026-11-18 · Lỗi nghiệm thu sau nâng cấp fdfcb15

- Bắt đầu tại `4c7033b`; bản cài hiện có sidecar `fdfcb15`. Đọc SQLite bằng `mode=ro`, xác nhận lượt `d00f236e-4679-464a-9ed8-39828cd2c83e` chứa lời chào “xin chào”, 9.929 input / 182 output và đúng một invocation. Hội thoại chưa có timeline trước lượt này. Máy có 0 endpoint chưa thu hồi. Bốn mức usage 9.929, 39.920, 105.410 và 132.005 đều còn trong SQLite.
- Tái tạo lời chào qua composition root đầy đủ với 46 tools, cùng profile DeepSeek đang dùng và credential DPAPI chỉ đọc, trong SQLite tạm. Input đúng 9.929. System content 5.513 byte gồm hướng dẫn nền/evidence, skill catalog, target context và thời gian ứng dụng; user content 9 byte, history/tool continuation 0. JSON parameters của 46 schema là 13.527 byte, chưa gồm tên/description/wrapper. Đo loại trừ trên cùng messages: bỏ tools còn 1.274 input; chỉ user còn 60 input. Chênh lệch 8.655 token là chi phí biên của định nghĩa tools và tool protocol, 1.214 là chi phí biên của system context; 60 là user cùng overhead cơ sở. Đây là chênh lệch provider usage, không phải quy đổi từ byte hoặc số đếm tokenizer cục bộ. Payload lịch sử không được lưu đủ để chia token từng câu system hoặc từng schema; kết quả tái tạo khớp tổng input thực tế.
- Mã `827e263` kiểm tra endpoint ghép nối theo scope mỗi model turn. Khi chưa có target hợp lệ, chỉ bỏ 25 endpoint operation schemas, giữ `endpoint.list`, RAG, calculator, command, skill, scheduler và internet. Khi endpoint được ghép, các schema trở lại ngay từ lượt kế tiếp, kể cả endpoint offline. Registry chuẩn và kiểm tra execution/scope vẫn giữ đầy đủ. Cách chọn này theo cấu hình khả dụng, dùng cùng quy tắc cho lời chào và tác vụ phức tạp.

| DeepSeek thật, SQLite fixture và registry ứng dụng đầy đủ | Model trước → sau | Input trước → sau | Output trước → sau |
| --- | ---: | ---: | ---: |
| Lời chào | 1 → 1 | 9.929 → 5.387 | 153 → 256 |
| RAG lấy đúng marker | 2 → 2 | 20.813 → 11.642 | 183 → 166 |
| Hai phép tính phụ thuộc | 3 → 3 | 30.767 → 17.141 | 228 → 208 |

- Mỗi hàng là một cặp đo, đều đạt tiêu chí nội dung/công cụ. Lời chào giảm 45,7% input, RAG 44,1%, chuỗi phụ thuộc 44,3%. Output của lượt chào gốc là 182, còn hai lần benchmark sinh output khác nhau như bảng. Mức tiết kiệm này áp dụng cho cấu hình chưa ghép endpoint. Logs `release-work/acceptance-fixes-4c7033b/token-before.log`, `token-after.log` và script `token-benchmark.py`.
- Nguyên nhân đồng bộ nằm ở native boundary. SDK đã cho phép `if-none-match` và backend có ETag/304 đúng, nhưng allowlist Rust chưa cho header ấy đi qua. Sau lần tải đầu, refresh conditional ném lỗi và observer giữ snapshot cũ. Ngoài ra Rust coi mọi 3xx, gồm 304, là redirect và JavaScript bridge tạo stream body cho 304 khiến `Response` ném lỗi. Sửa allowlist, chấp nhận bodyless 304 tại Rust và trả `Response(null)` ở JavaScript. Managed và remote native dùng cùng transport.
- Nguyên nhân thứ tự “Gần đây” là `upsertSession` prepend cả khi hydrate/load để đọc. Sửa cập nhật hàng hiện có tại đúng vị trí, append khi đọc một hội thoại cũ ngoài snapshot 100 hàng. Chỉ tạo Chat mới mới prepend cục bộ; sau đó snapshot Host quyết định thứ tự qua `last_activity_at DESC, session_id DESC`. Mở/chọn chat và polling chi tiết giữ nguyên thứ tự. Mục đang chọn và vị trí cuộn sidebar được đối chiếu trong fixture.
- Regression tập trung đạt 43 backend bootstrap/DeepSeek, 31 UI store/native bridge và 3 Rust transport tests. Có bài ghép/revoke endpoint thay đổi visibility, first-turn RAG/command còn đủ, HTTP conditional thật giữ ETag và 304, JavaScript managed IPC bodyless 304, hai store độc lập và hydrate archive ngoài danh sách. TypeScript, ESLint và Ruff tập trung đạt. Giữ các kết quả test khác còn hợp lệ.
- Hai Edge browser context độc lập chạy bundle production trên SQLite fixture, một Web HTTP và một chạy đường `installTauriHost`/SDK/nativeFetch với IPC fixture chuyển tiếp HTTP. Đã kiểm tạo Chat hai chiều, xóa truyền sang client kia, trạng thái 200/304 thật, đọc Chat cũ giữ thứ tự/cuộn/sidebar selection, và hoạt động mới đưa đúng Chat lên theo Host. Bài Rust transport riêng kiểm native HTTP thực. Log thành công đầy đủ tại `two-clients-pass.log`. Hai lần chạy harness đầu đạt assertions nhưng teardown giữ SQLite handle; đóng explicit store ở teardown rồi chạy lại thành công. Bằng chứng này còn cần bổ sung nghiệm thu Windows app đã cài cùng Owner Web qua Serve, trạng thái `PENDING_MANUAL`.
- Host thật vẫn giữ PID 17744 tại `127.0.0.1:61888`, Serve proxy đúng listener đó và Funnel 0 mapping bật. Phần dữ liệu thật chỉ được đọc để kiểm tra/đo profile và sao lưu. Chưa cài đè ứng viên trong phiên này.

- Ứng viên cập nhật tại chỗ từ source sạch `827e2630a4dd5b91667043b3cc057473d8c215dc`: `release-work/acceptance-827e263/Orion_0.1.5_x64_827e263-preview-setup.exe`, x64 debug preview chưa ký, 120.174.116 byte. SHA-256 `C4B18B60BF41405D181DDA731A986B7DC7A686A5F731CBACA130DFB60EE6F6B3`. Sidecar và Worker cùng source identity. Archive 926 tệp đạt; đối chiếu 844 hash backend/Worker, 72 Web và đủ 8 JS/CSS nhúng trong Orion.exe. Frozen managed smoke mới đạt 1 test với SQLite/cổng riêng. Logs tại `release-work/acceptance-827e263`.
- Backup trực tuyến mới giữ dữ liệu sau lần nâng cấp thật tại `C:/Users/phamg/AppData/Local/OrionRecovery/before-upgrade-8eb4ad2-20261118-085955`. Snapshot, hash, SQLite/Owner state và diễn tập phục hồi DPAPI đều đạt theo utility đã có. `upgrade-maintenance.ps1` đã pin bộ cài/SHA mới, vẫn yêu cầu cửa sổ bảo trì và Host dừng sạch; tạo lại backup trước cài và đối chiếu dữ liệu sau cài trước lần mở đầu.
- `PENDING_MANUAL`: chọn cửa sổ bảo trì, dừng Host sạch, chạy `F:/Orion/scripts/windows/upgrade-maintenance.ps1 -MaintenanceWindow`, rồi chủ máy tự mở Desktop và đăng nhập Owner Web qua Serve. Kiểm tạo/xóa chat hai chiều ở bản cài mới, mở chat cũ không đổi thứ tự/sidebar scroll/selection, có hoạt động mới mới đổi thứ tự, đo lời chào trên một Chat mới, và thử RAG/tác vụ nhiều bước. Android/iOS/Linux cùng transport hoặc shared UI nhưng nghiệm thu nền tảng tương ứng vẫn mở. Giữ Funnel tắt.

### 2026-11-23 · Xóa Chat, capability theo request và truy cập Internet

- Đối chiếu bản đang cài bằng hash và manifest, xác nhận `827e263`. Native bridge đã trả bodyless response cho 204/205/304. Lớp SDK phía trên vẫn dựng lại `Response` từ stream khi có abort signal. Fixture chuẩn mô phỏng transport trả stream rỗng với status cấm body, tái hiện lỗi constructor. SDK nay hủy stream dư và dựng response null body, giữ status và headers. DELETE chỉ cập nhật store khi Host xác nhận. 404 coi là đã xóa. 409 giữ row và báo request đang chạy. Chưa có trace từ lần lỗi trên WebView2 đang cài để khẳng định đường đi chính xác của lần đó.
- Model chọn capability qua `tools.enable`. Registry chuẩn vẫn quyết định schema, còn execution boundary áp dụng scope, read-only/confirm/auto và xác nhận payload. Catalog rút gọn dùng trên lượt đầu, chỉ nạp nhóm đã chọn và chỉ giữ trong vòng đời request. Retry mở lại nhóm hoặc chọn nhóm không tồn tại có giới hạn qua recovery tracker. Regression bao gồm chat thường, RAG, tải schema mutation nhưng vẫn bị chặn trong read-only, và vòng lặp yêu cầu mở cùng capability.
- Benchmark DeepSeek thật dùng cùng profile, SQLite tạm và composition root. PowerShell chỉ được chạy đúng fixture `Write-Output 17`. Cả năm cặp đạt kiểm tra nội dung và công cụ theo harness. Đây là mỗi kịch bản một cặp đo.

| Tác vụ | Lượt model trước → sau | Input trước → sau | Output trước → sau | Thời gian trước → sau |
| --- | ---: | ---: | ---: | ---: |
| Lời chào | 1 → 1 | 5.387 → 1.728 | 298 → 169 | 2,771 → 1,597 s |
| TCP/UDP | 1 → 1 | 5.402 → 1.743 | 147 → 124 | 1,812 → 1,457 s |
| PowerShell | 3 → 4 | 17.977 → 11.852 | 387 → 398 | 4,187 → 4,882 s |
| RAG | 2 → 3 | 11.637 → 8.659 | 160 → 257 | 2,545 → 3,346 s |
| PowerShell và calculator | 4 → 5 | 24.852 → 16.471 | 607 → 531 | 6,440 → 6,228 s |

- Giữ draft trong ChatProvider theo session/project, tách theo client và giữ được khi trình soạn thảo remount trong cùng provider. Người dùng đổi server hoặc đóng ứng dụng vẫn bắt đầu provider mới. Phiên kết nối native được làm mới qua cùng observer với các snapshot Host. Thứ tự Chat tiếp tục do last_activity_at của Host quyết định.
- Settings Windows có bật/tắt Internet, yêu cầu xác nhận công khai, Host Mode, Owner MFA, HTTPS và route Serve khớp upstream. Bật dùng Funnel trên cổng được hỗ trợ. Tắt dùng Serve riêng tư trên cùng upstream. Có fixture cho consent, route xung đột, port, và lệnh quay về Serve. Các kiểm tra HTTP/WS, Origin, cookie, rate limit, enrollment/revoke, SSE, lệnh confirm và Stop chạy trên fixture. Không thực hiện mutation Tailscale trên máy đang dùng. [Nghiệm thu Internet](INTERNET_ACCEPTANCE.md).
- Backup mới và diễn tập rollback đạt tại `C:/Users/phamg/AppData/Local/OrionRecovery/before-upgrade-8eb4ad2-20261123-055027`. Chuyển guard backup từ ba mốc token lịch sử cố định sang kiểm tra toàn bộ bảng hiện có, vốn đã là điều kiện rollback. Tại thời điểm đọc chỉ thấy 132.005 trong các mốc 9.929, 39.920, 105.410, 132.005. Không kết luận nguyên nhân thiếu các mốc kia và không thay đổi dữ liệu nguồn. Backup cũ vẫn giữ riêng. Log kiểm tra ở `release-work/final-internet-batch`.

- Mã ứng dụng, sidecar và Worker từ checkpoint sạch `253dae09de3d1fafbb578871f9b31165307d1113`. Một bộ NSIS Windows x64 preview chưa ký tại `release-work/final-internet-batch/Orion_0.1.5_x64_final-preview-setup.exe` có SHA-256 `D617E63DD323199A9B454CA200C2F5A54967AC5C08F1C9257F5A9DD7EF018545`. Kiểm archive, hash payload backend/Worker/Web và JS/CSS nhúng trong Orion.exe đạt. Frozen managed smoke đạt trên SQLite/cổng riêng.
- UI có 143 ca đạt trong suite, ca Funnel fixture chạy lại đạt sau khi sửa fixture polling để trả đúng trạng thái CLI hiện tại, tổng 144. TypeScript, ESLint, Ruff phần mã thay đổi và 8 Rust tests đạt. Rust có 3 bài ignored theo điều kiện môi trường. Backend đầy đủ 1.622 pass, 23 skip, 23 subtests pass và 1 fail do ca Worker wire trả outcome_unknown. Ca fail đạt khi chạy riêng và trong nhóm lại 14 command service test. Ghi nhận là kết quả chập chờn, không ghi full suite xanh. Security fixture đạt 40 ca.
- Hai browser context Edge độc lập trên SQLite tạm, một Web và một dùng bridge managed IPC giả lập transport, đã tạo hai chiều, đổi tên native → Web và xóa một lần từ mỗi phía. Giữ sidebar/selection khi đọc, cập nhật order theo hoạt động, nhận 200/304 và giữ session snapshot. Native transport thật được kiểm ở Rust. Chưa nghiệm thu GUI bản cài mới, Web xác thực trên Host thật, Linux trên máy riêng hay thiết bị Android/iOS trong phiên này.
- Serve thật tại Host đang chạy trả 200 cho health và 401 cho Chat/Models/Remote Control trước xác thực. Funnel có 0 mapping bật. `PENDING_MANUAL`: cửa sổ bảo trì và nâng cấp tại chỗ, đăng nhập Owner, Internet ngoài tailnet qua Chrome/Edge và Android/iOS, kiểm bật/tắt quay về Serve riêng tư. Các bước ghi tại `docs/refactor/INTERNET_ACCEPTANCE.md`.

### 2026-11-23 · Giao diện dùng chung trên điện thoại, PowerShell và kiểm tra bản cập nhật

- Mã ứng dụng `5a9e1aa`. Orion Desktop và Web tiếp tục dùng cùng React UI, ChatProvider và API. Ở viewport điện thoại, sidebar dùng lại Projects, Remote Control, Commands, Settings và lịch sử. Menu cho phép mở/đóng, Chat mới có nút riêng. Sign out nằm trong menu điện thoại. Bảng hoạt động dùng panel hiện có. Shell bám visual viewport khi bàn phím mở. Nút menu và điều hướng desktop vẫn dùng bố cục Orion.
- Worker dùng `-NoProfile -NonInteractive -ExecutionPolicy Bypass -File` cho tập lệnh riêng tư đã được duyệt. Execution Policy áp dụng trong tiến trình, giữ giới hạn, payload đã xác nhận, audit và mã thoát. Race trước đây gắn exit code hoặc process-tree termination vào quan sát còn `running` trong lúc cleanup, khiến Host từ chối kết quả. Worker nay xuất đồng thời state, exit code và trạng thái process tree sau cleanup. Host giữ mã thoát đã xác minh nếu lần đọc kết quả sau đó gặp lỗi. Lệnh ngắn có thể trả kết quả ngay trong `system.command.run` sau khi chờ tối đa 3 giây. Lệnh dài trả handle để đọc hoặc Stop theo cơ chế hiện có.
- Đo DeepSeek cùng đầu bài trên Windows, dùng SQLite tạm và một PowerShell chỉ đọc được đối chiếu nguyên văn. Kiểm tra đủ hostname, Windows version, IPv4, DNS và gateway với output thực tế. Một lần thực thi ở mỗi mẫu. Trước (`a2e9e91`) dùng tools.enable, run và status. Sau dùng tools.enable và run. Giá trị cấu hình mạng và credential không nằm trong kết quả ghi.

| Mẫu | Lượt model | Input theo lượt | Tổng input | Tổng output | Thời gian |
| --- | ---: | --- | ---: | ---: | ---: |
| Trước | 4 | 1.941 + 3.195 + 3.665 + 4.216 | 13.017 | 970 | 6,879 s |
| Sau | 3 | 1.940 + 3.229 + 3.796 | 8.965 | 1.185 | 9,281 s |

- Input giảm 31,1% trong cặp đo. Mốc sự cố người dùng báo là 6 lượt và 25.227 input. Mẫu mới giảm 64,5% so với mốc đó. Một cặp đo cho thấy thời gian tăng 2,402 giây cùng với output dài hơn.
- Regression Windows runner, runtime/Stop, command service và SSH đạt 41 ca. Vitest đạt 55 ca Chat/sidebar/store và 11 ca Settings/ContextPanel, có 4 ca ContextPanel trùng giữa hai lượt chạy. TypeScript, ESLint, Ruff và ca Rust xét release ổn định đều đạt. Build Web production đạt. Hai ca trình duyệt trên bundle đóng gói đạt với Chromium/Pixel 7 và WebKit/iPhone 13. Chrome thật trên trình giả lập Android API 35 và Edge Windows chạy đồng thời trên SQLite cô lập, tạo Chat hai chiều, chuyển phiên, mở bảng hoạt động và xác minh composer trên bàn phím Android thật. Safari iPhone và Orion Desktop đã cài với Owner/Serve thật còn `PENDING_MANUAL`.
- Settings trên Windows kiểm tra phiên bản ổn định mới hơn có bộ NSIS trên GitHub Releases và mở trang tải khi người dùng chọn. Kiểm tra GitHub công khai trả bản v0.1.2, chưa có ứng viên NSIS ổn định mới hơn để nghiệm thu luồng tải thật. Cài đặt trên Host cần cửa sổ bảo trì. Nghiệm thu APK và iOS native trên thiết bị thật vẫn mở.
- Backup trực tuyến và diễn tập rollback đạt tại `C:/Users/phamg/AppData/Local/OrionRecovery/before-upgrade-8eb4ad2-20261123-205410`. Kiểm toàn bộ bảng SQLite, Chat, Owner MFA, DPAPI, tệp cài và cấu hình Host/Serve. Tùy chọn `--online-only` ghi lại cấu hình đang chạy khi sao lưu. Kịch bản cài bảo trì vẫn yêu cầu Funnel tắt và Host dừng sạch. Chưa cài đè hoặc thay đổi Host/Serve/Funnel.

- Bộ cài Windows x64 NSIS preview chưa ký, 120.344.198 byte, tại `release-work/mobile-runtime-5a9e1aa/Orion_0.1.5_x64_mobile-runtime-preview-setup.exe`. SHA-256 `8E753FD7182142039CBAC474DBECAECAC14C9D94E444F286F917794AE6635982`. Archive 926 tệp đạt. Đối chiếu 844 hash backend/Worker, 72 Web và đủ 8 JS/CSS nhúng trong Orion.exe. Frozen managed smoke đạt với SQLite và cổng riêng. [Quy trình bảo trì và rollback](UPGRADE_8EB4AD2.md).

### 2026-11-23 · Cuộn ngang Mobile Web, cập nhật có chữ ký và cold-start

- Checkpoint ứng dụng `da87a15`. Nội dung không có dấu cách trước đây giữ chiều rộng nội tại. Markdown render `<pre>` và `<table>` không có vùng cuộn ngang riêng, nên timeline cuộn bên trong toàn trang Chat. Tin nhắn nay ngắt từ dài. Code, bảng, công thức dài và stdout/stderr cuộn ngang trong vùng của chính component. Giữ giao diện Orion hiện tại.
- Chrome Android 124 trên trình giả lập API 35 dùng cùng một fixture dài với bundle đã nâng cấp và bundle mới. Viewport và root là 393 px. Timeline rộng 383 px nhưng có scrollWidth 6.784 px ở bundle cũ. Bundle mới có scrollWidth 383 px, code và bảng vẫn tự cuộn đến cột cuối. Kiểm thử bằng Host và SQLite tạm.
- Web và mobile nhận thông báo bản Host qua `GET /api/updates` sau xác thực. Host chỉ kiểm kê bản Windows ổn định trên GitHub Releases với metadata kích thước và digest. Cài đặt chạy trên Windows Host cục bộ. Trước khi dừng, Windows kiểm Authenticode, fingerprint đã đóng vào bản build, SHA-256 và phiên bản, rồi yêu cầu xác nhận bảo trì trong hộp thoại Windows. Host bận trả 409. Khi Host rảnh, chặn request mới và tạm dừng scheduler trước khi đóng sidecar, sao lưu và diễn tập rollback. NSIS chỉ được thực thi sau khi đủ điều kiện. Bản preview chưa ký bị từ chối bằng kiểm thử thật. Chính thức phát hành và chạy một lần nâng cấp đã ký trên môi trường cô lập còn `PENDING_MANUAL`. [Quy trình phát hành và nâng cấp](UPGRADE_8EB4AD2.md).
- Cold-start dùng debug native WebView2 với profile, SQLite và cổng riêng. Sidecar đóng gói có trace đạt UI tương tác ở 9.390, 4.179 và 4.291 ms. Mẫu đầu chờ sidecar 8.375 ms. Trong đó 7.740 ms trước dấu mốc xác minh owner pipe, 528 ms từ dấu mốc đó đến bind và 107 ms từ bind đến ready. WebView2 mất 806 ms, auth và giao diện sau load mất 139 ms. Khoảng chờ chủ yếu nằm ở lúc khởi tạo tiến trình sidecar và nạp runtime/import trước khi Python ghi trace. Số đo này chưa tách riêng bộ nạp, I/O và các import. Đo lại với sidecar đang cài có trung vị 4.201 ms và một mẫu 37.488 ms với 32.757 ms trước native entry, chưa xác định nguyên nhân riêng của mẫu ngoại lệ.
- Regression backend 104 ca. Rust 5 ca và ca Windows từ chối NSIS không ký đạt. Vitest phần Chat, Commands và Settings đạt. Chromium và WebKit đạt 5 ca fixture responsive và thông báo cập nhật. OpenAPI/SDK, TypeScript, ESLint, Ruff, build Windows/Web và frozen managed smoke đạt. Host đang vận hành và cấu hình Funnel không được tác động. Không phát hành hoặc cài bộ preview.
- PR #173 tiếp nối PR #172 đã merge. CI lần đầu dùng `ubuntu-latest` là Ubuntu 26.04 và không cài được Python 3.12.10. Pin ba job Linux dùng Python của PR vào Ubuntu 24.04, có đúng bản Python trong manifest chính thức.
- Cập nhật kiểm tra tài liệu kiến trúc theo ADR 0019 và hành vi `tools.enable` đang chạy. Kiểm tra cũ vẫn yêu cầu mô tả phát toàn bộ schema theo ADR 0007. Nội dung lịch sử trong changelog được giữ.

### 2026-11-24 · PR #173 · Cập nhật một chạm, kiểm thử Android và cold-start

- Kênh Preview chạy trực tiếp trên nhánh `codex/orion-windows-acceptance`. Stable dùng workflow phát hành trên `main`. Hai kênh dùng chung thứ tự phiên bản Windows. Workflow chờ đủ bảy job CI trên chính commit phát hành. Bộ NSIS phải đạt kiểm tra chữ ký Authenticode theo fingerprint đóng vào ứng dụng, SHA-256 và nghiệm thu cài, khởi động, rollback trên runner Windows cô lập trước khi có thể xuất bản.
- Desktop kiểm tra kênh đã chọn và có nút **Cập nhật ngay**. Dừng Host chỉ sau xác nhận bảo trì, xác minh installer, kiểm tra tác vụ đang chạy và tạo bản sao. Bản mới giữ API và scheduler ở chế độ bảo trì cho đến khi WebView2 và Host qua kiểm tra. Lỗi kích hoạt rollback dữ liệu và bản cài. Các Client Web/Mobile nhận thông báo qua Host. Quy trình cứu hộ và cài bootstrap đã ký ghi trong [hướng dẫn nâng cấp](UPGRADE_8EB4AD2.md).
- PASS tự động trên Windows cô lập: 114 ca backend, gồm xác nhận PowerShell, bảo trì và rollback SQLite, Chat, Projects, Owner MFA và dữ liệu mã hóa DPAPI với fixture. Rust 6 ca mặc định đạt, một ca yêu cầu Serve thật được để riêng. Ca Windows từ chối NSIS chưa ký đã chạy và đạt. Frozen managed smoke, Ruff, mypy, OpenAPI/SDK, kiểm tra kiến trúc, TypeScript, ESLint phần thay đổi, build Web/Windows và 12 ca Vitest đạt.
- PASS 7 ca trình duyệt Chromium/WebKit trên Host dữ liệu tạm, gồm đồng bộ giữa hai client, Projects, mất mạng và giữ bản nháp, Runtime và thông báo cập nhật. Chrome 124 trên trình giả lập Android API 35 xác minh bàn phím Android thật, composer, bảng PowerShell, code và Runtime dài. Không có cuộn ngang toàn trang, bảng và code cuộn trong vùng tương ứng.
- Backend/Worker trước đó vướng Python 3.12.10 trên Ubuntu 26.04. CI với Ubuntu 24.04 cài được Python và Worker đã qua. Backend tiếp tục lộ lỗi Ruff và kiểm tra kiểu, đã sửa và chạy kiểm tra cục bộ. Android CI đã tạo APK nhưng ca kết nối chọn ô Mã kết nối nằm ngoài vùng nhìn thấy. Màn hình kết nối nay co theo bàn phím và vùng trường nhập cuộn được. Kiểm thử Android tìm trường đang hiển thị trước khi nhập và lấy tệp thử nghiệm từ bộ nhớ thiết bị để tránh độ trễ lập chỉ mục Downloads. APK x86_64 trên trình giả lập Android API 35 đã qua ca mở rộng, gồm kết nối, lưu phiên khi mở lại, bàn phím, gửi Chat, ngắt mạng, hủy và tiếp tục stream, đính kèm và thu hồi phiên khi đăng xuất.
- Cold-start dùng cùng frozen sidecar và profile cô lập. Ba lượt mới có trung vị mở shell 0,891 giây so với 4,124 giây, và sẵn sàng 3,471 giây so với 4,291 giây. Khởi tạo WebView2 chạy song song với sidecar. Có một lượt sẵn sàng sau 37,796 giây, trong đó 32,464 giây trước khi mã Rust bắt đầu chạy. Chưa xác định nguyên nhân độ trễ đó. Giữ các bước xác thực và kiểm tra dữ liệu.
- PENDING_MANUAL: phát hành lần đầu cần signing environment có chứng chỉ hợp lệ và CI xanh, sau đó cài bootstrap đã ký một lần trong cửa sổ bảo trì do chủ máy chọn. Nghiệm thu nâng cấp trên Host đang dùng, đăng nhập Owner MFA, Funnel thật, Safari iPhone và thiết bị native cần thực hiện riêng. Không dừng Host, không đổi Funnel, không cài hoặc phát hành preview chưa ký trong phiên này.

### 2026-11-24 · PR #173 · Windows feature và Android ADB

- Run Windows 45324225290 thất bại vì crate mặc định biên dịch hai hàm HTTP bảo trì dành riêng cho Tauri. Giới hạn chúng vào feature `desktop`, giữ lớp transport mặc định và test chặn header nội bộ. Windows CI chạy cả hai cấu hình Cargo và kiểm `custom-protocol`.
- Run Android 45324225282 đã boot thiết bị trước khi probe IME trả 255 và cleanup cũng mất ADB. Log cũ thiếu stderr và tình trạng runner nên chưa chứng minh được lý do kết nối bị ngắt. CI chuẩn bị dependencies trước khi mở emulator, dừng Gradle daemon của job, chờ boot và hai dịch vụ package/IME, đặt timeout, đồng thời lưu trạng thái tiến trình, bộ nhớ và log Android khi lỗi. Smoke chờ lại transport có giới hạn và chỉ thử lại lệnh an toàn. Assertion và lỗi lệnh thật vẫn làm job thất bại.
- Bốn ca regression mô phỏng phục hồi kênh ADB, ngắt kéo dài, lỗi dịch vụ và cleanup giữ nguyên lỗi đầu tiên. Workflow Preview vẫn yêu cầu bảy job thành công trên đúng push SHA. Run 45324217904 thực tế đã chặn ứng viên `4b4a4fc`.

### 2026-11-24 · PR #173 · Menu Android dưới thanh trạng thái

- Checkpoint `ef68847` qua Windows CI trên cả push và PR. Android đã qua luồng Chat, ngắt mạng, tiếp tục stream và đính kèm, sau đó không mở được menu để đăng xuất. Cả hai runner ghi ADB ở trạng thái `device` sau lỗi. Release gate chặn phát hành đúng SHA.
- Tái hiện lỗi với APK cũ trên emulator API 35 ở 320×640, 160 dpi như GitHub. Android đặt nút Menu tại `[8,0][44,36]`, nên tâm chạm ở y=18 nằm dưới thanh trạng thái. Ảnh khi test hết thời gian xác nhận menu còn đóng và thanh hệ thống che phần đầu ứng dụng.
- Điểm vào Android xử lý vùng thanh trạng thái, điều hướng và cutout bằng window insets. WebView nhận phần insets của bàn phím để tiếp tục co viewport. Smoke xác minh thanh bên thực sự mở trước khi chạm Sign out, rồi kiểm revocation như trước.

- APK mới qua ca ABI x86_64 ở 320×640. Nút Menu mở thanh bên, Sign out thu hồi phiên fixture. GitHub Android push trên `e856443` cũng đạt toàn bộ bước, gồm file picker và đăng xuất.
- Với cấu hình emulator khác, form kết nối vẫn cần cuộn xuống sau khi nhập mã. Smoke chỉ chạm nút khi có vùng hiển thị. Khi DocumentsUI đã mở bộ nhớ nội bộ trước đó, bộ chọn dùng đúng hàng trong ngăn điều hướng thay vì tiêu đề trùng tên. Hai ca này có regression riêng cùng bốn ca ADB.

- Worker CI trên `cf93a10` lộ lỗi WebSocket ngắt kết nối nhưng còn báo online. Tái hiện cục bộ với test API. Khi handler bị hủy lúc chờ heartbeat kết thúc, bước dọn phiên có thể bị bỏ qua. Đã dọn kết nối, quyền điều khiển và trạng thái pending trước khi chờ heartbeat. Ca hủy xác định cho kết quả FAIL trên mã cũ và PASS trên mã mới. Nhóm kiểm thử endpoint và Android smoke đạt cục bộ.

### 2026-11-24 · PR #173 · Chứng chỉ Authenticode riêng cho Preview

- Preview dùng `orion-desktop-signing`. Stable dùng environment riêng trên main. Runner xác minh public CER và PFX theo fingerprint SHA-256, ký có timestamp, xóa PFX/khóa đã import, rồi thử đúng NSIS với Authenticode, checksum và rollback. Trust của Preview chỉ được thêm tạm trên runner dùng một lần. Gate bảy job cùng SHA giữ nguyên.
- Hướng dẫn tạo khóa, bảo vệ và sao lưu PFX, cấu hình GitHub, chạy lại release và bootstrap Windows nằm ở [quy trình ký Preview](PREVIEW_SIGNING.md). Kiểm bootstrap không chạy installer.
- PASS cục bộ với chứng chỉ tạm: tạo và mở PFX, runner nhận đúng signer pin, từ chối fingerprint sai, PFX đưa nhầm vào luồng CER, NSIS chưa ký, sai checksum, phiên bản ngang bản đang có và trust Preview trên Stable. PowerShell, YAML và cú pháp Bash đạt. PENDING_MANUAL: cấu hình khóa thật của chủ repo, chạy Release kiểm NSIS đã ký trên runner và bootstrap trong cửa sổ bảo trì. Không chỉnh certificate store hoặc Host đang chạy trong phiên kiểm thử.

### 2026-11-25 · PR #173 · Timestamp ký Preview và phục hồi IME trên Android

- Run 45384516105 vào được bước ký với cấu hình hiện có. SignTool từ chối URL HTTPS của DigiCert. Đổi sang endpoint HTTP RFC 3161 DigiCert công bố, giữ SHA-256 và bắt buộc chứng thực timestamp, Authenticode, signer pin, checksum, cài thử và rollback.
- Android run 45384530164 có lúc ADB ngắt sau khi `dumpsys input_method` đã ghi một phần stdout. Hệ thống cũ coi có stdout là lỗi ứng dụng và bỏ qua thử lại. Smoke bỏ phần stdout của lần exit 255 không có stderr, kiểm lại transport và chỉ thử lại một lần với thao tác được đánh dấu an toàn. Lần thử lại vẫn thất bại thì bài test thất bại.
- PASS cục bộ: 11 ca Android smoke/rollback, Ruff, PowerShell AST và kiểm tra các chốt phát hành. DigiCert trả trạng thái RFC 3161 Granted cho digest SHA-256 thử nghiệm. Chữ ký và nghiệm thu đúng NSIS còn phụ thuộc lượt Release trên GitHub. Cấu hình chứng chỉ hiện có và Host đang dùng không bị chỉnh.
