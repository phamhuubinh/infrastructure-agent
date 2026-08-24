# Configuration

## Base environment

The repository includes `.env.example` with the current base settings:

```text
API_PORT
ORION_API_KEY
DATABASE_URL
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_DB
```

Copy only when needed; the installer normally creates `.env`.

## Integration configuration

Additional tool/model/RAG settings may be defined by the current implementation and deployment.

Configuration categories:

```text
Model
Embeddings
Reranker
RAG/vector store
Internet
Linux/SSH targets
Grafana
Zabbix
Persistence
UI/API
```

## Principle

Configuration determines whether a registered integration can initialize.

It does not create a per-chat tool selection system.

Once a tool is registered/configured successfully, the model may use it automatically in both Chat and Project.

## Secrets

Keep secrets in `.env`, secret files, or an appropriate local secret mechanism. Never put credentials into project documents or prompt templates as a configuration strategy.
