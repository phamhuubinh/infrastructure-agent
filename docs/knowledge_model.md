# Knowledge
## Mục tiêu
Knowledge cung cấp thông tin cho Reasoning Model thông qua Knowledge Tool.
Knowledge được chia thành:
- Stable Information
- Runtime Information
---
# Stable Information
Stable Information là dữ liệu thay đổi ít.
Ví dụ:
- Operating System
- Hardware
- Network Inventory
- Installed Software
- Repository Information
- Docker Inventory
- VMware Inventory
Stable Information được lưu trong Stable Store.
Collector chịu trách nhiệm tạo và cập nhật.
---
# Runtime Information
Runtime Information là dữ liệu chỉ tồn tại trong một Reasoning Session.
Ví dụ:
- Tool Result
- Command Output
- API Response
- Observation
Runtime Information không được lưu lâu dài.
---
# Knowledge Tool
Knowledge Tool là giao diện duy nhất để truy cập Knowledge.
Reasoning Model không truy cập trực tiếp:
- Stable Store
- Collector
- Operating System
Reasoning Model chỉ giao tiếp với Knowledge Tool.
---
# Responsibilities
Knowledge Tool chịu trách nhiệm:
- Đọc Stable Information.
- Trả dữ liệu theo yêu cầu.
- Yêu cầu Collector cập nhật dữ liệu khi cần.
- Trả Knowledge Result.
---
# Non-Responsibilities
Knowledge Tool không:
- Reasoning.
- Phân tích dữ liệu.
- Quyết định cần dữ liệu gì.
- Thu thập dữ liệu trực tiếp.
---
# Data Flow
```
Reasoning Model
        │
            ▼
Knowledge Tool
        │
 ┌──────┴──────┐
 ▼                   ▼
Stable Store  Collector
```
- Knowledge Tool mặc định đọc từ Stable Store. Collector chỉ được gọi khi cần cập nhật (refresh) dữ liệu.
---
# Constraints
- Stateless.
- Không cache Working Context.
- Không chứa Business Logic.
- Không quyết định khi nào refresh dữ liệu.
---
# Design Goal
Knowledge là lớp truy cập dữ liệu duy nhất của hệ thống.
Mọi thay đổi về nơi lưu trữ hoặc cách thu thập dữ liệu không được ảnh hưởng đến Reasoning Model.
