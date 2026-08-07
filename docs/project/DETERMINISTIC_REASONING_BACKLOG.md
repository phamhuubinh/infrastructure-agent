# Orion — Corrective Backlog & Deterministic Reasoning v1

> **Mục đích:** backlog triển khai hợp nhất cho việc nâng độ chính xác của Orion theo nguyên tắc **Code investigates. AI explains.**  
> **Phạm vi:** sửa pipeline, Tool, evidence, deterministic reasoning, assessment guard và QA harness. Không chuyển quyền chọn lệnh/capability sang LLM.  
> **Ngày tạo:** 2026-08-03  
> **Ngày chốt:** 2026-08-03  
> **Cập nhật gần nhất:** 2026-08-07 — DR1-901–905 hoàn tất: execution/tool
> contracts, ADR evidence validity + deterministic reasoning v1, migration
> compatibility adapters/deprecation warnings, phase rollout flags, và operator
> guide collection failures đã có source/docs/tests tương ứng. 2026-08-06 — DR1-702 và DR1-707 hoàn tất (xem chi tiết ở từng mục): xóa
> hẳn fallback key-guessing trong prompt builder (dead code kể từ khi fact normalizer có generic
> fallback), và refactor 9/15 responder trong `DeterministicResponder` sang đọc canonical Fact
> trước/dict thô fallback sau — quá trình này còn phát hiện và sửa 2 bug đơn vị (KB vs byte) khiến
> `_check_ram_available`/`_check_swap` gần như luôn trả `None` trên dữ liệu thật trước đây. 2
> responder (`top_cpu`, `uptime`) và nhánh generic failed/disabled service vẫn giữ dict-based có
> chủ đích vì `LinuxFactNormalizer` chưa emit fact cho các trường này — đã ghi chú tại chỗ, theo
> dõi như việc kế tiếp ngoài scope. 2026-08-05 — EPIC 7 / DR1-701, 703, 704, 705, 706, 708 hoàn
> thành: mở rộng AssessmentRequest, prompt sections tường minh (confirmed/contradicting/missing
> facts, findings, uncertainty wording), claim grounding + redaction, action hallucination guard,
> numeric consistency check, language-script guard, và guard chặn fast path khi package có fact
> contradictory/stale. EPIC 6 / DR1-601–610 hoàn thành trước đó. DR1-001–509 hoàn thành trước đó.
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
| DR1-301 | P0 | ✅ | EPIC 3 | Loại LLM khỏi quyết định routing investigation | DR1-002 |
| DR1-302 | P0 | ✅ | EPIC 3 | Tạo RequestFrame thống nhất | DR1-301 |
| DR1-303 | P1 | ✅ | EPIC 3 | Mở rộng deterministic normalizer cho typo và code-switching | DR1-302 |
| DR1-304 | P2 | ✅ | EPIC 3 | Semantic candidate retrieval có deterministic validation | DR1-303 |
| DR1-305 | P1 | ✅ | EPIC 3 | IntentResolver trả confidence, candidates và ambiguity margin | DR1-302 |
| DR1-306 | P0 | ✅ | EPIC 3 | TargetResolver dùng threshold + margin + unknown-target guard | DR1-302 |
| DR1-307 | P2 | ✅ | EPIC 3 | Alias có scope và vòng đời | DR1-306 |
| DR1-308 | P0 | ✅ | EPIC 3 | Chuẩn hóa request class, routing status, evidence status, answer strategy | DR1-302 |
| DR1-309 | P1 | ✅ | EPIC 3 | Deterministic clarification responses | DR1-305, DR1-306, DR1-308 |
| DR1-401 | P0 | ✅ | EPIC 4 | Tạo SessionInvestigationContext có cấu trúc | DR1-302 |
| DR1-402 | P0 | ✅ | EPIC 4 | Resolve context trước Normalizer/Target/Planner | DR1-401 |
| DR1-403 | P0 | ✅ | EPIC 4 | Tạo ParameterBinder và truyền params xuống capability | DR1-302 |
| DR1-404 | P0 | ✅ | EPIC 4 | Validate required parameters trước execution | DR1-403 |
| DR1-405 | P1 | ✅ | EPIC 4 | Decompose multi-intent thành subrequests có giới hạn | DR1-302, DR1-305 |
| DR1-406 | P1 | ✅ | EPIC 4 | Chuẩn hóa TimeRange và temporal requirements | DR1-302, DR1-403 |
| DR1-407 | P0 | ✅ | EPIC 4 | Guard comparison/forecast khi thiếu time series | DR1-406, DR1-505 |
| DR1-501 | P0 | ✅ | EPIC 5 | Tạo canonical Fact model | DR1-104, DR1-302 |
| DR1-502 | P0 | ✅ | EPIC 5 | FactNormalizer cho Linux core capabilities | DR1-210, DR1-501 |
| DR1-503 | P1 | ✅ | EPIC 5 | FactNormalizer cho Zabbix và Grafana | DR1-501 |
| DR1-504 | P1 | ✅ | EPIC 5 | Investigation FactSet và indexing | DR1-501..503 |
| DR1-505 | P0 | ✅ | EPIC 5 | EvidenceCompleteness dựa trên required facts | DR1-501, DR1-504 |
| DR1-506 | P1 | ✅ | EPIC 5 | Detect và biểu diễn contradictory facts | DR1-504 |
| DR1-507 | P1 | ✅ | EPIC 5 | Sửa EvidenceCache key và freshness policy | DR1-501, DR1-505 |
| DR1-508 | P1 | ✅ | EPIC 5 | Mở rộng EvidencePackage: raw, facts, failures | DR1-501, DR1-505 |
| DR1-509 | P2 | ✅ | EPIC 5 | Provenance và claim source links | DR1-501, DR1-508 |
| DR1-601 | P1 | ✅ | EPIC 6 | Refactor atomic threshold rules dùng canonical metrics | DR1-501, DR1-505 |
| DR1-602 | P1 | ✅ | EPIC 6 | Tạo CompositeRule và WeightedCondition | DR1-601 |
| DR1-603 | P0 | ✅ | EPIC 6 | Định nghĩa semantics false/unknown/stale/failed trong rule | DR1-602 |
| DR1-604 | P1 | ✅ | EPIC 6 | Tạo Finding model | DR1-602 |
| DR1-605 | P1 | ✅ | EPIC 6 | Tích hợp EvidenceCorrelation vào Fact/Findings flow | DR1-604 |
| DR1-606 | P1 | ✅ | EPIC 6 | Bounded capability recovery theo error contract | DR1-107, DR1-204, DR1-505 |
| DR1-607 | P1 | ✅ | EPIC 6 | Weighted missing-evidence selection | DR1-603, DR1-606 |
| DR1-608 | P0 | ✅ | EPIC 6 | Budget và stop conditions cho investigation expansion | DR1-607 |
| DR1-609 | P0 | ✅ | EPIC 6 | Deterministic health aggregator đa nguồn | DR1-604, DR1-505 |
| DR1-610 | P2 | ✅ | EPIC 6 | Rule config schema, versioning và human review | DR1-601, DR1-602 |
| DR1-701 | P0 | ✅ | EPIC 7 | Mở rộng AssessmentRequest | DR1-505, DR1-604 |
| DR1-702 | P0 | ✅ | EPIC 7 | Prompt builder hiển thị failure và giới hạn evidence | DR1-701 |
| DR1-703 | P0 | ✅ | EPIC 7 | Claim grounding validator | DR1-701 |
| DR1-704 | P0 | ✅ | EPIC 7 | Action hallucination guard và ActionReceipt contract | DR1-211, DR1-703 |
| DR1-705 | P0 | ✅ | EPIC 7 | Numeric và unit consistency validator | DR1-501, DR1-703 |
| DR1-706 | P1 | ✅ | EPIC 7 | Language quality validator | DR1-703 |
| DR1-707 | P0 | ✅ | EPIC 7 | DeterministicResponder chỉ đọc valid facts/findings | DR1-501, DR1-604 |
| DR1-708 | P1 | ✅ | EPIC 7 | Chuẩn hóa uncertainty và confidence wording | DR1-701 |
| DR1-801 | P0 | ✅ | EPIC 8 | Unit test matrix cho CommandResult/CapabilityResult | DR1-101..107 |
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
| DR1-901 | P1 | ✅ | EPIC 9 | Cập nhật execution/tool docs theo contracts mới | DR1-101, DR1-501, DR1-606 |
| DR1-902 | P1 | ✅ | EPIC 9 | ADR cho evidence validity và deterministic reasoning v1 | DR1-501, DR1-602 |
| DR1-903 | P1 | ✅ | EPIC 9 | Kế hoạch backward compatibility và migration | DR1-101, DR1-104, DR1-508 |
| DR1-904 | P1 | ✅ | EPIC 9 | Feature flags cho rollout theo phase | DR1-903 |
| DR1-905 | P2 | ✅ | EPIC 9 | Operator troubleshooting guide cho collection failures | DR1-107, DR1-201 |
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
3. ✅ Sau `DR1-308`, `routing_status` và `evidence_status` được đọc từ field canonical
   của `ExecutionTrace`/`InvestigationRequest`, được chấm như field first-class; suy luận
   best-effort chỉ còn là compatibility fallback cho trace lịch sử.
4. ✅ Report JSON + Markdown ghi `git_commit`, `config_hash` (sha256 của `targets.json` +
   `servers.json`), `model`/`provider` (qua `benchmark/metadata.py:collect_benchmark_metadata`),
   `golden_dataset_path`, cases_total, và toàn bộ danh sách case fail kèm field mismatch.
5. ✅ Ghi stage accuracy (concept/operation/intent/target/params/answer_type/answer_strategy/
   llm_usage_reason/required_evidence), outcome rates (deterministic_answer_coverage,
   expected_assessment_rate, routing_fallback_rate, insufficient_evidence_rate), accuracy theo
   nhóm A–J/M, và latency (median/p95 `total_duration_ms`).
6. Không sửa `run_acceptance.py` (dùng `TEST_CASES` hardcode, không phải golden dataset) — việc
   đổi nó sang stage-level scoring thuộc `DR1-807`, ngoài scope DR1-005.
7. Bản report DR1-005 chưa tổng hợp `unsafe_assumption_rate`/
   `correct_clarification_rate`: clarification outcome nay đã observable nhờ `DR1-308/309`,
   nhưng aggregate metric thuộc `DR1-810`; unsafe assumption còn cần claim validator
   (`DR1-703`). Không suy ra số giả từ response text.

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
- **Status:** ✅
- **Dependencies:** DR1-002
- **Files dự kiến:** `src/agent/deterministic_agent.py`, `src/pipeline/intent_resolver.py`

**Vấn đề**  
Low-confidence classifier dùng LLM làm mờ ranh giới “AI explains” và khó đo routing fallback.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Xóa Tier-2 `assess_raw()` classifier; `_route_request()` chỉ trả quyết định deterministic `resolved`, `clarification_required`, `unsupported`, `general_chat`.
2. ✅ General chat giữ path riêng; investigation lỗi/không rõ không fallback sang model.
3. ✅ Trace ghi routing status độc lập; clarification/refusal dùng `llm_usage_reason=NONE`, pipeline failure ghi `FALLBACK` mà không gọi model.

**Acceptance criteria**
- [x] Không có call model trước AssessmentRequest trong investigation path.
- [x] Ambiguous request hỏi lại, không đoán.

**Tests/verification**
- ✅ `tests/agent/test_deterministic_agent.py` kiểm model/execution call count cho ambiguous/action/missing-service paths.

---
### DR1-302 — Tạo RequestFrame thống nhất
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-301
- **Files dự kiến:** `src/pipeline/request_frame.py (new)`, `src/pipeline/semantic_request.py`, `src/pipeline/investigation_request.py`

**Vấn đề**  
Normalizer, IntentResolver và planner có thể parse raw text theo mapping riêng, gây concept/intent lệch nhau.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `RequestFrame` bất biến chứa concepts, operation, target raw/resolved, params, answer type, timeframe, confidence, ambiguity và candidate evidence.
2. ✅ Normalizer tạo frame một lần; IntentResolver, TargetResolver và hai ExecutionEngine paths enrich/cùng đọc frame; `semantic_request` chỉ còn compatibility alias trỏ cùng object.
3. ✅ Raw request và actual/expected frame có serialization an toàn trong trace.

**Acceptance criteria**
- [x] Một request có một semantic frame canonical.
- [x] Trace ghi expected/actual frame.

**Tests/verification**
- ✅ `tests/pipeline/test_request_frame.py`.

---
### DR1-303 — Mở rộng deterministic normalizer cho typo và code-switching
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-302
- **Files dự kiến:** `src/pipeline/normalizer.py`, `config/concepts.yaml`

**Vấn đề**  
Các diễn đạt như “web bị ì”, typo và Việt-Anh trộn có thể rơi khỏi concept mapping.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Exact alias/phrase grammar chạy trước trên text case/accent-normalized.
2. ✅ Typo fallback dùng token/BM25-like overlap, character trigram và edit similarity.
3. ✅ Lexicon review thêm code-switch/slowness/port/forecast variants; không có online learning từ transcript.
4. ✅ Frame giữ ranked concept candidates, source và matched text.

**Acceptance criteria**
- [x] Coverage tăng trên golden typo/code-switching mà focused regression không giảm.
- [x] Mọi alias global có review metadata.

**Tests/verification**
- ✅ `tests/pipeline/test_normalizer.py` bao phủ missing accents, typo service/kernel, code-switching và multi-concept.

---
### DR1-304 — Semantic candidate retrieval có deterministic validation
- **Priority:** P2
- **Status:** ✅
- **Dependencies:** DR1-303
- **Files dự kiến:** `src/pipeline/semantic_candidate_retriever.py (new, optional)`, `src/pipeline/normalizer.py`

**Vấn đề**  
Exact/fuzzy có thể thiếu paraphrase; embedding local có thể hỗ trợ nhưng không được tự quyết capability.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `SemanticCandidateRetriever` trả exact/lexical-fuzzy ranked candidates; không có route authority.
2. ✅ Validator bắt buộc score threshold, top1/top2 margin và compatibility predicate.
3. ✅ Chỉ dùng standard-library BM25-like token weighting, char n-gram và edit similarity; không thêm model dependency.

**Acceptance criteria**
- [x] Retriever chỉ trả candidates, không trả final route.
- [x] Case top1 0.83/top2 0.81 bị reject với `ambiguous_margin`.

**Tests/verification**
- ✅ `tests/pipeline/test_semantic_candidate_retriever.py`.

---
### DR1-305 — IntentResolver trả confidence, candidates và ambiguity margin
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-302
- **Files dự kiến:** `src/pipeline/intent_resolver.py`

**Vấn đề**  
Một intent label không đủ để biết có nên accept hay clarify.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `IntentResolution`/`IntentCandidate` trả top candidates, numeric score, enum confidence và ambiguity margin.
2. ✅ Candidate ghi operation/concept compatibility; generic machine không veto strong domain match.
3. ✅ Multi-resource request được giữ multi-concept và `down`/state words không bind thành service name.

**Acceptance criteria**
- [x] Intent regression và correct clarification focused tests pass.
- [x] Không route “5 việc: disk, service down…” thành service tên `down`.

**Tests/verification**
- ✅ `tests/pipeline/test_intent_resolver.py`.

---
### DR1-306 — TargetResolver dùng threshold + margin + unknown-target guard
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-302
- **Files dự kiến:** `src/pipeline/target_resolver.py`, `config/target_aliases.yaml`

**Vấn đề**  
Fuzzy target có thể accept ứng viên sát nhau hoặc fallback về localhost cho hostname không tồn tại.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Exact target/scoped alias/name-pattern chạy trước fuzzy.
2. ✅ Fuzzy accept khi score >= 0.78 và margin >= 0.10; candidate sát nhau raise `AmbiguousTargetError`.
3. ✅ Explicit numeric hoặc alphabetic hostname không tồn tại raise unknown-target trước collection.
4. ✅ `localhost` chỉ là implicit default khi frame không có explicit target candidate.

**Acceptance criteria**
- [x] 100% unknown target focused cases không chạy localhost.
- [x] Ambiguous target hỏi lại với tối đa ba candidates.

**Tests/verification**
- ✅ `tests/pipeline/test_target_resolver.py`, `test_target_resolver_upgrade.py`.

---
### DR1-307 — Alias có scope và vòng đời
- **Priority:** P2
- **Status:** ✅
- **Dependencies:** DR1-306
- **Files dự kiến:** `src/pipeline/alias_store.py (new hoặc mở rộng config)`, `config/target_aliases.yaml`

**Vấn đề**  
Transcript correction chỉ đúng một session không nên tự thành global alias.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `AliasStore` hỗ trợ session/user/project/global với precedence rõ.
2. ✅ Lifecycle observed/suggested/approved/active/deprecated; chỉ ACTIVE được resolve.
3. ✅ Transcript observation không active tự động; global active/approved bắt buộc reviewer và evidence count. Config aliases đã migrate metadata.

**Acceptance criteria**
- [x] Session alias không rò sang session khác.
- [x] Global alias có reviewer và evidence count.

**Tests/verification**
- ✅ `tests/pipeline/test_alias_scope.py`.

---
### DR1-308 — Chuẩn hóa request class, routing status, evidence status, answer strategy
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-302
- **Files dự kiến:** `src/pipeline/answer_type.py`, `src/pipeline/routing_decision.py (new)`, `src/pipeline/investigation_request.py`

**Vấn đề**  
Chỉ đo “có gọi LLM” làm KPI sai và không phân biệt assessment hợp lệ với fallback.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `AnswerType` đủ fact/list/table/chart/assessment/comparison/forecast/action/explanation.
2. ✅ `RoutingStatus` đủ resolved/clarification/fallback/unsupported và explicit general-chat separation.
3. ✅ `EvidenceStatus` đủ sufficient/partial/unavailable/stale/contradictory/not-applicable; engine ghi canonical observed status.
4. ✅ `AnswerStrategy` phân biệt deterministic fact/template, LLM assessment, clarification và refusal; trace/QA runner đọc taxonomy first-class.

**Acceptance criteria**
- [x] Mỗi investigation/clarification/refusal trace có đủ taxonomy và `llm_usage_reason`.
- [x] EXPECTED_ASSESSMENT không bị tính là routing failure.

**Tests/verification**
- ✅ `tests/pipeline/test_answer_type.py`, `tests/pipeline/test_routing_decision.py`, `tests/qa/test_run_baseline.py`.

---
### DR1-309 — Deterministic clarification responses
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-305, DR1-306, DR1-308
- **Files dự kiến:** `src/pipeline/clarification_responder.py (new)`, `src/agent/deterministic_agent.py`

**Vấn đề**  
Ambiguity không cần LLM; câu hỏi làm rõ phải chỉ đúng trường thiếu.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `ClarificationResponder` có template theo target/service/path/timeframe/concept/operation.
2. ✅ Candidate output được de-duplicate và giới hạn ba lựa chọn.
3. ✅ Agent short-circuit clarification/refusal trước ExecutionEngine; model và evidence collector đều không được gọi.

**Acceptance criteria**
- [x] Clarification nêu đúng ambiguity và không đoán.
- [x] Routing/answer strategy first-class làm correct clarification rate đo được.

**Tests/verification**
- ✅ `tests/pipeline/test_clarification_responder.py`, `tests/agent/test_deterministic_agent.py`.

---

## 7. EPIC 4 — Context, parameter và temporal wiring
### DR1-401 — Tạo SessionInvestigationContext có cấu trúc
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-302
- **Files dự kiến:** `src/agent/session_investigation_context.py (new)`, `src/agent/conversation_store.py`

**Vấn đề**  
Conversation summary hiện chủ yếu phục vụ prompt; target/concept của turn trước không ảnh hưởng routing đúng lúc.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `SessionInvestigationContext` lưu active target/concept/service/path/TimeRange và incident IDs với serialization giới hạn.
2. ✅ JSON, SQLite và PostgreSQL conversation stores persist context ở field riêng; không lưu raw execution evidence vào context.
3. ✅ Agent chỉ cập nhật context từ `RequestFrame` đã resolve; đổi target xóa resource context thuộc target cũ.

**Acceptance criteria**
- [x] Follow-up “Còn RAM?” kế thừa đúng target monitor.
- [x] Context reset/switch target rõ ràng.

**Tests/verification**
- ✅ `tests/agent/test_session_investigation_context.py`.

---
### DR1-402 — Resolve context trước Normalizer/Target/Planner
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-401
- **Files dự kiến:** `src/agent/deterministic_agent.py`, `src/pipeline/execution_engine.py`

**Vấn đề**  
Context được đưa vào assessment sau khi execution đã chọn sai target thì không thể sửa.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `SessionContextResolver` enrich canonical frame trước intent/target/capability planning.
2. ✅ Explicit target hiện tại luôn thắng; context target chỉ được inherit cho follow-up hoặc concept đủ confidence.
3. ✅ Concept/service/path/time range chỉ được kế thừa bằng rule follow-up/reference giới hạn; trace có `context` stage và snapshot semantic an toàn.

**Acceptance criteria**
- [x] Context được ghi trong trace trước capability plan.
- [x] Cross-turn target tests pass.

**Tests/verification**
- ✅ `tests/agent/test_session_investigation_context.py`, `tests/agent/test_deterministic_agent.py`, `tests/pipeline/test_execution_trace.py`.

---
### DR1-403 — Tạo ParameterBinder và truyền params xuống capability
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-302
- **Files dự kiến:** `src/pipeline/parameter_extractor.py`, `src/pipeline/parameter_binder.py (new)`, `src/pipeline/execution_runtime.py`

**Vấn đề**  
ParameterExtractor có thể lấy service_name/path/port nhưng runtime chỉ truyền source/resource.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `ParameterSpec` + `ParameterBinder` map canonical source fields sang child arguments, gồm service/process/path/port/ping target/time bounds.
2. ✅ Router giữ candidate metadata và chọn parameterized route phù hợp; runtime không còn nhánh hardcode resource→argument.
3. ✅ `ExecutionTrace.plan` lưu cả extracted và bound params; Linux collectors nhận argument list đã bind.

**Acceptance criteria**
- [x] “nginx status” gọi capability với `name=nginx`.
- [x] Ping/path/time range được truyền chính xác.

**Tests/verification**
- ✅ `tests/pipeline/test_parameter_extractor.py`, `tests/pipeline/test_parameter_binder.py`, `tests/pipeline/test_execution_runtime.py`.

---
### DR1-404 — Validate required parameters trước execution
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-403
- **Files dự kiến:** `src/pipeline/capability_planner.py`, `src/pipeline/security/parameter_safety_inspector.py`

**Vấn đề**  
Thiếu service/path/target hiện có thể chạy generic capability rồi suy đoán.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Capability metadata xuất `parameter_specs` gồm source/required/default/type/enum/pattern/range.
2. ✅ Engine validate toàn graph trước dispatch; missing/invalid params tạo deterministic clarification và runtime fail-closed nếu gọi trực tiếp.
3. ✅ Binder + mandatory security inspector reject shell/path/newline injection; collectors tiếp tục dùng argument list.

**Acceptance criteria**
- [x] Không capability nào nhận parameter thiếu hoặc chưa validate.
- [x] Injection strings bị reject.

**Tests/verification**
- ✅ `tests/pipeline/test_parameter_validation.py`, `tests/pipeline/test_parameter_binder.py`.

---
### DR1-405 — Decompose multi-intent thành subrequests có giới hạn
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-302, DR1-305
- **Files dự kiến:** `src/pipeline/request_decomposer.py (new)`, `src/pipeline/capability_planner.py`

**Vấn đề**  
Một câu hỏi chứa disk + service + CPU + logs bị keyword đơn route sai hoặc bỏ phần.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `RequestDecomposer` tách các concept explicit thành tối đa bốn subframes dùng chung target/timeframe/params.
2. ✅ Engine resolve evidence/capability từng subframe, merge required/optional contracts và deduplicate capability trước graph parallel.
3. ✅ Request vượt budget trả deterministic scope clarification trước collection.

**Acceptance criteria**
- [x] Multi-intent golden cases thu đủ required evidence.
- [x] Không tạo capability trùng.

**Tests/verification**
- ✅ `tests/pipeline/test_request_decomposer.py`; integration check CPU+RAM+Disk tạo required CPU Hardware/Memory/Storage và không lặp capability.

---
### DR1-406 — Chuẩn hóa TimeRange và temporal requirements
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-302, DR1-403
- **Files dự kiến:** `src/pipeline/time_range_resolver.py`, `src/pipeline/evidence_planner.py`

**Vấn đề**  
Comparison/forecast đang dùng snapshot vì timeframe không được gắn vào evidence requirement đầy đủ.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Canonical `TimeRange` gồm start/end/granularity/timezone/source phrase/temporal kind/windows và giữ tuple compatibility cho deep links.
2. ✅ Relative, named historical, comparison và future phrases tạo HISTORICAL/COMPARISON/FORECAST requirements khác snapshot.
3. ✅ Resolver nhận timezone + clock inject được để relative ranges deterministic/testable; binder truyền since/until.

**Acceptance criteria**
- [x] Historical query không bị route thành current fact.
- [x] Relative range deterministic và testable.

**Tests/verification**
- ✅ `tests/pipeline/test_time_range_resolver.py`.

---
### DR1-407 — Guard comparison/forecast khi thiếu time series
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-406, DR1-505
- **Files dự kiến:** `src/pipeline/evidence_completeness.py`, `src/pipeline/deterministic_responder.py`, `src/model/protocol/prompt_builder_v2.py`

**Vấn đề**  
Orion từng kết luận trend, capacity 6 tháng và false positive chỉ từ snapshot.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Temporal evidence requirements khai báo minimum points/windows; comparison cần ít nhất hai windows tương thích.
2. ✅ Forecast cần tối thiểu sáu điểm và growth model có định danh; thiếu bất kỳ phần nào trở thành insufficient evidence.
3. ✅ `TemporalEvidenceGuard` chạy trong completeness và trước mọi deterministic/LLM response, fail-closed với thông báo không suy xu hướng từ snapshot. Canonical fact-level matching sâu hơn đã hoàn tất trong DR1-505.

**Acceptance criteria**
- [x] 100% forecast/comparison golden cases thiếu history được từ chối đúng.

**Tests/verification**
- ✅ `tests/pipeline/test_temporal_evidence_guard.py`.
- ✅ Verification chung EPIC 4: 234 focused tests pass; 1.357 agent/pipeline/tool/shared/model/QA/benchmark/CLI tests pass (4 skipped, 5 subtests pass); 36 backend session-store tests pass; `ruff check .` clean.

---

## 8. EPIC 5 — Canonical Facts và evidence quality
### DR1-501 — Tạo canonical Fact model
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-104, DR1-302
- **Files dự kiến:** `src/pipeline/fact.py (new)`, `src/pipeline/evidence_package.py`

**Vấn đề**  
Rule và LLM hiện nhận nhiều dict/key/unit khác nhau, khó kiểm soát validity và provenance.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `Fact` immutable chứa đầy đủ identity, metric/value/unit, timestamps, source/target, validity, freshness, confidence, dimensions và provenance; serialization trả cấu trúc JSON-safe.
2. ✅ `FactValidity` triển khai đủ `VALID`, `VALID_EMPTY`, `COMMAND_FAILED`, `NOT_COLLECTED`, `UNSUPPORTED`, `STALE`, `SCHEMA_INVALID`, `CONTRADICTORY`.
3. ✅ Zero chỉ được chấp nhận cho `VALID`; invalid/stale/contradictory facts không thể ngụy trang giá trị đo bằng `0`.

**Acceptance criteria**
- [x] Fact immutable và serializable.
- [x] Không thể tạo VALID fact thiếu metric/unit cần thiết.

**Tests/verification**
- ✅ `tests/pipeline/test_fact.py`.

---
### DR1-502 — FactNormalizer cho Linux core capabilities
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-210, DR1-501
- **Files dự kiến:** `src/pipeline/fact_normalizers/linux.py (new)`

**Vấn đề**  
Linux evidence phải map sang metric canonical như cpu.usage, memory.usage, filesystem.usage.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Linux normalizer dispatch theo capability/schema và chuẩn hóa CPU, memory, filesystem, service, network.
2. ✅ Units được map deterministic (`percent`, `bytes`, `state`, `interface`) và metric dùng namespace canonical.
3. ✅ Mỗi fact giữ capability/target/timestamp/source reference qua provenance.
4. ✅ Failure/schema mismatch sinh fact invalid có failure metadata, không sinh measurement zero.

**Acceptance criteria**
- [x] CPU/memory/disk/service/network fixtures sinh expected facts.

**Tests/verification**
- ✅ `tests/pipeline/fact_normalizers/test_linux.py`.

---
### DR1-503 — FactNormalizer cho Zabbix và Grafana
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-501
- **Files dự kiến:** `src/pipeline/fact_normalizers/zabbix.py (new)`, `src/pipeline/fact_normalizers/grafana.py (new)`

**Vấn đề**  
Cross-source correlation chỉ đúng khi cùng metric/target/time semantics.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Zabbix items/problems và Grafana series/queries được map sang facts canonical cùng target/time/unit semantics.
2. ✅ Provenance giữ `item_id`, `event_id`, dashboard/query source reference và timestamp quan sát.
3. ✅ Host status chỉ trở thành monitoring configuration state, không bị diễn giải thành health; empty payload được biểu diễn `VALID_EMPTY` rõ ràng.

**Acceptance criteria**
- [x] Cùng cpu.usage từ Linux/Grafana có unit/time chuẩn.
- [x] Active problem facts giữ severity và observed time.

**Tests/verification**
- ✅ `tests/pipeline/fact_normalizers/test_zabbix.py`.
- ✅ `tests/pipeline/fact_normalizers/test_grafana.py`.

---
### DR1-504 — Investigation FactSet và indexing
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-501..503
- **Files dự kiến:** `src/pipeline/fact_set.py (new)`, `src/pipeline/execution_engine.py`

**Vấn đề**  
Reasoning cần truy vấn fact theo target/metric/time/source mà không tạo persistence state lâu dài.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Tạo immutable `FactSet` và append-only `FactSetBuilder` cho từng investigation.
2. ✅ Index/query theo metric, target, validity và source; thứ tự canonical hóa theo stable fact identity.
3. ✅ FactSet nằm trong `InvestigationRequest`/`PipelineState`, không được lưu cross-session; evidence cache giữ policy riêng.

**Acceptance criteria**
- [x] FactSet chỉ sống trong trace/investigation.
- [x] Parallel collection merge deterministic.

**Tests/verification**
- ✅ `tests/pipeline/test_fact_set.py`.

---
### DR1-505 — EvidenceCompleteness dựa trên required facts
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-501, DR1-504
- **Files dự kiến:** `src/pipeline/evidence_completeness.py`, `src/pipeline/evidence_requirement.py`

**Vấn đề**  
Hiện completeness chỉ so evidence_name và success, không biết đúng target/param/time/richness hay không.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `EvidenceRequirement` khai báo canonical metric, target, parameter scope, timeframe, allowed validity và freshness limit.
2. ✅ Completeness trả evaluation chi tiết `satisfied`/`missing`/`failed`/`stale`/`contradictory`, cùng matching fact IDs và lý do.
3. ✅ Exact service facts dùng metric scoped như `service.nginx.status`; `service.inventory` không thể thỏa requirement này.

**Acceptance criteria**
- [x] Complete chỉ true khi mọi required fact đạt contract.
- [x] Output giải thích missing facts.

**Tests/verification**
- ✅ `tests/pipeline/test_evidence_completeness.py` và `tests/pipeline/test_evidence_completeness_facts.py`.

---
### DR1-506 — Detect và biểu diễn contradictory facts
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-504
- **Files dự kiến:** `src/pipeline/fact_reconciler.py (new)`, `src/pipeline/evidence_merge.py`

**Vấn đề**  
Các source có thể cho số khác nhau hoặc data ở thời điểm khác; LLM không nên tự chọn.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `FactReconciler` nhóm facts cùng metric/target/time window và so số theo absolute/relative tolerance cấu hình được.
2. ✅ Merge không overwrite theo source/freshness; mọi candidate được giữ và sắp xếp deterministic.
3. ✅ Cả hai phía mâu thuẫn được đánh dấu `CONTRADICTORY`, giữ provenance, và nâng evidence status của investigation.

**Acceptance criteria**
- [x] Mâu thuẫn disk free/size được surface.
- [x] Evidence status trở thành contradictory, không “healthy”.

**Tests/verification**
- ✅ `tests/pipeline/test_fact_reconciler.py` và `tests/pipeline/test_evidence_merge_facts.py`.

---
### DR1-507 — Sửa EvidenceCache key và freshness policy
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-501, DR1-505
- **Files dự kiến:** `src/pipeline/evidence_cache.py`

**Vấn đề**  
Key target+evidence_name không phân biệt nginx/docker, / và /var, CPU 1h/7d.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Cache key gồm target, capability, normalized params, normalized timeframe và schema version; engine chỉ dùng legacy-key fallback khi request không có params/timeframe.
2. ✅ TTL tách identity, snapshot và event classes; cache hit tái tạo đầy đủ provenance/facts.
3. ✅ Stale cache miss theo mặc định; explicit opt-in trả evidence/facts được đánh dấu `STALE`.

**Acceptance criteria**
- [x] Cache không cross-contaminate parameter/timeframe.
- [x] Cache hit giữ provenance và freshness.

**Tests/verification**
- ✅ `tests/pipeline/test_evidence_cache.py` và `tests/pipeline/test_evidence_cache_policy.py`.

---
### DR1-508 — Mở rộng EvidencePackage: raw, facts, failures
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-501, DR1-505
- **Files dự kiến:** `src/pipeline/evidence_package.py`, `src/pipeline/evidence_merge.py`

**Vấn đề**  
Cần giữ raw normalized evidence để debug nhưng reasoning phải dùng facts và failures rõ.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `EvidencePackage` chứa bounded `raw_data`, immutable facts, capability status, collection failures, source identity và schema version.
2. ✅ `to_dict()` bỏ raw mặc định và hỗ trợ byte-bound, JSON-safe serialization khi audit cần raw.
3. ✅ Assessment contract/prompt nhận canonical facts và failures trước phần raw/legacy evidence.

**Acceptance criteria**
- [x] Package đủ audit nhưng không làm response payload phình lớn.

**Tests/verification**
- ✅ `tests/pipeline/test_evidence_package.py` và `tests/pipeline/test_evidence_package_facts.py`.

---
### DR1-509 — Provenance và claim source links
- **Priority:** P2
- **Status:** ✅
- **Dependencies:** DR1-501, DR1-508
- **Files dự kiến:** `src/pipeline/provenance.py (new)`, `src/agent/deterministic_agent.py`

**Vấn đề**  
Operator cần biết claim đến từ command/API/event nào.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `Provenance` tạo safe stable IDs từ capability/source/target/time/reference và giữ schema/source kind có cấu trúc.
2. ✅ Tool/claim links được dựng từ provenance source references; Grafana/Zabbix raw heuristics chỉ còn compatibility fallback tại merge boundary.
3. ✅ Secret-like keys, credentials và query tokens được redact khỏi identifiers, serialized provenance và URLs.

**Acceptance criteria**
- [x] Mỗi deterministic fact/finding có source traceable.

**Tests/verification**
- ✅ `tests/pipeline/test_provenance.py`.
- ✅ Verification chung EPIC 5: 32 contract tests pass; 1.207 agent/pipeline/tool/shared/model regression tests pass; `mypy src --ignore-missing-imports` clean trên 210 source files; `ruff check .` clean.

---

## 9. EPIC 6 — Deterministic Reasoning v1
### DR1-601 — Refactor atomic threshold rules dùng canonical metrics
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-501, DR1-505
- **Files dự kiến:** `src/pipeline/threshold_evaluator.py`, `config/thresholds.yaml (new hoặc hiện có)`

**Vấn đề**  
Threshold hiện đánh giá key dict độc lập và load absolute, dễ sai trên máy nhiều core.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Production evaluator đọc `FactSet`; compatibility adapter raw dict được cô lập cho caller cũ.
2. ✅ Tạo derived fact có provenance `cpu.load_per_core` từ load và logical cores valid/fresh.
3. ✅ Atomic rule có metric/operator/threshold/severity/context/version/owner/rationale/source cases.
4. ✅ Disk 37% không warning; load 10 trên 64 cores không bị đánh critical.

**Acceptance criteria**
- [x] Atomic rule outputs deterministic và explainable.

**Tests/verification**
- ✅ `tests/pipeline/test_threshold_evaluator.py`

---
### DR1-602 — Tạo CompositeRule và WeightedCondition
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-601
- **Files dự kiến:** `src/pipeline/composite_rule.py (new)`, `src/pipeline/rule_engine.py (new hoặc mở rộng evaluator)`

**Vấn đề**  
Orion chưa biểu diễn được CPU cao + load/core cao + top process cao thành finding tổ hợp.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `CompositeRule`/`WeightedCondition` khai báo weight, threshold, required/optional, coverage policy và review metadata.
2. ✅ RuleEngine cộng đúng satisfied weights; false giữ vai trò contradicting; missing mặc định không renormalize.
3. ✅ Evaluation trả supporting/contradicting IDs, missing canonical metrics và source links.

**Acceptance criteria**
- [x] CPU saturation finding chỉ supported khi score đủ và evidence observable đủ.

**Tests/verification**
- ✅ `tests/pipeline/test_composite_rules.py`

---
### DR1-603 — Định nghĩa semantics false/unknown/stale/failed trong rule
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-602
- **Files dự kiến:** `src/pipeline/rule_engine.py`

**Vấn đề**  
Nếu thiếu two conditions mà normalize 0.35/0.35 thành 1.0 sẽ tạo certainty giả.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Condition state là `SATISFIED`, `FALSE`, `UNKNOWN`, `STALE`, `COLLECTION_FAILED`.
2. ✅ Missing weight không renormalize trừ explicit reviewed policy.
3. ✅ Finding ghi raw score, maximum observable/possible score và evidence coverage.

**Acceptance criteria**
- [x] Missing facts dẫn tới insufficient_evidence, không supported.

**Tests/verification**
- ✅ `tests/pipeline/test_rule_missing_evidence.py`

---
### DR1-604 — Tạo Finding model
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-602
- **Files dự kiến:** `src/pipeline/finding.py (new)`, `src/pipeline/assessment_request.py`

**Vấn đề**  
LLM cần findings có cấu trúc thay vì tự suy luận từ mọi raw dict.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Immutable `Finding` gồm identity/type/score/decision/severity/facts/confidence/coverage/rule version/provenance links.
2. ✅ Decision enum chuẩn hóa ba trạng thái supported/not_supported/insufficient_evidence.

**Acceptance criteria**
- [x] Findings serializable và source-linked.

**Tests/verification**
- ✅ `tests/pipeline/test_finding.py`

---
### DR1-605 — Tích hợp EvidenceCorrelation vào Fact/Findings flow
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-604
- **Files dự kiến:** `src/pipeline/evidence_correlation.py`, `src/pipeline/execution_engine.py`

**Vấn đề**  
Module correlation tồn tại nhưng không nên đọc raw evidence hoặc đứng ngoài pipeline.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Correlation production path nhận `FactSet`/atomic findings; raw adapter chỉ giữ compatibility.
2. ✅ CPU/memory/filesystem/system patterns nằm trong reviewed composite config.
3. ✅ ExecutionEngine gắn findings vào Investigation/AssessmentRequest/ExecutionTrace và health flow.

**Acceptance criteria**
- [x] Không có correlation chỉ tồn tại trong code mà không ảnh hưởng output/trace.

**Tests/verification**
- ✅ `tests/pipeline/test_evidence_correlation.py`, `test_execution_engine.py`, `test_assessment_adapter.py`

---
### DR1-606 — Bounded capability recovery theo error contract
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-107, DR1-204, DR1-505
- **Files dự kiến:** `src/pipeline/capability_recovery.py (new)`, `src/pipeline/execution_runtime.py`

**Vấn đề**  
Tool cần tự phục hồi deterministic khi strategy không hỗ trợ môi trường.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Capability metadata khai `alternatives` và `recoverable_errors`; KnowledgeTool export cùng metadata nguồn.
2. ✅ `CapabilityRecovery` chọn alternative khả dụng theo thứ tự ổn định, chống loop và hard-limit depth 2.
3. ✅ Transport timeout/unreachable dừng ngay, không phát thêm remote command.
4. ✅ ToolResult/EvidencePackage/runtime metrics ghi primary/error/alternative/facts recovered/duration.

**Acceptance criteria**
- [x] Fallback success rate đo được; loop không xảy ra.

**Tests/verification**
- ✅ `tests/pipeline/test_capability_recovery.py`, `test_execution_runtime.py`

---
### DR1-607 — Weighted missing-evidence selection
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-603, DR1-606
- **Files dự kiến:** `src/pipeline/evidence_expander.py (new)`, `src/pipeline/execution_engine.py`

**Vấn đề**  
Adaptive evidence selection cần nhỏ và deterministic, không thành information-gain research project.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Missing condition map qua canonical metric → operational capability.
2. ✅ Priority dùng đúng `condition_weight × expected_reliability / estimated_cost`.
3. ✅ Stable tie-break và dedupe capability; chọn tối đa 2 facts.
4. ✅ ExecutionEngine dùng selection deterministic, không gọi LLM.

**Acceptance criteria**
- [x] Cùng input tạo cùng next plan.
- [x] Expansion bị chặn bởi hard budget/tool-count gate.

**Tests/verification**
- ✅ `tests/pipeline/test_evidence_expander.py`

---
### DR1-608 — Budget và stop conditions cho investigation expansion
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-607
- **Files dự kiến:** `src/pipeline/execution_engine.py`, `src/pipeline/execution_budget.py (new)`

**Vấn đề**  
Fallback/expansion không giới hạn có thể chạy quá nhiều command và tăng latency.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Per-investigation budget hard-limit rounds/capabilities/duration/estimated cost.
2. ✅ Stop reasons chuẩn hóa: sufficient/no path/exhausted/transport failed; primary graph được fit trước execution.
3. ✅ Budget và expansion metrics xuất hiện trong request/runtime/ExecutionTrace.

**Acceptance criteria**
- [x] Không plan/expansion request nào vượt configured hard limit.

**Tests/verification**
- ✅ `tests/pipeline/test_execution_budget.py`, `test_execution_engine.py`

---
### DR1-609 — Deterministic health aggregator đa nguồn
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-604, DR1-505
- **Files dự kiến:** `src/pipeline/health_aggregator.py (new)`, `src/pipeline/deterministic_responder.py`

**Vấn đề**  
Vague health check đôi khi bỏ active Zabbix problems và kết luận “mọi thứ ổn”.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Priority policy được encode: active critical incident → unavailable evidence → active warning/supported finding → confirmed healthy.
2. ✅ `monitoring.host_enabled=true` không xóa active problems/triggers/agent unavailable.
3. ✅ Health summary aggregate per-target và global; deterministic responder dùng summary cho vague health checks.

**Acceptance criteria**
- [x] Có active DHCP/link-down thì global response không được “không có vấn đề”.
- [x] Incomplete evidence được nêu rõ.

**Tests/verification**
- ✅ `tests/pipeline/test_health_aggregator.py`, `test_deterministic_responder.py`

---
### DR1-610 — Rule config schema, versioning và human review
- **Priority:** P2
- **Status:** ✅
- **Dependencies:** DR1-601, DR1-602
- **Files dự kiến:** `config/rules/*.yaml (new)`, `src/shared/config_schema.py`

**Vấn đề**  
Rule cần test/review; transcript không được tự ghi production rule.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ Pydantic validation và startup loader cho `config/rules/*.yaml` atomic/composite rules.
2. ✅ Production rules bắt buộc id/version/owner/rationale/source cases và `review_status: approved`.
3. ✅ Không có auto-learning/write path; production config chỉ thay đổi qua reviewed source + regression tests.

**Acceptance criteria**
- [x] Invalid rule fail startup/config load rõ ràng.
- [x] Không có auto-learning production rule.

**Tests/verification**
- ✅ `tests/shared/test_rule_config_schema.py`

**Verification chung EPIC 6 (2026-08-05)**
- ✅ 35 contract tests trực tiếp cho DR1-601–610 pass.
- ✅ 1.232 agent/pipeline/tool/shared/model regression tests pass.
- ✅ 172 RAG/benchmark/CLI/QA tests + 5 subtests pass.
- ✅ `mypy src --ignore-missing-imports` clean trên 217 source files; `ruff check .` clean.
- ✅ Full repository regression: 1518 tests passed (`pytest -q` không còn treo tại
  `tests/backend/test_app.py::test_health_endpoint` — ghi chú cũ về hang môi trường không còn
  đúng; health endpoint pass cùng toàn bộ suite trong lần chạy xác nhận lại 2026-08-06).

---

### Hardening commit trước Epic 7 (2026-08-06) — theo review độc lập trên code

Một review đọc trực tiếp code (không chỉ test/backlog) trước khi bắt đầu Epic 7 phát hiện 5 vấn đề
logic ảnh hưởng tới cam kết của Epic 1 và Epic 6. Cả 5 đã được sửa trong cùng một commit hardening:

1. **Dependency thất bại vẫn force-run node phụ thuộc** (`execution_runtime.py`).
   `_get_ready_nodes()` trước đây, khi không còn node nào sẵn sàng, force-pop node đầu tiên còn lại
   bất kể dependency của nó đã thất bại hay chưa — vi phạm failure contract DR1-101/DR1-107. Đã
   sửa: thêm `_validate_dependencies()` chạy trước khi execute (raise `GraphValidationError` nếu
   `depends_on` trỏ tới capability không có trong graph — fail fast thay vì rơi vào runtime), và
   `_get_ready_nodes()` giờ đánh dấu node có dependency **đã chạy và thất bại** là
   `COLLECTION_FAILED` ("Blocked by dependency: ...") thay vì force-execute. Thêm metric
   `RuntimeMetrics.blocked_by_dependency`. Test cũ `test_unmet_dependency_does_not_loop` (đang
   assert đúng hành vi lỗi) đã thay bằng
   `test_dependency_on_unknown_capability_fails_graph_validation` và
   `test_node_blocked_by_failed_dependency_is_not_force_executed`.
2. **Hard budget Epic 6 có thể bị vượt qua recovery** (`execution_budget.py`,
   `capability_recovery.py`, `execution_runtime.py`, `execution_engine.py`). Trước đây
   `budget.capabilities += metrics.recovery_attempts` chỉ được cộng **sau khi** recovery đã chạy
   xong bên trong runtime, nên round có thể vượt `max_capabilities`/`max_estimated_cost` trước khi
   bị phát hiện. Đã sửa bằng reservation trước khi dispatch: thêm
   `ExecutionBudget.try_reserve_capability()` (atomic, không thread-safe tự thân — caller giữ lock)
   và tham số `can_attempt` cho `CapabilityRecovery.recover()` (dừng ngay với
   `RecoveryStopReason.BUDGET_EXHAUSTED` nếu hết ngân sách). `ExecutionRuntime.execute()` nhận thêm
   `budget: ExecutionBudget | None` và một lock riêng cho budget, nối xuống
   `_execute_single_node`/`_execute_batch_parallel`/`_execute_node`/`_recover_node`. Cả 3 call site
   trong `execution_engine.py` (`execute()` primary round, `_expand_evidence()` expansion round) đã
   đổi sang truyền `budget=budget` và xóa dòng cộng dồn hậu-kỳ.
3. **`_bounded_graph()` có thể làm mất prerequisite** (`execution_engine.py`). Khi cắt node theo
   budget, code cũ chỉ xóa cạnh `depends_on` trỏ tới node bị cắt, khiến node phụ thuộc (B) biến
   thành "độc lập" và vẫn được chạy dù prerequisite (A) đã bị loại. Đã sửa: sau bước chọn theo
   budget, tính dependency closure — lặp loại bỏ mọi node còn thiếu ít nhất một dependency (kể cả
   gián tiếp) cho tới khi ổn định, rồi mới dựng graph cuối cùng. Không còn node nào trong graph trả
   về có `depends_on` trỏ ra ngoài chính graph đó.
4. **Hai execution path lệch nhau** (`execution_engine.py`). `execute_immutable()` không có nơi
   production nào gọi và không có test trực tiếp; đã xác nhận (grep toàn repo) rồi **xóa hẳn**
   thay vì giữ một path chết có nguy cơ lệch hành vi với `execute()`. Docstring class
   `ExecutionEngine` cũng bỏ câu nhắc "supports both mutable and immutable paths".
5. **Rule config fallback âm thầm sang hardcoded rules** (`execution_engine.py`,
   `src/shared/config_schema.py`). Trước đây nếu `config/rules/` thiếu/rỗng khi deploy,
   `ThresholdEvaluator(atomic_rules or None)` âm thầm dùng `DEFAULT_ATOMIC_RULES` hardcoded, vi
   phạm mục tiêu DR1-610 (rule production phải versioned/owned/reviewed/trong config đã validate).
   Đã thêm `RuleConfigError` và tham số `ExecutionEngine.__init__(..., require_configured_rules:
   bool = True)`: mặc định, nếu không load được atomic rule nào từ config, engine raise ngay lúc
   khởi tạo thay vì fallback âm thầm; caller cố ý muốn hành vi permissive cũ (ví dụ script nhẹ
   không cần reasoning rule) có thể truyền `require_configured_rules=False`.

**Tests/verification (2026-08-06)**
- ✅ `tests/pipeline/test_execution_runtime.py` — 31 tests pass (thay 1 test cũ bằng 2 test mới cho
  mục 1).
- ✅ `tests/pipeline/test_execution_runtime.py`, `tests/pipeline/test_execution_engine.py`,
  `tests/pipeline/test_execution_graph.py`, `tests/pipeline/test_capability_recovery.py`,
  `tests/pipeline/test_execution_budget.py`, `tests/shared/test_rule_config_schema.py`,
  `tests/shared/test_config_schema.py` — 104 tests pass.
- ✅ Full repository regression: `pytest tests/` — 1511 passed, 4 skipped (không regression).
- ✅ `ruff check` sạch trên toàn bộ file đã sửa; `mypy --ignore-missing-imports` sạch trên toàn bộ
  file đã sửa.

---

## 10. EPIC 7 — Assessment layer hardening
### DR1-701 — Mở rộng AssessmentRequest
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-505, DR1-604
- **Files:** `src/pipeline/assessment_request.py`, `src/pipeline/assessment_adapter.py`, `src/agent/deterministic_agent.py`

**Vấn đề**  
Model hiện nhận raw evidence + complete flag, chưa nhận facts/findings/failures/allowed claims rõ.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `AssessmentRequest` có thêm `request_frame` (dict an toàn, không phải object runtime),
   `unknowns`, `evidence_status`, `allowed_claims`.
2. ✅ `AssessmentAdapter.build()` populate đủ field mới từ `InvestigationRequest`: `unknowns` gộp
   `missing_facts` của mọi finding + `missing_evidence` legacy; `allowed_claims` là id của mọi fact
   `usable` và mọi finding id; `request_frame` lấy từ `request.request_frame.to_dict()`.
3. ✅ Sửa lại nhánh rebuild `AssessmentRequest` khi có conversation context trong
   `deterministic_agent.py` — trước đây bị rơi mất `findings`/`health_summary` khi rebuild, nay giữ
   đủ toàn bộ field.
4. Raw evidence (`evidence: tuple[EvidencePackage, ...]`) vẫn giữ nguyên làm optional debug context
   như trước; chưa bound kích thước nghiêm ngặt hơn ngoài truncation sẵn có ở prompt builder.

**Acceptance criteria**
- [x] Model có đủ context để giải thích nhưng không cần tự xác định validity (facts đã lọc
      `usable`, findings đã có decision/severity/coverage).

**Tests/verification**
- ✅ `tests/pipeline/test_assessment_request.py`, `tests/pipeline/test_assessment_adapter.py`,
  `tests/agent/test_deterministic_agent.py` — pass.

---
### DR1-702 — Prompt builder hiển thị failure và giới hạn evidence
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-701
- **Files:** `src/model/protocol/prompt_builder_v2.py`

**Vấn đề**  
Prompt hiện bỏ package failed, khiến model tưởng evidence chỉ đơn giản là missing.

**Cách làm (đã thực hiện 2026-08-05, hoàn tất 2026-08-06)**
1. ✅ Thêm đủ section: "Confirmed facts", "Deterministic findings", "Contradicting facts",
   "Missing facts / unknowns", "Scope limitations: collection failures", cùng dòng
   `Evidence status: <status>` + wording uncertainty tương ứng (DR1-708).
2. ✅ Thêm "Grounding rule" nhắc model không suy ra trend/health/action ngoài facts/findings khi có
   `allowed_claims`.
3. ✅ **Hoàn tất 2026-08-06**: đã xóa hẳn `_summarize_evidence` (fallback key-guessing theo tên
   evidence). Lý do an toàn để xóa: `FactNormalizerRegistry` (dùng bởi `EvidenceMerge`) đã có
   fallback generic ở tầng normalizer từ trước — mọi capability Linux/Zabbix/Grafana đăng ký
   `produces_facts` mặc định `f"{provider}.{capability}"` khi không có mapping riêng
   (`src/tool/linux/__init__.py::_PRODUCED_FACTS.get(_name, (f"linux.{_name...}",))` và tương tự
   cho zabbix/grafana). Nghĩa là **mọi package `valid_for_requirements=True` từ 3 provider này luôn
   có ít nhất một usable Fact** — nhánh `if usable_facts: ... continue` trong prompt builder đã che
   hết nhánh `_summarize_evidence` từ trước, hàm này thực chất là dead code. Với provider không có
   fact normalizer (vd. `internet_tool.web_fetch`), `_summarize_evidence` cũng không có case riêng
   (luôn trả `""`) nên đã tự rơi vào JSON fallback từ trước — xóa hàm không làm mất evidence, chỉ
   loại bỏ code không còn đường chạy tới được. Đường JSON fallback (`_normalize_evidence` + dump)
   vẫn giữ nguyên cho các provider chưa có fact normalizer.

**Acceptance criteria**
- [x] Command not found/SSH timeout xuất hiện như limitation (`collection_failures` section), không
      biến thành zero.
- [x] Loại bỏ hoàn toàn fallback key-guessing — `_summarize_evidence` đã xóa khỏi
      `prompt_builder_v2.py`.

**Tests/verification**
- ✅ `tests/model/protocol/test_prompt_builder_v2.py` — 12 tests pass, gồm test mới
  `test_no_usable_facts_falls_back_to_full_json_not_key_guessing` xác nhận package không có usable
  facts render ra JSON đầy đủ thay vì subset field đoán theo tên.
- ✅ Full suite: `pytest tests/` — 1505 passed, 4 skipped (không regression).

---
### DR1-703 — Claim grounding validator
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-701
- **Files:** `src/model/claim_validator.py (new)`, `src/model/assessment_guard.py (new)`,
  `src/agent/deterministic_agent.py`

**Vấn đề**  
LLM có thể thêm số liệu, target hoặc kết luận không có trong facts/findings.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `ClaimValidator.validate()` trích số có đơn vị (`%`, GB/MB/KB/TB, giây/phút/giờ) và target
   mention (`server X`, `máy chủ X`) từ response text, so với tập số/target lấy từ facts usable +
   findings + `request_frame`.
2. ✅ Không phải full theorem prover: chỉ so khớp normalized-number string và substring target —
   đủ để chặn số/target bịa hoàn toàn khác, có thể miss số liệu diễn đạt gián tiếp (chấp nhận theo
   đúng scope "chặn pattern nguy hiểm và mismatch rõ", không phải chứng minh từng câu).
3. ✅ `redact_ungrounded_claims()` thay trực tiếp số/target không grounded bằng marker
   `[số liệu chưa xác nhận]` / `[mục tiêu chưa xác nhận]`, giữ nguyên phần còn lại của câu trả lời.
4. ✅ Không có evidence nào (facts/findings/allowed_claims rỗng) → không có gì để chặn, tránh false
   positive khi bản thân investigation thiếu evidence (đó là lỗi evidence-completeness, không phải
   lỗi claim).

**Acceptance criteria**
- [x] Số GB/% không có trong fact set bị chặn (redact) — `test_ungrounded_number_flagged`,
      `test_redact_ungrounded_claims_replaces_invented_number`.
- [x] Target không khớp evidence bị chặn — logic `_allowed_targets`/`ungrounded_targets`; chưa có
      case cụ thể "đổi monitor thành localhost" trong test, nên coi acceptance criterion này là
      partial cho tới khi có golden case thật.

**Tests/verification**
- ✅ `tests/model/test_claim_validator.py` — 5 tests pass.
- ✅ `tests/model/test_assessment_guard.py` — 3 tests pass (tích hợp với action guard/numeric/
  language guard theo đúng thứ tự).

---
### DR1-704 — Action hallucination guard và ActionReceipt contract
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-211, DR1-703
- **Files:** `src/model/action_receipt.py (new)`, `src/model/assessment_guard.py (new)`

**Vấn đề**  
Orion từng nói "đã xóa /tmp" dù không thực thi.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `contains_action_claim()` match actor-attributed completion verbs ("tôi đã xóa", "Orion đã
   restart", "I have deleted", "I've removed"...), cố tình hẹp theo actor để không false-positive
   trên mô tả trạng thái hệ thống ("dịch vụ đã dừng").
2. ✅ `ActionReceipt` (frozen dataclass) định nghĩa contract tương lai: action_id/capability/target/
   status/timestamps/exit_code/verified. Không có code path nào tạo receipt hôm nay (Orion read-
   only) nên `action_receipts=()` luôn rỗng trong production.
3. ✅ `guard_action_claims()` fail-closed: nếu phát hiện action claim và không có receipt đã
   `verified=True`, thay toàn bộ response bằng câu từ chối chuẩn ("Orion chưa thực hiện hành động
   nào...").
4. ✅ Wired vào `apply_assessment_guards()` làm bước đầu tiên (ưu tiên cao nhất, chặn trước khi chạy
   claim/numeric/language guard).

**Acceptance criteria**
- [x] Actor-attributed action claim bị chặn trong test đơn vị (tiếng Việt + tiếng Anh).
- [ ] "0 hallucinated action trong adversarial suite" — chưa có adversarial suite riêng (thuộc
      DR1-809, ngoài scope task này); mới có unit-level coverage.

**Tests/verification**
- ✅ `tests/model/test_action_receipt.py` — 4 tests pass, gồm case "mô tả trạng thái không phải
  action claim" để tránh false positive.
- ✅ `tests/model/test_assessment_guard.py::test_action_claim_short_circuits_everything`.

---
### DR1-705 — Numeric và unit consistency validator
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-501, DR1-703
- **Files:** `src/model/numeric_claim_validator.py (new)`, `src/model/assessment_guard.py`

**Vấn đề**  
Transcript có disk free 154 GB rồi 391.8 GB và nhầm size/used.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `find_arithmetic_inconsistencies()` gom fact cùng `(subject, target)`, so
   `filesystem.size_bytes` ≈ `filesystem.used_bytes` + `filesystem.available_bytes` (và cặp tương
   tự cho memory) trong dung sai 2%.
2. ✅ `find_duplicate_metric_conflicts()` phát hiện cùng `(subject, target, metric)` bị report với
   giá trị khác nhau trong cùng investigation — chính là lớp lỗi "154 GB rồi 391.8 GB".
3. ✅ Không sửa số tự động (không đoán số nào đúng); `apply_assessment_guards()` chỉ thêm scope-note
   yêu cầu kiểm tra thủ công khi phát hiện mâu thuẫn, đúng nguyên tắc "surface thay vì chọn ngẫu
   nhiên" — số liệu gốc trong response vẫn do claim grounding (DR1-703) xử lý riêng.
4. Chưa có bước "normalize displayed units từ fact canonical" cho phần response text (ví dụ ép mọi
   response quy đổi cùng về GB) — mới dừng ở phát hiện mâu thuẫn giữa facts, chưa rewrite unit hiển
   thị trong câu trả lời model.

**Acceptance criteria**
- [x] Contradiction giữa facts được phát hiện và surface qua scope-note thay vì bị che giấu.
- [ ] "Cùng fact set luôn render cùng số" — đúng ở tầng fact (canonical value cố định), nhưng chưa
      kiểm chứng ở tầng response text (model vẫn có thể diễn đạt số khác nhau theo ngôn ngữ tự
      nhiên); cần DR1-703 claim redaction + golden test để đóng hẳn.

**Tests/verification**
- ✅ `tests/model/test_numeric_claim_validator.py` — 2 tests pass.

---
### DR1-706 — Language quality validator
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-703
- **Files:** `src/model/output_sanitizer.py`, `src/model/assessment_guard.py`

**Vấn đề**  
Response có ký tự Trung/Nhật/Nga xen giữa tiếng Việt.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `detect_script_leakage()` phát hiện Han/Hiragana/Katakana/Hangul và Cyrillic ngoài code
   span (loại trừ backtick/code fence trước khi check).
2. ✅ `enforce_language_quality()` chỉ áp dụng cho câu trả lời tiếng Việt (`lang == "vi"`); tiếng
   Anh không bị ép script-pure.
3. 🔁 Khác với đề xuất gốc ("regenerate một lần hoặc dùng deterministic safe summary"): vì
   `apply_assessment_guards()` không có quyền gọi lại model (không có model handle ở layer này),
   nên chọn cách an toàn hơn — xóa trực tiếp ký tự ngoài script mong đợi thay vì rewrite câu. Đánh
   đổi: câu có thể hơi cụt nếu ký tự lạ nằm giữa từ, nhưng không bao giờ để lọt CJK/Cyrillic ra
   ngoài.

**Acceptance criteria**
- [x] Script lạ bị loại khỏi output trong mọi test case hiện có; chưa đo được "0 mixed-script
      leakage trong QA tiếng Việt" ở mức suite thật (cần DR1-806/809).

**Tests/verification**
- ✅ `tests/model/test_output_sanitizer.py` — 5 tests pass (bao gồm case code-span không bị đụng).

---
### DR1-707 — DeterministicResponder chỉ đọc valid facts/findings
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-501, DR1-604
- **Files:** `src/pipeline/deterministic_responder.py`

**Vấn đề**  
Fast path nhanh nhưng nguy hiểm nếu đọc raw/default zero.

**Cách làm (đã thực hiện 2026-08-05, hoàn tất refactor 2026-08-06)**
1. ✅ `_package_has_untrustworthy_facts()`: trước khi bất kỳ responder nào đọc evidence của một
   package, kiểm tra `pkg.facts` — nếu có fact `CONTRADICTORY` hoặc `STALE`, bỏ qua toàn bộ package
   (fast path trả `None`, rơi xuống LLM assessment nơi đã hiển thị contradiction/staleness tường
   minh qua DR1-702). Không đổi trong lượt hoàn tất — đây vẫn là guard an toàn chính.
2. ✅ `_health_response()` dùng `fact_set`/`HealthSummary` (DR1-609) từ trước, không đổi.
3. ✅ **Hoàn tất 2026-08-06**: thêm helper `_facts_by_metric()` / `_first_fact_value()` và refactor
   9/15 responder con để đọc **canonical Fact trước, dict thô chỉ làm fallback**:
   `_check_zombie_processes` (`process.zombie_count`), `_check_hostname` (`system.hostname`),
   `_check_kernel` (`system.kernel`), `_check_ram_available` (`memory.available`/`memory.total`,
   đơn vị byte), `_check_load_average` (`system.load_1m/5m/15m`), `_check_swap`
   (`swap.total`/`swap.used`, đơn vị byte), `_check_listening_ports`
   (`network.listening_socket`), `_check_disk_full` (`filesystem.usage` theo từng mountpoint qua
   `dimensions`), và `_check_service_status` (nhánh tra cứu service cụ thể qua fact
   `service.status` + `dimensions.service_name`; nhánh liệt kê failed/disabled toàn bộ service vẫn
   đọc dict vì `LinuxFactNormalizer._services` hiện chỉ emit `service.inventory`, chưa có fact
   per-service failed/disabled — xem điểm 5).
4. **Phát hiện phụ trong lúc refactor — đây là sửa bug thật, không chỉ đổi kiến trúc**: đối chiếu
   với `src/tool/linux/output_schema.py`, `_check_ram_available` (khoá cũ `available_kb`/
   `total_kb`) và `_check_swap` (khoá cũ `swap_total`/`swap_total_kb`) **không bao giờ khớp** với
   schema thật (`available_bytes`/`total_bytes`, `total_bytes`/`used_bytes`) — nghĩa là hai
   responder này gần như luôn trả `None` trên dữ liệu thật trước bản vá này. Đọc qua Fact (đơn vị
   byte chuẩn hoá bởi normalizer) sửa luôn lỗi này. Tương tự, `_check_listening_ports` dùng khoá
   `port`/`service` trong khi schema thật là `port_number`/`process`; đã thêm các khoá đúng làm ưu
   tiên đầu (áp dụng cho cả nhánh fact và nhánh dict fallback).
4b. **Phát hiện bug thứ hai, độc lập với (4), nghiêm trọng hơn**: đối chiếu điều kiện
   `pkg.evidence_name in (...)` ở từng nhánh trong `try_response()` với bảng ánh xạ thật
   `src/pipeline/capability_library.py` (nơi định nghĩa mọi `evidence_name` hợp lệ mà router có
   thể gán cho một `EvidenceRequirement`), phát hiện 4 evidence_name hợp lệ, riêng biệt trong
   production **chưa từng nằm trong điều kiện khớp của responder tương ứng**, khiến các package đó
   luôn rơi thẳng xuống LLM dù có fact đầy đủ:
   - `"Swap"` (không phải chỉ `"Memory"`) — `PERFORMANCE_ASSESSMENT`/`MACHINE_ASSESSMENT` định
     nghĩa Swap là evidence riêng biệt với Memory.
   - `"Load Average"` (không phải chỉ `"CPU"`) — định nghĩa riêng trong `PERFORMANCE_ASSESSMENT`.
   - `"Listening Ports"` (không phải chỉ `"Network"`) — định nghĩa riêng trong
     `NETWORK_ASSESSMENT`.
   - `"System Uptime"` (không phải `"CPU"`/`"System Information"`) — định nghĩa riêng trong
     `_ADDITIONAL_EVIDENCE`, ánh xạ từ capability `get_uptime` độc lập với `get_system`/`get_cpu`.
   - Đã thêm `"Disk Usage"` (từ `STORAGE_ASSESSMENT`) vào điều kiện của `_check_disk_full` cho
     đồng bộ, dù `"Storage"`/`"Filesystem"` cũ vẫn đúng và không đổi.
   Đã bổ sung các giá trị này vào điều kiện khớp tương ứng (giữ nguyên giá trị cũ, chỉ thêm OR),
   nên không ảnh hưởng hành vi đã có, chỉ mở rộng số package thực sự kích hoạt được fast path.
5. ❌ **Chưa làm** (còn lại có chủ đích, rủi ro thấp — không có canonical Fact để đọc):
   `_check_top_cpu` (không có fact `process.top_cpu`) và `_check_uptime` (không có fact
   `system.uptime`) — `LinuxFactNormalizer` chưa emit hai metric này; cần thêm normalizer trước khi
   refactor được. Nhánh liệt kê failed/disabled service (không hỏi service cụ thể) cũng chưa có
   fact backing vì lý do tương tự (điểm 3). Cả ba đã có comment `DR1-707` tại chỗ đọc `pkg.data`
   giải thích rõ lý do, để task tiếp theo (mở rộng `LinuxFactNormalizer`) dễ tìm.
6. Guard package-level (điểm 1) không đổi, không thêm I/O; các đọc-fact mới chỉ duyệt
   `pkg.facts` (đã có sẵn trong bộ nhớ), không thêm round-trip.

**Acceptance criteria**
- [x] Fast path không bypass evidence quality cho trường hợp contradictory/stale — đã đóng từ
      2026-08-05, không đổi.
- [x] "Refactor responder sang FactSet" — hoàn tất cho 9/15 responder có canonical Fact coverage
      (chiếm toàn bộ nhóm RAM/swap/disk/load/hostname/kernel/zombie/ports/service-cụ-thể). 2 responder
      không có Fact coverage (`top_cpu`, `uptime`) và nhánh generic failed/disabled service được
      giữ nguyên dict-based có chủ đích, đã ghi rõ lý do và điều kiện đóng (cần thêm fact normalizer
      cho `process.top_cpu`/`system.uptime`/per-service failed state — theo dõi như việc kế tiếp,
      ngoài scope hiện tại).
- [x] Fact response P95 không đổi — đọc `pkg.facts` là tra cứu trong bộ nhớ, không thêm I/O.

**Tests/verification**
- ✅ `tests/pipeline/test_deterministic_responder.py` — 45 tests pass: 2 test cũ
  (contradictory/stale guard), 10 test `TestDeterministicResponderReadsCanonicalFacts` (fact-first
  read + fallback + đơn vị byte đúng), và 5 test mới `TestDeterministicResponderMatchesRealEvidenceNames`
  phủ đúng 4 evidence_name production bị bỏ sót ở điểm 4b (Swap/Load Average/Listening
  Ports/System Uptime/Disk Usage).
- ✅ Full suite: `pytest tests/` — 1510 passed, 4 skipped (không regression trên toàn bộ codebase,
  bao gồm cả các module trước đó không cài được do thiếu dependency — đã cài đủ để chạy full suite).
- ✅ `ruff check` sạch trên toàn bộ file đã sửa.

---
### DR1-708 — Chuẩn hóa uncertainty và confidence wording
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-701
- **Files:** `src/model/protocol/prompt_builder_v2.py`

**Vấn đề**  
Model thường nói chắc chắn khi evidence partial.

**Cách làm (đã thực hiện 2026-08-05)**
1. ✅ `_EVIDENCE_STATUS_WORDING_VI`/`_EN` trong `prompt_builder_v2.py` map từng `EvidenceStatus`
   (`SUFFICIENT`/`PARTIAL`/`UNAVAILABLE`/`STALE`/`CONTRADICTORY`) sang câu hướng dẫn wording tương
   ứng, chèn ngay đầu prompt qua `_evidence_status_preamble()`.
2. ✅ Wording cho `UNAVAILABLE`/`CONTRADICTORY` cấm rõ việc suy đoán/kết luận "mọi thứ ổn"; wording
   cho `PARTIAL`/`STALE` yêu cầu nêu rõ phần chưa xác nhận và mốc thời gian quan sát.
3. ❌ Chưa sửa `deterministic_responder.py` để áp cùng bảng wording cho các câu trả lời fast-path
   khi evidence không đầy đủ — hiện fast path đã tự có logic riêng (`TemporalEvidenceGuard.refusal`,
   `_health_response` theo `HealthStatus`) nhưng chưa dùng chung bảng wording DR1-708; để lại làm
   theo dõi (không tạo hai nguồn wording khác nhau nhưng chưa hợp nhất trong lượt này).

**Acceptance criteria**
- [x] Prompt có wording khác nhau rõ rệt theo từng evidence_status — test
      `test_findings_and_unknowns_rendered` xác nhận `Evidence status: PARTIAL` xuất hiện.
- [ ] "Unsafe conclusion rate đạt gate" — cần golden/assessment test suite thực tế (DR1-805/810),
      ngoài scope một task prompt-wording.

**Tests/verification**
- ✅ `tests/model/protocol/test_prompt_builder_v2.py`.

---

## 11. EPIC 8 — QA harness, evaluator và acceptance gates
### DR1-801 — Unit test matrix cho CommandResult/CapabilityResult
- **Priority:** P0
- **Status:** ✅
- **Dependencies:** DR1-101..107
- **Files dự kiến:** `tests/tool/`, `tests/shared/execution/`

**Vấn đề**  
Failure semantics là nền móng nên cần test theo ma trận.

**Cách làm**
1. Matrix local/SSH × success/empty/notfound/nonzero/permission/timeout/unreachable.
2. Capability valid/valid_empty/partial/failed/unsupported/parse_failed.

**Acceptance criteria**
- [x] Coverage branch đủ cho mapping lỗi core. (100% branch coverage: `command_result.py`, `capability_result.py`, `errors.py`)

**Tests/verification**
- `pytest touched modules`
- Đã thêm: `tests/shared/execution/test_command_result_matrix.py` (ma trận target local/SSH × toàn bộ `CommandStatus`, legacy_output/success/iter/to_dict)
- Đã thêm: `tests/tool/test_capability_result_matrix.py` (ma trận local/SSH command_results → `CapabilityStatus` valid/valid_empty/partial/collection_failed, cộng construction trực tiếp cho unsupported/invalid_parameters/parse_failed)
- Đã bổ sung 2 case vào `tests/tool/test_error_mapping.py` để phủ nốt nhánh `capability_error_from_status("valid")` và fallback status lạ → `INTERNAL_ERROR`
- Kết quả: `pytest tests/shared/execution tests/tool/test_capability_result_matrix.py tests/tool/test_capability_result.py tests/tool/test_error_mapping.py --cov=src.shared.execution.command_result --cov=src.tool.capability_result --cov=src.tool.errors --cov-branch` → 170 passed, 100% branch coverage cả 3 module
- Full regression `tests/tool` + `tests/shared` (trừ `test_cli.py`, thiếu `python-multipart` trong sandbox, không liên quan) → 499 passed

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
- **Status:** ✅
- **Dependencies:** DR1-101, DR1-501, DR1-606
- **Files dự kiến:** `docs/ai/05_EXECUTION_PIPELINE.md`, `docs/ai/06_TOOL_AND_CAPABILITY_DESIGN.md`, `docs/tools/linux.md`

**Vấn đề**  
Docs cần mô tả CommandResult, Fact, Finding, recovery và LLM boundary mới.

**Cách làm (hoàn tất 2026-08-07)**
1. ✅ Cập nhật flow từ `RequestFrame` đến `ExecutionTrace`, Fact/Findings, deterministic responder và assessment guards trong `05_EXECUTION_PIPELINE.md`.
2. ✅ Ghi rõ command strategy/fallback là sở hữu của Child Tool, không có đường LLM/raw command, trong `06_TOOL_AND_CAPABILITY_DESIGN.md` và `docs/tools/linux.md`.
3. ✅ Chuẩn hóa tài liệu failure semantics, `VALID_EMPTY`, structured error, provenance, bounded recovery và rollout compatibility.

**Acceptance criteria**
- [x] Docs khớp source và tests.

**Tests/verification**
- ✅ Review đối chiếu `CommandResult`, `CapabilityResult`, `Fact`, `Finding`, `EvidenceMerge`, `CapabilityRecovery` và test contract; `git diff --check` pass.

---
### DR1-902 — ADR cho evidence validity và deterministic reasoning v1
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-501, DR1-602
- **Files dự kiến:** `docs/adr/ADR-0008-evidence-validity.md (new)`, `docs/adr/ADR-0009-deterministic-reasoning-v1.md (new)`

**Vấn đề**  
Đây là thay đổi contract kiến trúc cần quyết định rõ, không chỉ implicit code.

**Cách làm (hoàn tất 2026-08-07)**
1. ✅ Thêm ADR-0008 cho missing vs zero, validity/freshness/provenance và evidence contract.
2. ✅ Thêm ADR-0009 cho atomic/composite rule, bounded recovery/expansion, no self-learning và no LLM planning.
3. ✅ Nêu trade-off/rejected alternatives và cross-link hai ADR ở `09_ARCHITECTURE_DECISIONS.md` (AD-023/024).

**Acceptance criteria**
- [x] ADR được cross-link trong architecture decisions.

**Tests/verification**
- ✅ Doc review: ADR links, Decision/Consequences/Rejected alternatives và architecture summaries được đối chiếu.

---
### DR1-903 — Kế hoạch backward compatibility và migration
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-101, DR1-104, DR1-508
- **Files dự kiến:** `docs/migrations/deterministic_reasoning_v1.md (new)`, `src/tool/ compatibility adapters`

**Vấn đề**  
Đổi tuple/dict contracts có thể phá tools/tests/UI.

**Cách làm (hoàn tất 2026-08-07)**
1. ✅ Thêm `docs/migrations/deterministic_reasoning_v1.md`: matrix public/internal interfaces, thứ tự vertical-slice, rollback/exit criteria.
2. ✅ `CommandResult.__iter__` và direct `CapabilityResult.from_legacy()` phát `DeprecationWarning`; internal dispatcher bridges suppress duplicate warning cho legacy handler chưa migrate.
3. ✅ Ghi rõ không big-bang và điều kiện remove adapter/flag sau khi callers/tests chuyển hết.

**Acceptance criteria**
- [x] Old callers vẫn hoạt động trong migration window.

**Tests/verification**
- ✅ `tests/shared/execution/test_command_result.py`, `tests/tool/test_capability_result.py` — legacy caller behavior + warning contract pass.

---
### DR1-904 — Feature flags cho rollout theo phase
- **Priority:** P1
- **Status:** ✅
- **Dependencies:** DR1-903
- **Files dự kiến:** `src/model/config_store.py`, `config hoặc env docs`

**Vấn đề**  
Facts/rules/validators mới cần rollback độc lập khi regression.

**Cách làm (hoàn tất 2026-08-07)**
1. ✅ Thêm schema/loader strict cho `structured_command_result`, `canonical_facts`, `composite_rules`, `claim_guard` ở `config/feature_flags.yaml` (optional) và override `ORION_FEATURE_*`.
2. ✅ Migration default là off; QA/deployment bật theo thứ tự documented, mỗi layer rollback độc lập mà không đổi response schema.
3. ✅ Wire flags vào EvidenceMerge/ExecutionEngine/assessment guard; action-claim/read-only guard luôn bắt buộc. Migration doc ghi exit criteria và removal phải có task riêng.

**Acceptance criteria**
- [x] Có rollback không đổi data schema bên ngoài.

**Tests/verification**
- ✅ `tests/model/test_feature_flags.py` — default, file, env override, unknown/invalid input và named lookup; runtime/config tests pass.

---
### DR1-905 — Operator troubleshooting guide cho collection failures
- **Priority:** P2
- **Status:** ✅
- **Dependencies:** DR1-107, DR1-201
- **Files dự kiến:** `docs/troubleshooting.md`, `docs/tools/linux.md`

**Vấn đề**  
Operator cần biết COMMAND_NOT_FOUND/SSH_AUTH/UNSUPPORTED khác nhau và cách sửa.

**Cách làm (hoàn tất 2026-08-07)**
1. ✅ Thêm bảng stable error code → nguyên nhân → safe checks → operator action trong `docs/troubleshooting.md`.
2. ✅ Mô tả `localhost`/Compose container, explicit-target không fallback, preflight/transport behavior ở troubleshooting và Linux Tool doc.
3. ✅ Hướng dẫn giữ read-only/parameter/target inspectors, redaction và least privilege; không có hướng dẫn bypass security guard.

**Acceptance criteria**
- [x] Guide dùng đúng error codes trong source.

**Tests/verification**
- ✅ Đối chiếu `CommandStatus`, `CapabilityErrorCode`, preflight và Linux capability contracts; `git diff --check` pass.

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
