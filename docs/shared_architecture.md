# Shared Architecture

## Definition

The **Shared** layer is the common architectural foundation of the
Autonomous Agent.

It defines reusable domain models, contracts, value objects, metadata,
requests, responses, and state definitions that are shared across
multiple architectural components.

The Shared layer does **not** implement behavior. It only defines the
common language used by the architecture.

------------------------------------------------------------------------

## Purpose

The Shared layer exists to eliminate duplicated model definitions and
avoid ownership conflicts between architectural components.

Without a Shared layer, common concepts such as `ExecutionContext`,
`ExecutionSession`, `ExecutionResult`, `Plan`, or `ToolResult` would
incorrectly belong to individual modules even though they are consumed
by multiple layers.

Shared provides a single source of truth for reusable domain
definitions.

------------------------------------------------------------------------

## Responsibilities

The Shared layer owns reusable definitions including:

-   Requests
-   Responses
-   Results
-   Contexts
-   Sessions
-   States
-   Constraints
-   Contracts
-   Metadata
-   Value Objects
-   Enumerations
-   Identifiers
-   Common error definitions

These definitions are immutable whenever possible and contain no
execution logic.

------------------------------------------------------------------------

## Responsibilities Outside the Shared Layer

The Shared layer must never contain:

-   Planning
-   Execution
-   Runtime management
-   Tool execution
-   Capability resolution
-   Verification logic
-   Discovery logic
-   Knowledge processing
-   AI reasoning
-   Business logic
-   Side effects
-   External system interaction

------------------------------------------------------------------------

## Design Principles

-   Single Source of Truth
-   Separation of Concerns
-   Reusability
-   High Cohesion
-   Low Coupling
-   Immutable Models where possible
-   No Business Behavior
-   Replaceable Components

------------------------------------------------------------------------

## Dependency Rules

Every architectural component may depend on the Shared layer.

The Shared layer must never depend on:

-   Agent Core
-   Planner
-   Executor
-   Runtime
-   Capability
-   Tool
-   Verification
-   Discovery
-   Knowledge Model

The dependency graph must always point toward Shared and never away from
it.

------------------------------------------------------------------------

## Relationship with Other Components

### Agent Core

Uses Shared definitions to coordinate communication between
architectural layers.

### Planner

Consumes shared planning models but never owns them.

### Executor

Consumes shared execution models and produces shared execution results.

### Runtime

Consumes shared execution models while managing execution.

### Capability

Consumes shared contracts, requests and results.

### Tool

Consumes shared requests and returns shared structured results.

### Verification

Consumes shared execution results and produces shared verification
results.

### Discovery

Consumes shared observation models and produces shared knowledge
artifacts.

### Knowledge Model

Consumes shared domain objects but remains the owner of persistent
knowledge.

------------------------------------------------------------------------

## Typical Shared Concepts

Examples of concepts that naturally belong to the Shared layer include:

-   ExecutionContext
-   ExecutionSession
-   ExecutionState
-   ExecutionResult
-   ExecutionConstraints
-   Plan
-   Step
-   Goal
-   ToolRequest
-   ToolResult
-   CapabilityRequest
-   CapabilityResult
-   VerificationResult
-   RuntimeMetadata

These are architectural examples only and do not prescribe
implementation details.

------------------------------------------------------------------------

## Architectural Constraints

The Shared layer:

-   contains only reusable definitions;
-   contains no business behavior;
-   contains no execution orchestration;
-   contains no planning logic;
-   contains no reasoning;
-   contains no infrastructure implementation.

------------------------------------------------------------------------

## Summary

The Shared layer establishes a common architectural vocabulary for the
Autonomous Agent. By centralizing reusable models and contracts, it
reduces coupling, prevents duplicated definitions, and allows each
architectural component to focus solely on its own responsibilities
while communicating through shared, stable abstractions.
