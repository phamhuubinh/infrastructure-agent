# Shared Architecture
## Mục tiêu
Shared Models định nghĩa các cấu trúc dữ liệu dùng chung giữa các component.
Shared Models chỉ chứa dữ liệu.
Không chứa hành vi.
---
# Responsibilities
Shared Models chịu trách nhiệm:
- Chuẩn hóa dữ liệu trao đổi.
- Giảm coupling giữa các component.
- Định nghĩa contract của dữ liệu.
---
# Non-Responsibilities
Shared Models không:
- Reasoning.
- Thực thi.
- Thu thập dữ liệu.
- Quản lý workflow.
- Chứa Business Logic.
---
# Characteristics
Mọi Shared Model nên:
- Immutable.
- Rõ ràng.
- Độc lập.
- Có thể tái sử dụng.
---
# Categories
## Runtime Models
Ví dụ:
- ExecutionState
- ExecutionContext
- ExecutionResult
- ExecutionConstraints
- ExecutionSession
---
## Lifecycle Models
Ví dụ:
- LifecycleState
- LifecycleTransition
- RuntimeMetadata
---
## Reasoning Models
Ví dụ:
- Action
- Observation
- FinalResponse
---
## Knowledge Models
Ví dụ:
- KnowledgeEntry
- StableInformation
- RuntimeInformation
---
# Dependency
```
Reasoning Model
        │
Agent   │
Runtime │
Tool    │
            ▼
Shared Models
```
Shared Models không phụ thuộc ngược vào bất kỳ component nào.
---
# Design Rules
- Chỉ chứa dữ liệu.
- Không có side effect.
- Không truy cập môi trường.
- Không gọi component khác.
- Không lưu trạng thái runtime.
---
# Constraints
- Immutable.
- Serializable.
- Dễ kiểm thử.
- Không phụ thuộc implementation.
---
# Design Goal
Shared Models là contract dữ liệu chung của toàn hệ thống.
Mọi component chỉ trao đổi dữ liệu thông qua Shared Models.
