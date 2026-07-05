# Runtime Architecture
## Mục tiêu
Runtime chịu trách nhiệm thực thi Action và trả Observation.
Runtime không reasoning.
Runtime không quyết định workflow.
---
# Responsibilities
Runtime chịu trách nhiệm:
- Thực thi Action.
- Gọi Tool tương ứng.
- Thu thập Observation.
- Trả Observation về Agent.
- Quản lý vòng đời của một lần thực thi.
---
# Non-Responsibilities
Runtime không:
- Reasoning.
- Sinh Action.
- Quyết định Action tiếp theo.
- Phân tích Observation.
- Lưu Working Context.
- Chứa Business Logic.
---
# Runtime Flow
```
Action
    │
      ▼
Runtime
    │
      ▼
Tool
    │
      ▼
Observation
    │
      ▼
Runtime
    │
      ▼
Agent
```
---
# Runtime Components
## Execution Environment
Cung cấp môi trường thực thi cho Tool.
Ví dụ:
- Local Shell
- SSH
- Docker
- VMware
Execution Environment không reasoning.
---
## Lifecycle Manager
Quản lý trạng thái của một lần thực thi.
Ví dụ:
- Created
- Running
- Completed
- Failed
- Cancelled
Không chứa Business Logic.
---
## Transition Policy
Kiểm tra tính hợp lệ của State Transition.
Không thay đổi trạng thái.
Không lưu dữ liệu.
---
## Result Collector
Thu thập:
- Output
- Error
- Metadata
Tạo Observation.
Không phân tích kết quả.
---
## Result Dispatcher
Trả Observation về Agent.
Không chỉnh sửa dữ liệu.
---
# Dependency
```
Agent
    │
      ▼
Runtime
    │
      ▼
Execution Environment
    │
      ▼
Tool
```
Dependency chỉ theo một chiều.
---
# Design Rules
- Runtime chỉ thực thi.
- Runtime không reasoning.
- Runtime không biết Model suy nghĩ gì.
- Runtime không quyết định workflow.
- Runtime không truy cập Stable Store.
---
# Constraints
- Stateless.
- Không cache.
- Không lưu Working Context.
- Không chứa Business Logic.
---
# Design Goal
Runtime là lớp thực thi chung của hệ thống.
Có thể thay đổi cách thực thi mà không ảnh hưởng đến:
- Reasoning Model
- Agent
- Tool Contract
