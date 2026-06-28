# Coding Standards

## Purpose

This document defines the coding standards for the Autonomous Agent
project.

All source code must follow these rules unless an architecture document
explicitly specifies otherwise.

## 1. Source of Truth

-   The `docs/` directory is the only Source of Truth.
-   Code must conform to the architecture documents.
-   Do not change architecture during implementation unless a real
    architectural issue is discovered.

## 2. Python Version

-   Python 3.12+

## 3. Project Structure

-   `src/`
-   `tests/`
-   `docs/`

Production code belongs in `src/`.

## 4. Naming Conventions

-   Classes: PascalCase
-   Functions: snake_case
-   Variables: snake_case
-   Constants: UPPER_CASE

## 5. Type Hints

Use type hints for all public APIs. Avoid `Any` whenever possible.

## 6. Data Models

Prefer `@dataclass`. Use immutable models (`frozen=True`) where
appropriate.

## 7. Enumerations

Use `Enum` unless the project explicitly adopts `StrEnum`.

## 8. Imports

Order: 1. Standard Library 2. Third-party Packages 3. Project Modules

## 9. Documentation

Use concise Google-style docstrings when they add value.

## 10. Logging

Use the `logging` module. Do not use `print()` for application logging.

## 11. Exceptions

Catch specific exceptions. Avoid bare `except:`.

## 12. Formatting

Recommended tools: - Ruff - Black

## 13. Testing

Use pytest. Mirror the source structure inside `tests/`.

## 14. Git Workflow

One commit = one logical change.

## 15. AI Development Rules

-   Read only the required architecture documents.
-   Modify only the requested files.
-   Do not change architecture.
-   Do not create unrelated files.
-   Do not introduce TODOs or placeholders.
-   Stop after completing the requested task.

## 16. Review Workflow

1.  Read architecture.
2.  Plan.
3.  Implement one logical unit.
4.  Review.
5.  Test.
6.  Commit.

## Summary

These standards ensure a consistent, maintainable, and
architecture-driven codebase.

## Architecture Compliance

Architecture documents and model specification documents are the only Source of Truth.

AI implementations must never invent:

- fields
- enums
- model relationships
- helper structures

If required information is missing, implementation must stop and request an architecture update.

Implementation always follows the model specification exactly.
