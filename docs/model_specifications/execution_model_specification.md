# Execution Models

## Purpose

This document defines the shared execution models used by the Runtime,
Executor and Verification layers.

These definitions are the implementation Source of Truth.

## ExecutionState

Enum values:

-   CREATED
-   READY
-   RUNNING
-   COMPLETED
-   FAILED
-   CANCELLED
-   TIMEOUT

## ExecutionContext

Lifetime: one execution.

  Field          Type
  -------------- ------------------
  execution_id   str
  parameters     dict\[str, Any\]
  metadata       dict\[str, Any\]

Immutable.

## ExecutionSession

Groups one or more executions.

  Field           Type
  --------------- -------------------
  session_id      str
  execution_ids   tuple\[str, ...\]
  created_at      datetime
  state           ExecutionState
  metadata        dict\[str, Any\]

Immutable.

## ExecutionConstraints

  Field             Type
  ----------------- ------
  timeout_seconds   int
  cancellable       bool
  retry_limit       int

Immutable.

## RuntimeMetadata

  Field             Type
  ----------------- ----------
  runtime_version   str
  started_at        datetime
  finished_at       datetime
  duration_ms       int

Immutable.

## ExecutionResult

  Field          Type
  -------------- -----------------
  execution_id   str
  state          ExecutionState
  output         Any
  error          str
  metadata       RuntimeMetadata

Immutable.
