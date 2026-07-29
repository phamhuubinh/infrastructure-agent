# PROJECT_CONTEXT.md — Orion

<!-- Bản nháp do THINK tự đọc repo viết ra (2026-07-29).
Mục 1-2-7 là THINK tự mô tả — Bình đọc lại, sửa chỗ sai.
Mục 3-6 THINK KHÔNG được tự điền vì đó là quyết định của Bình — bắt buộc tự viết trước khi
chạy issue thật, không thì để trống cũng chạy được (THINK sẽ hỏi lại qua request_human khi cần
quyết định mà mục 3-6 chưa có câu trả lời). -->

## 1. Orion là gì
Orion is an infrastructure investigation platform with AI-powered assessment, currently implemented as a local, single-user system. It processes infrastructure queries through a deterministic pipeline where AI is only used for assessment, not for core processing. The platform provides CLI and Web UI interfaces for infrastructure investigations.

## 2. Kiến trúc hiện tại (tóm tắt)
The system features a 6-stage deterministic pipeline (Normalize → Target → Plan → Graph → Execute → Assess) with core components including ConversationStore, EvidenceCache, KnowledgeTool (dispatch point), and Child Tools (Linux, Grafana, Zabbix, Internet, KnowledgeBase). The assessment layer uses LLMAssessmentAdapter (real) and MockAssessmentAdapter (offline) behind AssessmentModelAdapter. A RAG microservice (RAGTool) handles document processing with embedding, vector store, and query pipelines. The Web UI (React/TanStack) and CLI interfaces communicate with the backend.

## 3. Quyết định ĐÃ CHỐT — làm theo hướng nào


## 4. Cân nhắc nhưng CHƯA làm / không làm (và vì sao)


## 5. Việc KHÔNG BAO GIỜ được tự làm mà không hỏi Bình


## 6. Giới hạn hiện tại của việc kiểm chứng tự động


## 7. Mục tiêu/tính năng đang hướng tới (theo docs hiện có)
Implemented: 6-stage pipeline, KnowledgeTool dispatch, Child Tools (Linux, Grafana, Zabbix, Internet, KB), local target registry, assessment layer, CLI, Web UI, RAG microservice (with embedding, vector store, query pipelines), 1,101 tests. Gaps: No accounts, no remote hosting, optional PostgreSQL session store (not default), optional API key auth (not default), Docker Compose for local deployment only, no desktop app in current release (though desktop/ directory exists).
