# Coding Standards
---
# Purpose
This document defines the coding standards for the Autonomous Agent project.
All implementations shall follow these standards unless an Architecture document explicitly specifies otherwise.
Architecture documents remain the single source of truth.
---
# Documentation Rules
The documentation hierarchy is:
```text
Architecture
        ↓
Component Specification
        ↓
API Specification
        ↓
Model Specification
        ↓
Implementation
```
Implementation must always follow the documentation hierarchy.
Architecture changes shall never be introduced during implementation.
---
# Architecture Compliance
Architecture documents and Model Specifications are the only source of truth.
Implementations must never invent:
* models;
* fields;
* enums;
* relationships;
* helper abstractions;
* public APIs.
If required information is missing:
* stop implementation;
* update the specification;
* implement only after the specification is complete.
---
# Python Standards
## Python Version
* Python 3.12+
## Project Structure
```text
src/
tests/
docs/
```
Production code belongs only in `src/`.
---
# Naming
* Classes: PascalCase
* Functions: snake_case
* Variables: snake_case
* Constants: UPPER_CASE
---
# Type Hints
All public APIs shall use type hints.
Prefer Python 3.12 built-in generics:
* dict
* list
* tuple
* set
Avoid:
* Dict
* List
* Tuple
* Set
* Any (unless unavoidable)
---
# Data Models
Prefer immutable dataclasses.
Use:
```python
@dataclass(frozen=True, slots=True)
```
where appropriate.
---
# Enumerations
Use `Enum` unless another enumeration type is explicitly required by the architecture.
---
# Imports
Import order:
1. Standard Library
2. Third-party Packages
3. Project Modules
Project imports must never use:
```text
src.*
```
Imports must satisfy:
* no unused imports;
* no unresolved names.
---
# Documentation
Use concise docstrings only where they improve readability.
Avoid redundant comments.
---
# Logging
Use the `logging` module.
Never use `print()` for application logging.
---
# Exceptions
Catch only specific exceptions.
Never use:
```python
except:
```
---
# Formatting
Recommended tools:
* Ruff
* Black
---
# Testing
Use `pytest`.
Mirror the source structure inside `tests/`.
---
# Git Rules
One logical unit equals one commit.
Never mix unrelated architectural changes in the same commit.
Review before committing.
---
# AI Development Rules
AI implementations shall:
* read only the required documents;
* modify only the requested files;
* preserve public APIs;
* preserve architecture;
* avoid placeholder implementations;
* avoid TODO/FIXME markers;
* stop after completing the requested task.
Runtime components must never invent shared models.
---
# Development Workflow
Every implementation follows:
```text
Architecture
        ↓
Component Specification
        ↓
API Specification
        ↓
Model Specification (if required)
        ↓
Implementation
        ↓
Review
        ↓
Test
        ↓
Commit
```
Implementation always follows the specification.
Never modify the specification to match incorrect code.
