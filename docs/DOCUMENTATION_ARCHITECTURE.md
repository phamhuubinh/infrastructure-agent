# Documentation Architecture
## Mục tiêu
Tài liệu này định nghĩa kiến trúc của toàn bộ hệ thống tài liệu.
Mục tiêu:
- Mỗi thông tin chỉ có một Source of Truth.
- Không trùng lặp.
- Dễ bảo trì.
- Dễ cho cả Developer và AI đọc.
---
# Documentation Hierarchy
```
Project Principles
        │
            ▼
Architecture Decision Records (ADR)
        │
            ▼
Architecture Overview
        │
            ▼
Component Specification
        ├────────────► API Specification
        └────────────► Behavior Specification
Shared Model Specification
Protocol Specification
Project State
AI Working Guide
```
---
# 1. Project Principles
Mục đích
- Triết lý của project.
- Nguyên tắc không thay đổi.
Được phép chứa
- Philosophy
- Principles
- Design Rules
Không được chứa
- Component
- API
- Runtime Flow
- Implementation
- Roadmap
---
# 2. Architecture Decision Record (ADR)
Mục đích
Giải thích:
- Vì sao quyết định được đưa ra.
Được phép chứa
- Context
- Decision
- Consequence
Không được chứa
- Implementation
- API
- TODO
---
# 3. Architecture Overview
Mục đích
Mô tả bức tranh tổng thể của một subsystem.
Được phép chứa
- Component
- Relationship
- Data Flow
- Dependency
Không được chứa
- API
- Implementation
- Decision
---
# 4. Component Specification
Mục đích
Định nghĩa trách nhiệm của một component.
Được phép chứa
- Purpose
- Responsibility
- Non Responsibility
- Input
- Output
- Dependency
- Constraint
Không được chứa
- Method Signature
- Runtime Sequence
- Decision
---
# 5. API Specification
Mục đích
Định nghĩa public interface.
Được phép chứa
- Method
- Parameters
- Return
- Error Contract
Không được chứa
- Responsibility
- Runtime Behavior
---
# 6. Behavior Specification
Mục đích
Mô tả trình tự thực thi.
Được phép chứa
- Sequence
- State Transition
- Runtime Behavior
Không được chứa
- API
- Decision
---
# 7. Shared Model Specification
Mục đích
Định nghĩa các immutable data model dùng chung.
Được phép chứa
- Fields
- Types
- Constraints
Không được chứa
- Behavior
- Responsibility
---
# 8. Protocol Specification
Mục đích
Định nghĩa format giao tiếp giữa các thành phần.
Được phép chứa
- Message Format
- Schema
- Validation Rules
Không được chứa
- Business Logic
---
# 9. Project State
Mục đích
Theo dõi trạng thái hiện tại của project.
Được phép chứa
- Done
- In Progress
- Next Step
Không được chứa
- Architecture
- Decision
---
# 10. AI Working Guide
Mục đích
Hướng dẫn AI làm việc với repository.
Được phép chứa
- Workflow
- Reading Order
- Review Process
Không được chứa
- Architecture
- API
- Component Specification
---
# Source of Truth
Priority:
1. Project Principles
2. ADR
3. Architecture Overview
4. Component Specification
5. API Specification
6. Behavior Specification
7. Shared Model Specification
8. Protocol Specification
9. Project State
10. AI Working Guide
---
# Documentation Rules
- Một thông tin chỉ xuất hiện ở một nơi.
- Không lặp nội dung giữa các tài liệu.
- Mọi thay đổi kiến trúc bắt đầu từ ADR.
- Component Specification phải tuân theo ADR.
- API Specification phải tuân theo Component Specification.
- Behavior Specification phải tuân theo API Specification.
- AI Working Guide chỉ được tham chiếu tài liệu khác, không được định nghĩa kiến trúc.
