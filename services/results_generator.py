"""Generate the results.json artefact required by the hackathon spec."""

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.logging_config import get_logger
from config.settings import get_settings

logger = get_logger(__name__)
settings = get_settings()


def calculate_score(
    total_time_seconds: float,
    total_commits: int,
    total_failures: int,
    total_fixes: int,
) -> Dict[str, Any]:
    """Calculate the hackathon score.

    Scoring rules:
        Base score      : 100
        Speed bonus     : +10  if total time < 5 minutes
        Efficiency penalty : -2  per commit over 20

    Returns:
        Dict with base, speed_bonus, efficiency_penalty, final
    """
    base = 100
    speed_bonus = 10 if total_time_seconds < 300 else 0
    extra_commits = max(0, total_commits - 20)
    efficiency_penalty = extra_commits * 2
    final = max(0, base + speed_bonus - efficiency_penalty)

    return {
        "base": base,
        "speed_bonus": speed_bonus,
        "efficiency_penalty": efficiency_penalty,
        "total_commits": total_commits,
        "final": final,
    }


def build_results_json(
    *,
    repository: str,
    team_name: str,
    leader_name: str,
    branch_name: str,
    total_failures: int,
    total_fixes: int,
    iterations_used: int,
    max_iterations: int,
    final_status: str,           # "PASSED" or "FAILED"
    total_time_seconds: float,
    total_commits: int,
    fixes: List[Dict[str, Any]],
    timeline: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build the results.json payload.

    Args:
        (see parameter names – they map 1-to-1 to the spec)

    Returns:
        Complete results dictionary
    """
    score = calculate_score(total_time_seconds, total_commits, total_failures, total_fixes)

    return {
        "repository": repository,
        "team_name": team_name,
        "leader_name": leader_name,
        "branch_name": branch_name,
        "total_failures": total_failures,
        "total_fixes": total_fixes,
        "iterations_used": iterations_used,
        "max_iterations": max_iterations,
        "final_status": final_status,
        "total_time": _format_duration_human(total_time_seconds),
        "total_time_seconds": round(total_time_seconds, 2),
        "score": score,
        "fixes": fixes,
        "timeline": timeline or [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def save_results_json(
    results: Dict[str, Any],
    run_id: str,
    repo_path: Optional[str] = None,
) -> str:
    """Write results.json to disk.

    Saves two copies:
        1. <RESULTS_DIR>/<run_id>/results.json
        2. <repo_path>/results.json  (if repo_path given)

    Returns:
        Path of the primary results.json file
    """
    results_dir = Path(settings.RESULTS_DIR) / run_id
    results_dir.mkdir(parents=True, exist_ok=True)
    primary_path = results_dir / "results.json"

    payload = json.dumps(results, indent=2, default=str)

    primary_path.write_text(payload, encoding="utf-8")
    logger.info("results.json saved", path=str(primary_path))

    if repo_path:
        repo_results = Path(repo_path) / "results.json"
        try:
            repo_results.write_text(payload, encoding="utf-8")
            logger.info("results.json also saved in repo", path=str(repo_results))
        except Exception as exc:
            logger.warning("Could not write results.json to repo", error=str(exc))

    return str(primary_path)


def _format_duration(seconds: float) -> str:
    """Format seconds into M:SS or H:MM:SS."""
    m, s = divmod(int(seconds), 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _format_duration_human(seconds: float) -> str:
    """Format seconds into human-readable like '2m 45s'."""
    m, s = divmod(int(seconds), 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"
