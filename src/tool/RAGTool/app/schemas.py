from __future__ import annotations

from pydantic import BaseModel


class IngestResponse(BaseModel):
    doc_id: str
    chunk_count: int
    parser_used: str
    warnings: list[str]


class QueryRequest(BaseModel):
    query: str
    use_hyde: bool = False
    top_k: int = 5


class RetrievedChunkResponse(BaseModel):
    id: str
    text: str
    score: float
    payload: dict


class QueryResponse(BaseModel):
    answer: str
    retrieved: list[RetrievedChunkResponse]
