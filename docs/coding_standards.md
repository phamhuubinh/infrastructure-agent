# Coding Standards
## Mục tiêu
Viết code đơn giản, dễ đọc, dễ kiểm thử và phù hợp với kiến trúc của project.
Code phải phản ánh tài liệu kiến trúc.
---
# General Rules
- Ưu tiên thư viện chuẩn của Python.
- Không tối ưu sớm.
- Không over-engineering.
- Không thêm abstraction khi chưa cần.
- Không viết code "đón đầu" nhu cầu tương lai.
---
# Architecture Rules
Mọi component chỉ có một trách nhiệm.
Không thay đổi ownership giữa các component.
Không bypass architecture.
Dependency chỉ đi theo một chiều.
---
# Naming
Tên phải rõ nghĩa.
Không viết tắt.
Ưu tiên tên mô tả trách nhiệm.
---
# Functions
Function chỉ làm một việc.
Ưu tiên hàm ngắn.
Nếu function quá dài, tách nhỏ.
Không lồng logic quá sâu.
---
# Classes
Class chỉ đại diện cho một abstraction.
Không tạo Interface hoặc Abstract Class nếu chưa thực sự cần.
Không thêm Design Pattern chỉ để "đẹp".
---
# Dependencies
Không thêm package mới nếu Python Standard Library giải quyết được.
Mọi dependency mới phải có lý do rõ ràng.
---
# Error Handling
Không bỏ qua exception.
Thông báo lỗi phải rõ ràng.
Không che giấu lỗi.
---
# Logging
Chỉ log thông tin hữu ích.
Không log dữ liệu dư thừa.
Không dùng log thay cho exception.
---
# Testing
Code mới phải có test tương ứng.
Không làm hỏng test hiện có.
Ưu tiên unit test.
---
# Documentation
Mọi thay đổi kiến trúc phải cập nhật tài liệu trước hoặc cùng lúc với code.
Không để tài liệu và code lệch nhau.
---
# Pull Request Checklist
Trước khi hoàn thành một thay đổi:
- Kiến trúc vẫn đúng.
- Không tăng coupling.
- Không thêm abstraction không cần thiết.
- Không thay đổi public contract ngoài phạm vi.
- Test liên quan đã chạy.
- Tài liệu đã được cập nhật.
---
# Prohibited
Không:
- Over-engineering.
- Refactor ngoài phạm vi.
- Đổi tên không cần thiết.
- Format toàn bộ project.
- Thêm TODO không có kế hoạch thực hiện.
- Thêm feature ngoài yêu cầu.
- Thêm dependency không cần thiết.
