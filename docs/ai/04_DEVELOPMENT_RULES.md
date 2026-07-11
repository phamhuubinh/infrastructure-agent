# 02 - Development Rules
These rules are mandatory for all work performed in this repository.
If implementation convenience conflicts with these rules, the rules take precedence.
---
# 1. Development Goals
Development should always prioritize:
- Deterministic execution
- Evidence quality
- Simplicity
- Maintainability
- Extensibility
- Token efficiency
- Benchmarkability
Avoid unnecessary complexity.
The platform should become more capable by improving deterministic execution rather than increasing AI reasoning.
---
# 2. Architecture is Authoritative
The approved architecture is the source of truth.
Do not modify:
- responsibilities
- dependencies
- ownership
- architectural boundaries
without explicit approval.
Architecture changes require:
- context
- motivation
- trade-off analysis
- impact analysis
Implementation must never change architecture implicitly.
---
# 3. Deterministic Before AI
Whenever deterministic logic can solve a problem, deterministic logic should be preferred.
Examples include:
- intent routing
- target resolution
- evidence planning
- capability selection
- result aggregation
- severity calculation
- threshold evaluation
Do not introduce AI reasoning where deterministic execution is sufficient.
---
# 4. Single Responsibility
Every component owns exactly one responsibility.
| Component | Responsibility |
|------------|----------------|
| Assessment Model | Evidence interpretation |
| Execution Engine | Investigation execution |
| KnowledgeTool | Capability routing |
| Child Tool | Evidence collection |
| Provider | Infrastructure access |
| Environment | Source of Truth |
Responsibilities must never overlap.
---
# 5. Evidence First
Always improve evidence before improving AI.
Preferred order:
```
Better Tool
↓
Better Evidence
↓
Better Assessment
```
Avoid compensating poor evidence with:
- larger prompts
- more iterations
- more AI reasoning
---
# 6. Composite Before Atomic
Prefer exposing complete operational capabilities.
Prefer:
```
assess_machine()
```
instead of requiring multiple independent calls:
```
cpu()
memory()
disk()
network()
service()
```
Composite capabilities reduce:
- token usage
- iterations
- planning complexity
---
# 7. Batch Before Loop
If multiple evidence requests are independent, execute them together.
Prefer:
```
parallel execution
```
instead of:
```
tool
↓
LLM
↓
tool
↓
LLM
```
Minimize investigation iterations.
---
# 8. Stateless Execution
Execution state exists only during a single investigation.
Never persist:
- execution state
- observations
- tool outputs
- runtime context
Only lightweight summarized session memory may remain.
---
# 9. Child Tools
Each Child Tool owns exactly one infrastructure domain.
Child Tools:
- collect evidence
- normalize outputs
- compute deterministic summaries
Child Tools never:
- perform reasoning
- decide investigation flow
- generate recommendations
---
# 10. Providers
Providers communicate with infrastructure only.
Providers never know:
- user intent
- AI
- investigation workflow
- business logic
Providers should exist only when access complexity justifies them.
---
# 11. Coding Principles
Prefer:
- small functions
- explicit naming
- readable code
- deterministic logic
- incremental patches
Avoid unnecessary abstraction.
---
# 12. No Over-Engineering
Do not introduce:
- Factory
- Strategy
- Repository Pattern
- Plugin System
- Event Bus
- Middleware
- Service Locator
unless an actual implementation problem requires them.
---
# 13. Repository First
Before changing code:
1. Understand the repository.
2. Reuse existing implementations.
3. Extend existing abstractions.
4. Avoid duplicate implementations.
Never create parallel solutions.
---
# 14. Backward Compatibility
Do not break:
- public interfaces
- capability outputs
- APIs
- data formats
without explicit approval.
Backward compatibility is the default.
---
# 15. Dependencies
Prefer the Python Standard Library.
Do not introduce external dependencies unless:
- technically justified
- approved
---
# 16. Implementation Mode
Unless explicitly requested otherwise, AI always operates in **Implementation Mode**.
Implementation Mode means:
- implement approved designs
- preserve existing behavior
- avoid unrelated refactoring
- keep patches small
- stop after the sprint
Architecture discussion occurs only when explicitly requested.
---
# 17. Implementation Rules
During implementation:
- modify only the approved scope
- avoid speculative features
- avoid speculative APIs
- avoid speculative workflows
- preserve existing behavior unless required otherwise
Never guess missing requirements.
---
# 18. Verification
Before every commit:
- review implementation
- verify responsibilities
- verify dependencies
- verify architecture boundaries
- run affected tests
- run affected benchmarks when behavior changes
- review git diff
- review git status
Regression must be resolved before committing.
---
# 19. Definition of Done
A sprint is complete only when:
- implementation is complete
- tests pass
- benchmarks pass (when applicable)
- no regressions remain
- architecture remains intact
- repository is clean
- one logical improvement
- one commit
---
# 20. Benchmark-Driven Development
Benchmarks drive platform evolution.
New capabilities should exist because benchmark scenarios require additional evidence.
Do not introduce capabilities simply because they appear useful.
Benchmark quality is more important than implementation quantity.
---
# 21. Capability Metadata
Capability metadata has exactly one source of truth.
Rules:
- Child Tools define capabilities.
- KnowledgeTool aggregates metadata.
- Execution Engine consumes metadata.
- Capability definitions must never be duplicated.
---
# 22. Reporting
Never report planned work as completed.
Completed work must always be verifiable through:
- git diff
- git status
- test results
- benchmark results
Claims without evidence are not considered complete.
---
# 23. Final Principle
Whenever uncertain, choose the simpler solution.
Priority order:
```
Evidence
↓
Deterministic Execution
↓
Architecture
↓
Correctness
↓
Maintainability
↓
Performance
↓
Convenience
```
Simple solutions should always be preferred until benchmark results prove otherwise.
