# Orion — Kế hoạch Dọn dẹp & Tái cấu trúc (Blueprint)

> Kế hoạch từng bước cho người không biết code.
> Mỗi Phase là một nhóm công việc. Mỗi Task làm xong là dừng, kiểm tra, rồi mới sang task tiếp theo.

---

## Phase 0: Chẩn đoán & Chuẩn bị (1-2 ngày)

### Task 0.1 — Kiểm tra xem code có chạy được không
**Mục tiêu:** Biết chắc rằng dự án đang ở trạng thái "chạy được" trước khi động vào.
**Người không code có thể kiểm tra bằng cách:**
- Chạy `make test` — nếu không có lỗi đỏ là ổn
- Chạy `make lint` — nếu không có lỗi là ổn
**Nếu có lỗi:** Ghi lại lỗi, báo cho người code sửa trước.

**Kết quả kiểm tra (2026-07-19):**
- `make lint`: **FAILED** — 1847 lỗi (hầu hết là type annotation, unused import, formatting)
- `make test`: **FAILED** — 1 test failure:
  - `tests/backend/test_app.py::test_dify_knowledge_query_returns_results` — gọi sai URL path `/api/dify/knowledge/query`, route thực tế là `/api/knowledge/query`. Cùng lỗi ở test_dify_knowledge_missing_query và test_dify_knowledge_handles_error (dòng 163, 175, 186).
- Hướng xử lý: Sửa URL path trong test, sau đó chạy `ruff check --fix` và `ruff format` để xử lý các lỗi lint cơ bản.

### Task 0.2 — Sao lưu toàn bộ dự án
**Mục tiêu:** Có bản backup phòng khi làm hỏng.
**Cách làm:**
```bash
cd ~/Orion_agent && tar czf ~/orion_backup_before_cleanup.tar.gz .
```
File backup này để ở `~/` không đụng vào nữa.

### Task 0.3 — Xóa file rác
**Mục tiêu:** Dự án sạch sẽ, không có file thừa.
**Cần xóa:**
- `report.json`, `report_v2.json`, `report_acceptance.json` — báo cáo benchmark cũ
- `run_tests.py`, `run_tests_v2.py`, `run_acceptance.py` — script chạy test cũ (đã có `make test`)
- `orion.egg-info/` — thư mục build cũ
