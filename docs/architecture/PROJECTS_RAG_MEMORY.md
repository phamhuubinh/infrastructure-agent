# Projects, RAG, Context, and Memory

## Project model

A Project is a workspace containing project files/knowledge and multiple chats.
It is intentionally similar to the project concept in modern AI chat products.

```text
Project
├── Files / knowledge
├── Chat A
│   └── chat context
├── Chat B
│   └── chat context
└── Chat C
    └── chat context
```

A Project is primarily a container for knowledge and conversations. It does not
need to own infrastructure connections or credentials unless a future product
requirement makes that useful.

## RAG is part of the agent

Project retrieval is exposed to the agent as a normal READ capability. The
model decides when to retrieve project material.

This enables mixed investigations such as:

```text
live Linux evidence
+ Grafana/Zabbix
+ project runbook retrieval
+ Internet research
-> one model assessment
```

The UI may provide a dedicated Project/files experience, but the reasoning
runtime remains one agent.

## Document isolation

Each document should have its own durable identity and retrieval index/state.
Project retrieval can search across the Project while preserving document
provenance.

Deleting a document must remove its retrievable content. Deleting one Project
must not affect another Project.

## Retrieval design

The retrieval engine should be efficient on a personal/local deployment and
should not require a dedicated GPU embedding/reranking model by default.

A suitable default is:

1. deterministic parsing and chunking;
2. Unicode/Vietnamese-aware normalization;
3. lexical/BM25 retrieval;
4. optional bounded use of the active model for query expansion when useful;
5. deterministic fusion and document balancing;
6. bounded evidence returned to the agent;
7. final reasoning performed by the active model.

The retrieval backend is replaceable. The agent contract should depend on
retrieval results, not a specific index technology.

## Chat memory

Orion does not need a permanent global personal memory for this product.
Memory is primarily scoped to the current chat/session.

To reduce token use, chat context should be layered:

- recent turns retained verbatim within a budget;
- older turns compacted into a bounded summary;
- important structured references retained separately;
- retrieved document contents not copied permanently into the prompt;
- prior evidence stored with identity/time and reintroduced only when useful.

The model should retrieve project content again when it needs exact detail
instead of depending on an old conversational paraphrase.

## Static vs dynamic information

Orion tracks whether an observation is comparatively static or dynamic.

Static examples:

- project documents;
- architecture descriptions;
- stable identifiers;
- historical incident records.

Dynamic examples:

- CPU/RAM/disk state;
- processes and services;
- monitoring metrics;
- deployment/runtime state;
- current software releases;
- current Internet information.

Dynamic observations always keep their observation time. They may be useful as
history, but they must not be silently represented as freshly observed state.

The model decides when fresh evidence is required; the harness preserves enough
metadata for that decision to be possible.
