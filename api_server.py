#!/usr/bin/env python3
"""FastAPI server wrapping the Infrastructure Agent.

Provides REST API endpoints for the Lovable UI to query the agent.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.agent.runtime_factory import create_deterministic_agent

app = FastAPI(title="Infrastructure Agent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global agent instance (created once at startup).
_agent = None


class QueryRequest(BaseModel):
    question: str
    server: str | None = "sv1"
    model: str | None = None


class EvidenceItem(BaseModel):
    capability_name: str
    evidence_name: str
    success: bool
    error: str | None = None
    data: Any = None


class QueryResponse(BaseModel):
    assessment: str
    intent: str = ""
    target: str = ""
    evidence_count: int = 0
    evidence_complete: bool = False
    evidence: list[EvidenceItem] = []


class HealthResponse(BaseModel):
    status: str
    version: str


def _get_agent():
    global _agent
    if _agent is None:
        _agent = create_deterministic_agent(server_name="sv1")
    return _agent


@app.get("/api/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", version="1.0.0")


@app.post("/api/query", response_model=QueryResponse)
def query(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question is required")

    agent = _get_agent()

    try:
        investigation = agent.execute_pipeline_only(req.question)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}")

    try:
        assessment = agent.run(req.question)
    except Exception as exc:
        assessment = f"Assessment error: {exc}"

    evidence_list = []
    for pkg in investigation.evidence:
        evidence_list.append(EvidenceItem(
            capability_name=pkg.capability_name,
            evidence_name=pkg.evidence_name,
            success=pkg.success,
            error=pkg.error if not pkg.success else None,
            data=pkg.data if pkg.success else None,
        ))

    return QueryResponse(
        assessment=assessment,
        intent=investigation.intent.name if investigation.intent else "",
        target=investigation.target or "",
        evidence_count=len(investigation.evidence),
        evidence_complete=investigation.evidence_complete,
        evidence=evidence_list,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
