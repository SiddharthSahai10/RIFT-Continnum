"""POST /run-agent — main entry-point for the hackathon pipeline."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field, field_validator

from config.logging_config import get_logger
from services.langgraph_pipeline import make_branch_name, run_pipeline
from services.websocket_manager import manager as ws

router = APIRouter()
logger = get_logger(__name__)


# ── Request / Response schemas ──────────────────────────────

class RunAgentRequest(BaseModel):
    repository_url: str = Field(..., min_length=10, description="GitHub HTTPS URL")
    team_name: str = Field(..., min_length=1, max_length=100)
    leader_name: str = Field(..., min_length=1, max_length=100)

    @field_validator("repository_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("https://github.com/"):
            raise ValueError("Only GitHub HTTPS URLs are accepted")
        # Strip trailing .git
        if v.endswith(".git"):
            v = v[:-4]
        return v


class RunAgentResponse(BaseModel):
    run_id: str
    status: str
    branch_name: str
    ws_url: str
    message: str


class RunResultResponse(BaseModel):
    run_id: str
    results: Dict[str, Any]


# ── In-memory run tracker (no Redis / Celery) ──────────────

_active_runs: Dict[str, Dict[str, Any]] = {}


# ── Endpoints ───────────────────────────────────────────────

@router.post("/run-agent", response_model=RunAgentResponse, status_code=202)
async def run_agent(
    body: RunAgentRequest,
    background_tasks: BackgroundTasks,
):
    """Start the autonomous CI/CD healing pipeline.

    Accepts a GitHub repo URL, team name, and leader name.
    Returns immediately with a run_id; progress is streamed over WebSocket.
    """
    run_id = str(uuid4())
    branch_name = make_branch_name(body.team_name, body.leader_name)

    logger.info(
        "Starting run-agent",
        run_id=run_id,
        repo=body.repository_url,
        branch=branch_name,
    )

    _active_runs[run_id] = {
        "status": "started",
        "repository_url": body.repository_url,
        "team_name": body.team_name,
        "leader_name": body.leader_name,
        "branch_name": branch_name,
        "results": None,
    }

    # Fire-and-forget background task (no Celery, no Redis)
    background_tasks.add_task(
        _execute_pipeline,
        run_id,
        body.repository_url,
        body.team_name,
        body.leader_name,
    )

    return RunAgentResponse(
        run_id=run_id,
        status="started",
        branch_name=branch_name,
        ws_url=f"/ws/{run_id}",
        message="Pipeline started — connect to ws_url for real-time updates",
    )


@router.get("/run-agent/{run_id}", response_model=RunResultResponse)
async def get_run_result(run_id: str):
    """Poll for the final results of a pipeline run."""
    entry = _active_runs.get(run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Run not found")

    return RunResultResponse(
        run_id=run_id,
        results=entry.get("results") or {"status": entry["status"]},
    )


@router.get("/run-agent/{run_id}/results.json")
async def get_run_results_json(run_id: str):
    """Return the results.json for a pipeline run (matches hackathon spec)."""
    entry = _active_runs.get(run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Run not found")

    results = entry.get("results")
    if not results:
        raise HTTPException(status_code=202, detail="Run still in progress")

    return results


@router.get("/runs")
async def list_runs():
    """List all active / completed pipeline runs."""
    return [
        {
            "run_id": rid,
            "status": info.get("status", "unknown"),
            "repository_url": info.get("repository_url"),
            "team_name": info.get("team_name"),
            "branch_name": info.get("branch_name"),
        }
        for rid, info in _active_runs.items()
    ]


# ── Background worker ──────────────────────────────────────

async def _execute_pipeline(
    run_id: str,
    repository_url: str,
    team_name: str,
    leader_name: str,
) -> None:
    """Execute the LangGraph pipeline in the background."""
    try:
        _active_runs[run_id]["status"] = "running"
        results = await run_pipeline(
            repository_url=repository_url,
            team_name=team_name,
            leader_name=leader_name,
            run_id=run_id,
        )
        _active_runs[run_id]["status"] = results.get("final_status", "COMPLETED")
        _active_runs[run_id]["results"] = results
    except Exception as exc:
        logger.exception("Pipeline background task failed", run_id=run_id, error=str(exc))
        _active_runs[run_id]["status"] = "FAILED"
        _active_runs[run_id]["results"] = {"error": str(exc)[:500], "final_status": "FAILED"}
        await ws.send_error(run_id, str(exc)[:300])
        await ws.send_step_update(run_id, "failed", "failed", {"error": str(exc)[:300]})
