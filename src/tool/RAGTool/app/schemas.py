from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class IngestResponse(BaseModel):
    project_id: str = "default"
    doc_id: str
    chunk_count: int
    parser_used: str
    warnings: list[str]


class AnalysisModelConfig(BaseModel):
    base_url: str = Field(min_length=1, max_length=2000)
    model: str = Field(min_length=1, max_length=500)
    api_key: str = Field(default="", max_length=4000)
    timeout: float = Field(default=180, ge=1, le=3600)


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    use_hyde: bool = False
    top_k: int = Field(default=5, ge=1, le=20)
    analysis_model: AnalysisModelConfig | None = Field(
        default=None, alias="model_config"
    )


class RetrievedChunkResponse(BaseModel):
    id: str
    text: str
    score: float
    payload: dict


class QueryResponse(BaseModel):
    answer: str
    retrieved: list[RetrievedChunkResponse]


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)


class ProjectDocument(BaseModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    chunk_count: int
    created_at: datetime


class ProjectAnalysis(BaseModel):
    id: str
    query: str
    answer: str
    retrieved: list[RetrievedChunkResponse]
    created_at: datetime


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    documents: list[ProjectDocument]
    analyses: list[ProjectAnalysis]
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]
