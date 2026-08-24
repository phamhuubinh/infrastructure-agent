# Orion product specification

## Purpose

Orion is an infrastructure investigation and operations agent. An operator can ask natural-language questions or request infrastructure actions. A language model reasons about the request and proposes calls to reviewed capabilities; a deterministic harness controls what can actually execute.

## Primary users

- infrastructure and platform engineers;
- SRE and operations teams;
- security-conscious teams that want LLM assistance without granting a model arbitrary shell/network/credential authority.

## Core user journeys

### Investigate

The operator asks why a host, service, dashboard, alert, or application is unhealthy. Orion searches available capabilities, invokes read-only tools, correlates evidence, and explains what it found.

### Execute a reviewed change

The operator asks for a mutation such as restarting a service. Orion proposes the exact reviewed capability with exact target and arguments. The harness validates authority and permission, requests approval when policy requires it, executes using least privilege, verifies evidence, and reports the result.

### Use project knowledge

The operator attaches or indexes architecture/runbook material. Orion retrieves relevant project evidence through bounded retrieval tools; project documents do not automatically become execution instructions.

### Current information

When current external information is required, Orion uses a reviewed internet capability with explicit network/source policy and evidence provenance.

## Product principles

- Powerful inside explicit boundaries.
- Low-friction for safe reads; deliberate for risky writes.
- Model-native interaction, harness-native control.
- No hidden semantic router that guesses tool/target authority from language.
- Explanations are useful, but evidence and action state remain inspectable independently of prose.
- A failed or unavailable tool must never be presented as successful.

## Non-goals

- unrestricted remote shell assistant;
- general browser automation platform;
- automatic root-level infrastructure administrator;
- multi-agent orchestration framework;
- model-owned authorization or policy engine;
- transparent compatibility with every previous Orion internal API.

## Success criteria

A competent model should be able to solve common read-only tasks with a small number of natural tool calls. Invalid or malicious model calls must fail closed. High-risk actions must be controllable by policy and approval. Operators must be able to audit what was proposed, authorized, executed, and evidenced.
