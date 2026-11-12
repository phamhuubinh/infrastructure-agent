# Orion trên Linux headless

Cần Python 3.12 trở lên. Cài wheel backend hoặc cài từ checkout trong môi trường
riêng. Các bước này dùng dependencies lõi và các skill đi kèm wheel.

```sh
python3 -m venv "$HOME/.local/share/orion-install/.venv"
. "$HOME/.local/share/orion-install/.venv/bin/activate"
python -m pip install ./backend  # Từ checkout. Với wheel, thay ./backend bằng đường dẫn wheel.
orion serve
```

`orion serve` giữ foreground, chạy API tại `http://127.0.0.1:61888` mặc định và
xử lý shutdown khi nhận SIGINT hoặc SIGTERM. Nó chạy với Python và không cần
display, browser, Node, UI bundle hay E5. Nếu bản cài có UI bundle, cùng service
cũng phục vụ UI. `orion web` vẫn là lệnh mở giao diện web.

Dùng một tài khoản Linux riêng cho service nếu máy có nhiều người dùng. Mọi tiến
trình truy cập được cổng loopback đều thuộc ranh giới tin cậy của chế độ local.
Đặt `ORION_DATA_DIR` nếu cần thư mục dữ liệu khác. Database, file đính kèm, cấu hình
và log mặc định ở `~/.local/share/orion` (hoặc `$XDG_DATA_HOME/orion`).

## Chạy bằng systemd

Unit user dùng đường dẫn mặc định ở trên. Nếu cài vào prefix khác, sửa `ExecStart`
trong bản copy trước khi nạp unit.

```sh
install -Dm 644 scripts/linux/orion.service "$HOME/.config/systemd/user/orion.service"
systemctl --user daemon-reload
systemctl --user enable --now orion.service
journalctl --user -u orion.service
orion doctor --json
```

Unit chạy theo vòng đời của user manager. Để chạy từ lúc boot và qua các lần
đăng xuất, bật linger cho tài khoản dịch vụ bằng `loginctl enable-linger`.

Để cập nhật, dừng service, cài wheel mới vào cùng venv rồi khởi động lại. Sao lưu
dữ liệu theo [quy trình backup](../architecture/DATA_AND_PERSISTENCE.md) trước khi
đổi phiên bản. Để gỡ cài đặt, chạy `systemctl --user disable --now orion.service`,
xóa bản unit trong `~/.config/systemd/user`, chạy `systemctl --user daemon-reload`
và gỡ venv cài đặt. Dữ liệu ứng dụng có vòng đời riêng.

## Dùng terminal

```sh
orion doctor --json
orion profile list
orion profile create --input-file profile.json
orion profile activate PROFILE_ID
orion project list
orion run --prompt-file prompt.txt --project PROJECT_ID --json
printf '%s\n' 'Tiếp tục từ kết quả trước' | orion chat --session SESSION_ID
orion api skill list --session SESSION_ID
orion api mcp list
orion target
orion command list --session SESSION_ID
orion command status COMMAND_ID --session SESSION_ID --stdout-offset 0
orion command cancel COMMAND_ID --session SESSION_ID
```

`profile create` nhận DTO `ModelConfigInput` của API. Dùng profile provider-native
theo [cấu hình provider](CONFIGURATION.md), lưu file chứa credential với quyền riêng
hoặc dùng `--input-file -` để cấp JSON qua stdin. Session mới dùng `read_only`.
`orion session mode SESSION_ID --mode confirm` cho phép Orion hỏi trước khi chạy
lệnh cần duyệt. Quan sát request hoặc thao tác ở terminal thứ hai để xem payload
đang chờ và gửi quyết định gắn với hash của payload.

```sh
orion request payload REQUEST_ID --session SESSION_ID --call CALL_ID
orion request allow REQUEST_ID --session SESSION_ID --call CALL_ID --payload-hash HASH
orion request status REQUEST_ID
orion request watch REQUEST_ID --after EVENT_ID --json
orion request cancel REQUEST_ID
```

`chat` và `run` mỗi lần nhận một prompt UTF-8 từ stdin hoặc `--prompt-file`.
Chế độ thường in nội dung assistant đã chốt ra stdout, cùng thông tin theo dõi ra
stderr. `--json` in từng record NDJSON theo thứ tự submission, admission, event
và status. Event có thể chứa delta tạm thời. Dùng `event_id` cuối cùng làm
`--after` để nối lại. Nếu chưa nhận được request ID, có thể chạy lại với đúng
`--session`, `--client-request-id` và nội dung prompt ban đầu. Chỉ retry theo
bộ ba này khi muốn tiếp tục cùng một lần gửi.

Ctrl+C khi gửi hoặc chờ kết quả yêu cầu server hủy đúng admission. Nếu trạng
thái trả về còn `running`, dùng `request status` để quan sát kết quả cuối.
Ctrl+C với `request watch` chỉ dừng quan sát. Mã thoát của chat/run/watch là
`0` khi completed, `1` khi failed hoặc lỗi giao tiếp, `2` khi cú pháp sai,
`3` khi incomplete, và `130` khi cancelled hoặc Ctrl+C.

## Server từ xa

Dùng [cấu hình HTTPS và xác thực](REMOTE_ACCESS.md) hiện hành. Chọn một origin
với `--server https://orion.example.org` hoặc `ORION_SERVER`. Thêm `--login` để
nhập mật khẩu chủ sở hữu trên terminal, hoặc `--enroll` để nhập mã dùng một lần
từ Settings. Thông tin đăng nhập của hai luồng này nằm trong bộ nhớ và CLI gửi
yêu cầu thu hồi khi kết thúc. Automation có thể cấp bearer token ngắn hạn từ kho
secret qua `ORION_CLI_ACCESS_TOKEN`. CLI xác minh TLS, cố định origin và từ chối
redirect. HTTP chỉ được hỗ trợ với địa chỉ IP loopback.
