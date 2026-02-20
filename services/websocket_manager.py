"""WebSocket connection manager for real-time pipeline updates."""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import WebSocket

from config.logging_config import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """Manages WebSocket connections keyed by run_id.
    
    Each pipeline run has a unique run_id. Clients connect with that
    run_id and receive real-time step updates, logs, and results.
    """

    def __init__(self) -> None:
        # run_id  →  list of active WebSocket connections
        self._connections: Dict[str, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, run_id: str) -> None:
        """Accept a WebSocket and register it under *run_id*."""
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(run_id, []).append(websocket)
        logger.info("WebSocket connected", run_id=run_id)

    async def disconnect(self, websocket: WebSocket, run_id: str) -> None:
        """Remove a WebSocket from its run_id group."""
        async with self._lock:
            conns = self._connections.get(run_id, [])
            if websocket in conns:
                conns.remove(websocket)
            if not conns:
                self._connections.pop(run_id, None)
        logger.info("WebSocket disconnected", run_id=run_id)

    async def broadcast(self, run_id: str, message: Dict[str, Any]) -> None:
        """Send a JSON message to every client watching *run_id*."""
        message.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        payload = json.dumps(message, default=str)

        async with self._lock:
            conns = list(self._connections.get(run_id, []))

        dead: List[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        # Prune dead connections
        if dead:
            async with self._lock:
                for ws in dead:
                    conns = self._connections.get(run_id, [])
                    if ws in conns:
                        conns.remove(ws)

    # ── Convenience helpers used by pipeline nodes ──────────
    #
    # IMPORTANT:  Every message uses a consistent envelope that the
    #   React frontend expects:
    #       { type, data: { ... }, timestamp }
    #   The frontend reads  msg.type  and  msg.data.*  — never top-level fields.

    async def send_step_update(
        self,
        run_id: str,
        step: str,
        status: str = "running",
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Broadcast a pipeline step update.

        Frontend reads: data.step, data.label, data.status,
                        data.test_framework, data.branch_name  (optional)
        """
        msg_data: Dict[str, Any] = {
            "step": step,
            "status": status,
            **(data or {}),
        }
        # Auto-generate a human-readable label if not already present
        if "label" not in msg_data:
            msg_data["label"] = step.replace("_", " ").title()
        await self.broadcast(run_id, {
            "type": "step_update",
            "data": msg_data,
        })

    async def send_log(
        self, run_id: str, agent: str, level: str, message: str,
    ) -> None:
        """Broadcast a single log line.

        Frontend reads: data.message
        """
        await self.broadcast(run_id, {
            "type": "log",
            "data": {"agent": agent, "level": level, "message": message},
        })

    async def send_failure(
        self,
        run_id: str,
        file: str,
        bug_type: str,
        line: int,
        message: str,
        test_name: str = "",
    ) -> None:
        """Broadcast a detected failure.

        Frontend reads: data.file, data.bug_type, data.line,
                        data.message, data.test_name
        """
        await self.broadcast(run_id, {
            "type": "failure",
            "data": {
                "file": file,
                "bug_type": bug_type,
                "line": line,
                "message": message,
                "test_name": test_name,
            },
        })

    async def send_fix(
        self,
        run_id: str,
        file: str,
        bug_type: str,
        line: int,
        diff: str,
        status: str,
        *,
        summary: str = "",
        commit_message: str = "",
        confidence: float = 0.85,
        root_cause: str = "",
        iteration: int = 0,
    ) -> None:
        """Broadcast a fix attempt.

        Frontend reads: data.file, data.bug_type, data.line, data.diff,
                        data.status, data.summary, data.commit_message,
                        data.confidence, data.root_cause, data.iteration
        """
        await self.broadcast(run_id, {
            "type": "fix",
            "data": {
                "file": file,
                "bug_type": bug_type,
                "line": line,
                "diff": diff,
                "status": status,
                "summary": summary,
                "commit_message": commit_message,
                "confidence": confidence,
                "root_cause": root_cause,
                "iteration": iteration,
            },
        })

    async def send_iteration(
        self,
        run_id: str,
        iteration: int,
        max_retries: int,
        passed: bool,
        failures_remaining: int,
        *,
        tests_run: int = 0,
        tests_passed: int = 0,
        tests_failed: int = 0,
        fixes_applied: int = 0,
    ) -> None:
        """Broadcast an iteration summary.

        Frontend reads: data.iteration, data.max_retries, data.passed,
                        data.tests_run, data.tests_passed, data.tests_failed,
                        data.fixes_applied
        """
        await self.broadcast(run_id, {
            "type": "iteration",
            "data": {
                "iteration": iteration,
                "max_retries": max_retries,
                "passed": passed,
                "failures_remaining": failures_remaining,
                "tests_run": tests_run,
                "tests_passed": tests_passed,
                "tests_failed": tests_failed,
                "fixes_applied": fixes_applied,
            },
        })

    async def send_result(self, run_id: str, results: Dict[str, Any]) -> None:
        """Broadcast the final results.json payload.

        Flattens the nested ``score`` object so the frontend can read
        ``data.score`` (number), ``data.speed_bonus``, ``data.efficiency_penalty``
        directly.  Also maps ``final_status`` → ``status`` (lowercase).
        """
        score_obj = results.get("score", {})
        flat: Dict[str, Any] = {
            **results,
            # Map final_status → status (frontend RunStatus: idle|running|passed|failed)
            "status": results.get("final_status", "FAILED").lower(),
            # Flatten score object into top-level data fields
            "score": score_obj.get("final", 0) if isinstance(score_obj, dict) else score_obj,
            "speed_bonus": score_obj.get("speed_bonus", 0) if isinstance(score_obj, dict) else 0,
            "efficiency_penalty": score_obj.get("efficiency_penalty", 0) if isinstance(score_obj, dict) else 0,
        }
        await self.broadcast(run_id, {
            "type": "result",
            "data": flat,
        })


    async def send_error(
        self, run_id: str, message: str, details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Broadcast an error event.

        Frontend reads: data.message
        """
        await self.broadcast(run_id, {
            "type": "error",
            "data": {"message": message, **(details or {})},
        })


# Singleton used across the application
manager = ConnectionManager()
