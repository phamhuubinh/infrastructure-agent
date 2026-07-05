# Agent
## Mục tiêu
Agent là Dispatcher giữa Reasoning Model và Tool.
Agent không chứa business logic.
---
# Responsibilities
Agent chịu trách nhiệm:
- Nhận Action từ Reasoning Model.
- Kiểm tra Action hợp lệ.
- Chuyển Action tới Tool phù hợp.
- Nhận Observation từ Tool.
- Trả Observation về Reasoning Model.
---
# Non-Responsibilities
Agent không:
- Reasoning.
- Phân tích dữ liệu.
- Quyết định bước tiếp theo.
- Thu thập dữ liệu.
- Truy cập trực tiếp Stable Store.
- Truy cập trực tiếp Environment.
---
# Communication
Agent chỉ giao tiếp với:
- Reasoning Model
- Tool
Agent không giao tiếp trực tiếp với:
- Collector
- Stable Store
- Operating System
---
# Lifecycle
```
Receive Action
        │
            ▼
Validate Action
        │
            ▼
Dispatch To Tool
        │
            ▼
Receive Observation
        │
            ▼
Return Observation
```
---
# Constraints
- Stateless.
- Không lưu Working Context.
- Không cache dữ liệu.
- Không retry theo business logic.
- Không thay đổi Observation.
---
# Dependency
```
Reasoning Model
        │
            ▼
      Agent
        │
            ▼
      Tool
```
Dependency chỉ theo một chiều.
---
# Design Goal
Agent phải càng nhỏ càng tốt.
Nếu một logic có thể chuyển sang:
- Model
- Tool
thì không được đặt trong Agent.
