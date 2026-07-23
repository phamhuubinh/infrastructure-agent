# Architecture Diagrams

> Visual reference for Orion's system architecture and data flows.

---

## Pipeline Execution Flow

```mermaid
sequenceDiagram
    participant User
    participant Agent as DeterministicAgent
    participant IR as IntentResolver
    participant TR as TargetResolver
    participant EP as EvidencePlanner
    participant CR as CapabilityResolver
    participant EPl as ExecutionPlanner
    participant EG as ExecutionGraphBuilder
    participant ER as ExecutionRuntime
    participant KT as KnowledgeTool
    participant CT as ChildTool
    participant AM as AssessmentModel

    User->>Agent: "Check disk on webserver01"
    Agent->>IR: resolve(user_request)
    IR-->>Agent: intent=disk_usage, confidence=0.95
    Agent->>TR: resolve(request)
    TR-->>Agent: target=webserver01
    Agent->>EP: plan(request)
    EP-->>Agent: evidence_requirements=[disk]
    Agent->>CR: resolve(request)
    CR-->>Agent: capability_refs=[disk@webserver01]
    Agent->>EPl: plan(request)
    EPl-->>Agent: execution_plan
    Agent->>EG: build(plan)
    EG-->>Agent: execution_graph
    Agent->>ER: execute(graph)
    ER->>KT: execute(disk, webserver01)
    KT->>CT: dispatch to LinuxTool
    CT-->>KT: ToolResult(disk data)
    KT-->>ER: evidence_package
    ER-->>Agent: collected_evidence
    Agent->>AM: assess(evidence)
    AM-->>Agent: "Disk healthy: 45% used"
    Agent-->>User: assessment response
```

---

## Component Architecture

```mermaid
graph TB
    subgraph "Entry Points"
        CLI[CLI main.py]
        API[FastAPI backend]
        UI[React Web UI]
        Desktop[Electron Desktop]
    end

    subgraph "Agent Layer"
        DA[DeterministicAgent]
        RF[RuntimeFactory]
        CS[ConversationStore]
    end

    subgraph "Pipeline"
        IR[IntentResolver]
        TR[TargetResolver]
        EP[EvidencePlanner]
        CR2[CapabilityResolver]
        EPl2[ExecutionPlanner]
        EG2[ExecutionGraph]
        ER2[ExecutionRuntime]
        EC[EvidenceCompleteness]
        EM[EvidenceMerge]
    end

    subgraph "Tools"
        KT[KnowledgeTool]
        LT[LinuxTool]
        GT[GrafanaTool]
        ZT[ZabbixTool]
        IT[InternetTool]
        KBT[KnowledgeBaseTool]
    end

    subgraph "Assessment"
        AM[AssessmentModelAdapter]
        LLM[LLMAssessmentAdapter]
        Mock[MockAssessmentAdapter]
        PB[PromptBuilder]
    end

    subgraph "Infrastructure"
        DB[(PostgreSQL)]
        RAG[RAG Service]
        Proxy[Nginx Reverse Proxy]
    end

    CLI --> RF
    API --> DA
    UI --> API
    Desktop --> UI

    DA --> IR --> TR --> EP --> CR2 --> EPl2 --> EG2 --> ER2
    ER2 --> KT
    KT --> LT
    KT --> GT
    KT --> ZT
    KT --> IT
    KT --> KBT

    DA --> AM
    AM --> LLM
    AM --> Mock

    API --> DB
    KBT --> RAG
    API --> Proxy
```

---

## Tool Interaction Diagram

```mermaid
graph LR
    subgraph "KnowledgeTool (Single Entry Point)"
        KT2[dispatch]
    end

    subgraph "Child Tools"
        LT2[LinuxTool<br/>SSH Execution]
        GT2[GrafanaTool<br/>HTTP API]
        ZT2[ZabbixTool<br/>JSON-RPC]
        IT2[InternetTool<br/>HTTP Fetch]
        KBT2[KnowledgeBaseTool<br/>RAG Proxy]
    end

    subgraph "External"
        SSH[Target Servers<br/>SSH:22]
        Grafana[Grafana<br/>HTTPS:443]
        Zabbix[Zabbix<br/>HTTPS:443]
        Web[Internet<br/>HTTPS]
        RAG2[RAG Service<br/>HTTP:8000]
    end

    KT2 -->|capability: disk| LT2
    KT2 -->|capability: dashboards| GT2
    KT2 -->|capability: hosts| ZT2
    KT2 -->|capability: web_fetch| IT2
    KT2 -->|capability: knowledge_search| KBT2

    LT2 --> SSH
    GT2 --> Grafana
    ZT2 --> Zabbix
    IT2 --> Web
    KBT2 --> RAG2
```

---

## Deployment Architecture (Local Docker Compose)

```mermaid
graph TB
    subgraph "Host Machine"
        Browser[Browser<br/>https://localhost]
        Terminal[Terminal<br/>orion run]
    end

    subgraph "Docker Compose"
        Nginx[Nginx<br/>:443 → :61888]
        API2[FastAPI API<br/>:61888]
        UI2[React UI<br/>:5173]
        DB2[(PostgreSQL<br/>:5432)]
        RAG3[RAG Service<br/>:8000]
    end

    Browser -->|HTTPS| Nginx
    Nginx -->|proxy_pass| API2
    Nginx -->|proxy_pass| UI2
    Terminal -->|CLI| API2
    API2 --> DB2
    API2 --> RAG3
```

---

## Data Model

```mermaid
erDiagram
    InvestigationRequest {
        string raw_request
        string intent_name
        float confidence
        string target
        list evidence_requirements
        list capability_references
        list evidence_packages
        bool evidence_complete
    }

    EvidencePackage {
        string evidence_name
        string target
        bool success
        dict data
        string error
        float elapsed_ms
    }

    AssessmentRequest {
        string intent
        string target
        list evidence_items
        string prompt
    }

    ConversationStore {
        string session_id
        list messages
        string summary
        int threshold
    }

    InvestigationRequest ||--o{ EvidencePackage : collects
    InvestigationRequest ||--|| AssessmentRequest : produces
```

---

> **Last updated:** 2026-07-23