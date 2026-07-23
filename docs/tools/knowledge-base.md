# Knowledge Base Tool

> RAG-powered document search and retrieval tool.

## Overview

The Knowledge Base Tool queries a RAG (Retrieval-Augmented Generation) microservice to search indexed documents and return relevant chunks. It supports semantic search, query expansion, reranking, and graph-based retrieval.

## Capabilities

| Capability | Description |
|------------|-------------|
| `knowledge_search` | Search indexed documents by semantic similarity |
| `knowledge_ingest` | Index a document for future retrieval |
| `knowledge_health` | Check RAG service health |

## Usage Examples

### Via CLI

```bash
orion run
> Search knowledge base for Kubernetes best practices
```

### Via API

```bash
# Search documents
curl -X POST http://localhost:61888/api/knowledge/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Kubernetes pod security policies", "top_k": 5}'

# Health check
curl http://localhost:61888/api/knowledge/health
```

### Python

```python
from src.tool.knowledge_base_tool import KnowledgeBaseTool

tool = KnowledgeBaseTool(rag_service_url="http://localhost:8000")
result = tool.execute({
    "capability": "knowledge_search",
    "query": "nginx configuration best practices",
    "top_k": 5,
})
print(result.data)
```

## Architecture

The Knowledge Base Tool delegates to a separate RAG microservice (`src/tool/RAGTool/`) that provides:

- **Embedding**: Qwen3, BGE-M3, compatible providers
- **Vector Store**: In-memory, Qdrant
- **Chunking**: Hierarchical semantic chunking with heading-aware splitting
- **Query Expansion**: HyDE (Hypothetical Document Embeddings)
- **Reranking**: BGE Reranker
- **GraphRAG/LightRAG**: Entity-relationship graph indexing
- **OCR**: PaddleOCR for image-based documents
- **Parsers**: Docling, Marker, MinerU, PyPDF

## Configuration

The RAG service URL is configured on startup:

```bash
export ORION_RAG_SERVICE_URL="http://localhost:8000"
```

Secrets for LLM-based components (HyDE, GraphRAG) are stored in `config/secrets.local.json`:

```json
{
  "rag_llm": {
    "base_url": "https://llm.example.com/v1",
    "api_token": "..."
  }
}