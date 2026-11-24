# Ký và cài bootstrap Orion Preview

Dùng chứng chỉ Authenticode tự ký dành riêng cho Orion Preview khi cập nhật các máy Windows của mình. Chứng chỉ chỉ có quyền ký mã, hết hạn sau hai năm và không cấp chứng chỉ khác. Mỗi máy xác minh SHA-256 của chứng chỉ từ bản gốc do chủ khóa giữ rồi tin cậy bản `.cer` cho đúng tài khoản Windows dùng Orion. Windows xác minh Authenticode và Orion kiểm tra thêm fingerprint đã đóng vào ứng dụng, SHA-256 của NSIS và phiên bản. SmartScreen có thể vẫn báo ứng dụng mới. Nếu chính sách máy chặn bộ cài, dừng và kiểm tra chính sách với người quản trị máy. [Microsoft SignTool](https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool)

## Tạo và cất khóa một lần

Tại thư mục repo đã đối chiếu với PR #173, chạy bằng PowerShell 7 dưới tài khoản Windows của người giữ khóa. Dùng mật khẩu mới do trình quản lý mật khẩu tạo, ít nhất 24 ký tự. Lưu lại đường dẫn `$keys` từ buổi thiết lập.

```powershell
$keys = & ./scripts/desktop/new-preview-signer.ps1
Get-Content -LiteralPath (Join-Path $keys 'ORION_UPDATE_SIGNER_SHA256.txt')
```

Script tạo RSA 3072 và lưu trong thư mục riêng dưới `%LOCALAPPDATA%\OrionSigning`. Bản `OrionPreview.cer` và fingerprint là công khai. Giữ `OrionPreview.pfx` trong bản sao lưu mã hóa ngoại tuyến và lưu mật khẩu riêng trong trình quản lý mật khẩu. Giữ ít nhất một bản sao có thể phục hồi. Thử mở bản sao bằng mật khẩu trên Windows cô lập và xác nhận fingerprint trước khi xóa bản làm việc. Khóa riêng, PFX, Base64 của PFX và mật khẩu chỉ đi vào kho bí mật được chỉ định, không đưa vào Git, PR, artifact, log hay ChatGPT.

## Chủ repo cấu hình GitHub

Vào **Settings → Environments → New environment**, tạo `orion-desktop-signing`. Trong **Deployment branches and tags**, chọn **Selected branches and tags**, rồi thêm quy tắc loại **Branch** chính xác `codex/orion-windows-acceptance`. Giới hạn người có thể đẩy vào nhánh ký. Nếu có người duyệt độc lập, dùng **Required reviewers** để khóa chưa được cấp vào job trước khi duyệt. Với repo dùng một mình, giữ quyền ghi nhánh cho đúng tài khoản quản trị repo. [GitHub Environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)

| Mục trong environment | Tên | Giá trị |
| --- | --- | --- |
| Environment variable | `ORION_UPDATE_SIGNER_SHA256` | 64 ký tự hex từ `ORION_UPDATE_SIGNER_SHA256.txt`. |
| Environment variable | `ORION_PREVIEW_CERT_B64` | Base64 một dòng của `OrionPreview.cer` công khai. |
| Environment secret | `ORION_SIGNING_PFX_B64` | Base64 một dòng của `OrionPreview.pfx`. |
| Environment secret | `ORION_SIGNING_PFX_PASSWORD` | Mật khẩu đã dùng khi tạo PFX. |

In riêng Base64 của **chứng chỉ công khai** để dán vào ô variable. Nếu có GitHub CLI đã đăng nhập bằng tài khoản chủ repo, hai lệnh sau gửi secrets qua stdin và nhập ẩn. Dùng PowerShell 7 trên máy giữ khóa, không bật transcript hoặc ghi lại clipboard. Có thể nhập secrets trực tiếp vào **Environment secrets** trên GitHub nếu dùng trình quản lý bí mật để cung cấp giá trị. [GitHub CLI](https://cli.github.com/manual/gh_secret_set)

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $keys 'OrionPreview.cer')))
[Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $keys 'OrionPreview.pfx'))) |
    gh secret set ORION_SIGNING_PFX_B64 --env orion-desktop-signing --repo phamhuubinh/infrastructure-agent
gh secret set ORION_SIGNING_PFX_PASSWORD --env orion-desktop-signing --repo phamhuubinh/infrastructure-agent
```

Stable dùng `orion-desktop-stable-signing`, giới hạn `main`, với publisher riêng đã được Windows tin cậy và ba trường fingerprint/PFX/mật khẩu tương ứng. Chứng chỉ tự ký cá nhân ở trên chỉ dành cho Preview. Tránh đặt khóa ký ở Repository secrets để job dùng khóa luôn chịu giới hạn của environment.

## Chạy Release và kiểm đúng NSIS

Trong **Actions → Release bundles**, mở lượt push của commit đã có thay đổi hỗ trợ chứng chỉ Preview. Sau khi lưu environment, nếu lượt đó thất bại do thiếu signing, chọn **Re-run failed jobs** trên chính lượt đó. Nếu lượt còn chạy, để job dùng environment đã cấu hình hoặc chạy lại phần thất bại sau khi lượt kết thúc. Dùng SHA có đủ bảy job push CI thành công. Runner Windows dùng một lần ký, gắn timestamp, xác minh đúng publisher, xóa bản PFX và khóa đã import, rồi chạy thử cài và rollback với đúng NSIS. Job chỉ xuất bản khi toàn bộ quy trình đạt. Tải `Orion_<version>_x64-setup.exe` và `DESKTOP-SHA256SUMS` từ cùng bản Preview đã qua workflow. [GitHub Actions](https://github.com/phamhuubinh/infrastructure-agent/actions/workflows/release.yml)

## Bootstrap một lần trên Windows Host

1. Chuyển bản `.cer` gốc và fingerprint đã lưu từ máy giữ khóa sang tài khoản Windows đang chạy Orion. Dùng giá trị SHA-256 của đúng tên NSIS trong `DESKTOP-SHA256SUMS` của bản Preview đã được CI nghiệm thu. Chạy lệnh kiểm dưới đây với đường dẫn thật. Lệnh kiểm checksum trước khi thêm trust và chỉ tin cậy chứng chỉ này trong `CurrentUser`. Nếu thêm trust rồi xác minh thất bại, script cố gỡ chứng chỉ vừa thêm. Lệnh không khởi chạy NSIS.

   ```powershell
   & ./scripts/desktop/test-preview-bootstrap.ps1 `
       -Installer $installer -Certificate $publicCer -SignerSha256 $fingerprint `
       -InstallerSha256 $installerSha256 -TrustPreviewCertificate
   ```

2. Chọn cửa sổ bảo trì. Xác minh phiên bản Preview mới hơn bản đang chạy và Orion dùng đường dẫn mặc định `%LOCALAPPDATA%\Orion`. Chờ lượt đang chạy hoàn tất, sao lưu mới theo [quy trình backup và rollback](UPGRADE_8EB4AD2.md), kiểm bản backup rồi tự dừng Host sạch. Dùng `--online-only` khi chụp snapshot để ghi trạng thái Serve/Funnel đang có. Giữ nguyên cấu hình mạng đang sử dụng. Mở đúng NSIS đã kiểm và cài vào cùng thư mục, dưới cùng tài khoản Windows. Mở lại Orion, xác nhận Host và Chat/Projects, rồi tự kiểm Owner MFA cần thiết.

   Dùng Python đã cài dependencies backend của Orion. Lệnh đầu in đường dẫn snapshot sau khi diễn tập khôi phục đạt. Dùng đúng đường dẫn đó ở lệnh kiểm lại.

   ```powershell
   $env:PYTHONPATH = (Resolve-Path './backend/src').Path
   python scripts/windows/upgrade_readiness.py --snapshot (Join-Path $env:LOCALAPPDATA 'OrionRecovery') --online-only
   python scripts/windows/upgrade_readiness.py --verify '<đường dẫn snapshot ở dòng PASS>'
   ```

3. Chọn **Preview** trong **Cài đặt → Cập nhật Orion** nếu ứng dụng từng lưu kênh khác. Những lần sau, bấm **Cập nhật ngay → Đồng ý**. Orion thực hiện tải, xác minh, sao lưu, cài và rollback từ giao diện.

Nếu khóa bị lộ, tắt môi trường ký, xóa secrets Preview bị ảnh hưởng và bỏ trust của đúng chứng chỉ cũ trong `certmgr.msc` dưới tài khoản chạy Orion. Tạo khóa mới rồi làm lại bootstrap với fingerprint mới. Lên lịch đổi khóa trước khi chứng chỉ hết hạn vì bản đang cài cố định fingerprint cũ.
