# ADR-0003 — Project Knowledge Is an Agent Capability

**Status:** Accepted

## Decision

A Project contains files/knowledge and multiple chats. Each chat has its own
bounded conversational context. Project knowledge is retrievable by chats in
that Project through a normal READ capability.

RAG is not a separate agent mode. The UI may provide a dedicated Project/files
experience because document work is a primary Orion use case.

## Consequence

The agent can combine project knowledge with infrastructure and Internet
evidence in one reasoning loop while preserving project/document isolation.
