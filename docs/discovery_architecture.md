# Discovery Architecture
## Mục tiêu
Discovery chịu trách nhiệm thu thập dữ liệu từ môi trường và chuyển thành Knowledge.
Discovery không reasoning.
Discovery không quyết định cần thu thập dữ liệu gì.
---
# Responsibilities
Discovery chịu trách nhiệm:
- Thu thập dữ liệu.
- Chuẩn hóa dữ liệu.
- Tạo hoặc cập nhật Stable Information.
- Thu thập dữ liệu.
- Chuẩn hóa dữ liệu.
- Tạo hoặc cập nhật Stable Information.
---
# Non-Responsibilities
Discovery không:
- Reasoning.
- Quyết định workflow.
- Phân tích dữ liệu.
- Trả lời người dùng.
- Quản lý Reasoning Session.
---
# Discovery Flow
```
Environment
      │
         ▼
Collector
         ↓
Raw Data
         ↓
Normalizer
         ↓
Stable Information
      │
         ▼
Stable Store
```
---
# Components
## Collector
Thu thập dữ liệu từ:
- Linux
- Docker
- VMware
- Git
- Repository
- Operating System
Collector chỉ lấy dữ liệu.
---
## Normalizer
Chuẩn hóa dữ liệu thành cùng một định dạng.
Không thêm dữ liệu mới.
Không suy luận.
---
## Stable Store
Lưu dữ liệu ổn định.
Ví dụ:
- Hardware
- Operating System
- Installed Software
- Docker Inventory
- Repository Information
---
# Communication
```
Knowledge Tool
        │
            ▼
Collector
        │
            ▼
Environment
```
Collector không giao tiếp trực tiếp với:
- Reasoning Model
- Agent
---
# Design Rules
- Discovery chỉ thu thập dữ liệu.
- Không reasoning.
- Không cache Working Context.
- Không chứa Business Logic.
- Không phụ thuộc Reasoning Model.
---
# Constraints
- Stateless.
- Có thể chạy độc lập.
- Có thể chạy theo lịch.
- Có thể chạy theo yêu cầu.
- Có thể mở rộng bằng Collector mới.
---
# Design Goal
Discovery là lớp Data Collection duy nhất của hệ thống.
Việc thay đổi nguồn dữ liệu hoặc cách thu thập không được ảnh hưởng đến:
- Reasoning Model
- Agent
- Runtime
- Tool Contract
