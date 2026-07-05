# Project Principles
## Mục tiêu
Xây dựng một AI Agent tối giản, stateless, dễ hiểu, dễ bảo trì và dễ mở rộng.
Mọi quyết định phải phục vụ mục tiêu hoàn thành MVP trước khi tối ưu.
---
# Core Principles
## 1. Simplicity First
Luôn ưu tiên giải pháp đơn giản nhất.
Không thêm abstraction nếu chưa thực sự cần.
---
## 2. Single Responsibility
Mỗi component chỉ có một trách nhiệm duy nhất.
Không trộn nhiều vai trò vào cùng một component.
---
## 3. Model-Driven
Reasoning chỉ thuộc về Reasoning Model.
Model quyết định:
- cần thông tin gì
- sử dụng tool nào
- khi nào kết thúc reasoning
---
## 4. Stateless
Reasoning Session không lưu trạng thái.
Working Context chỉ tồn tại trong một session.
Chỉ Stable Information mới được lưu lâu dài.
---
## 5. Separation of Concerns
Reasoning và Data Collection là hai bài toán khác nhau.
Model không thu thập dữ liệu.
Collector không reasoning.
Tool không reasoning.
Agent không reasoning.
---
## 6. Stable Before Dynamic
Ưu tiên sử dụng Stable Information trước.
Chỉ thu thập dữ liệu mới khi thực sự cần.
---
## 7. MVP First
Làm cho hệ thống chạy trước.
Sau đó mới:
- Refactor
- Optimize
- Extend
Không thiết kế cho nhu cầu chưa tồn tại.
---
## 8. Explicit Over Implicit
Mọi component phải có:
- Responsibility rõ ràng
- Boundary rõ ràng
- Dependency rõ ràng
Không suy diễn.
---
## 9. Low Coupling
Component chỉ giao tiếp thông qua contract.
Không truy cập trực tiếp implementation của component khác.
---
## 10. Documentation First
Kiến trúc được thống nhất trong tài liệu trước.
Code phải phản ánh tài liệu.
Không để code trở thành nguồn sự thật duy nhất.
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
---
# Success Criteria
Một thay đổi được coi là tốt khi:
- Kiến trúc đơn giản hơn.
- Trách nhiệm rõ ràng hơn.
- Ít coupling hơn.
- Dễ đọc hơn.
- Dễ kiểm thử hơn.
- Không làm tăng độ phức tạp không cần thiết.
