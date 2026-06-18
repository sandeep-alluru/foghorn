"""FastAPI REST wrapper for foghorn.

Start:   uvicorn foghorn.api:app --reload
Install: pip install "foghorn[api]"
"""

from __future__ import annotations

from typing import Any

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field
except ImportError as exc:
    raise ImportError("API server requires: pip install 'foghorn[api]'") from exc

from foghorn import __version__
from foghorn.repo import WorldRepo

app = FastAPI(
    title="foghorn API",
    description="Decision staleness alerts for AI agents.",
    version=__version__,
    license_info={
        "name": "MIT",
        "url": "https://github.com/sandeep-alluru/foghorn/blob/main/LICENSE",
    },
)


class FactRequest(BaseModel):
    """Request body for POST /fact."""

    subject: str = Field(..., description="The entity this fact is about.")
    predicate: str = Field(..., description="The relationship being asserted.")
    object: str = Field(..., description="The value of the assertion.")
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    db: str = Field(".foghorn/world.db")


class DecideRequest(BaseModel):
    """Request body for POST /decide."""

    label: str = Field(..., description="Short slug for this decision.")
    content: str = Field(..., description="Full reasoning text.")
    depends_on: list[str] = Field(default_factory=list)
    db: str = Field(".foghorn/world.db")


class CommitRequest(BaseModel):
    """Request body for POST /commit."""

    message: str = Field(..., description="Commit message.")
    db: str = Field(".foghorn/world.db")


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    status: str
    version: str


@app.get("/health", response_model=HealthResponse)
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "version": __version__}


@app.post("/fact")
async def add_fact(request: FactRequest) -> Any:
    """Stage a new fact triple."""
    with WorldRepo.init(request.db) as repo:
        f = repo.add_fact(request.subject, request.predicate, request.object, request.confidence)
        return f.to_dict()


@app.post("/decide")
async def add_decision(request: DecideRequest) -> Any:
    """Stage a new decision."""
    with WorldRepo.init(request.db) as repo:
        d = repo.decide(request.label, request.content, request.depends_on)
        return d.to_dict()


@app.post("/commit")
async def commit(request: CommitRequest) -> Any:
    """Commit all staged facts and decisions."""
    with WorldRepo.init(request.db) as repo:
        try:
            wc = repo.commit(request.message)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return wc.to_dict()


@app.get("/stale")
async def stale(db: str = ".foghorn/world.db") -> Any:
    """Return staleness alerts for the current HEAD."""
    with WorldRepo.init(db) as repo:
        alerts = repo.stale()
        return {
            "has_stale": len(alerts) > 0,
            "stale_count": len(alerts),
            "alerts": [a.to_dict() for a in alerts],
        }


@app.get("/log")
async def log(db: str = ".foghorn/world.db") -> Any:
    """Return the commit log."""
    with WorldRepo.init(db) as repo:
        commits = repo.log()
        return {"commits": [wc.to_dict() for wc in commits]}
