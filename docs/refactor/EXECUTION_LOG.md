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
