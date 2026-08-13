# Project Principles

## Mục tiêu hiện tại

Orion là ứng dụng điều tra hạ tầng local, single-operator, deterministic và
evidence-driven; phân tích tài liệu RAG là một luồng project riêng biệt.

## Nguyên tắc

### 1. Code investigates. AI explains.

Code quyết định routing, target, source, parameter, capability, execution,
recovery, evidence validity và rule. Model chỉ giải thích evidence hoặc xử lý
general chat không có quyền gọi tool.

### 2. Evidence first

Ưu tiên theo thứ tự Tool -> Evidence -> Assessment. Không dùng prompt để che
lấp evidence thiếu, lỗi hoặc stale.

### 3. Deterministic before AI

Logic có thể kiểm thử và lặp lại được phải nằm trong code/config đã review.

### 4. Trách nhiệm rõ ràng

- `DeterministicAgent`: routing và response orchestration.
- `ExecutionEngine`: điều tra hạ tầng.
- `KnowledgeTool`: capability routing và dispatch.
- Child Tool: thu thập evidence trong một domain.
- Assessment Model: giải thích evidence.
- RAG service: phân tích corpus của project được chọn.

### 5. Execution state là tạm thời

Command, raw observation, DAG và runtime state chỉ tồn tại trong một lần điều
tra. Session chỉ lưu conversation, summary và semantic context có kiểu; cache
chỉ tái sử dụng evidence hợp lệ và còn fresh.

### 6. Explicit over implicit

Contract, status, unit, provenance, failure và boundary phải được biểu diễn rõ.
Không suy diễn success từ giá trị rỗng hoặc lỗi dạng text.

### 7. Simplicity and low coupling

Tái sử dụng abstraction đang có, giữ dependency một chiều, tránh pattern hoặc
dependency không giải quyết vấn đề hiện tại.

### 8. Current-state documentation

Tài liệu mô tả đúng code/config/test hiện tại. Không lưu roadmap, backlog,
target architecture hoặc feature chưa triển khai trong tài liệu hoạt động.

## Tiêu chí cho một thay đổi

- Đúng phạm vi yêu cầu và giữ nguyên public contract ngoài phạm vi đó.
- Không phá vỡ boundary giữa model, pipeline và tool.
- Failure/unknown không bị chuyển thành kết quả khỏe mạnh.
- Có validation phù hợp với mức rủi ro và được báo cáo chính xác.
- Diff không chứa refactor hoặc tài liệu không liên quan.
