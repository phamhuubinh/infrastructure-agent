# Tool Architecture
## Mục tiêu
Tool là abstraction dùng trong Reasoning Session để tương tác với hệ thống bên ngoài.
Tool thực hiện đúng một Action và trả về đúng một Observation.
---
# Responsibilities
Tool chịu trách nhiệm:
- Thực thi Action.
- Truy cập hệ thống bên ngoài.
- Thu thập dữ liệu.
- Trả Observation.
Ví dụ:
- Local Shell
- SSH
- Docker
- VMware
- Stable Store
---
# Non-Responsibilities
Tool không:
- Reasoning.
- Quyết định Action tiếp theo.
- Phân tích dữ liệu.
- Quản lý workflow.
- Lưu Working Context.
---
# Tool Contract
Mỗi Tool:
- Nhận đúng một Action.
- Thực hiện đúng một nhiệm vụ.
- Trả đúng một Observation.
Tool không gọi Tool khác.
---
# Communication
```
Agent
    │
      ▼
Runtime
    │
      ▼
Tool
    │
      ▼
Environment
```
Tool không giao tiếp trực tiếp với:
- Reasoning Model
- Agent
- Collector
---
# Categories
## Knowledge Tool
Đọc Stable Information.
Ví dụ:
- Hardware
- OS
- Repository
- Docker Inventory
---
## Runtime Tool
Thu thập Runtime Information.
Ví dụ:
- Shell
- SSH
- API
- Docker Command
- VMware API
---
# Constraints
- Stateless.
- Không cache.
- Không reasoning.
- Không chứa Business Logic.
- Không quyết định workflow.
---
# Design Rules
Một Tool chỉ làm một việc.
Nếu cần nhiều bước, Model sẽ sinh nhiều Action.
Không gom nhiều hành động vào một Tool.
---
# Design Goal
Tool là abstraction duy nhất giữa hệ thống và môi trường bên ngoài.
Có thể thay đổi implementation của Tool mà không ảnh hưởng:
- Reasoning Model
- Agent
- Runtime
