# Product Definition

## What Orion is

Orion is a personal AI agent for project knowledge and infrastructure work.
The intended experience is closer to a capable modern AI agent than to a
command router: the user describes the goal in normal language, the model
chooses how to solve it, and Orion supplies safe access to tools and evidence.

The two primary product goals are:

### Project knowledge and document work

Orion should reduce the amount of manual work required to understand and create
project material. A Project contains files and multiple chats. The model can
retrieve relevant project material when useful and combine it with the current
conversation.

Typical requests include:

- explain architecture or requirements from project files;
- draft or review project documentation;
- compare a proposed change with existing project material;
- find relevant prior decisions or incidents;
- answer questions grounded in uploaded documents.

### Infrastructure assessment

Orion should investigate infrastructure, assess what is happening, and propose
the best practical course of action.

Typical requests include:

- inspect CPU, memory, disk, processes, services, logs, and networking;
- compare observations from Linux, Grafana, and Zabbix;
- diagnose why a system is slow or unhealthy;
- use project runbooks together with live evidence;
- research current external information when useful;
- recommend what should be changed and, when WRITE permission is enabled,
  perform approved changes.

## One agent, many capabilities

The user should not need to choose an "infra mode", "RAG mode", "Internet
mode", or "calculator mode". The model decides whether any capability is
needed.

A request may combine multiple capability families in one reasoning loop. For
example:

```text
project knowledge -> Linux -> Grafana -> Internet -> reasoning -> answer
```

The agent remains one continuous conversation.

## User intent vs execution authority

The user describes a goal. The model interprets the goal and proposes the next
step. Orion validates whether that proposed step exists, is allowed, and can be
executed safely.

The model may be wrong. A wrong model decision must be able to cause a rejected
action, clarification, or poor answer, but it must not widen execution
authority.

## User-visible autonomy

The product exposes three practical execution modes:

| Mode | Read actions | Write actions |
|---|---|---|
| READ | automatic | blocked |
| RW + ASK | automatic | approval required |
| RW + FULL | automatic | automatic |

The mode controls execution authority, not reasoning. The model can still
recommend a write in READ mode; Orion simply cannot execute it.

## Dynamic reality

Infrastructure and current external information change frequently. Orion must
not treat an old observation as current merely because it exists in chat
history.

Project documents may be comparatively static, while CPU load, service state,
monitoring metrics, current versions, and Internet information are dynamic.
The evidence system records time and provenance so the model can decide when to
re-read dynamic information.

## Product non-goals

The architecture does not require Orion to become a paid multi-tenant SaaS
product. It is optimized for a personal/local deployment and can stay simple
where product-scale complexity provides no benefit.

The architecture also does not require every possible future tool to exist now.
It requires only that adding a new tool later is straightforward.
