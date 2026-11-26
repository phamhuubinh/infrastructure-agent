# Phát hành Orion Preview trên Windows

Preview được build, ký và nghiệm thu trên máy local. GitHub Release lưu đúng bộ NSIS đã qua nghiệm thu cùng tệp SHA-256. Bản Preview dùng tag `orion-preview-vX.Y.Z`, được đánh dấu prerelease và dùng chung thứ tự phiên bản tăng dần với Stable. Phiên bản của bộ cài mới phải cao hơn phiên bản nguồn và mọi bản Windows đã phát hành. Bootstrap cho nguồn `0.1.5` là Orion Preview `0.1.6`.

## Build từ commit sạch

Cần Windows x64, PowerShell 7, Python và Node theo các pin trong repo, Rust theo `ui/src-tauri/rust-toolchain.toml`, bộ công cụ Windows cho target x64, Windows SDK SignTool và GitHub CLI đã xác thực. Dùng checkout mới cho mỗi ứng viên để build không lấy nhầm wheel, sidecar hoặc NSIS cũ. Chạy các bài kiểm theo [phạm vi thay đổi](CI_EVIDENCE.md).

Trên máy build, dùng bản CER và SHA-256 đã lưu từ buổi thiết lập chứng chỉ Orion Preview. Nếu cần mở lại PFX gốc, dùng trình nhập chứng chỉ Windows dưới tài khoản người ký và chọn **Current User → Personal**. Giữ PFX và mật khẩu trong kho riêng. Chỉ chuyển CER công khai sang guest.

```powershell
$version = '0.1.6'
$pin = (Get-Content -LiteralPath $fingerprintFile -Raw).Trim()
$commit = (git rev-parse HEAD).Trim()
& ./scripts/desktop/build-update.ps1 -Source $commit -Version $version -Channel preview -SignerSha256 $pin
$out = (Resolve-Path ./release-work/desktop-update).Path
& ./scripts/desktop/sign-preview.ps1 -Directory $out -Certificate $publicCer -SignTool $signTool
```

Ký bằng khóa đã mở trong `Cert:\CurrentUser\My`. SignTool dùng SHA-256 và timestamp RFC 3161. Build ghi `build.json` để ràng buộc nguồn, phiên bản, signer pin và digest trước khi ký. Script ký tạo `DESKTOP-SHA256SUMS` từ bộ cài sau khi ký.

## Nghiệm thu đúng bộ cài đã ký

Dùng Windows Sandbox hoặc VM Windows x64 dùng một lần, có desktop tương tác, WebView2, Git, PowerShell 7 và Python với dependencies backend đã khóa. Có thể cài dependencies bằng `python -m pip install --require-hashes -r scripts/refactor/locks/core.txt`. Checkout sạch cùng commit trong guest. Đưa vào guest bộ cài, checksum, `build.json` và CER công khai. Để thư mục dữ liệu, registry và tài khoản Host thật ngoài môi trường này. Ưu tiên thư mục chia sẻ chỉ đọc cho đầu vào và thư mục trống riêng để xuất kết quả.

```powershell
& ./scripts/desktop/exercise-signed-update.ps1 -DisposableGuest `
    -Installer $installer -Certificate $publicCer -Evidence $evidence
```

Bài nghiệm thu kiểm Authenticode, timestamp, signer pin, SHA-256 và phiên bản trước khi cài. Sau khi cài bootstrap, nó chạy handoff thật với cùng NSIS trong ca cài thành công và ca giả lập lỗi để khôi phục. Cả hai ca yêu cầu SQLite, DPAPI, Owner MFA, cài đặt Host và autostart được bảo toàn. Giữ tệp bằng chứng JSON sinh sau khi hai ca đạt, rồi hủy guest. [Windows Sandbox](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-overview)

## Phát hành

Đẩy commit nguồn lên GitHub rồi chạy từ chính checkout build. Script đối chiếu bộ cài với bằng chứng guest, kiểm phiên bản và phát hành hai tệp `Orion_<version>_x64-setup.exe` và `DESKTOP-SHA256SUMS`. Xác nhận trang Release có đủ hai tệp và digest NSIS trên GitHub API khớp kết quả local.

```powershell
& ./scripts/desktop/publish-preview.ps1 -Directory $out -Evidence $evidence
```

## Bootstrap một lần trên Windows Host

1. Dùng đúng CER và fingerprint gốc. Lấy SHA-256 của tên NSIS tương ứng từ `DESKTOP-SHA256SUMS` trên Release. Script sau kiểm phiên bản đang cài và Authenticode, rồi chỉ thêm trust cho đúng chứng chỉ vào tài khoản Windows chạy Orion. Nếu xác minh sau khi thêm trust thất bại, script gỡ trust vừa thêm.

   ```powershell
   & ./scripts/desktop/test-preview-bootstrap.ps1 `
       -Installer $installer -Certificate $publicCer -SignerSha256 $pin `
       -InstallerSha256 $installerSha256 -TrustPreviewCertificate
   ```

2. Trong cửa sổ bảo trì do chủ máy chọn, xác minh [backup và rollback](UPGRADE_8EB4AD2.md). `upgrade_readiness.py --snapshot <thư-mục-backup> --online-only` ghi nhận cả cấu hình Serve/Funnel đang dùng. Chạy `upgrade_readiness.py --verify <snapshot>` trước khi chủ máy dừng Host sạch và cài đúng NSIS vào vị trí mặc định `%LOCALAPPDATA%\Orion` dưới cùng tài khoản. Mở lại Orion và xác minh Chat, Projects và Owner MFA.
3. Chọn **Preview** trong **Cài đặt → Cập nhật Orion** nếu ứng dụng đang ở kênh khác. Những lần sau, bấm **Cập nhật ngay → Đồng ý**. Orion tự tải, xác minh, sao lưu, cài và rollback từ giao diện.

Nếu nghi khóa bị lộ, dừng phát hành Preview và bỏ trust của đúng chứng chỉ cũ trên các máy đã bootstrap. Ứng dụng ghim fingerprint của chứng chỉ khi build, nên việc đổi chứng chỉ cần bootstrap mới.
