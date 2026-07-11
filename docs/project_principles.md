# Project Principles
## Mục tiêu
Xây dựng một Infrastructure AI Agent tối giản, stateless, evidence-driven.

Mọi quyết định phải phục vụ mục tiêu hoàn thành MVP trước khi tối ưu.

---
# Core Principles

## 1. Simplicity First
Luôn ưu tiên giải pháp đơn giản nhất.
Không thêm abstraction nếu chưa thực sự cần.

## 2. Single Responsibility
Mỗi component chỉ có một trách nhiệm duy nhất.
Không trộn nhiều vai trò vào cùng một component.

## 3. Code Investigates. AI Explains.
Investigation là deterministic, thuộc về code.
AI chỉ interpret evidence đã collected.

## 4. Stateless
Mỗi investigation là độc lập.
Execution state chỉ tồn tại trong một request.

## 5. Evidence First
Better Tool → Better Evidence → Better Assessment.
Không compensate poor evidence với prompt engineering.

## 6. Deterministic Before AI
Luôn ưu tiên deterministic logic.
AI chỉ được dùng khi deterministic không đủ.

## 7. MVP First
Làm cho hệ thống chạy trước.
Sau đó mới:
- Refactor
- Optimize
- Extend
Không thiết kế cho nhu cầu chưa tồn tại.

## 8. Explicit Over Implicit
Mọi component phải có:
- Responsibility rõ ràng
- Boundary rõ ràng
- Dependency rõ ràng

## 9. Low Coupling
Component chỉ giao tiếp thông qua contract.
Không truy cập trực tiếp implementation của component khác.

## 10. Benchmark-Driven
Mọi cải tiến phải được validate bằng benchmark.
Không tối ưu dựa trên giả định.

---
# Design Rules
- Đơn giản hơn phức tạp.
- Rõ ràng hơn thông minh.
- Ít abstraction hơn nhiều abstraction.
- Ít dependency hơn nhiều dependency.
- Có thể chạy quan trọng hơn thiết kế đẹp.
- Không tối ưu sớm.
- Không over-engineering.

---
# Out of Scope
Không triển khai nếu chưa có nhu cầu thực tế:
- Plugin System
- Search Engine
- Embedding
- Cache
- Scheduler
- Distributed Runtime
- Workflow Engine
- Multi-Agent

---
# Success Criteria
Một thay đổi được coi là tốt khi:
- Kiến trúc đơn giản hơn.
- Trách nhiệm rõ ràng hơn.
- Ít coupling hơn.
- Dễ đọc hơn.
- Dễ kiểm thử hơn.
- Không làm tăng độ phức tạp không cần thiết.
- Benchmark evidence cho thấy cải thiện.
