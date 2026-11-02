# AI providers — DeepSeek, Claude và OpenAI

## 1. Phạm vi được chốt

Đợt refactor bắt buộc ba vendor này. Không yêu cầu Gemini, Ollama, mọi gateway,
mọi SaaS API hoặc mọi model từng tồn tại. Model ID là profile/config, không hardcode
tên “latest”, giá hoặc kích thước context chưa xác minh.

| Vendor | Adapter tối thiểu | Nghiệm thu |
| --- | --- | --- |
| DeepSeek | Mặc định Chat Completions-compatible với profile/adapter riêng cho tools/stream/thinking khi model hỗ trợ | Không chỉ đổi base_url rồi giả tương thích mọi field |
| Claude | Anthropic Messages native | Content/tool_use/tool_result, stream deltas, stop/usage và provider state hợp lệ |
| OpenAI | Responses native; Chat Completions-compatible là đường tương thích riêng | Typed Responses events không dùng lại nguyên Chat Completions parser |

Không cần hiện thực mọi wire format của cùng vendor. Bắt buộc chọn đường hoạt
động được cho chat/tool/stream và giữ adapter extensible. Thêm vendor về sau
không sửa ChatRuntime hoặc nhân đôi tool authorization.

## 2. Contract adapter

ModelProfile: provider_id, protocol, endpoint, model_id, credential_ref, capability
descriptor, options có schema, context/request/transport bounds, retry settings.

Capabilities: text, streaming, tools/tool-result continuation, structured output,
vision nếu profile hỗ trợ, usage, reasoning controls. Missing capability trả lỗi
có cấu trúc hoặc UI disabled có lý do; không âm thầm mô phỏng success.
Native SDK object/wire event không đi qua core domain; adapter tạo normalized
events/turn và adapter-owned opaque continuation envelope khi cần.

Core giữ một canonical registry và model loop. Provider schema projection có thể
map tên/hình dạng/schema subset, nhưng không thay authority hoặc bỏ validation
phía Orion. Tool name mapping round-trip, call IDs và argument fragmentation phải
giữ đúng; parse partial JSON không được dispatch sớm.

## 3. State, thinking và protocol differences

DeepSeek thinking/tool-loop có yêu cầu continuation khác với chat thường; phải
đọc tài liệu model/protocol hiện tại và giữ trường bắt buộc trong adapter-owned
state, không loại bỏ máy móc mọi reasoning payload rồi làm request sau lỗi.
[DeepSeek thinking](https://api-docs.deepseek.com/guides/thinking_mode/).

Claude dùng Messages/content blocks và streamed message/block events, cần parser
riêng và ghép đúng tool_use/tool_result thay vì coi event như OpenAI delta.
[Claude streaming](https://platform.claude.com/docs/en/build-with-claude/streaming).

OpenAI Responses có lifecycle/event/tool output contract riêng; triển khai native
Responses adapter và round-trip function call thay vì chỉ gọi /chat/completions.
[OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling),
[Responses streaming](https://developers.openai.com/api/docs/guides/streaming-responses).

State cần trả lại vendor là protocol data, không phải quyền chạy tool. Giữ biệt
lập khỏi public assistant answer, UI reasoning dump, ordinary log và skill guidance.
Retention/persistence tối thiểu đủ correctness phải có schema và test; nếu không
hỗ trợ resume provider state, báo giới hạn rõ.

## 4. Xác thực và profile

Server lưu secret qua credential reference/secret store; UI và app không chứa
provider API key. Cho phép endpoint override/proxy được owner cấu hình; không coi
mọi URL là OpenAI-compatible. Model list/connection test có timeout và không tự
tạo paid job ngoài mức smoke đã cho phép.

Mỗi profile có protocol và capability rõ, không đoán vendor bằng regex tên model.
Đổi profile có hiệu lực ở request boundary; không đổi giữa tool loop.
Không fallback sang vendor/model khác mà người dùng chưa chọn.

## 5. Kiểm thử bắt buộc

Một conformance suite dùng fake HTTP/SSE chuẩn từng protocol, fixtures đã
sanitise và cùng bộ tình huống:

- complete/stream/direct answer và model → tool → result → model;
- nhiều tool call, fragmented/interleaved arguments, Unicode, invalid/partial JSON;
- source/call identity, tool-error return và continuation state qua nhiều vòng;
- provider auth/header/options, unsupported capability, stop/usage;
- timeout, cancel, connection drop, retry an toàn trước nhận kết quả;
- HTTP/rate-limit/upstream stream errors, truncation và no terminal result;
- không replay một tool mutation do provider/network retry;
- secret và private provider state không ra API/log/public conversation.

Live smoke cho đúng ba vendor khi có key; giới hạn request nhỏ, không benchmark
triền miên hoặc suy test fake là live pass. Thiếu key → needs_external ở live
smoke, không chặn triển khai adapter/conformance/clients độc lập.

## 6. Tài liệu nguồn

Đối chiếu chính thức ngày 29/10/2026; khi implementation phải kiểm tra version/
schema đang dùng, pin SDK/fixtures và ghi source link. Không copy cả tài liệu
vendor vào repo.

- [DeepSeek tool calls](https://api-docs.deepseek.com/guides/tool_calls/)
- [DeepSeek thinking](https://api-docs.deepseek.com/guides/thinking_mode/)
- [Claude Messages](https://platform.claude.com/docs/en/build-with-claude/working-with-messages)
- [Claude streaming](https://platform.claude.com/docs/en/build-with-claude/streaming)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI Responses overview](https://developers.openai.com/api/reference/responses/overview)
