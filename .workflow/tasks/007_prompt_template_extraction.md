# Task 007: Prompt Template Extraction

> **Source:** IMPLEMENTATION_BACKLOG.md, Item 7 (Sprint 3, P2 - Refactor)
> **Created:** 2026-07-26
> **Status:** pending

---

## 1. Problem Summary

Prompts are embedded as hardcoded Python strings in `prompt_builder_v2.py` (368 LOC) and `deterministic_agent.py`. This couples prompt engineering to code changes — a prompt iteration requires a code deployment. The comparison projects all separate prompts from code via Jinja2 templates or external files.

**Strengths to preserve:**
- 11 intent-specific prompts
- `_summarize_evidence()` — domain-specific field extraction per evidence type
- `_normalize_evidence()` — truncation rules
- `_detect_language()` — Vietnamese character pattern matching with bilingual enforcement
- Output format enforcement (`NEVER wrap in JSON or code blocks`)

---

## 2. Files to Modify

| # | File | Change | LOC Impact |
|---|------|--------|------------|
| 1 | `config/prompts/assess_cpu.j2` (NEW) | CPU assessment template | ~20 lines |
| 2 | `config/prompts/assess_memory.j2` (NEW) | Memory assessment template | ~20 lines |
| 3 | `config/prompts/assess_disk.j2` (NEW) | Disk assessment template | ~20 lines |
| 4 | `config/prompts/assess_network.j2` (NEW) | Network assessment template | ~20 lines |
| 5 | `config/prompts/assess_process.j2` (NEW) | Process assessment template | ~20 lines |
| 6 | `config/prompts/assess_service.j2` (NEW) | Service assessment template | ~20 lines |
| 7 | `config/prompts/assess_troubleshoot.j2` (NEW) | Troubleshooting template | ~20 lines |
| 8 | `config/prompts/assess_application.j2` (NEW) | Application assessment template | ~20 lines |
| 9 | `config/prompts/assess_monitoring.j2` (NEW) | Monitoring assessment template | ~20 lines |
| 10 | `config/prompts/assess_performance.j2` (NEW) | Performance assessment template | ~20 lines |
| 11 | `config/prompts/assess_security.j2` (NEW) | Security assessment template | ~20 lines |
| 12 | `config/prompts/chat_system.j2` (NEW) | Chat system prompt | ~15 lines |
| 13 | `src/model/protocol/prompt_loader.py` (NEW) | Jinja2 template loader + renderer | ~50 lines |
| 14 | `src/model/protocol/prompt_builder_v2.py` | Replace hardcoded strings with template loading | ~30 lines modified |
| 15 | `src/agent/deterministic_agent.py` | Replace chat system prompt with template reference | ~10 lines modified |

**Total estimated change:** ~345 lines (+315 template, +50 loader, -40 hardcoded)

---

## 3. Detailed Instructions

### 3.1 Template format

Use Jinja2 with these variables exposed:

```jinja2
{# config/prompts/assess_cpu.j2 #}
Bạn là trợ lý quản trị hệ thống. Phân tích thông tin CPU sau:

CPU Model: {{ evidence.cpu.model | default('N/A') }}
CPU Cores: {{ evidence.cpu.cores | default('N/A') }}
CPU Usage: {{ evidence.cpu.usage_percent | default('N/A') }}%
Load 1m/5m/15m: {{ evidence.cpu.load_1min | default('N/A') }}/{{ evidence.cpu.load_5min | default('N/A') }}/{{ evidence.cpu.load_15min | default('N/A') }}

Yêu cầu:
1. Đánh giá mức sử dụng CPU (thấp/trung bình/cao)
2. So sánh load average với số cores
3. Đề xuất nếu có vấn đề

QUAN TRỌNG: Trả lời TOÀN BỘ bằng tiếng Việt. Không dùng ngôn ngữ khác.
KHÔNG wrap trong JSON hoặc code blocks.
{% if output_format == 'compact' %}Trả lời ngắn gọn, tối đa 3 câu.{% endif %}
```

### 3.2 `prompt_loader.py` (NEW)

```python
from __future__ import annotations

from jinja2 import Environment, FileSystemLoader, Template
from pathlib import Path

class PromptLoader:
    """Load and render Jinja2 prompt templates."""
    
    def __init__(self, template_dir: Path | None = None):
        self._env = Environment(
            loader=FileSystemLoader(template_dir or Path("config/prompts")),
            autoescape=False,
        )
    
    def render(self, template_name: str, **context) -> str:
        template = self._env.get_template(template_name)
        return template.render(**context)
```

### 3.3 Integration

```python
# OLD in prompt_builder_v2.py:
cpu_prompt = """Bạn là trợ lý quản trị hệ thống..."""

# NEW:
loader = PromptLoader()
cpu_prompt = loader.render("assess_cpu.j2",
    evidence=evidence_package,
    language=language,
    output_format=output_format)
```

Functions `_summarize_evidence()`, `_normalize_evidence()`, `_detect_language()` remain Python — invoked before template rendering to prepare context variables.

---

## 4. Verification Criteria

- [ ] All 11 intent templates + 1 chat template externalized as `.j2` files
- [ ] `_summarize_evidence()`, `_normalize_evidence()`, `_detect_language()` preserved
- [ ] `set_prompt_version()` still works (compact/minimal toggle)
- [ ] Prompt rendering time <5% increase
- [ ] Assessment quality unchanged (benchmark gate)
- [ ] Tests pass: `python -m pytest tests/ -q --tb=short -x -k "not slow"`
- [ ] One atomic commit: `refactor: extract 11+1 prompts to Jinja2 templates`