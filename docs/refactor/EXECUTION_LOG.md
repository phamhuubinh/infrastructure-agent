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
- Checkpoint: commit của mục này trên nhánh `codex/orion-windows-acceptance`. R21 chờ các điều kiện trên.
