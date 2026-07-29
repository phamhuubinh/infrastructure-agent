# PROJECT_CONTEXT.md — Orion

File này là "hiến pháp" cho THINK. Nó đọc file này trước mỗi TaskSpec, trước mỗi directive,
và trong discovery pass. Sửa trực tiếp file này khi định hướng thay đổi — không cần nhắc lại
mỗi lần chat.

## 1. Orion là gì
<!-- TODO: 2-3 câu: pipeline giám sát hạ tầng, deterministic investigation + LLM-only assessment
ở bước cuối. -->

## 2. Kiến trúc hiện tại (tóm tắt, không cần chi tiết)
<!-- TODO: các thành phần chính, vd Normalizer, ToolSelector, DeterministicResponder,
investigation pipeline, UI (ui/), backend (src/). -->

## 3. Quyết định ĐÃ CHỐT — làm theo hướng nào
<!-- Ví dụ format:
- Orchestrator: dùng mô hình Think/Reviewer/Coder 3 vai, KHÔNG làm multi-agent 5 vai
  (Planner/Research/Reviewer/QA Agent/Coder) như đề xuất trong tài liệu kiến trúc — lý do:
  quy mô dự án cá nhân, 3 vai đã đủ, thêm vai chỉ tăng độ trễ và điểm lỗi.
- Checkpoint/rollback: dùng git reset --hard theo checkpoint, KHÔNG dùng git worktree/branch
  riêng — lý do: đơn giản, đủ dùng với repo hiện tại.
-->

## 4. Cân nhắc nhưng CHƯA làm / không làm (và vì sao)
<!-- Ví dụ:
- Working memory / indexer (architecture graph, dependency graph) — CHƯA làm, THINK hiện đọc
  trực tiếp file cần thiết mỗi vòng thay vì có index sẵn. Cân nhắc lại khi repo lớn hơn.
- QA nhiều tầng (build/lint/security/benchmark riêng biệt) — CHƯA làm, hiện chỉ dùng
  orion_qa_runner.py (transcript Q&A) làm tín hiệu chính.
- Web search cache cho THINK — CHƯA làm.
-->

## 5. Việc KHÔNG BAO GIỜ được tự làm mà không hỏi Bình
<!-- Ví dụ:
- Đổi API public / breaking change.
- Xoá file ngoài phạm vi TaskSpec.
- Tự quyết định bỏ qua 1 issue trong backlog vì "không quan trọng" — phải request_human.
-->

## 6. Giới hạn hiện tại của việc kiểm chứng tự động
<!-- Ghi rõ cái gì orion_qa_runner.py KHÔNG kiểm tra được, để THINK biết khi nào phải
request_human thay vì tự tin QA pass. Ví dụ:
- Bug UI/session (vd session rename mất sau F5) không thể hiện qua transcript Q&A —
  cần Bình tự kiểm tra bằng tay hoặc bổ sung công cụ UI test riêng.
-->

## 7. Mục tiêu/tính năng đang hướng tới (để discovery pass so sánh)
<!-- Liệt kê tính năng/UI đã định làm theo BACKLOG.md / IMPLEMENTATION_BACKLOG.md, để THINK
biết "đáng lẽ phải có X" khi tự soi code lúc discovery. -->
