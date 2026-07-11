# Legacy Runtime Removal — Risk Assessment

## Risk 1: Regression in default deterministic path

**Probability:** Very Low
**Impact:** Critical

**Mitigation:** The deterministic path (`runtime_factory.create_deterministic_agent()`) imports zero legacy files. Removing legacy files cannot affect imports or runtime behavior of the default path. Verified by grep of all imports in `runtime_factory.py`, `deterministic_agent.py`, and all `src/pipeline/` files.

**Evidence:**
```
$ grep -rn "from src.agent.agent\|from src.tool.tool_registry\|from src.shared.reasoning" src/pipeline/ src/agent/deterministic_agent.py src/agent/runtime_factory.py 
→ (no output)
```

---

## Risk 2: Broken CLI --legacy path during transition

**Probability:** High (intended — the path is being removed)
**Impact:** Low

**Mitigation:** The `--legacy` flag is removed in Step 1. After removal, there is no way to invoke the legacy path. All users must use the deterministic path. Since the deterministic path is already the default and has been running without issue, this is an acceptable transition.

---

## Risk 3: Broken benchmark --legacy path

**Probability:** High (intended)
**Impact:** Low

**Mitigation:** Same as Risk 2. Removed in Step 2.

---

## Risk 4: Missed import that references legacy components

**Probability:** Very Low
**Impact:** Medium

**Mitigation:** Full grep of every legacy component name has been performed. The dependency analysis confirmed that legacy components are only imported by other legacy components. All import chains terminate at `src/cli.py` (in `if args.legacy:`) or `benchmark/__main__.py` (in `_build_legacy_runtime()`).

**Evidence from dependency audit:**
```
Agent → 3 importers (cli.py in --legacy, benchmark in --legacy, test_agent.py)
ToolRegistry → 3 importers (agent.py, cli.py in --legacy, benchmark in --legacy)
Action → 6 importers (all legacy chain)
FinalResponse → 5 importers (all legacy chain)
ReasoningState → 1 importer (agent.py — being removed)
```

---

## Risk 5: Test coverage loss

**Probability:** Low
**Impact:** Medium

**Mitigation:** 1,281 lines of legacy tests will be removed. These are replaced by ~2,400 lines of deterministic pipeline tests. The deterministic tests cover:
- Intent resolution (124 tests)
- Evidence planning (30 tests)
- Capability resolution (25 tests)
- Execution graph (16 tests)
- Execution runtime (14 tests)
- Assessment request/adapter (7 tests)
- Evidence completeness (8 tests)
- Capability routing (15 tests)
- Deterministic agent integration (2 tests)
- Total: ~240 pipeline tests

---

## Risk 6: Documentation becomes stale

**Probability:** Medium
**Impact:** Low

**Mitigation:** Old `docs/component_specifications/` and `docs/runtime_behavior/` directories describe the legacy ReAct architecture. These are already stale (they describe the old architecture). The `docs/ai/` directory is the approved Source of Truth and already describes the deterministic architecture. After removal, the stale docs should either be removed or archived, but this is a documentation cleanup task, not a runtime risk.

---

## Risk 7: Benchmark regression detection gap

**Probability:** Low
**Impact:** Medium

**Mitigation:** The benchmark `scoring.py` was designed for ReAct output format (checking for "evidence" and "assessment" keywords in response text). The deterministic `MockAssessmentAdapter` produces output that matches these criteria (PASS 0.70). If the assessment format changes, benchmark scores may need recalibration. This is a benchmark maintenance task, not a runtime risk.

---

## Risk Summary

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Default path regression | Very Low | Critical | Zero import overlap verified |
| CLI --legacy broken | High | Low | Intended removal |
| Benchmark --legacy broken | High | Low | Intended removal |
| Missed import | Very Low | Medium | Full dependency audit completed |
| Test coverage loss | Low | Medium | 2,400 lines of pipeline tests |
| Documentation stale | Medium | Low | docs/ai is authoritative |
| Benchmark regression | Low | Medium | Scores already validated |
