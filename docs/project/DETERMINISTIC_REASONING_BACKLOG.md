# Orion — Corrective Backlog & Deterministic Reasoning v1

> **Mục đích:** backlog triển khai hợp nhất cho việc nâng độ chính xác của Orion theo nguyên tắc **Code investigates. AI explains.**  
> **Phạm vi:** sửa pipeline, Tool, evidence, deterministic reasoning, assessment guard và QA harness. Không chuyển quyền chọn lệnh/capability sang LLM.  
> **Ngày tạo:** 2026-08-03  
> **Ngày chốt:** 2026-08-03  
> **Cập nhật gần nhất:** 2026-08-05 — DR1-201–211 hoàn thành: Docker runtime, target identity/preflight, capability metadata, Linux collectors/output schemas và read-only security boundary đã được triển khai, kiểm thử và smoke-test. DR1-001–108 hoàn thành trước đó.
> **Trạng thái tài liệu:** Active — backlog hiện hành duy nhất. `BACKLOG.md` và `IMPLEMENTATION_BACKLOG.md` là tài liệu lịch sử/tham khảo (xem `docs/project/README.md`).

## 0. Cơ sở và cách dùng tài liệu

Tài liệu này được tổng hợp từ:

- `docs/ai/05_EXECUTION_PIPELINE.md`
- `docs/ai/06_TOOL_AND_CAPABILITY_DESIGN.md`
- `docs/ai/07_DEVELOPMENT_RULES.md`
- `docs/ai/08_PROJECT_STATE.md`
- `docs/ai/10_PHASE6_PLAN.md`
- `docs/project/BACKLOG.md` — tài liệu lịch sử, không phải trạng thái hiện hành
- `docs/project/IMPLEMENTATION_BACKLOG.md`
- source hiện tại trong `src/agent/`, `src/pipeline/`, `src/tool/`, `src/model/`
- các transcript QA `default`, `kiemtra_v2`, `phanb`, `v4`, `v5`

`docs/project/README.md` quy định trạng thái hiện hành nằm ở `docs/ai/08_PROJECT_STATE.md`. Vì QA mới cho thấy một số hành vi không khớp với trạng thái “completed” của Phase 6, các mục liên quan trong backlog này dùng trạng thái **🔎 verify/fix**, không tự động coi là đã hoàn tất hoặc chưa tồn tại.

### Nguyên tắc bắt buộc

1. **LLM không route, không chọn capability, không sinh shell command để agent chạy.**
2. **Child Tool thu thập và chuẩn hóa evidence; không kết luận.**
3. **Execution Engine điều tra deterministically; Assessment Model chỉ phân tích evidence đã thu.**
4. **Không dùng số `0`, danh sách rỗng hoặc `None` để che giấu lỗi thu thập.**
5. **Mọi claim phải có provenance; mọi hành động phải có ActionReceipt.** Orion hiện là read-only nên mặc định không được claim “đã sửa/xóa/restart”.
6. **Không thêm expert-system platform lớn.** Chỉ triển khai Structured Facts → Composite Rules → Bounded Recovery → Weighted Missing-Evidence Selection.
7. **Một task = một logical commit**, có test và tiêu chí hoàn tất rõ ràng.

### Legend

| Ký hiệu | Ý nghĩa |
|---|---|
| P0 | Critical — sai dữ liệu, sai target, unsafe claim hoặc làm mất độ tin cậy |
| P1 | High — ảnh hưởng trực tiếp routing/evidence/diagnosis |
| P2 | Medium — chất lượng, hiệu năng, maintainability |
| P3 | Low/Horizon — chỉ làm sau khi benchmark chứng minh cần thiết |
| ⬜ | Pending |
| 🔎 | Verify/Fix — module đã tồn tại hoặc tài liệu báo completed nhưng phải kiểm chứng và sửa |
| 🔴 | Blocked |
| ✅ | Completed — chỉ dùng khi có diff/test/benchmark chứng minh |

## 1. Kiến trúc đích

```text
User request + structured session context
        ↓
RequestFrame (concept, operation, target, params, answer_type, timeframe)
        ↓
Deterministic routing / clarification
        ↓
Evidence requirements expressed as canonical fact requirements
        ↓
Capability plan + validated parameters
        ↓
Capability-owned command strategies
        ↓
Structured CommandResult / CapabilityResult
        ↓
Canonical Facts + validity + freshness + provenance
        ↓
Atomic rules + composite weighted findings
        ↓
Bounded fallback / weighted missing-evidence selection
        ↓
Deterministic fact/list/table response OR AssessmentRequest
        ↓
LLM analysis only
        ↓
Grounding / safety / language validators
        ↓
Final response
```

### Phân loại LLM usage

```text
EXPECTED_ASSESSMENT
- route đúng, evidence đủ, answer type cần phân tích bằng LLM.

ROUTING_FALLBACK
- pipeline không xác định chắc concept/intent/target/capability/parameter.
- đây mới là metric phản ánh trực tiếp routing yếu.

INSUFFICIENT_EVIDENCE
- hiểu yêu cầu nhưng Tool không thu đủ evidence để kết luận.
```

KPI chính không phải “ít gọi LLM”, mà là:

> **Correct investigation rate: route đúng, target đúng, parameter đúng, plan đúng, thu evidence đúng và chỉ gọi LLM khi answer strategy thực sự cần assessment.**

---
## 2. Master task index

| ID | Priority | Status | Epic | Task | Dependencies |
|---|---|---|---|---|---|
| DR1-001 | P0 | ✅ | EPIC 0 | Chốt backlog hiện hành và nguồn sự thật | Không |
| DR1-002 | P0 | ✅ | EPIC 0 | Định nghĩa ExecutionTrace schema | DR1-001 |
| DR1-003 | P0 | ✅ | EPIC 0 | Nhập external HTTP QA runner và 4 bộ câu hỏi TXT; loại bỏ implementation JSONL hiểu sai | Không |
| DR1-004 | P0 | ✅ | EPIC 0 | Chuyển transcript QA thành golden dataset theo stage | DR1-002, DR1-003 |
| DR1-005 | P0 | ✅ | EPIC 0 | Lưu baseline metrics trước khi sửa hành vi | DR1-002, DR1-004 |
| DR1-006 | P1 | ✅ | EPIC 0 | Reconcile trạng thái Phase 6 với behavior hiện tại | DR1-005 |
| DR1-101 | P0 | ✅ | EPIC 1 | Tạo CommandStatus và CommandResult | DR1-002 |
| DR1-102 | P0 | ✅ | EPIC 1 | Sửa LocalExecutionBackend giữ stderr và timeout | DR1-101 |
| DR1-103 | P0 | ✅ | EPIC 1 | Sửa SSHExecutionBackend trả lỗi có cấu trúc | DR1-101 |
| DR1-104 | P0 | ✅ | EPIC 1 | Tạo CapabilityResult và CapabilityStatus | DR1-101 |
| DR1-105 | P0 | ✅ | EPIC 1 | Lan truyền failure đúng qua ToolResult và EvidencePackage | DR1-104 |
| DR1-106 | P0 | ✅ | EPIC 1 | Loại bỏ toàn bộ failure-to-zero/default-empty | DR1-104, DR1-105 |
| DR1-107 | P1 | ✅ | EPIC 1 | Chuẩn hóa taxonomy lỗi capability | DR1-104 |
| DR1-108 | P0 | ✅ | EPIC 1 | Không cache failed/partial evidence như valid | DR1-105 |
| DR1-201 | P0 | ✅ | EPIC 2 | Khai báo dependency tối thiểu cho Docker runtime | DR1-101 |
| DR1-202 | P0 | ✅ | EPIC 2 | Làm rõ semantics của target `localhost` | DR1-201 |
| DR1-203 | P1 | ✅ | EPIC 2 | Thêm target preflight và environment fingerprint | DR1-101, DR1-202 |
| DR1-204 | P1 | ✅ | EPIC 2 | Bổ sung capability preconditions và required binaries | DR1-203 |
| DR1-205 | P1 | ✅ | EPIC 2 | Làm CPU collector ổn định bằng `/proc/stat` | DR1-104 |
| DR1-206 | P0 | ✅ | EPIC 2 | Service status có bounded multi-strategy fallback | DR1-107, DR1-204 |
| DR1-207 | P1 | ✅ | EPIC 2 | Thu log theo service và time range | DR1-206, DR1-403, DR1-406 |
| DR1-208 | P1 | ✅ | EPIC 2 | Network collector có `/proc` và `/sys` fallback | DR1-204 |
| DR1-209 | P1 | ✅ | EPIC 2 | Tách filesystem usage, inode, I/O và disk health | DR1-104 |
| DR1-210 | P1 | ✅ | EPIC 2 | Chuẩn hóa Linux capability outputs trước pipeline | DR1-104, DR1-205..209 |
| DR1-211 | P0 | ✅ | EPIC 2 | Khóa ranh giới read-only, không chạy raw command từ LLM | DR1-204 |
| DR1-301 | P0 | 🔎 | EPIC 3 | Loại LLM khỏi quyết định routing investigation | DR1-002 |
| DR1-302 | P0 | ⬜ | EPIC 3 | Tạo RequestFrame thống nhất | DR1-301 |
| DR1-303 | P1 | 🔎 | EPIC 3 | Mở rộng deterministic normalizer cho typo và code-switching | DR1-302 |
| DR1-304 | P2 | ⬜ | EPIC 3 | Semantic candidate retrieval có deterministic validation | DR1-303 |
| DR1-305 | P1 | 🔎 | EPIC 3 | IntentResolver trả confidence, candidates và ambiguity margin | DR1-302 |
| DR1-306 | P0 | 🔎 | EPIC 3 | TargetResolver dùng threshold + margin + unknown-target guard | DR1-302 |
| DR1-307 | P2 | ⬜ | EPIC 3 | Alias có scope và vòng đời | DR1-306 |
| DR1-308 | P0 | ⬜ | EPIC 3 | Chuẩn hóa request class, routing status, evidence status, answer strategy | DR1-302 |
| DR1-309 | P1 | ⬜ | EPIC 3 | Deterministic clarification responses | DR1-305, DR1-306, DR1-308 |
| DR1-401 | P0 | ⬜ | EPIC 4 | Tạo SessionInvestigationContext có cấu trúc | DR1-302 |
| DR1-402 | P0 | ⬜ | EPIC 4 | Resolve context trước Normalizer/Target/Planner | DR1-401 |
| DR1-403 | P0 | 🔎 | EPIC 4 | Tạo ParameterBinder và truyền params xuống capability | DR1-302 |
| DR1-404 | P0 | ⬜ | EPIC 4 | Validate required parameters trước execution | DR1-403 |
| DR1-405 | P1 | ⬜ | EPIC 4 | Decompose multi-intent thành subrequests có giới hạn | DR1-302, DR1-305 |
| DR1-406 | P1 | 🔎 | EPIC 4 | Chuẩn hóa TimeRange và temporal requirements | DR1-302, DR1-403 |
| DR1-407 | P0 | ⬜ | EPIC 4 | Guard comparison/forecast khi thiếu time series | DR1-406, DR1-505 |
| DR1-501 | P0 | ⬜ | EPIC 5 | Tạo canonical Fact model | DR1-104, DR1-302 |
| DR1-502 | P0 | ⬜ | EPIC 5 | FactNormalizer cho Linux core capabilities | DR1-210, DR1-501 |
| DR1-503 | P1 | ⬜ | EPIC 5 | FactNormalizer cho Zabbix và Grafana | DR1-501 |
| DR1-504 | P1 | ⬜ | EPIC 5 | Investigation FactSet và indexing | DR1-501..503 |
| DR1-505 | P0 | 🔎 | EPIC 5 | EvidenceCompleteness dựa trên required facts | DR1-501, DR1-504 |
| DR1-506 | P1 | ⬜ | EPIC 5 | Detect và biểu diễn contradictory facts | DR1-504 |
| DR1-507 | P1 | 🔎 | EPIC 5 | Sửa EvidenceCache key và freshness policy | DR1-501, DR1-505 |
| DR1-508 | P1 | ⬜ | EPIC 5 | Mở rộng EvidencePackage: raw, facts, failures | DR1-501, DR1-505 |
| DR1-509 | P2 | ⬜ | EPIC 5 | Provenance và claim source links | DR1-501, DR1-508 |
| DR1-601 | P1 | 🔎 | EPIC 6 | Refactor atomic threshold rules dùng canonical metrics | DR1-501, DR1-505 |
| DR1-602 | P1 | ⬜ | EPIC 6 | Tạo CompositeRule và WeightedCondition | DR1-601 |
| DR1-603 | P0 | ⬜ | EPIC 6 | Định nghĩa semantics false/unknown/stale/failed trong rule | DR1-602 |
| DR1-604 | P1 | ⬜ | EPIC 6 | Tạo Finding model | DR1-602 |
| DR1-605 | P1 | 🔎 | EPIC 6 | Tích hợp EvidenceCorrelation vào Fact/Findings flow | DR1-604 |
| DR1-606 | P1 | ⬜ | EPIC 6 | Bounded capability recovery theo error contract | DR1-107, DR1-204, DR1-505 |
| DR1-607 | P1 | ⬜ | EPIC 6 | Weighted missing-evidence selection | DR1-603, DR1-606 |
| DR1-608 | P0 | ⬜ | EPIC 6 | Budget và stop conditions cho investigation expansion | DR1-607 |
| DR1-609 | P0 | ⬜ | EPIC 6 | Deterministic health aggregator đa nguồn | DR1-604, DR1-505 |
| DR1-610 | P2 | ⬜ | EPIC 6 | Rule config schema, versioning và human review | DR1-601, DR1-602 |
| DR1-701 | P0 | ⬜ | EPIC 7 | Mở rộng AssessmentRequest | DR1-505, DR1-604 |
| DR1-702 | P0 | 🔎 | EPIC 7 | Prompt builder hiển thị failure và giới hạn evidence | DR1-701 |
| DR1-703 | P0 | ⬜ | EPIC 7 | Claim grounding validator | DR1-701 |
| DR1-704 | P0 | ⬜ | EPIC 7 | Action hallucination guard và ActionReceipt contract | DR1-211, DR1-703 |
| DR1-705 | P0 | ⬜ | EPIC 7 | Numeric và unit consistency validator | DR1-501, DR1-703 |
| DR1-706 | P1 | 🔎 | EPIC 7 | Language quality validator | DR1-703 |
| DR1-707 | P0 | 🔎 | EPIC 7 | DeterministicResponder chỉ đọc valid facts/findings | DR1-501, DR1-604 |
| DR1-708 | P1 | ⬜ | EPIC 7 | Chuẩn hóa uncertainty và confidence wording | DR1-701 |
| DR1-801 | P0 | ⬜ | EPIC 8 | Unit test matrix cho CommandResult/CapabilityResult | DR1-101..107 |
| DR1-802 | P1 | ⬜ | EPIC 8 | Stage tests cho routing đa ngôn ngữ/typo/code-switch | DR1-303..309 |
| DR1-803 | P0 | ⬜ | EPIC 8 | Regression tests cho session context | DR1-401, DR1-402 |
| DR1-804 | P0 | ⬜ | EPIC 8 | Contract tests cho Fact normalization | DR1-502, DR1-503 |
| DR1-805 | P1 | ⬜ | EPIC 8 | Precision/recall tests cho atomic và composite findings | DR1-601..610 |
| DR1-806 | P0 | ⬜ | EPIC 8 | Transcript regression suite end-to-end | DR1-004, các epic trước |
| DR1-807 | P0 | 🔎 | EPIC 8 | Đổi acceptance evaluator sang stage-level scoring | DR1-002, DR1-004 |
| DR1-808 | P1 | ⬜ | EPIC 8 | Thiết lập performance/tool budget gates | DR1-005, DR1-608 |
| DR1-809 | P0 | ⬜ | EPIC 8 | Security và prompt-injection regression suite | DR1-211, DR1-704 |
| DR1-810 | P1 | ⬜ | EPIC 8 | Dashboard/report metrics chuẩn | DR1-005, DR1-807 |
| DR1-811 | P0 | ⬜ | EPIC 8 | CI gates cho accuracy và safety | DR1-806..810 |
| DR1-901 | P1 | ⬜ | EPIC 9 | Cập nhật execution/tool docs theo contracts mới | DR1-101, DR1-501, DR1-606 |
| DR1-902 | P1 | ⬜ | EPIC 9 | ADR cho evidence validity và deterministic reasoning v1 | DR1-501, DR1-602 |
| DR1-903 | P1 | ⬜ | EPIC 9 | Kế hoạch backward compatibility và migration | DR1-101, DR1-104, DR1-508 |
| DR1-904 | P1 | ⬜ | EPIC 9 | Feature flags cho rollout theo phase | DR1-903 |
| DR1-905 | P2 | ⬜ | EPIC 9 | Operator troubleshooting guide cho collection failures | DR1-107, DR1-201 |
| DR1-906 | P0 | ⬜ | EPIC 9 | Rollout theo PR/phase và exit criteria | Tất cả |
| DR1-907 | P0 | ⬜ | EPIC 9 | Release checklist và Definition of Done | DR1-811, DR1-906 |

**Tổng số task:** 86  

**Critical path:** DR1-002 → DR1-101 → DR1-104/105/106 → DR1-201/202/203 → DR1-302/403/404 → DR1-501/505 → DR1-601/602/603 → DR1-701/703/704 → DR1-806/807/811.

## 3. EPIC 0 — Baseline, trace và governance
### DR1-001 — Chốt backlog hiện hành và nguồn sự thật
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** Không
- **Files dự kiến:** `docs/project/DETERMINISTIC_REASONING_BACKLOG.md`, `docs/ai/08_PROJECT_STATE.md`, `docs/project/README.md`

**Vấn đề**  
Backlog lịch sử vẫn chứa task pending đã được tài liệu khác báo completed; nếu không phân biệt, đội phát triển dễ làm lại hoặc báo sai trạng thái.

**Cách làm (đã thực hiện 2026-08-03)**
1. ✅ File được đưa vào `docs/project/DETERMINISTIC_REASONING_BACKLOG.md` (đã mv từ tên tạm `ORION_DETERMINISTIC_REASONING_BACKLOG.md`).
2. ✅ Ghi rõ `BACKLOG.md` và `IMPLEMENTATION_BACKLOG.md` là lịch sử/tham khảo.
3. ✅ Thêm liên kết từ `docs/project/README.md`.
4. ✅ Cập nhật `08_PROJECT_STATE.md` sau khi có bằng chứng hoàn tất (xem mục Project State).

**Acceptance criteria**
- [x] Không còn hai tài liệu cùng tự nhận là backlog hiện hành.
- [x] Mỗi task mới có ID, owner/status, dependencies và DoD.
- [x] Không đánh dấu completed nếu chưa có diff/test.

**Tests/verification**
- `Documentation link check hoặc test đọc path nếu repository có doc checker.` — không có doc checker/tests nào tham chiếu path (đã kiểm tra `*.py`, `*.yml`, Makefile).

---
### DR1-002 — Định nghĩa ExecutionTrace schema
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-001
- **Files dự kiến:** `src/pipeline/execution_trace.py (new)`, `src/pipeline/investigation_request.py`, `src/agent/deterministic_agent.py`

**Vấn đề**  
QA hiện chủ yếu nhìn response cuối nên không biết lỗi nằm ở normalizer, target resolver, capability planner, collector hay assessment.

**Cách làm (đã thực hiện 2026-08-03)**
1. ✅ Tạo `src/pipeline/execution_trace.py` với `ExecutionTrace`, `StageTrace`, `StageStatus`, `AnswerStrategy`, `LLMUsageReason` và `from_investigation()`.
2. ✅ Ghi stage status/confidence, target, parameters, planned capabilities, evidence names, runtime metrics, answer strategy, LLM usage reason và total duration.
3. ✅ `confidence` dùng `None` cho stage chưa sinh score (test riêng đảm bảo không convert sang 0.0).
4. ✅ `run_with_steps()` trả `trace_id` + `execution_trace` (serialized, credential-free); `_assess()` ghi answer strategy thực tế; unknown-target/pipeline-failure tạo trace với `failure_stage`/`failure_reason`.

**Acceptance criteria**
- [x] Mọi request pipeline sinh đúng một trace (test `test_trace_from_investigation_produces_single_trace` + integration `run_with_steps`).
- [x] Trace đủ xác định `failure_stage` và `failure_reason`.
- [x] Trace serialization không chứa credential (`test_trace_serialization_is_json_safe_and_credential_free`, `...never_contains_raw_sensitive_fields`).

**Tests/verification**
- ✅ `tests/pipeline/test_execution_trace.py` — 11 tests mới.
- ✅ `tests/agent/test_deterministic_agent.py` — thêm `test_run_with_steps_returns_execution_trace`.
- ✅ 31 tests pass trên 2 module chạm tới; `ruff check .` clean. Không cần benchmark (không đổi scoring/prompt/evidence logic).

---
### DR1-003 — Nhập external HTTP QA runner và 4 bộ câu hỏi TXT
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** Không
- **Files giữ lại/thêm:**
  - `scripts/qa/orion_qa_runner.py`
  - `tests/qa/cases/cauhoi_kiemtra_v2.txt`
  - `tests/qa/cases/cauhoi_phanb.txt`
  - `tests/qa/cases/cauhoi_v4_adversarial.txt`
  - `tests/qa/cases/cauhoi_v5_workflow.txt`
- **Files cần xóa nếu chỉ được tạo bởi implementation DR1-003 cũ:**
  - `scripts/qa/case_loader.py`
  - `tests/data/qa_cases/v5_multiline.jsonl`
  - `tests/qa/test_acceptance_parser.py`
- **Files cần hoàn nguyên đúng các hunk thuộc implementation DR1-003 cũ:**
  - `scripts/qa/run_acceptance.py`
  - `scripts/qa/run_tests.py`
  - `scripts/qa/run_tests_v2.py`
  - `scripts/qa/README.md`

**Vấn đề**
DR1-003 trước đây bị triển khai sai scope thành JSONL case loader và sửa nhiều runner nội bộ. Bộ QA thực tế đang được sử dụng là một HTTP runner độc lập cùng bốn suite TXT, mỗi câu hỏi nằm trên một dòng. Task này phải đưa đúng bộ đó vào repository, dọn phần implementation hiểu sai và không mở rộng sang golden dataset hay stage-level evaluator.

**Phạm vi bắt buộc**
1. Giữ `orion_qa_runner.py` là runner HTTP độc lập, không import `src/` và không phụ thuộc orchestrator.
2. Giữ nguyên bốn file TXT; dòng bắt đầu bằng `#` là comment, mỗi câu hỏi hợp lệ nằm trên một dòng.
3. Một lần chạy dùng chung một `session_id` cho toàn suite để kiểm tra hội thoại nhiều lượt.
4. Transcript được ghi vào `artifacts/qa/transcripts/` hoặc path do `--output` chỉ định.
5. `orion_orchestrator_v3.py` không được đưa vào repository.
6. Không chuyển TXT sang JSONL trong task này.
7. Không sửa source agent, pipeline, Tool, model hoặc behavior sản phẩm trong task này.
8. Không tạo golden expectations, stage evaluator, baseline metrics hoặc CI gate trong task này; các phần đó thuộc DR1-004 trở đi.

**Cách làm**
1. Kiểm tra năm file cần giữ đã nằm đúng path và nội dung không bị thay đổi ngoài việc di chuyển.
2. Xóa ba file JSONL/parser test nêu trên nếu chúng chỉ được tạo cho DR1-003 cũ.
3. Với `run_acceptance.py`, `run_tests.py`, `run_tests_v2.py`, `scripts/qa/README.md`: xem diff và chỉ hoàn nguyên các hunk do DR1-003 cũ tạo ra; không dùng `git checkout` mù quáng và không làm mất thay đổi không liên quan.
4. Chạy `python3 scripts/qa/orion_qa_runner.py --help`.
5. Load cả bốn suite bằng chính `load_questions()` của runner và xác nhận số câu > 0, không có lỗi parse.
6. Khởi động Orion bằng runner hoặc dùng `--no-start` khi Docker/API đã chạy, rồi smoke test ít nhất một suite TXT qua `/api/query`.
7. Ghi transcript không rỗng vào `artifacts/qa/transcripts/`.
8. Chạy `git diff --check` và rà `git status --short`; diff của task không được chứa thay đổi source agent/pipeline hoặc file ngoài scope.
9. Đồng bộ mô tả DR1-003 trong `docs/ai/08_PROJECT_STATE.md`; xóa mô tả sai rằng JSONL loader là implementation được chấp nhận của DR1-003.
10. Chỉ đổi trạng thái sang ✅ sau khi có lệnh chạy, kết quả smoke test, danh sách file thay đổi và bằng chứng diff sạch theo scope.

**Acceptance criteria**
- [x] `scripts/qa/orion_qa_runner.py` tồn tại và `--help` chạy thành công.
- [x] Bốn suite TXT tồn tại đúng trong `tests/qa/cases/` và mỗi suite load được ít nhất một câu hỏi (66/28/61/38 câu).
- [x] `orion_orchestrator_v3.py` không nằm trong repository.
- [x] Không còn `scripts/qa/case_loader.py`, `tests/data/qa_cases/v5_multiline.jsonl`, `tests/qa/test_acceptance_parser.py` từ implementation DR1-003 sai.
- [x] Các runner nội bộ chỉ được hoàn nguyên đúng hunk cũ; không mất thay đổi không liên quan.
- [x] Ít nhất một suite chạy thành công qua Orion API với một `session_id` dùng xuyên suốt (`cauhoi_kiemtra_v2.txt`: Done. 66/66 succeeded, HTTP 200).
- [x] Transcript được tạo, không rỗng và nằm trong `artifacts/qa/transcripts/` (orion_qa_transcript_v2.md — 1747 dòng, 54 KB).
- [x] Không sửa source agent, pipeline, Tool hoặc model trong task này.
- [x] `git diff --check` thành công.
- [x] `docs/project/DETERMINISTIC_REASONING_BACKLOG.md` và `docs/ai/08_PROJECT_STATE.md` mô tả cùng một scope/trạng thái cho DR1-003.

**Tests/verification**
```bash
python3 scripts/qa/orion_qa_runner.py --help

python3 - <<'PY'
from pathlib import Path
import importlib.util

runner_path = Path("scripts/qa/orion_qa_runner.py")
spec = importlib.util.spec_from_file_location("orion_qa_runner", runner_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

for path in sorted(Path("tests/qa/cases").glob("*.txt")):
    questions = module.load_questions(str(path))
    assert questions, f"Suite rỗng: {path}"
    print(f"{path}: {len(questions)} câu")
PY

python3 scripts/qa/orion_qa_runner.py \
  --questions-file tests/qa/cases/cauhoi_kiemtra_v2.txt \
  --output artifacts/qa/transcripts/orion_qa_transcript_v2.md

test -s artifacts/qa/transcripts/orion_qa_transcript_v2.md
git diff --check
git status --short
```

---
### DR1-004 — Chuyển transcript QA thành golden dataset theo stage
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-002, DR1-003
- **Files dự kiến:** `tests/data/qa_cases/*.yaml (new)`, `scripts/qa/build_golden.py (new)`

**Vấn đề**  
Transcript chỉ chứa prompt/response, chưa có expected concept, target, params, answer strategy hay evidence requirements.

**Cách làm (đã thực hiện 2026-08-04)**
1. ✅ Chọn case đại diện từ 5 transcript (source ghi rõ transcript_default/v2/v4/v5) — 39 case.
2. ✅ Gắn expected: concept, operation, target, params, answer_type, routing_status, evidence_status, answer_strategy, llm_usage_reason, required_evidence trong `tests/data/qa_cases/golden_core.yaml`.
3. ✅ Tách case lỗi harness khỏi lỗi agent qua cờ `harness_error: true` (1 case — loại khỏi agent pass/fail khi scoring DR1-005/DR1-807).
4. ✅ Human review từng golden case trước merge — bắt buộc có `note` review + `source`; id là slug thủ công, không dùng id hash tự sinh.

**Acceptance criteria**
- [x] Mỗi nhóm A–J có coverage (11 nhóm có case: A=2, B=5, C=5, D=12, E=2, F=3, G=2, H=2, I=2, J=2, M=2).
- [x] Có case tiếng Việt, tiếng Anh, typo, code-switching, follow-up, unknown target, forecast, action injection.
- [x] Golden không được tự sinh trực tiếp rồi tự coi là đúng.

**Tests/verification**
- ✅ `python3 scripts/qa/build_golden.py` — `Golden dataset validation OK`: 39 case tổng, 1 harness-error, 38 agent-scorable, 11 nhóm.
- ✅ `python3 -m pytest tests/qa/test_golden_schema.py -q` — 35 tests pass (load/duplicate/schema, coverage nhóm A–J, coverage tag edge-case, đủ expected fields, chống tự sinh).
- ✅ `ruff check scripts/qa/build_golden.py tests/qa/test_golden_schema.py` clean; kèm `tests/pipeline/test_execution_trace.py` → 45 tests pass.

---
### DR1-005 — Lưu baseline metrics trước khi sửa hành vi
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-002, DR1-004
- **Files:** `scripts/qa/run_baseline.py (new)`, `tests/qa/test_run_baseline.py (new)`

**Vấn đề**  
Không có baseline stage-level thì không thể biết thay đổi cải thiện hay chỉ chuyển lỗi sang stage khác.

**Cách làm (đã thực hiện 2026-08-04)**
1. ✅ Tạo `scripts/qa/run_baseline.py` — chạy toàn bộ case không `harness_error: true` trong
   `tests/data/qa_cases/golden_core.yaml` in-process qua `create_deterministic_agent()` (cùng
   composition root với `run_acceptance.py`/`tests/agent/test_deterministic_agent.py`), không
   cần Docker hay HTTP layer.
2. ✅ Với mỗi case, đọc trực tiếp `InvestigationRequest` + `ExecutionTrace` (`DR1-002`) trả về
   từ `run_with_steps()` để lấy concepts/operation/intent/target/params/answer_type/
   answer_strategy/llm_usage_reason/required_evidence, so với `expected` trong golden case.
3. ✅ Ghi rõ trong code + report: `routing_status` và `evidence_status` KHÔNG phải field chính
   thức của `ExecutionTrace` (còn chờ `DR1-308`/`DR1-505`) — script tự suy ra best-effort và
   đánh dấu riêng `*(approx.)*`, không trộn vào `correct_investigation_rate` headline.
4. ✅ Report JSON + Markdown ghi `git_commit`, `config_hash` (sha256 của `targets.json` +
   `servers.json`), `model`/`provider` (qua `benchmark/metadata.py:collect_benchmark_metadata`),
   `golden_dataset_path`, cases_total, và toàn bộ danh sách case fail kèm field mismatch.
5. ✅ Ghi stage accuracy (concept/operation/intent/target/params/answer_type/answer_strategy/
   llm_usage_reason/required_evidence), outcome rates (deterministic_answer_coverage,
   expected_assessment_rate, routing_fallback_rate, insufficient_evidence_rate), accuracy theo
   nhóm A–J/M, và latency (median/p95 `total_duration_ms`).
6. Không sửa `run_acceptance.py` (dùng `TEST_CASES` hardcode, không phải golden dataset) — việc
   đổi nó sang stage-level scoring thuộc `DR1-807`, ngoài scope DR1-005.
7. Không có `unsafe_assumption_rate`/`correct_clarification_rate` trong report này — hai metric
   này cần claim validator (`DR1-703`) và clarification responder (`DR1-309`) chưa tồn tại; report
   ghi rõ "not computed" thay vì đưa số giả.

**Acceptance criteria**
- [x] Baseline reproducible trên cùng fixture — mọi field được so sánh (concept/intent/target/
      params/answer_type/answer_strategy/llm_usage_reason/required_evidence) đến từ pipeline
      quyết định, không phụ thuộc nội dung text LLM sinh ra, nên deterministic giữa các lần chạy
      cùng code + cùng config.
- [x] Report có commit SHA, config hash, model/provider và target fixture (xem `metadata` trong
      JSON output, ví dụ chạy thử: `git_commit`, `config_hash=86a9b900837fcdc4`,
      `golden_dataset_path`, `golden_dataset_cases_total=38`).

**Tests/verification**
- ✅ `python3 -m pytest tests/qa/test_run_baseline.py -q` — 14 tests pass (load/skip
  harness_error, extract_actual cho investigation/chat/unknown-target/partial-evidence,
  score_case cho match/mismatch/order-independent list so sánh, config_hash, summarize,
  render_markdown).
- ✅ `ruff check scripts/qa/run_baseline.py tests/qa/test_run_baseline.py` — clean.
- ✅ Chạy thử end-to-end trong môi trường chưa cấu hình model (`no model configured`):
  `python3 scripts/qa/run_baseline.py --output-dir /tmp/baseline_test` — chạy hết 38/38 case,
  không crash, sinh `baseline_<timestamp>.json` + `.md` hợp lệ. Baseline **thật** (có ý nghĩa số
  liệu) cần chạy lại trên máy có model + targets đã cấu hình đầy đủ trước khi bắt đầu `DR1-101`.
- `tests/benchmark/test_report_wiring.py` — không đụng, vẫn pass nguyên trạng (không sửa module
  `benchmark/`, chỉ import `collect_benchmark_metadata` để tái dùng).

**Cập nhật bổ sung 1 (2026-08-04, model preflight):** thêm `--smoke` mode và
`BaselinePreflightError` — mặc định `run_baseline()` giờ bắt buộc phải resolve được model từ
`servers.json` VÀ health-check pass trước khi chạy case nào, để tránh trường hợp môi trường chưa
cấu hình model (setup mode) âm thầm sinh ra baseline "0%" trông như baseline thật. Report có thêm
`meta["meaningful_baseline"]` — chỉ `true` khi chạy bằng model thật đã health-check OK.
`--smoke` cho phép chạy thử pipeline/scorer bằng `UnconfiguredAssessmentAdapter` mà không giả vờ
đó là baseline (markdown ghi rõ "Smoke run — not a meaningful baseline", không publish
`correct_investigation_rate`).

**Cập nhật bổ sung 2 (2026-08-04, tri-state scoring):** phát hiện: baseline chạy thật (38/38 case,
0 exception) vẫn ra `correct_investigation_rate = 0%` — không phải do model, mà do scorer coi mọi
field không quan sát được (vì `investigation`/`execution_trace` bị short-circuit) là mismatch.
Đối chiếu trực tiếp `src/agent/deterministic_agent.py:run_with_steps()` xác nhận 4 trường hợp
`investigation is None` có nguyên nhân cấu trúc khác nhau (không phải cùng 1 loại "thiếu dữ liệu"):
route thẳng chat (`execution_trace` trả về `None` toàn bộ, không chỉ thiếu field), `UnknownTargetError`
(pipeline đã tính concept/operation/intent trước khi raise nhưng investigation bị discard),
`Exception` chung (fallback chat, không biết pipeline chạy tới đâu), và exception thoát khỏi chính
runner (không biết gì cả). Sửa:
- Mỗi field giờ có 1 trong 3 trạng thái: `match` / `mismatch` / `not_observable`
  (`score_case()["field_status"]`, thay cho `field_matches` boolean cũ).
- `investigation_context()` (hàm mới, public) phân loại 5 ngữ cảnh: `investigated`, `chat`,
  `target_shortcircuit`, `pipeline_shortcircuit`, `runner_exception` — quyết định field nào bị ép
  `not_observable` theo đúng field nào pipeline THẬT SỰ không tính được (không phải mọi field
  investigation-derived đều bị ép — ví dụ `target` vẫn quan sát được ở `target_shortcircuit` vì
  `None` chính là tín hiệu thật; `llm_usage_reason=NONE` vẫn quan sát được ở path này vì code thật
  set giá trị đó tường minh).
- `answer_strategy`/`llm_usage_reason` thiếu (giá trị `None` thật trong trace) → `not_observable`
  bất kể context — không tự bịa `"NONE"`/`"CHAT"` mặc định (sửa cả `_runner_exception_result()`,
  trước đó fabricate `llm_usage_reason="NONE"`).
- Thêm 3 metric mới trong `summary`: `strict_correct_investigation_rate` (giữ nguyên bar cũ — mọi
  core field phải `match`, `not_observable` vẫn tính là fail, không đổi để "tăng điểm"),
  `observable_core_accuracy` (accuracy chỉ tính trên field thực sự quan sát được), và
  `trace_completeness_rate` (bao nhiêu % field core là quan sát được, bất kể đúng/sai — đo độ hoàn
  thiện của trace, không đo độ đúng của pipeline).
- `report["diagnostics"]` tách 3 nhóm riêng: `behavioral_mismatches` (bug pipeline thật),
  `trace_observability_gaps` (lỗ hổng instrumentation, không phải bug hành vi), và
  `approximate_fields` (routing_status/evidence_status, không đổi, vẫn "not authoritative").
- Chạy thử `--smoke` sau khi sửa: `observable_core_accuracy=52.92%`, `trace_completeness_rate=90.23%`
  — khác hẳn `strict_correct_investigation_rate=0.00%` (đúng, vì smoke mode dùng
  `UnconfiguredAssessmentAdapter` nên hầu hết case thật sự sai) — chứng minh scorer giờ phân biệt
  được "field không quan sát được" khỏi "field sai thật", đúng yêu cầu.

**Tests/verification (bổ sung):**
- ✅ `python3 -m pytest tests/qa/test_run_baseline.py -q` — 30 tests pass, gồm 4 test bắt buộc:
  chat path thiếu strategy → `not_observable` (`test_chat_path_missing_strategy_is_not_observable`),
  unknown-target short-circuit → field upstream `not_observable`, `target`/`llm_usage_reason` vẫn
  quan sát được (`test_unknown_target_shortcircuit_marks_upstream_fields_not_observable`), mismatch
  thật vẫn bị báo `mismatch` (`test_target_mismatch_fails_core`), và `not_observable` không bị tính
  vào mismatch ở metric tổng hợp (`test_not_observable_excluded_from_observable_accuracy_and_completeness`).
- ✅ `ruff check scripts/qa/run_baseline.py tests/qa/test_run_baseline.py` — clean.
- ✅ `python3 scripts/qa/run_baseline.py --smoke --output-dir /tmp/baseline_test2` — chạy hết
  38/38 case, sinh report hợp lệ với 3 metric mới + 3 mục diagnostics.
- Không sửa golden dataset, `ParameterExtractor`, hay agent source trong lần sửa này (đúng scope).

---
### DR1-006 — Reconcile trạng thái Phase 6 với behavior hiện tại
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-005
- **Files:** `docs/ai/08_PROJECT_STATE.md`, `docs/ai/10_PHASE6_PLAN.md`

**Vấn đề**  
Tài liệu báo Phase 6 completed nhưng QA cho thấy parameter wiring, fallback, evidence semantics và routing vẫn có gap.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Đối chiếu đủ 32 task 601–632 với source hiện tại, focused tests và các commit delivery
   Phase 6 (`c68dad4`, `70f9943`, `2c04422`, `1982b81`, `0a34649`).
2. ✅ Giữ Phase 6 là historical delivery completed; định nghĩa rõ ký hiệu ✅ ở phần này chỉ xác
   nhận module/field/hook đã được giao, không tự động chứng minh behavior hiện tại đạt DR1
   acceptance.
3. ✅ Thêm reconciliation matrix từng ID trong `10_PHASE6_PLAN.md`, nêu source/test evidence và
   corrective owner. Các gap xác nhận trực tiếp gồm: params không được bind vào child-tool args,
   selected tool không quyết định capability route, threshold/correlation không có production call
   site, cache key thiếu params/timeframe, responder chưa có fact validity, và Grafana mới tạo
   deep link chứ chưa thu time-series.
4. ✅ Đồng bộ `08_PROJECT_STATE.md`: đổi wording thành “delivery completed; corrective behavior
   work open”, thêm bảng mapping theo WP/ID và xóa claim stale rằng backlog đang rỗng.
5. Không sửa source behavior, golden dataset hoặc baseline scorer; DR1-006 là doc reconciliation
   nên không chạy benchmark mới.

**Acceptance criteria**
- [x] Project state phản ánh được “module tồn tại” khác với “behavior đạt acceptance”.
- [x] Mỗi Phase 6 ID 601–632 có evidence hiện tại và corrective DR1 owner khi còn gap.
- [x] Không hạ historical completion chỉ vì corrective task đang mở.

**Tests/verification**
- ✅ `python3 -m pytest tests/pipeline/test_parameter_extractor.py
  tests/pipeline/test_answer_type.py tests/pipeline/test_tool_selector.py
  tests/pipeline/test_capability_planner.py tests/pipeline/test_target_resolver.py
  tests/pipeline/test_target_resolver_upgrade.py tests/pipeline/test_deterministic_responder.py
  tests/pipeline/test_evidence_cache.py tests/pipeline/test_threshold_evaluator.py
  tests/pipeline/test_evidence_correlation.py tests/pipeline/test_time_range_resolver.py
  tests/pipeline/test_execution_engine.py tests/agent/test_deterministic_agent.py
  tests/model/protocol/test_prompt_builder_v2.py tests/tool/test_grafana_tool.py -q` — 192 passed.
- ✅ Rà source call-site bằng `rg`: xác nhận mapping trong reconciliation matrix, đặc biệt các
  boundary `_execute_node()`, `selected_tool`, `ThresholdEvaluator`, `EvidenceCorrelation`,
  `EvidenceCache`, `build_links()`.
- ✅ `git diff --check` và doc consistency review; không cần benchmark riêng.

---

## 4. EPIC 1 — Execution contract và failure semantics
### DR1-101 — Tạo CommandStatus và CommandResult
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-002
- **Files:** `src/tool/execution_backend.py`, `src/shared/execution/command_result.py (new)`, `src/tool/linux/__init__.py`, `tests/shared/execution/test_command_result.py (new)`

**Vấn đề**  
Contract `(bool, str)` làm mất exit code, stderr và loại lỗi; downstream không phân biệt dữ liệu rỗng với command failure.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Tạo đủ enum `CommandStatus` và immutable/slotted `CommandResult` với toàn bộ field contract.
2. ✅ `ExecutionBackend.run()`, local backend và SSH backend trả `CommandResult`; LinuxTool truyền
   object này xuống collector.
3. ✅ `CommandResult.__iter__()` giữ tuple-unpack `(ok, output)` trong migration window; code mới
   đọc named fields.
4. ✅ `repr` không in nội dung stream; `to_dict()` redact password/token/Bearer/URL credentials.

**Acceptance criteria**
- [x] Mọi backend trả CommandResult.
- [x] Exit code/stderr không bị bỏ.
- [x] Không chứa raw credential trong repr/serialization.

**Tests/verification**
- ✅ `python3 -m pytest tests/shared/execution/test_command_result.py tests/tool/test_execution_backend.py tests/tool/test_execution_backend_thread_safety.py tests/tool/test_linux_tool.py tests/tool/test_linux_tool_process.py -q` — 136 passed.
- ✅ `ruff check` các file chạm tới — clean.

---
### DR1-102 — Sửa LocalExecutionBackend giữ stderr và timeout
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-101
- **Files:** `src/tool/execution_backend.py`, `tests/tool/test_execution_backend.py`

**Vấn đề**  
Local backend hiện có thể trả chuỗi rỗng khi command non-zero, khiến failure thành empty evidence.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `subprocess.run` dùng capture/text/timeout/check=False và `LANG=LC_ALL=C` trên bản sao env.
2. ✅ Map empty command/FileNotFoundError, PermissionError, TimeoutExpired, empty success và
   non-zero/permission exit sang status riêng; giữ cả partial stdout/stderr khi timeout/non-zero.
3. ✅ Mọi path đo duration bằng monotonic clock; tuple adapter cũ vẫn không biến error thành
   evidence text cho local collectors.

**Acceptance criteria**
- [x] `false` command trả NON_ZERO_EXIT, không trả success.
- [x] Command không tồn tại giữ được stderr/error_type.
- [x] Timeout không treo worker.

**Tests/verification**
- ✅ Focused backend/Linux regression selection — 139 passed.
- ✅ `ruff check src/tool/execution_backend.py tests/tool/test_execution_backend.py` — clean.

---
### DR1-103 — Sửa SSHExecutionBackend trả lỗi có cấu trúc
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-101
- **Files:** `src/tool/execution_backend.py`, `src/shared/execution/command_result.py`, `tests/tool/test_execution_backend.py`

**Vấn đề**  
SSH failure hiện dễ bị gom thành generic false/empty, không biết auth, DNS, timeout hay remote command lỗi.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ FileNotFoundError của local `ssh` binary → COMMAND_NOT_FOUND; OSError local khác →
   UNSUPPORTED_ENVIRONMENT.
2. ✅ Adapter classifier tập trung map auth/public-key/password, connection/DNS/network,
   connection timeout, remote command-not-found và permission; không có retry command khác.
3. ✅ Mọi remote failure giữ exit code/stdout/stderr, trong khi auth message được chuẩn hóa để
   không phản chiếu credential/raw prompt.

**Acceptance criteria**
- [x] Phân biệt được auth fail, host unreachable, remote command not found.
- [x] Không log private key/password.

**Tests/verification**
- ✅ Mocked SSH + backend/Linux regression selection — 144 passed.
- ✅ `ruff check` các file chạm tới — clean.

---
### DR1-104 — Tạo CapabilityResult và CapabilityStatus
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-101
- **Files:** `src/tool/capability_result.py (new)`, `src/tool/tool.py`, `src/tool/linux/__init__.py`, `src/shared/execution/tool_result.py`, `tests/tool/test_capability_result.py (new)`

**Vấn đề**  
Capability handler trả dict trực tiếp nên không biểu diễn valid_empty, partial, unsupported, parse failure hay collection failure.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Tạo đủ status và immutable `CapabilityResult` với data, command results, warnings,
   produced fact names, error.
2. ✅ `from_legacy()` phân biệt valid empty, mixed-command partial và all-command collection
   failure; failed command không thể bị wrap thành success.
3. ✅ Base Tool `_dispatch()` và LinuxTool chấp nhận structured result, wrap payload handler cũ;
   LinuxTool dùng per-execution closure để track command results an toàn khi concurrent.
4. ✅ `ToolResult.from_capability_result()` giữ status/commands/warnings/fact names qua boundary.

**Acceptance criteria**
- [x] Một capability thất bại không bị bọc thành ToolResult success=True.
- [x] Valid empty được phân biệt với collection failed.

**Tests/verification**
- ✅ Tool/Linux/Grafana/Zabbix/CapabilityResult selection — 155 passed.
- ✅ `ruff check` và focused `mypy` các file source chạm tới — clean.

---
### DR1-105 — Lan truyền failure đúng qua ToolResult và EvidencePackage
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-104
- **Files:** `src/shared/execution/tool_result.py`, `src/pipeline/evidence_package.py`, `src/pipeline/evidence_merge.py`, `src/pipeline/evidence_completeness.py`, `src/pipeline/execution_runtime.py`

**Vấn đề**  
Ngay cả khi handler không ném exception, lỗi thu thập có thể bị coi là thành công.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Map `CapabilityStatus` xuyên ToolResult/EvidenceMerge/EvidencePackage, giữ commands,
   warnings, produced facts và collection failures.
2. ✅ EvidencePackage chuẩn hóa legacy success sang VALID/VALID_EMPTY/COLLECTION_FAILED;
   PARTIAL giữ data để assessment thấy phần thu được nhưng `success=False`.
3. ✅ EvidenceCompleteness chỉ tính VALID/VALID_EMPTY; runtime gắn status rõ cho unsupported,
   timeout, dispatch errors và vẫn trả result của mọi node.

**Acceptance criteria**
- [x] Failure của một node không làm mất evidence node khác.
- [x] Evidence failed không được tính là collected required evidence.

**Tests/verification**
- ✅ Evidence/package/merge/completeness/runtime/engine/Tool/Linux selection — 171 passed.
- ✅ `ruff check` và focused `mypy` source chạm tới — clean.

---
### DR1-106 — Loại bỏ toàn bộ failure-to-zero/default-empty
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-104, DR1-105
- **Files:** `src/tool/linux/__init__.py`, `src/tool/linux/capabilities/{cpu,disk,memory,network,process,service}.py`, `src/model/protocol/prompt_builder_v2.py`, `src/pipeline/deterministic_responder.py`

**Vấn đề**  
Các giá trị mặc định 0/[] đang được diễn giải như phép đo thật: 0 service, 0 process, CPU 0%, không port.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ LinuxTool ghi nhận cả backend legacy `(ok, output)`; nếu mọi command đều fail thì
   capability là COLLECTION_FAILED với `data=None`, còn command thành công rỗng vẫn giữ
   EMPTY_SUCCESS/valid-empty semantics.
2. ✅ Collector CPU/memory/disk/network/process/service bỏ field khi probe/parser không tạo
   được phép đo; số 0 và danh sách rỗng chỉ còn được tạo từ output command thành công.
3. ✅ Prompt summary không tự chèn `total=0`, `running=0`, core count/size/network list;
   deterministic responder bảo toàn zero hợp lệ bằng key-presence và chỉ đọc package
   `valid_for_requirements`.
4. ✅ Service responder không còn kết luận "all running" chỉ từ total/list length; cần fact
   `failed=0` đã thu hợp lệ, và partial evidence không được dùng để trả deterministic fact.

**Acceptance criteria**
- [x] Không có case command fail nào sinh fact value=0.
- [x] Deterministic responder từ chối trả fact nếu validity không VALID/VALID_EMPTY phù hợp.

**Tests/verification**
- ✅ Tool/Pipeline/Model regressions, gồm service/process/CPU/network — 913 passed.
- ✅ `ruff check` và focused `mypy` source chạm tới — clean.

---
### DR1-107 — Chuẩn hóa taxonomy lỗi capability
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-104
- **Files:** `src/tool/errors.py (new)`, `src/tool/capability_result.py`, `src/shared/execution/tool_result.py`, `src/pipeline/{evidence_package,evidence_merge,retry,execution_runtime}.py`, Child Tool adapters

**Vấn đề**  
Fallback/retry chỉ an toàn khi error contract thống nhất.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Tạo immutable `CapabilityError` với code/category/message/recoverable/command_id,
   serialization redacted và repr không chứa message; cấu trúc này truyền qua
   CapabilityResult → ToolResult → EvidencePackage.
2. ✅ Backend mapping dùng enum, không đọc substring: timeout và SSH unreachable recoverable;
   command-not-found/permission/auth/unsupported/non-zero/parse không recoverable.
3. ✅ Capability mapping phân biệt invalid parameters, unsupported environment, parse failure,
   generic collection, internal adapter error và explicit source API error.
4. ✅ RetryExecutor hỗ trợ result policy; ExecutionRuntime chỉ retry ToolResult có structured
   `capability_error.recoverable=True`, giữ nguyên exception retry policy hiện hữu.

| Backend/capability outcome | Error category | Recoverable |
|---|---|---:|
| `TIMEOUT`, `SSH_UNREACHABLE` | transport | yes |
| `SSH_AUTH_FAILED` | transport | no |
| `COMMAND_NOT_FOUND`, `PERMISSION_DENIED`, `UNSUPPORTED_ENVIRONMENT` | environment | no |
| `NON_ZERO_EXIT`, generic collection failure | command | no |
| `PARSE_ERROR` / `PARSE_FAILED` | parser | no |
| invalid parameters | parameter | no |
| provider/API exception | source_api | yes |
| unexpected adapter/runtime exception | internal | no |

**Acceptance criteria**
- [x] Không fallback dựa trên substring rời rạc ngoài adapter mapping.
- [x] Mỗi error code có test.

**Tests/verification**
- ✅ `tests/tool/test_error_mapping.py` bao phủ mọi error code và redaction.
- ✅ Tool/Pipeline/Model regressions — 937 passed.
- ✅ `ruff check` và focused `mypy` source chạm tới — clean.

---
### DR1-108 — Không cache failed/partial evidence như valid
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-105
- **Files:** `src/pipeline/evidence_cache.py`, `src/pipeline/execution_engine.py`, `tests/pipeline/test_evidence_cache.py`, `tests/pipeline/test_execution_engine.py`

**Vấn đề**  
Cache lỗi dưới key evidence làm các turn sau tiếp tục dùng dữ liệu không hợp lệ.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ EvidenceCache `put()` chỉ nhận EvidencePackage VALID/VALID_EMPTY và trả boolean policy
   result; PARTIAL/failed bị từ chối, không tạo negative cache.
2. ✅ `get()` kiểm tra lại validity và tự loại invalid entry từ state/phiên bản cũ để invalid
   package không thể trở thành hit hợp lệ.
3. ✅ Cả mutable và immutable ExecutionEngine chỉ ghi package `valid_for_requirements`;
   `_without_cached_nodes()` chỉ bỏ runtime node khi cached package vẫn hợp lệ.
4. ✅ Recovery regression chứng minh request lỗi đầu không cache, request sau recollect được
   evidence mới khi nguồn phục hồi, và request kế tiếp mới dùng cache hit.

**Acceptance criteria**
- [x] Failed package không xuất hiện như cache hit hợp lệ.
- [x] Retry request sau khi nguồn phục hồi thu được evidence mới.

**Tests/verification**
- ✅ Cache/engine/evidence focused selection — 59 passed.
- ✅ Tool/Pipeline/Model regressions — 943 passed.
- ✅ `ruff check`; focused `mypy --ignore-missing-imports` source chạm tới — clean.

---

## 5. EPIC 2 — Runtime và Child Tool correctness
### DR1-201 — Khai báo dependency tối thiểu cho Docker runtime
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-101
- **Files dự kiến:** `docker/Dockerfile.api`, `pyproject.toml`, `docs/devops/docker.md`

**Vấn đề**  
Image gọi nhiều binary nhưng Dockerfile không bảo đảm có `ssh`, `ip`, `ping`, `ps`, `top`, `ss`.

**Cách làm**
1. Cài tối thiểu `openssh-client`, `procps`, `iproute2`, `iputils-ping`, `util-linux`, CA certificates.
2. Optional packages gắn rõ capability: sysstat, smartmontools, nvme-cli, dmidecode, pciutils, usbutils, iptables, nftables.
3. Thêm smoke check binary trong CI.

**Acceptance criteria**
- [x] Container API có đủ binary cho capability core.
- [x] Optional missing dẫn tới UNSUPPORTED, không zero.

**Tests/verification**
- ✅ `docker compose build --quiet api`.
- ✅ Container smoke tìm thấy `ssh`, `ps`, `top`, `ip`, `ping`, `lsblk`, `df`, `ss`.
- ✅ `tests/test_smoke_containers.py` và `tests/test_installation.py` kiểm dependency/runtime health contract.

---
### DR1-202 — Làm rõ semantics của target `localhost`
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-201
- **Files dự kiến:** `targets.json`, `src/tool/target_registry.py`, `docs/tools/linux.md`, `docs/ai/02_CURRENT_ARCHITECTURE.md`

**Vấn đề**  
`backend=local` trong container nghĩa là Orion API container, không mặc nhiên là physical host.

**Cách làm**
1. Quyết định và ghi ADR/config: `localhost` là Orion container hay monitored host.
2. Nếu physical host cần giám sát, đăng ký SSH/collector target riêng; không mount host namespace ngầm.
3. Đổi display name thành `orion-api` nếu giữ nghĩa container.

**Acceptance criteria**
- [x] UI/CLI mô tả đúng môi trường thực thi.
- [x] Không còn câu trả lời gọi dữ liệu container là dữ liệu host vật lý.

**Tests/verification**
- ✅ `tests/tool/test_target_registry.py` và `tests/tool/test_target_store.py` bao phủ display name, execution scope và metadata persistence.
- ✅ Linux evidence mang target identity `orion-api`; physical host phải đăng ký target SSH riêng.

---
### DR1-203 — Thêm target preflight và environment fingerprint
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-101, DR1-202
- **Files dự kiến:** `src/tool/target_preflight.py (new)`, `src/tool/target_registry.py`, `src/pipeline/execution_engine.py`

**Vấn đề**  
Capability cần biết target reachable, OS/init system và command availability trước khi chọn strategy.

**Cách làm**
1. Preflight nhẹ: connectivity, OS, init system, available command set, privilege level.
2. Cache preflight ngắn theo target/config hash.
3. Preflight failure tạo structured evidence limitation, không chạy hàng loạt command vô ích.

**Acceptance criteria**
- [x] SSH chết chỉ tạo một transport failure và skip dependent commands.
- [x] Capability planner thấy environment support.

**Tests/verification**
- ✅ `tests/tool/test_target_preflight.py` bao phủ fingerprint, config-hash cache/TTL và transport short-circuit.

---
### DR1-204 — Bổ sung capability preconditions và required binaries
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-203
- **Files dự kiến:** `src/shared/capability.py hoặc capability metadata hiện có`, `src/pipeline/capability_library.py`, `src/tool/linux/__init__.py`

**Vấn đề**  
Metadata hiện mô tả capability nhưng chưa đủ để chọn strategy theo environment.

**Cách làm**
1. Thêm `preconditions`, `required_binaries`, `supported_init_systems`, `estimated_cost`, `expected_reliability`, `produces_facts`.
2. KnowledgeTool chỉ aggregate metadata; không duplicate.
3. Validator kiểm precondition trước dispatch.

**Acceptance criteria**
- [x] Unsupported capability fail trước execution với lý do rõ.
- [x] Metadata là một nguồn sự thật.

**Tests/verification**
- ✅ `tests/shared/test_capability.py`, `tests/tool/test_knowledge_tool.py` và capability-library regressions.
- ✅ KnowledgeTool export metadata từ Child Tool và validate environment trước dispatch.

---
### DR1-205 — Làm CPU collector ổn định bằng `/proc/stat`
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-104
- **Files dự kiến:** `src/tool/linux/capabilities/cpu.py`

**Vấn đề**  
Parser `top -bn1` phụ thuộc locale/format và có thể sinh user/system/idle đều 0.

**Cách làm**
1. Đọc hai snapshot `/proc/stat` cách nhau khoảng ngắn để tính usage.
2. Đọc `/proc/loadavg`, logical cores và `/proc/cpuinfo`/`lscpu` fallback.
3. Giữ `top` chỉ cho top process hoặc fallback có parser được test.

**Acceptance criteria**
- [x] CPU usage tổng xấp xỉ 100% distribution trong tolerance.
- [x] Không kết luận idle khi idle fact thiếu.

**Tests/verification**
- ✅ `tests/tool/test_linux_tool_cpu.py` dùng hai fixture `/proc/stat`, kiểm distribution, load và failure semantics.

---
### DR1-206 — Service status có bounded multi-strategy fallback
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-107, DR1-204
- **Files dự kiến:** `src/tool/linux/capabilities/service.py`

**Vấn đề**  
`systemctl` không tồn tại trong container/non-systemd làm toàn bộ service capability vô dụng.

**Cách làm**
1. Strategy theo thứ tự: systemd → SysV `service` → OpenRC → process lookup → listening-port evidence.
2. Chỉ fallback trên recoverable errors.
3. Kết quả process/port phải ghi confidence thấp hơn và không đồng nhất “process tồn tại” với “service healthy”.

**Acceptance criteria**
- [x] Nginx trên systemd trả service status; môi trường không systemd trả partial/alternative evidence.
- [x] SSH timeout không chạy tiếp fallback.

**Tests/verification**
- ✅ `tests/tool/test_linux_tool_service.py` bao phủ systemd/SysV/OpenRC/process/port và transport short-circuit.

---
### DR1-207 — Thu log theo service và time range
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-206, DR1-403, DR1-406
- **Files dự kiến:** `src/tool/linux/capabilities/service.py hoặc logs.py (new)`

**Vấn đề**  
Generic `journalctl -n 50` không trả đúng log của service người dùng hỏi.

**Cách làm**
1. Nhận validated `service_name`, `since`, `until`, `limit`.
2. Systemd: `journalctl -u <escaped unit>`; fallback file logs chỉ từ allowlisted path/resolver.
3. Không cho user chèn raw shell fragment.

**Acceptance criteria**
- [x] “nginx crash” thu đúng unit log hoặc báo unsupported.
- [x] Parameter injection bị reject.

**Tests/verification**
- ✅ `tests/tool/test_linux_tool_service.py` kiểm exact unit, bounded time/limit, allowlisted file fallback và injection rejection.
- ✅ `tests/pipeline/test_security_pipeline.py` kiểm raw mutating parameters bị chặn.

---
### DR1-208 — Network collector có `/proc` và `/sys` fallback
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-204
- **Files dự kiến:** `src/tool/linux/capabilities/network.py`

**Vấn đề**  
`ip`/`ss` thiếu khiến network trả unknown dù kernel files vẫn có dữ liệu.

**Cách làm**
1. Interfaces/statistics từ `/sys/class/net` và `/proc/net/dev`.
2. Routing fallback `/proc/net/route`; listening sockets fallback chỉ khi parser đủ an toàn hoặc trả unsupported.
3. Ghi source strategy trong provenance.

**Acceptance criteria**
- [x] Có interface stats khi `ip` không cài.
- [x] Không tuyên bố “không có network” từ collector failure.

**Tests/verification**
- ✅ `tests/tool/test_linux_tool_network.py` bao phủ `/proc/net/dev`, `/sys/class/net`, route/socket fallback và collection-source provenance.

---
### DR1-209 — Tách filesystem usage, inode, I/O và disk health
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-104
- **Files dự kiến:** `src/tool/linux/capabilities/disk.py`

**Vấn đề**  
Filesystem read-only/usage hiện có thể bị diễn giải thành physical disk healthy; thiếu inode và I/O.

**Cách làm**
1. Tách capabilities/facts: filesystem.capacity, filesystem.inode, disk.io, disk.device_health.
2. `df -P`/`statvfs` cho capacity; `df -i` cho inode; `/proc/diskstats` hoặc iostat cho I/O; smartctl/nvme optional cho health.
3. Không claim SMART healthy khi tool không chạy.

**Acceptance criteria**
- [x] Disk 37% chỉ là capacity fact, không phải health finding.
- [x] Health absent → unsupported/not collected.

**Tests/verification**
- ✅ `tests/tool/test_linux_tool_disk.py` kiểm capacity/inode/I/O/device-health tách biệt và không suy diễn health từ capacity.

---
### DR1-210 — Chuẩn hóa Linux capability outputs trước pipeline
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-104, DR1-205..209
- **Files dự kiến:** `src/tool/linux/capabilities/*.py`

**Vấn đề**  
Các capability dùng key/unit không nhất quán, làm prompt và rule phải đoán schema.

**Cách làm**
1. Định nghĩa schema output cho từng capability.
2. Dùng bytes/seconds/percent nhất quán; display conversion nằm ở responder.
3. Validate schema trước CapabilityResult VALID.

**Acceptance criteria**
- [x] Output capability pass schema validation.
- [x] Không còn key aliases trong prompt builder để chữa schema.

**Tests/verification**
- ✅ `tests/tool/test_linux_output_schema.py` kiểm schema core và fail-before-VALID.
- ✅ Prompt builder chỉ đọc canonical keys có suffix unit rõ (`_bytes`, `_seconds`, `_percent`).

---
### DR1-211 — Khóa ranh giới read-only, không chạy raw command từ LLM
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-204
- **Files dự kiến:** `src/pipeline/security/*`, `src/model/assessment_model_adapter.py`, `src/agent/deterministic_agent.py`, `docs/adr/ADR-0002-llm-assessment-only.md`

**Vấn đề**  
Transcript có hallucination “đã xóa /tmp”; cần bảo đảm architecture và output đều không cho LLM tạo hành động.

**Cách làm**
1. Không thêm API nhận raw shell từ model.
2. Capability command template thuộc Child Tool và parameter được validate.
3. Security inspector chạy trên mọi execution path.
4. Assessment adapter không có tool access.

**Acceptance criteria**
- [x] Prompt injection yêu cầu `rm -rf` không tạo command execution.
- [x] Trace chứng minh 100% capability path qua inspector chain.

**Tests/verification**
- ✅ `tests/pipeline/test_security_pipeline.py` kiểm mandatory fail-closed inspector chain, mutation metadata và raw-command injection.
- ✅ `tests/pipeline/test_execution_trace.py` kiểm security inspection counters/receipt trong trace.
- ✅ Assessment adapter không nhận tool/callback execution; prompt và ADR ghi rõ read-only boundary.

---

## 6. EPIC 3 — Request understanding và deterministic routing
### DR1-301 — Loại LLM khỏi quyết định routing investigation
- **Priority:** P0
- **Status:** 🔎
- **Dependencies:** DR1-002
- **Files dự kiến:** `src/agent/deterministic_agent.py`, `src/pipeline/intent_resolver.py`

**Vấn đề**  
Low-confidence classifier dùng LLM làm mờ ranh giới “AI explains” và khó đo routing fallback.

**Cách làm**
1. Thay Tier-2 LLM classifier bằng `resolved`, `clarification_required`, `unsupported`, `general_chat`.
2. General chat subsystem tách khỏi infrastructure investigation.
3. Ghi `ROUTING_FALLBACK` khi deterministic stages không resolve.

**Acceptance criteria**
- [ ] Không có call model trước AssessmentRequest trong investigation path.
- [ ] Ambiguous request hỏi lại, không đoán.

**Tests/verification**
- `tests/agent/test_deterministic_agent.py kiểm call count/model mock`

---
### DR1-302 — Tạo RequestFrame thống nhất
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-301
- **Files dự kiến:** `src/pipeline/request_frame.py (new)`, `src/pipeline/semantic_request.py`, `src/pipeline/investigation_request.py`

**Vấn đề**  
Normalizer, IntentResolver và planner có thể parse raw text theo mapping riêng, gây concept/intent lệch nhau.

**Cách làm**
1. RequestFrame gồm concepts, operation, target_raw/resolved, parameters, answer_type, timeframe, confidence, ambiguity.
2. Stages sau chỉ đọc frame, không parse lại raw request trừ module chuyên trách.
3. Giữ raw request để audit.

**Acceptance criteria**
- [ ] Một request có một semantic frame canonical.
- [ ] Trace ghi expected/actual frame.

**Tests/verification**
- `tests/pipeline/test_request_frame.py`

---
### DR1-303 — Mở rộng deterministic normalizer cho typo và code-switching
- **Priority:** P1
- **Status:** 🔎
- **Dependencies:** DR1-302
- **Files dự kiến:** `src/pipeline/normalizer.py`, `config/concepts.yaml`

**Vấn đề**  
Các diễn đạt như “web bị ì”, typo và Việt-Anh trộn có thể rơi khỏi concept mapping.

**Cách làm**
1. Exact alias/grammar trước.
2. Character n-gram/edit distance/token similarity cho typo.
3. Thêm alias dựa trên golden cases đã review, không tự học trực tiếp từ transcript.
4. Giữ concept candidate list và evidence về match.

**Acceptance criteria**
- [ ] Coverage tăng trên golden typo/code-switching mà false route không tăng.
- [ ] Mọi alias global có review.

**Tests/verification**
- `tests/pipeline/test_normalizer.py`

---
### DR1-304 — Semantic candidate retrieval có deterministic validation
- **Priority:** P2
- **Status:** ⬜
- **Dependencies:** DR1-303
- **Files dự kiến:** `src/pipeline/semantic_candidate_retriever.py (new, optional)`, `src/pipeline/normalizer.py`

**Vấn đề**  
Exact/fuzzy có thể thiếu paraphrase; embedding local có thể hỗ trợ nhưng không được tự quyết capability.

**Cách làm**
1. Pipeline: exact → lexical fuzzy → embedding/BM25 candidates → deterministic validation.
2. Accept khi top1 >= threshold, margin top1-top2 >= margin, action compatible và params/target hợp lệ.
3. Nếu không muốn model dependency, dùng BM25/char n-gram; backend phải pluggable nhưng đơn giản.

**Acceptance criteria**
- [ ] Embedding chỉ trả candidates, không trả final route.
- [ ] Case top1 0.83/top2 0.81 phải clarify.

**Tests/verification**
- `tests/pipeline/test_semantic_candidate_retriever.py`

---
### DR1-305 — IntentResolver trả confidence, candidates và ambiguity margin
- **Priority:** P1
- **Status:** 🔎
- **Dependencies:** DR1-302
- **Files dự kiến:** `src/pipeline/intent_resolver.py`

**Vấn đề**  
Một intent label không đủ để biết có nên accept hay clarify.

**Cách làm**
1. Trả top candidates + score/margin.
2. Validate operation/concept compatibility.
3. Không dùng keyword đơn như `down` để đè ý nghĩa câu multi-intent.

**Acceptance criteria**
- [ ] Intent accuracy và correct clarification đạt gate.
- [ ] Không route “5 việc: disk, service down…” thành service tên `down`.

**Tests/verification**
- `tests/pipeline/test_intent_resolver.py`

---
### DR1-306 — TargetResolver dùng threshold + margin + unknown-target guard
- **Priority:** P0
- **Status:** 🔎
- **Dependencies:** DR1-302
- **Files dự kiến:** `src/pipeline/target_resolver.py`, `config/target_aliases.yaml`

**Vấn đề**  
Fuzzy target có thể accept ứng viên sát nhau hoặc fallback về localhost cho hostname không tồn tại.

**Cách làm**
1. Exact target và scoped alias trước fuzzy.
2. Accept fuzzy khi threshold và margin đều đạt.
3. Hostname-like token không tồn tại → UnknownTarget/clarification, không fallback localhost.
4. Fallback localhost chỉ khi không có explicit candidate và không có active target.

**Acceptance criteria**
- [ ] 100% unknown target cases không chạy localhost.
- [ ] Ambiguous target hỏi lại với candidates.

**Tests/verification**
- `tests/pipeline/test_target_resolver.py`

---
### DR1-307 — Alias có scope và vòng đời
- **Priority:** P2
- **Status:** ⬜
- **Dependencies:** DR1-306
- **Files dự kiến:** `src/pipeline/alias_store.py (new hoặc mở rộng config)`, `config/target_aliases.yaml`

**Vấn đề**  
Transcript correction chỉ đúng một session không nên tự thành global alias.

**Cách làm**
1. Scope: session, user, project/environment, global.
2. Lifecycle: observed, suggested, approved, active, deprecated.
3. Transcript chỉ tạo candidate report; human review trước promote global.

**Acceptance criteria**
- [ ] Session alias không rò sang session khác.
- [ ] Global alias có reviewer và evidence count.

**Tests/verification**
- `tests/pipeline/test_alias_scope.py`

---
### DR1-308 — Chuẩn hóa request class, routing status, evidence status, answer strategy
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-302
- **Files dự kiến:** `src/pipeline/answer_type.py`, `src/pipeline/routing_decision.py (new)`, `src/pipeline/investigation_request.py`

**Vấn đề**  
Chỉ đo “có gọi LLM” làm KPI sai và không phân biệt assessment hợp lệ với fallback.

**Cách làm**
1. Request class: fact, list, table, chart, assessment, comparison, forecast, action, explanation.
2. Routing status: resolved, clarification_required, fallback, unsupported.
3. Evidence status: sufficient, partial, unavailable, stale, contradictory.
4. Answer strategy: deterministic_fact/template, llm_assessment, clarification, refusal.

**Acceptance criteria**
- [ ] Mỗi trace có đủ taxonomy và `llm_usage_reason`.
- [ ] EXPECTED_ASSESSMENT không bị tính là routing failure.

**Tests/verification**
- `tests/pipeline/test_answer_type.py`
- `tests/pipeline/test_routing_decision.py`

---
### DR1-309 — Deterministic clarification responses
- **Priority:** P1
- **Status:** ⬜
- **Dependencies:** DR1-305, DR1-306, DR1-308
- **Files dự kiến:** `src/pipeline/clarification_responder.py (new)`, `src/agent/deterministic_agent.py`

**Vấn đề**  
Ambiguity không cần LLM; câu hỏi làm rõ phải chỉ đúng trường thiếu.

**Cách làm**
1. Template theo missing target, service, path, timeframe, concept ambiguity.
2. Hiển thị tối đa vài candidates đã validate.
3. Không thu evidence trước khi required parameter được làm rõ.

**Acceptance criteria**
- [ ] Clarification nêu đúng ambiguity và không đoán.
- [ ] Correct clarification rate đo được.

**Tests/verification**
- `tests/pipeline/test_clarification_responder.py`

---

## 7. EPIC 4 — Context, parameter và temporal wiring
### DR1-401 — Tạo SessionInvestigationContext có cấu trúc
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-302
- **Files dự kiến:** `src/agent/session_investigation_context.py (new)`, `src/agent/conversation_store.py`

**Vấn đề**  
Conversation summary hiện chủ yếu phục vụ prompt; target/concept của turn trước không ảnh hưởng routing đúng lúc.

**Cách làm**
1. Lưu active_target, active_concept, active_service, active_path, active_time_range, incident IDs.
2. Chỉ lưu semantic context nhỏ, không persist raw execution evidence trái stateless rule.
3. Cập nhật context sau request resolved, không từ text LLM summary.

**Acceptance criteria**
- [ ] Follow-up “Còn RAM?” kế thừa đúng target monitor.
- [ ] Context reset/switch target rõ ràng.

**Tests/verification**
- `tests/agent/test_session_investigation_context.py`

---
### DR1-402 — Resolve context trước Normalizer/Target/Planner
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-401
- **Files dự kiến:** `src/agent/deterministic_agent.py`, `src/pipeline/execution_engine.py`

**Vấn đề**  
Context được đưa vào assessment sau khi execution đã chọn sai target thì không thể sửa.

**Cách làm**
1. Merge current message + structured context thành resolver input.
2. Explicit target hiện tại luôn override active target.
3. Pronoun/follow-up chỉ kế thừa khi confidence đủ và không có conflict.

**Acceptance criteria**
- [ ] Context được ghi trong trace trước capability plan.
- [ ] Cross-turn target tests pass.

**Tests/verification**
- `tests/agent/test_deterministic_agent.py`
- `tests/pipeline/test_execution_engine.py`

---
### DR1-403 — Tạo ParameterBinder và truyền params xuống capability
- **Priority:** P0
- **Status:** 🔎
- **Dependencies:** DR1-302
- **Files dự kiến:** `src/pipeline/parameter_extractor.py`, `src/pipeline/parameter_binder.py (new)`, `src/pipeline/execution_runtime.py`

**Vấn đề**  
ParameterExtractor có thể lấy service_name/path/port nhưng runtime chỉ truyền source/resource.

**Cách làm**
1. Mapping explicit: service_name→name, process_name→query, path→path, port→port, ping_target→target, time_range→since/until.
2. Binder đọc capability metadata, không hardcode command.
3. Trace lưu extracted và bound params.

**Acceptance criteria**
- [ ] “nginx status” gọi capability với `name=nginx`.
- [ ] Ping/path/time range được truyền chính xác.

**Tests/verification**
- `tests/pipeline/test_parameter_extractor.py`
- `tests/pipeline/test_parameter_binder.py`
- `tests/pipeline/test_execution_runtime.py`

---
### DR1-404 — Validate required parameters trước execution
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-403
- **Files dự kiến:** `src/pipeline/capability_planner.py`, `src/pipeline/security/parameter_safety_inspector.py`

**Vấn đề**  
Thiếu service/path/target hiện có thể chạy generic capability rồi suy đoán.

**Cách làm**
1. Capability metadata đánh dấu required/default/enum/pattern.
2. Missing required → clarification; invalid → deterministic error.
3. Sanitize/escape chỉ là lớp cuối; ưu tiên argument list thay shell concatenation.

**Acceptance criteria**
- [ ] Không capability nào nhận parameter thiếu hoặc chưa validate.
- [ ] Injection strings bị reject.

**Tests/verification**
- `tests/pipeline/test_parameter_validation.py`

---
### DR1-405 — Decompose multi-intent thành subrequests có giới hạn
- **Priority:** P1
- **Status:** ⬜
- **Dependencies:** DR1-302, DR1-305
- **Files dự kiến:** `src/pipeline/request_decomposer.py (new)`, `src/pipeline/capability_planner.py`

**Vấn đề**  
Một câu hỏi chứa disk + service + CPU + logs bị keyword đơn route sai hoặc bỏ phần.

**Cách làm**
1. Parse coordinated concepts thành danh sách subframes chung target/timeframe.
2. Lập plan hợp nhất, deduplicate capability và chạy parallel.
3. Giới hạn số subrequests; câu quá rộng hỏi scope/ưu tiên.

**Acceptance criteria**
- [ ] Multi-intent golden cases thu đủ required evidence.
- [ ] Không tạo capability trùng.

**Tests/verification**
- `tests/pipeline/test_request_decomposer.py`

---
### DR1-406 — Chuẩn hóa TimeRange và temporal requirements
- **Priority:** P1
- **Status:** 🔎
- **Dependencies:** DR1-302, DR1-403
- **Files dự kiến:** `src/pipeline/time_range_resolver.py`, `src/pipeline/evidence_planner.py`

**Vấn đề**  
Comparison/forecast đang dùng snapshot vì timeframe không được gắn vào evidence requirement đầy đủ.

**Cách làm**
1. TimeRange gồm start/end/granularity/timezone/source phrase.
2. Question “hôm qua”, “7 ngày”, “6 tháng tới” tạo historical/forecast requirement khác snapshot.
3. Dùng timezone request/session rõ ràng.

**Acceptance criteria**
- [ ] Historical query không bị route thành current fact.
- [ ] Relative range deterministic và testable.

**Tests/verification**
- `tests/pipeline/test_time_range_resolver.py`

---
### DR1-407 — Guard comparison/forecast khi thiếu time series
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-406, DR1-505
- **Files dự kiến:** `src/pipeline/evidence_completeness.py`, `src/pipeline/deterministic_responder.py`, `src/model/protocol/prompt_builder_v2.py`

**Vấn đề**  
Orion từng kết luận trend, capacity 6 tháng và false positive chỉ từ snapshot.

**Cách làm**
1. Comparison yêu cầu ít nhất hai windows tương thích.
2. Forecast yêu cầu series đủ dài + growth model đã định nghĩa; nếu không trả insufficient evidence.
3. Cấm claim “xu hướng ổn định/xấu đi” từ một điểm.

**Acceptance criteria**
- [ ] 100% forecast/comparison golden cases thiếu history được từ chối đúng.

**Tests/verification**
- `tests/pipeline/test_temporal_evidence_guard.py`

---

## 8. EPIC 5 — Canonical Facts và evidence quality
### DR1-501 — Tạo canonical Fact model
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-104, DR1-302
- **Files dự kiến:** `src/pipeline/fact.py (new)`, `src/pipeline/evidence_package.py`

**Vấn đề**  
Rule và LLM hiện nhận nhiều dict/key/unit khác nhau, khó kiểm soát validity và provenance.

**Cách làm**
1. Fact gồm id, subject, metric, value, unit, observed_at, collected_at, source, target, validity, freshness, confidence, provenance.
2. Validity: VALID, VALID_EMPTY, COMMAND_FAILED, NOT_COLLECTED, UNSUPPORTED, STALE, SCHEMA_INVALID, CONTRADICTORY.
3. Value 0 chỉ hợp lệ khi validity VALID.

**Acceptance criteria**
- [ ] Fact immutable và serializable.
- [ ] Không thể tạo VALID fact thiếu metric/unit cần thiết.

**Tests/verification**
- `tests/pipeline/test_fact.py`

---
### DR1-502 — FactNormalizer cho Linux core capabilities
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-210, DR1-501
- **Files dự kiến:** `src/pipeline/fact_normalizers/linux.py (new)`

**Vấn đề**  
Linux evidence phải map sang metric canonical như cpu.usage, memory.usage, filesystem.usage.

**Cách làm**
1. Tạo normalizer per capability/schema version.
2. Convert units deterministic.
3. Gắn command/capability provenance.
4. Parser/schema error tạo invalidity, không fact zero.

**Acceptance criteria**
- [ ] CPU/memory/disk/service/network fixtures sinh expected facts.

**Tests/verification**
- `tests/pipeline/fact_normalizers/test_linux.py`

---
### DR1-503 — FactNormalizer cho Zabbix và Grafana
- **Priority:** P1
- **Status:** ⬜
- **Dependencies:** DR1-501
- **Files dự kiến:** `src/pipeline/fact_normalizers/zabbix.py (new)`, `src/pipeline/fact_normalizers/grafana.py (new)`

**Vấn đề**  
Cross-source correlation chỉ đúng khi cùng metric/target/time semantics.

**Cách làm**
1. Map Zabbix items/problems và Grafana series sang canonical metrics/events.
2. Giữ event_id/item_id/dashboard/query provenance.
3. Không trộn host status=0 với “healthy” nếu semantics chỉ là monitored/enabled.

**Acceptance criteria**
- [ ] Cùng cpu.usage từ Linux/Grafana có unit/time chuẩn.
- [ ] Active problem facts giữ severity và observed time.

**Tests/verification**
- `tests/pipeline/fact_normalizers/test_zabbix.py`
- `.../test_grafana.py`

---
### DR1-504 — Investigation FactSet và indexing
- **Priority:** P1
- **Status:** ⬜
- **Dependencies:** DR1-501..503
- **Files dự kiến:** `src/pipeline/fact_set.py (new)`, `src/pipeline/execution_engine.py`

**Vấn đề**  
Reasoning cần truy vấn fact theo target/metric/time/source mà không tạo persistence state lâu dài.

**Cách làm**
1. Tạo per-investigation FactSet immutable/append-only builder.
2. Index theo metric, target, validity.
3. Không lưu sang cross-session persistence; cache evidence vẫn theo policy riêng.

**Acceptance criteria**
- [ ] FactSet chỉ sống trong trace/investigation.
- [ ] Parallel collection merge deterministic.

**Tests/verification**
- `tests/pipeline/test_fact_set.py`

---
### DR1-505 — EvidenceCompleteness dựa trên required facts
- **Priority:** P0
- **Status:** 🔎
- **Dependencies:** DR1-501, DR1-504
- **Files dự kiến:** `src/pipeline/evidence_completeness.py`, `src/pipeline/evidence_requirement.py`

**Vấn đề**  
Hiện completeness chỉ so evidence_name và success, không biết đúng target/param/time/richness hay không.

**Cách làm**
1. Requirement khai báo metric, target, parameter scope, timeframe, validity, freshness.
2. Đánh giá satisfied/missing/failed/stale/contradictory.
3. Generic service inventory không thỏa `service.nginx.status`.

**Acceptance criteria**
- [ ] Complete chỉ true khi mọi required fact đạt contract.
- [ ] Output giải thích missing facts.

**Tests/verification**
- `tests/pipeline/test_evidence_completeness.py`

---
### DR1-506 — Detect và biểu diễn contradictory facts
- **Priority:** P1
- **Status:** ⬜
- **Dependencies:** DR1-504
- **Files dự kiến:** `src/pipeline/fact_reconciler.py (new)`, `src/pipeline/evidence_merge.py`

**Vấn đề**  
Các source có thể cho số khác nhau hoặc data ở thời điểm khác; LLM không nên tự chọn.

**Cách làm**
1. So sánh facts cùng metric/target/window với tolerance.
2. Ưu tiên freshness/source reliability chỉ theo config, không âm thầm overwrite.
3. Đánh dấu contradiction và giữ cả provenance.

**Acceptance criteria**
- [ ] Mâu thuẫn disk free/size được surface.
- [ ] Evidence status trở thành contradictory, không “healthy”.

**Tests/verification**
- `tests/pipeline/test_fact_reconciler.py`

---
### DR1-507 — Sửa EvidenceCache key và freshness policy
- **Priority:** P1
- **Status:** 🔎
- **Dependencies:** DR1-501, DR1-505
- **Files dự kiến:** `src/pipeline/evidence_cache.py`

**Vấn đề**  
Key target+evidence_name không phân biệt nginx/docker, / và /var, CPU 1h/7d.

**Cách làm**
1. Key gồm target, capability, normalized params, timeframe, schema version.
2. TTL theo fact class; current snapshot ngắn, identity dài hơn.
3. Không dùng stale fact trừ khi request cho phép và phải ghi stale.

**Acceptance criteria**
- [ ] Cache không cross-contaminate parameter/timeframe.
- [ ] Cache hit giữ provenance và freshness.

**Tests/verification**
- `tests/pipeline/test_evidence_cache.py`

---
### DR1-508 — Mở rộng EvidencePackage: raw, facts, failures
- **Priority:** P1
- **Status:** ⬜
- **Dependencies:** DR1-501, DR1-505
- **Files dự kiến:** `src/pipeline/evidence_package.py`, `src/pipeline/evidence_merge.py`

**Vấn đề**  
Cần giữ raw normalized evidence để debug nhưng reasoning phải dùng facts và failures rõ.

**Cách làm**
1. EvidencePackage có raw_data (bounded), facts, capability_status, collection_failures, schema_version.
2. Frontend serialization không gửi raw lớn mặc định.
3. Assessment nhận facts/findings trước raw.

**Acceptance criteria**
- [ ] Package đủ audit nhưng không làm response payload phình lớn.

**Tests/verification**
- `tests/pipeline/test_evidence_package.py`
- `serialization tests`

---
### DR1-509 — Provenance và claim source links
- **Priority:** P2
- **Status:** ⬜
- **Dependencies:** DR1-501, DR1-508
- **Files dự kiến:** `src/pipeline/provenance.py (new)`, `src/agent/deterministic_agent.py`

**Vấn đề**  
Operator cần biết claim đến từ command/API/event nào.

**Cách làm**
1. Provenance dùng safe IDs, capability, target, observed time, source reference.
2. Build tool links từ provenance thay vì heuristic raw evidence.
3. Không lộ command secret.

**Acceptance criteria**
- [ ] Mỗi deterministic fact/finding có source traceable.

**Tests/verification**
- `tests/pipeline/test_provenance.py`

---

## 9. EPIC 6 — Deterministic Reasoning v1
### DR1-601 — Refactor atomic threshold rules dùng canonical metrics
- **Priority:** P1
- **Status:** 🔎
- **Dependencies:** DR1-501, DR1-505
- **Files dự kiến:** `src/pipeline/threshold_evaluator.py`, `config/thresholds.yaml (new hoặc hiện có)`

**Vấn đề**  
Threshold hiện đánh giá key dict độc lập và load absolute, dễ sai trên máy nhiều core.

**Cách làm**
1. Input chỉ là valid fresh facts.
2. Tạo derived fact `cpu.load_per_core`.
3. Rule config có metric, operator, threshold, severity, required context, version.
4. Disk 37% không warning; load so theo core.

**Acceptance criteria**
- [ ] Atomic rule outputs deterministic và explainable.

**Tests/verification**
- `tests/pipeline/test_threshold_evaluator.py`

---
### DR1-602 — Tạo CompositeRule và WeightedCondition
- **Priority:** P1
- **Status:** ⬜
- **Dependencies:** DR1-601
- **Files dự kiến:** `src/pipeline/composite_rule.py (new)`, `src/pipeline/rule_engine.py (new hoặc mở rộng evaluator)`

**Vấn đề**  
Orion chưa biểu diễn được CPU cao + load/core cao + top process cao thành finding tổ hợp.

**Cách làm**
1. CompositeRule khai báo conditions, weight, decision_threshold và required/optional.
2. Score cộng weights satisfied; false là contradicting; unknown không được normalize lại.
3. Trả supporting/contradicting/missing fact IDs.

**Acceptance criteria**
- [ ] CPU saturation finding chỉ supported khi score đủ và evidence observable đủ.

**Tests/verification**
- `tests/pipeline/test_composite_rules.py`

---
### DR1-603 — Định nghĩa semantics false/unknown/stale/failed trong rule
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-602
- **Files dự kiến:** `src/pipeline/rule_engine.py`

**Vấn đề**  
Nếu thiếu two conditions mà normalize 0.35/0.35 thành 1.0 sẽ tạo certainty giả.

**Cách làm**
1. Condition state: SATISFIED, FALSE, UNKNOWN, STALE, COLLECTION_FAILED.
2. Không renormalize missing weight trừ khi rule khai báo explicit policy.
3. Tính maximum_observable_score và evidence coverage.

**Acceptance criteria**
- [ ] Missing facts dẫn tới insufficient_evidence, không supported.

**Tests/verification**
- `tests/pipeline/test_rule_missing_evidence.py`

---
### DR1-604 — Tạo Finding model
- **Priority:** P1
- **Status:** ⬜
- **Dependencies:** DR1-602
- **Files dự kiến:** `src/pipeline/finding.py (new)`, `src/pipeline/assessment_request.py`

**Vấn đề**  
LLM cần findings có cấu trúc thay vì tự suy luận từ mọi raw dict.

**Cách làm**
1. Finding gồm id/type/score/decision/severity/supporting/contradicting/missing facts/confidence/rule_version.
2. Decision: supported, not_supported, insufficient_evidence.

**Acceptance criteria**
- [ ] Findings serializable và source-linked.

**Tests/verification**
- `tests/pipeline/test_finding.py`

---
### DR1-605 — Tích hợp EvidenceCorrelation vào Fact/Findings flow
- **Priority:** P1
- **Status:** 🔎
- **Dependencies:** DR1-604
- **Files dự kiến:** `src/pipeline/evidence_correlation.py`, `src/pipeline/execution_engine.py`

**Vấn đề**  
Module correlation tồn tại nhưng không nên đọc raw evidence hoặc đứng ngoài pipeline.

**Cách làm**
1. Correlation nhận FactSet/atomic findings.
2. Chuyển patterns thành composite rules nhỏ hoặc deterministic correlators.
3. Đưa findings vào AssessmentRequest/trace.

**Acceptance criteria**
- [ ] Không có correlation chỉ tồn tại trong code mà không ảnh hưởng output/trace.

**Tests/verification**
- `tests/pipeline/test_evidence_correlation.py`

---
### DR1-606 — Bounded capability recovery theo error contract
- **Priority:** P1
- **Status:** ⬜
- **Dependencies:** DR1-107, DR1-204, DR1-505
- **Files dự kiến:** `src/pipeline/capability_recovery.py (new)`, `src/pipeline/execution_runtime.py`

**Vấn đề**  
Tool cần tự phục hồi deterministic khi strategy không hỗ trợ môi trường.

**Cách làm**
1. CapabilitySpec khai alternatives và recoverable_errors.
2. Recovery chọn alternative phù hợp environment, max depth 2.
3. Không recovery transport timeout bằng thêm remote command.
4. Trace primary, error, alternative, facts recovered, extra duration.

**Acceptance criteria**
- [ ] Fallback success rate đo được; loop không xảy ra.

**Tests/verification**
- `tests/pipeline/test_capability_recovery.py`

---
### DR1-607 — Weighted missing-evidence selection
- **Priority:** P1
- **Status:** ⬜
- **Dependencies:** DR1-603, DR1-606
- **Files dự kiến:** `src/pipeline/evidence_expander.py (new)`, `src/pipeline/execution_engine.py`

**Vấn đề**  
Adaptive evidence selection cần nhỏ và deterministic, không thành information-gain research project.

**Cách làm**
1. Từ missing conditions, map metric → capability.
2. Priority = condition_weight × expected_reliability / estimated_cost.
3. Chọn 1–2 fact thiếu có giá trị cao nhất.
4. Không dùng LLM để quyết định vòng tiếp.

**Acceptance criteria**
- [ ] Cùng input tạo cùng next plan.
- [ ] Accuracy tăng mà tool count/budget không vượt gate.

**Tests/verification**
- `tests/pipeline/test_evidence_expander.py`

---
### DR1-608 — Budget và stop conditions cho investigation expansion
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-607
- **Files dự kiến:** `src/pipeline/execution_engine.py`, `src/pipeline/execution_budget.py (new)`

**Vấn đề**  
Fallback/expansion không giới hạn có thể chạy quá nhiều command và tăng latency.

**Cách làm**
1. Budget: max rounds, max capabilities, max total duration, max estimated cost.
2. Stop khi evidence sufficient, no recoverable path, budget exhausted hoặc target transport failed.
3. Ghi budget reason trong trace.

**Acceptance criteria**
- [ ] Không request nào vượt configured hard limit.

**Tests/verification**
- `tests/pipeline/test_execution_budget.py`

---
### DR1-609 — Deterministic health aggregator đa nguồn
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-604, DR1-505
- **Files dự kiến:** `src/pipeline/health_aggregator.py (new)`, `src/pipeline/deterministic_responder.py`

**Vấn đề**  
Vague health check đôi khi bỏ active Zabbix problems và kết luận “mọi thứ ổn”.

**Cách làm**
1. Priority policy: active critical incidents → unavailable critical evidence → supported warnings/findings → confirmed healthy facts.
2. Không coi host status=0 là không có problem.
3. Nếu scope nhiều target/source, aggregate per target và global.

**Acceptance criteria**
- [ ] Có active DHCP/link-down thì global response không được “không có vấn đề”.
- [ ] Incomplete evidence được nêu rõ.

**Tests/verification**
- `tests/pipeline/test_health_aggregator.py`

---
### DR1-610 — Rule config schema, versioning và human review
- **Priority:** P2
- **Status:** ⬜
- **Dependencies:** DR1-601, DR1-602
- **Files dự kiến:** `config/rules/*.yaml (new)`, `src/shared/config_schema.py`

**Vấn đề**  
Rule cần test/review; transcript không được tự ghi production rule.

**Cách làm**
1. Pydantic/schema validation cho atomic/composite rules.
2. Rule có id/version/owner/rationale/source cases.
3. Transcript classifier chỉ tạo candidate report; human review + regression test trước merge.

**Acceptance criteria**
- [ ] Invalid rule fail startup/config load rõ ràng.
- [ ] Không có auto-learning production rule.

**Tests/verification**
- `tests/shared/test_rule_config_schema.py`

---

## 10. EPIC 7 — Assessment layer hardening
### DR1-701 — Mở rộng AssessmentRequest
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-505, DR1-604
- **Files dự kiến:** `src/pipeline/assessment_request.py`, `src/pipeline/assessment_adapter.py`

**Vấn đề**  
Model hiện nhận raw evidence + complete flag, chưa nhận facts/findings/failures/allowed claims rõ.

**Cách làm**
1. Thêm request_frame, facts, findings, unknowns, collection_failures, evidence_status, allowed_claims.
2. Raw evidence là optional bounded debug context.
3. AssessmentRequest immutable.

**Acceptance criteria**
- [ ] Model có đủ context để giải thích nhưng không cần tự xác định validity.

**Tests/verification**
- `tests/pipeline/test_assessment_request.py`

---
### DR1-702 — Prompt builder hiển thị failure và giới hạn evidence
- **Priority:** P0
- **Status:** 🔎
- **Dependencies:** DR1-701
- **Files dự kiến:** `src/model/protocol/prompt_builder_v2.py`, `config/prompts/*.j2`

**Vấn đề**  
Prompt hiện bỏ package failed, khiến model tưởng evidence chỉ đơn giản là missing.

**Cách làm**
1. Sections: confirmed facts, deterministic findings, contradicting facts, missing facts, collection failures, scope limitations.
2. Bỏ fallback key guessing sau khi fact normalizer ổn định.
3. Nhắc model không suy ra trend/health/action ngoài allowed claims.

**Acceptance criteria**
- [ ] Command not found/SSH timeout xuất hiện như limitation, không biến thành zero.

**Tests/verification**
- `tests/model/protocol/test_prompt_builder_v2.py`

---
### DR1-703 — Claim grounding validator
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-701
- **Files dự kiến:** `src/model/claim_validator.py (new)`, `src/agent/deterministic_agent.py`

**Vấn đề**  
LLM có thể thêm số liệu, target hoặc kết luận không có trong facts/findings.

**Cách làm**
1. Extract/check numeric claims, target names, severity và action verbs với allowed facts/findings.
2. Không cần full semantic theorem prover; chặn các pattern nguy hiểm và mismatch rõ.
3. Fail closed cho action claims; downgrade/replace response với safe template khi violation.

**Acceptance criteria**
- [ ] Số GB/% không có trong fact set bị chặn.
- [ ] Không đổi monitor thành localhost.

**Tests/verification**
- `tests/model/test_claim_validator.py`

---
### DR1-704 — Action hallucination guard và ActionReceipt contract
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-211, DR1-703
- **Files dự kiến:** `src/model/output_sanitizer.py`, `src/model/action_receipt.py (new, future-compatible)`

**Vấn đề**  
Orion từng nói “đã xóa /tmp” dù không thực thi.

**Cách làm**
1. Read-only mode: cấm completion verbs `đã xóa/sửa/restart/deploy` nếu không có ActionReceipt.
2. ActionReceipt gồm capability/action ID, target, status, timestamps, exit/result và verification; hiện không có write capability nên luôn absent.
3. Output violation trả “Orion chưa thực hiện hành động”.

**Acceptance criteria**
- [ ] 0 hallucinated action trong adversarial suite.

**Tests/verification**
- `tests/model/test_output_sanitizer.py`
- `prompt injection cases`

---
### DR1-705 — Numeric và unit consistency validator
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-501, DR1-703
- **Files dự kiến:** `src/model/numeric_claim_validator.py (new)`

**Vấn đề**  
Transcript có disk free 154 GB rồi 391.8 GB và nhầm size/used.

**Cách làm**
1. Normalize displayed units từ fact canonical.
2. Check arithmetic total-used≈available trong tolerance nếu cùng semantics.
3. Không cho prompt/model tự convert từ ambiguous field.

**Acceptance criteria**
- [ ] Cùng fact set luôn render cùng số.
- [ ] Contradiction được surface thay vì chọn ngẫu nhiên.

**Tests/verification**
- `tests/model/test_numeric_claim_validator.py`

---
### DR1-706 — Language quality validator
- **Priority:** P1
- **Status:** 🔎
- **Dependencies:** DR1-703
- **Files dự kiến:** `src/model/output_sanitizer.py`

**Vấn đề**  
Response có ký tự Trung/Nhật/Nga xen giữa tiếng Việt.

**Cách làm**
1. Detect script leakage ngoài code/quoted identifiers.
2. Cho phép thuật ngữ kỹ thuật Latin; reject unexpected CJK/Cyrillic trong Vietnamese answer.
3. Nếu fail, regenerate một lần hoặc dùng deterministic safe summary.

**Acceptance criteria**
- [ ] 0 mixed-script leakage trong QA tiếng Việt.

**Tests/verification**
- `tests/model/test_output_sanitizer.py`

---
### DR1-707 — DeterministicResponder chỉ đọc valid facts/findings
- **Priority:** P0
- **Status:** 🔎
- **Dependencies:** DR1-501, DR1-604
- **Files dự kiến:** `src/pipeline/deterministic_responder.py`

**Vấn đề**  
Fast path nhanh nhưng nguy hiểm nếu đọc raw/default zero.

**Cách làm**
1. Refactor responders hostname/kernel/uptime/CPU/RAM/disk/service sang FactSet.
2. Require validity/freshness và exact target/params.
3. Nếu insufficient, trả deterministic limitation hoặc chuyển assessment khi phù hợp.

**Acceptance criteria**
- [ ] Fast path không bypass evidence quality.
- [ ] Fact response P95 vẫn dưới target.

**Tests/verification**
- `tests/pipeline/test_deterministic_responder.py`

---
### DR1-708 — Chuẩn hóa uncertainty và confidence wording
- **Priority:** P1
- **Status:** ⬜
- **Dependencies:** DR1-701
- **Files dự kiến:** `config/prompts/*.j2`, `src/pipeline/deterministic_responder.py`

**Vấn đề**  
Model thường nói chắc chắn khi evidence partial.

**Cách làm**
1. Templates theo evidence_status: confirmed, partial, unavailable, contradictory, stale.
2. Không dùng “mọi thứ ổn” khi critical evidence missing.
3. Nêu chính xác cái chưa biết và lý do thu thập thất bại.

**Acceptance criteria**
- [ ] Unsafe conclusion rate đạt gate.

**Tests/verification**
- `assessment golden tests`

---

## 11. EPIC 8 — QA harness, evaluator và acceptance gates
### DR1-801 — Unit test matrix cho CommandResult/CapabilityResult
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-101..107
- **Files dự kiến:** `tests/tool/`, `tests/shared/execution/`

**Vấn đề**  
Failure semantics là nền móng nên cần test theo ma trận.

**Cách làm**
1. Matrix local/SSH × success/empty/notfound/nonzero/permission/timeout/unreachable.
2. Capability valid/valid_empty/partial/failed/unsupported/parse_failed.

**Acceptance criteria**
- [ ] Coverage branch đủ cho mapping lỗi core.

**Tests/verification**
- `pytest touched modules`

---
### DR1-802 — Stage tests cho routing đa ngôn ngữ/typo/code-switch
- **Priority:** P1
- **Status:** ⬜
- **Dependencies:** DR1-303..309
- **Files dự kiến:** `tests/pipeline/test_normalizer.py`, `test_intent_resolver.py`, `test_target_resolver.py`

**Vấn đề**  
Cần đo từng stage thay vì response length.

**Cách làm**
1. Parameterize golden cases.
2. Assert candidates, confidence/margin, resolved/clarify.
3. Negative cases chống false positive.

**Acceptance criteria**
- [ ] Concept/intent/target accuracy report được.

**Tests/verification**
- `pytest pipeline routing suite`

---
### DR1-803 — Regression tests cho session context
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-401, DR1-402
- **Files dự kiến:** `tests/agent/test_deterministic_agent.py`

**Vấn đề**  
Follow-up từng đổi target từ monitor sang localhost.

**Cách làm**
1. Test target inheritance, explicit override, ambiguous pronoun, context reset và concurrent sessions.

**Acceptance criteria**
- [ ] 100% follow-up golden cases giữ đúng target.

**Tests/verification**
- `pytest agent context suite`

---
### DR1-804 — Contract tests cho Fact normalization
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-502, DR1-503
- **Files dự kiến:** `tests/pipeline/fact_normalizers/`, `tests/data/`

**Vấn đề**  
Schema/source changes có thể âm thầm làm facts sai.

**Cách làm**
1. Fixture raw outputs thực tế và edge cases.
2. Assert metric, unit, timestamp, validity, provenance.
3. Malformed data → SCHEMA_INVALID.

**Acceptance criteria**
- [ ] Fact extraction accuracy đo được.

**Tests/verification**
- `pytest normalizer suite`

---
### DR1-805 — Precision/recall tests cho atomic và composite findings
- **Priority:** P1
- **Status:** ⬜
- **Dependencies:** DR1-601..610
- **Files dự kiến:** `tests/pipeline/test_threshold_evaluator.py`, `test_composite_rules.py`

**Vấn đề**  
Rule cần kiểm cả false positive và insufficient evidence.

**Cách làm**
1. Positive, negative, missing, stale, contradictory scenarios.
2. Golden finding IDs/scores/decisions.

**Acceptance criteria**
- [ ] Composite finding precision/recall đạt threshold được review.

**Tests/verification**
- `pytest reasoning suite`

---
### DR1-806 — Transcript regression suite end-to-end
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-004, các epic trước
- **Files dự kiến:** `tests/qa/test_transcript_regression.py`, `tests/data/qa_cases/`

**Vấn đề**  
Các lỗi thực tế cần trở thành regression test, không chỉ báo cáo thủ công.

**Cách làm**
1. Chọn case load/CPU zero, service 0, context, forecast, Zabbix aggregation, prompt injection, unknown target, multiline.
2. Mock infrastructure deterministic; không phụ thuộc trạng thái máy developer.

**Acceptance criteria**
- [ ] 0 regression cho P0 cases.
- [ ] Không response rỗng HTTP 200.

**Tests/verification**
- `pytest qa regression suite`

---
### DR1-807 — Đổi acceptance evaluator sang stage-level scoring
- **Priority:** P0
- **Status:** 🔎
- **Dependencies:** DR1-002, DR1-004
- **Files dự kiến:** `scripts/qa/run_acceptance.py`, `benchmark/assessment_evaluator.py`

**Vấn đề**  
Evaluator cũ có thể PASS câu dài nhưng sai; consistency từng bị hardcode 1.0 và grounding dựa keyword/số.

**Cách làm**
1. Score concept, intent, target, params, plan, facts, findings, answer strategy.
2. Assessment quality chấm trên allowed claims/facts, không chỉ keyword overlap.
3. Không hardcode consistency.
4. Output per-stage diff và regression count.

**Acceptance criteria**
- [ ] Một response hallucinated dài phải FAIL.
- [ ] Evaluator tests có known pass/fail fixtures.

**Tests/verification**
- `tests/benchmark/test_assessment_evaluator.py`
- `tests/qa/test_acceptance_scoring.py`

---
### DR1-808 — Thiết lập performance/tool budget gates
- **Priority:** P1
- **Status:** ⬜
- **Dependencies:** DR1-005, DR1-608
- **Files dự kiến:** `benchmark/`, `scripts/qa/`

**Vấn đề**  
Fallback/adaptive selection có thể tăng accuracy nhưng chạy quá nhiều command.

**Cách làm**
1. Đo median/P95 pipeline excluding LLM, total latency, capability count, parallel ratio, expansion rounds.
2. Gate: execution time không tăng >10% nếu accuracy không cải thiện đáng kể; tool count không tăng vô hạn.
3. Fact fast path P95 target riêng.

**Acceptance criteria**
- [ ] Report so baseline theo commit.

**Tests/verification**
- `performance benchmark tests`

---
### DR1-809 — Security và prompt-injection regression suite
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-211, DR1-704
- **Files dự kiến:** `tests/security/`, `tests/qa/`

**Vấn đề**  
Agent vận hành phải chứng minh model text không thể tạo destructive execution hoặc false action claim.

**Cách làm**
1. Cases raw shell, command substitution, service/path injection, SSRF target, fake action receipt.
2. Assert no write command, no unsafe capability, safe response.

**Acceptance criteria**
- [ ] 0 unsafe execution/claim.
- [ ] 100% execution path qua security inspectors.

**Tests/verification**
- `pytest security suite; CI gate`

---
### DR1-810 — Dashboard/report metrics chuẩn
- **Priority:** P1
- **Status:** ⬜
- **Dependencies:** DR1-005, DR1-807
- **Files dự kiến:** `scripts/qa/report.py (new hoặc mở rộng)`, `benchmark_results/`

**Vấn đề**  
Cần nhìn regression theo stage/group/language chứ không một điểm tổng.

**Cách làm**
1. Metrics: concept, intent, target, params, plan, clarification, unsafe assumption, deterministic coverage, expected assessment, routing fallback, insufficient evidence, regression by stage/group/language/typo/code-switch.
2. Correct investigation rate là headline.

**Acceptance criteria**
- [ ] JSON machine-readable + Markdown human-readable.

**Tests/verification**
- `tests/benchmark/test_report_wiring.py`

---
### DR1-811 — CI gates cho accuracy và safety
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-806..810
- **Files dự kiến:** `.github/workflows/ hoặc CI hiện hành`

**Vấn đề**  
Không có gate thì regression sẽ quay lại dù unit tests pass.

**Cách làm**
1. Run fast P0 golden suite mỗi PR.
2. Full domain benchmark khi pipeline/model evidence logic thay đổi theo rule 21.
3. Fail build trên P0 regression, unsafe claim, response rỗng, failure-to-zero.
4. Upload trace/report artifacts.

**Acceptance criteria**
- [ ] CI status phản ánh đúng gate, không flaky vì live infrastructure.

**Tests/verification**
- `CI dry-run trên fixture`

---

## 12. EPIC 9 — Documentation, migration và rollout
### DR1-901 — Cập nhật execution/tool docs theo contracts mới
- **Priority:** P1
- **Status:** ⬜
- **Dependencies:** DR1-101, DR1-501, DR1-606
- **Files dự kiến:** `docs/ai/05_EXECUTION_PIPELINE.md`, `docs/ai/06_TOOL_AND_CAPABILITY_DESIGN.md`, `docs/tools/linux.md`

**Vấn đề**  
Docs cần mô tả CommandResult, Fact, Finding, recovery và LLM boundary mới.

**Cách làm**
1. Cập nhật flow diagram.
2. Ghi rõ command strategy thuộc Child Tool.
3. Ghi failure semantics và provenance.

**Acceptance criteria**
- [ ] Docs khớp source và tests.

**Tests/verification**
- `Doc review`

---
### DR1-902 — ADR cho evidence validity và deterministic reasoning v1
- **Priority:** P1
- **Status:** ⬜
- **Dependencies:** DR1-501, DR1-602
- **Files dự kiến:** `docs/adr/ADR-0008-evidence-validity.md (new)`, `docs/adr/ADR-0009-deterministic-reasoning-v1.md (new)`

**Vấn đề**  
Đây là thay đổi contract kiến trúc cần quyết định rõ, không chỉ implicit code.

**Cách làm**
1. ADR-0008: missing vs zero, validity/freshness/provenance.
2. ADR-0009: atomic/composite rules, bounded recovery, no self-learning/no LLM planning.
3. Nêu trade-offs và rejected alternatives.

**Acceptance criteria**
- [ ] ADR được cross-link trong architecture decisions.

**Tests/verification**
- `Doc review`

---
### DR1-903 — Kế hoạch backward compatibility và migration
- **Priority:** P1
- **Status:** ⬜
- **Dependencies:** DR1-101, DR1-104, DR1-508
- **Files dự kiến:** `docs/migrations/deterministic_reasoning_v1.md (new)`, `src/tool/ compatibility adapters`

**Vấn đề**  
Đổi tuple/dict contracts có thể phá tools/tests/UI.

**Cách làm**
1. Liệt kê public/internal interfaces.
2. Compatibility adapter có deprecation warning.
3. Migration theo vertical slice, không big bang.
4. Bỏ adapter chỉ sau khi callers chuyển hết.

**Acceptance criteria**
- [ ] Old callers vẫn hoạt động trong migration window.

**Tests/verification**
- `compatibility tests`

---
### DR1-904 — Feature flags cho rollout theo phase
- **Priority:** P1
- **Status:** ⬜
- **Dependencies:** DR1-903
- **Files dự kiến:** `src/model/config_store.py`, `config hoặc env docs`

**Vấn đề**  
Facts/rules/validators mới cần rollback độc lập khi regression.

**Cách làm**
1. Flags tạm: structured_command_result, canonical_facts, composite_rules, claim_guard.
2. Default off trong migration, bật trên QA, sau gate mới default on.
3. Không giữ flags vô thời hạn; có removal task.

**Acceptance criteria**
- [ ] Có rollback không đổi data schema bên ngoài.

**Tests/verification**
- `config tests`

---
### DR1-905 — Operator troubleshooting guide cho collection failures
- **Priority:** P2
- **Status:** ⬜
- **Dependencies:** DR1-107, DR1-201
- **Files dự kiến:** `docs/troubleshooting.md`, `docs/tools/linux.md`

**Vấn đề**  
Operator cần biết COMMAND_NOT_FOUND/SSH_AUTH/UNSUPPORTED khác nhau và cách sửa.

**Cách làm**
1. Bảng error code → nguyên nhân → cách kiểm tra → dependency/config cần có.
2. Nêu rõ localhost/container semantics.
3. Không hướng dẫn bỏ security guard tùy tiện.

**Acceptance criteria**
- [ ] Guide dùng đúng error codes trong source.

**Tests/verification**
- `Doc review`

---
### DR1-906 — Rollout theo PR/phase và exit criteria
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** Tất cả
- **Files dự kiến:** `docs/project/DETERMINISTIC_REASONING_BACKLOG.md`

**Vấn đề**  
Scope lớn cần thứ tự để không xây rule trên evidence sai.

**Cách làm**
1. PR1 trace/baseline; PR2 execution contract; PR3 runtime correctness; PR4 routing/context/params; PR5 facts/completeness/cache; PR6 recovery; PR7 deterministic reasoning; PR8 assessment guards; PR9 docs/cleanup.
2. Mỗi phase có gate ở mục cuối tài liệu.

**Acceptance criteria**
- [ ] Không bắt đầu composite rules trước CommandResult/Fact validity.

**Tests/verification**
- `Review checklist`

---
### DR1-907 — Release checklist và Definition of Done
- **Priority:** P0
- **Status:** ⬜
- **Dependencies:** DR1-811, DR1-906
- **Files dự kiến:** `CHANGELOG.md`, `docs/ai/08_PROJECT_STATE.md`

**Vấn đề**  
Cần tránh báo completed chỉ vì code compile.

**Cách làm**
1. DoD: implementation, touched tests, required benchmark, no regression, clean git, one logical commit.
2. Ghi benchmark IDs/report path.
3. Cập nhật project state sau verification.

**Acceptance criteria**
- [ ] Không task completed thiếu test/evidence.

**Tests/verification**
- `Release review`

---

## 13. Thứ tự triển khai khuyến nghị

### PR 1 — Observability baseline

- DR1-001 → DR1-006
- Chốt trace; dọn implementation DR1-003 sai; nhập external HTTP runner + 4 suite TXT; sau đó xây golden schema và baseline.
- **Exit:** external runner smoke-test thành công, tài liệu không còn mô tả DR1-003 theo JSONL loader, và có stage-level baseline cho DR1-004/005.

### PR 2 — Explicit execution failures

- DR1-101 → DR1-108, DR1-801
- **Exit:** không command failure nào biến thành valid zero/empty.

### PR 3 — Runtime và Tool correctness

- DR1-201 → DR1-211
- **Exit:** dependencies core có mặt; localhost semantics rõ; service/network/disk/CPU không hallucinate từ collector failure.

### PR 4 — Routing, context và parameters

- DR1-301 → DR1-309, DR1-401 → DR1-407
- **Exit:** không LLM routing; target follow-up đúng; specific parameter được bind; forecast thiếu history bị từ chối.

### PR 5 — Canonical facts

- DR1-501 → DR1-509
- **Exit:** mọi core evidence có validity/freshness/provenance; completeness theo required facts.

### PR 6 — Capability recovery

- DR1-606, DR1-608 và fallback Tool core
- **Exit:** recoverable environment failure có bounded alternative; transport failure không tạo retry storm.

### PR 7 — Deterministic Reasoning v1

- DR1-601 → DR1-610
- **Exit:** atomic/composite findings có test; missing evidence không được renormalize thành certainty.

### PR 8 — Assessment hardening

- DR1-701 → DR1-708
- **Exit:** 0 hallucinated action; numeric/target/language claim guard pass.

### PR 9 — QA gates và documentation

- DR1-802 → DR1-811, DR1-901 → DR1-907
- **Exit:** CI chặn P0 regression; project state/backlog/ADR đồng bộ.

## 14. Acceptance gates bắt buộc trước khi gọi là production-ready

- [ ] **0** command/capability failure bị biến thành giá trị `0` hoặc empty hợp lệ.
- [ ] **0** hallucinated action (`đã xóa`, `đã restart`, `đã sửa`, `đã deploy`) khi không có ActionReceipt.
- [ ] **100%** unknown-target cases không fallback sang localhost.
- [ ] **100%** required parameters được bind đúng hoặc clarification trước execution.
- [ ] **100%** follow-up target cases giữ đúng active target hoặc hỏi lại khi mơ hồ.
- [ ] **100%** forecast/comparison thiếu historical evidence trả insufficient evidence.
- [ ] **0** response rỗng với HTTP 200 trong golden suite.
- [ ] **0** failed evidence được cache/trả lại như valid evidence.
- [ ] **0** contradiction số liệu bị che giấu trong cùng session.
- [ ] **100%** infrastructure execution path đi qua security inspectors.
- [ ] Fact/list deterministic fast path đạt P95 đã chốt trong baseline; pipeline expansion không vượt hard budget.
- [ ] Correct investigation rate tăng so baseline; routing fallback giảm mà expected assessment không bị ép thành rule-based nghèo nàn.

## 15. Metrics dashboard

### Stage accuracy

- Concept accuracy
- Intent/operation accuracy
- Target accuracy
- Parameter extraction/binding accuracy
- Capability-plan accuracy
- Fact normalization accuracy
- Evidence completeness accuracy
- Composite finding precision/recall

### Outcome quality

- Correct clarification rate
- Unsafe assumption rate
- Deterministic answer coverage
- Expected assessment rate
- Routing fallback rate
- Insufficient-evidence rate
- Correct investigation rate
- Regression count theo stage, nhóm A–J, ngôn ngữ, typo và code-switching

### Cost/performance

- Median/P95 investigation duration excluding LLM
- Median/P95 total duration
- Capability count/request
- Fallback success rate
- Expansion round count
- Unnecessary capability count
- Parallel execution ratio

## 16. Scope hoãn / không được đưa vào phase này

Các mục sau **không thuộc Deterministic Reasoning v1**:

- LLM-generated raw shell commands hoặc model-driven ReAct loop
- Tự học/sửa production rules trực tiếp từ transcript
- Automatic global alias promotion
- Case-based reasoning engine tổng quát
- Bayesian network / HMM / random forest / multi-armed bandit
- World model / ontology platform
- Unrestricted hypothesis search
- Plugin platform mới chỉ để giải quyết coverage hiện tại
- Multi-user/public ingress/TLS ngoài sequencing của `04_ROADMAP.md`

Transcript chỉ được dùng theo luồng:

```text
Transcript
  → failure classifier
  → candidate rule/alias/example
  → human review
  → regression test
  → merge
```

## 17. Carry-over ngoài phạm vi accuracy hardening

Các mục sau vẫn thuộc roadmap/backlog khác và không bị file này thay thế:

- Dependency reconciliation (`numpy`, `requests` placeholders) trong `08_PROJECT_STATE.md`.
- WP1 public VM/platform work chỉ bắt đầu khi điều kiện roadmap được đáp ứng.
- Các item configuration, retry, prompt extraction, immutable state, RAG rationalization, SQLite và plugin horizon trong `IMPLEMENTATION_BACKLOG.md` tiếp tục theo dependency/risk riêng.
- Plugin/Extension System vẫn là Horizon vì gate nhu cầu/API stability chưa đạt.

## 18. Definition of Done cho từng task

Một task chỉ chuyển sang `✅ completed` khi:

1. Code/config/doc đúng scope đã được triển khai.
2. Unit/integration tests của phần chạm tới pass.
3. Benchmark được chạy nếu task làm thay đổi pipeline scoring, prompt hoặc evidence logic theo `07_DEVELOPMENT_RULES.md` rule 21.
4. Không có P0 regression trong golden suite.
5. `git diff` và `git status` đã review; không có unrelated change.
6. Một logical task tương ứng một commit.
7. `08_PROJECT_STATE.md` chỉ cập nhật sau khi có bằng chứng trên.

---

**Tên phase đề xuất:** `Deterministic Reasoning v1`  
**Mục tiêu:** làm Orion chính xác hơn bằng contract và evidence tốt hơn, không bằng cách giao điều tra cho LLM.
