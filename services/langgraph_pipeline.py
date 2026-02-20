"""LangGraph multi-agent pipeline for autonomous CI/CD healing.

Implements the full flow:
  Clone → Detect Framework → Run Tests → Sanitize → Analyze (Detective)
  → Generate Fix (Reasoner / LLM) → Apply Patch → Verify → Retry or Publish
  → Generate results.json

Uses existing NeverDown agents under the hood but wraps them in a
LangGraph StateGraph for the required multi-agent architecture.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, TypedDict
from uuid import UUID, uuid4

from langgraph.graph import END, START, StateGraph

from agents.agent_2_reasoner.reasoner import ReasonerAgent
from agents.agent_3_verifier.sandbox_runner import SandboxConfig, SandboxRunner
from config.logging_config import get_logger
from config.settings import get_settings
from services.bug_classifier import classify_bug_type, format_summary_line
from services.git_service import GitService
from services.results_generator import build_results_json, save_results_json
from services.test_discovery import detect_test_framework, discover_tests, get_test_command
from services.websocket_manager import manager as ws

logger = get_logger(__name__)
settings = get_settings()

# ════════════════════════════════════════════════════════════════
# Framework → Docker Image Mapping
# ════════════════════════════════════════════════════════════════

_FRAMEWORK_DOCKER_IMAGE: dict[str, str] = {
    "pytest":     "python:3.11-slim",
    "unittest":   "python:3.11-slim",
    "jest":       "node:18-slim",
    "mocha":      "node:18-slim",
    "vitest":     "node:18-slim",
    "go_test":    "golang:1.21-bookworm",
    "cargo_test": "rust:1.74-slim-bookworm",
}

_FRAMEWORK_INSTALL_CMD: dict[str, list[str]] = {
    "pytest":     ["pip", "install", "-r", "requirements.txt"],
    "unittest":   ["pip", "install", "-r", "requirements.txt"],
    "jest":       ["npm", "install", "--legacy-peer-deps"],
    "mocha":      ["npm", "install", "--legacy-peer-deps"],
    "vitest":     ["npm", "install", "--legacy-peer-deps"],
    "go_test":    ["go", "mod", "download"],
    "cargo_test": ["cargo", "fetch"],
}


# ════════════════════════════════════════════════════════════════
# State Schema
# ════════════════════════════════════════════════════════════════

class PipelineState(TypedDict, total=False):
    """Typed state that flows through every node."""

    # ── Inputs (set once at invocation) ─────────────────────
    run_id: str
    repository_url: str
    team_name: str
    leader_name: str
    branch_name: str

    # ── Repo paths ──────────────────────────────────────────
    repo_path: str
    sanitized_repo_path: str

    # ── Test detection ──────────────────────────────────────
    test_framework: str
    test_files: list

    # ── Dependency install ───────────────────────────────────
    deps_installed: bool

    # ── Test results ────────────────────────────────────────
    test_output: str
    all_passed: bool

    # ── Failures & Fixes ────────────────────────────────────
    failures: list          # list of dicts
    fixes: list             # accumulated across all iterations
    commit_count: int

    # ── Iteration tracking ──────────────────────────────────
    iteration: int
    max_retries: int

    # ── Timing ──────────────────────────────────────────────
    start_time: float
    end_time: float

    # ── Status / error ──────────────────────────────────────
    status: str
    error: str

    # ── Timeline events ─────────────────────────────────────
    timeline: list

    # ── Final results payload ───────────────────────────────
    results_json: dict


# ════════════════════════════════════════════════════════════════
# Helper: generate branch name
# ════════════════════════════════════════════════════════════════

def make_branch_name(team: str, leader: str) -> str:
    """TEAMNAME_LEADERNAME_AI_Fix  — all uppercase, underscores only."""
    sanitize = lambda s: re.sub(r"[^A-Z0-9]", "_", re.sub(r"\s+", "_", s.strip().upper()))
    return f"{sanitize(team)}_{sanitize(leader)}_AI_Fix"


# ════════════════════════════════════════════════════════════════
# Graph Nodes
# ════════════════════════════════════════════════════════════════

async def clone_node(state: PipelineState) -> dict:
    """Clone the target GitHub repository.
    
    Smart auth use karta hai — pehle GitHub App token try karta hai,
    phir PAT pe fallback karta hai.
    """
    run_id = state["run_id"]
    await ws.send_step_update(run_id, "cloning", "running")
    await ws.send_log(run_id, "System", "INFO", f"Cloning {state['repository_url']}...")

    _add_timeline(state, "CLONING", {"url": state["repository_url"]})

    git_svc = GitService()
    
    # Smart auth: GitHub App > PAT fallback
    result = await git_svc.clone_with_smart_auth(
        state["repository_url"],
        run_id,
        depth=0,  # full clone for branch creation later
    )

    if not result.success:
        await ws.send_step_update(run_id, "cloning", "failed", {"error": result.error})
        return {"status": "failed", "error": f"Clone failed: {result.error}"}

    await ws.send_step_update(run_id, "cloning", "completed")
    await ws.send_log(run_id, "System", "INFO", "Repository cloned successfully")
    return {"repo_path": result.path, "status": "cloned"}


async def detect_framework_node(state: PipelineState) -> dict:
    """Detect test framework and discover test files."""
    run_id = state["run_id"]
    await ws.send_step_update(run_id, "detecting_framework", "running")

    repo = state.get("repo_path", "")
    if not repo or not Path(repo).exists():
        return {"status": "failed", "error": "No repository path"}

    fw = detect_test_framework(repo)
    tests = discover_tests(repo, fw)

    await ws.send_log(run_id, "System", "INFO", f"Detected framework: {fw} ({len(tests)} test files)")
    await ws.send_step_update(run_id, "detecting_framework", "completed", {"test_framework": fw, "test_count": len(tests)})
    _add_timeline(state, "FRAMEWORK_DETECTED", {"framework": fw, "tests": len(tests)})

    return {"test_framework": fw, "test_files": tests}


async def install_deps_node(state: PipelineState) -> dict:
    """Install project dependencies before running tests."""
    run_id = state["run_id"]
    repo = state.get("repo_path", "")
    fw = state.get("test_framework", "pytest")

    await ws.send_step_update(run_id, "installing_deps", "running")
    await ws.send_log(run_id, "System", "INFO", f"Installing dependencies for {fw}...")

    install_cmd = _FRAMEWORK_INSTALL_CMD.get(fw, [])
    if not install_cmd:
        await ws.send_log(run_id, "System", "WARN", "No install command for framework")
        return {"deps_installed": True}

    # For Python: skip if requirements.txt doesn't exist
    if fw in ("pytest", "unittest") and not (Path(repo) / "requirements.txt").exists():
        # Try pyproject.toml
        if (Path(repo) / "pyproject.toml").exists():
            install_cmd = ["pip", "install", "-e", "."]
        else:
            await ws.send_log(run_id, "System", "INFO", "No requirements file — skipping install")
            return {"deps_installed": True}

    image = _FRAMEWORK_DOCKER_IMAGE.get(fw, settings.SANDBOX_IMAGE)
    sandbox = SandboxRunner(config=SandboxConfig(image=image, timeout_seconds=600, network_mode="bridge"))
    docker_ok = await sandbox.check_docker_available()

    if docker_ok:
        result = await sandbox.run(repo, install_cmd)
        success = result.exit_code == 0
        if not success:
            await ws.send_log(run_id, "System", "WARN",
                f"Dependency install exited {result.exit_code}: {result.stderr[:300]}")
    else:
        # Local fallback
        try:
            proc = await asyncio.create_subprocess_exec(
                *install_cmd, cwd=repo,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
            success = proc.returncode == 0
            if not success:
                await ws.send_log(run_id, "System", "WARN",
                    f"Local install failed: {stderr.decode(errors='replace')[:300]}")
        except Exception as exc:
            await ws.send_log(run_id, "System", "WARN", f"Install failed: {exc}")
            success = False

    await ws.send_step_update(run_id, "installing_deps", "completed", {"success": success})
    _add_timeline(state, "DEPS_INSTALLED", {"framework": fw, "success": success})

    # ── Auto-create setupTests.js for CRA projects ──────────────
    # If @testing-library/jest-dom is a dep but setupTests.js is missing,
    # tests will fail with "toBeInTheDocument is not a function".
    if fw in ("jest", "mocha", "vitest"):
        _ensure_cra_setup_tests(repo)

    return {"deps_installed": success}


async def run_tests_node(state: PipelineState) -> dict:
    """Run tests in Docker sandbox and capture output."""
    run_id = state["run_id"]
    iteration = state.get("iteration", 1)
    await ws.send_step_update(run_id, "running_tests", "running", {"iteration": iteration})
    await ws.send_log(run_id, "Verifier", "INFO", f"Running tests (iteration {iteration})...")

    repo = state.get("repo_path", "")
    fw = state.get("test_framework", "pytest")

    # Ensure CRA setupTests.js exists before running tests
    if fw in ("jest", "mocha", "vitest"):
        _ensure_cra_setup_tests(repo)

    cmd = get_test_command(fw, repo_path=repo)

    # Use the correct Docker image for this framework
    image = _FRAMEWORK_DOCKER_IMAGE.get(fw, settings.SANDBOX_IMAGE)
    sandbox = SandboxRunner(config=SandboxConfig(image=image))
    docker_ok = await sandbox.check_docker_available()

    # For JS frameworks, set CI=true so warnings are errors
    env = {}
    if fw in ("jest", "mocha", "vitest"):
        env["CI"] = "true"

    if docker_ok:
        result = await sandbox.run(repo, cmd, env=env if env else None)
        output = result.stdout + "\n" + result.stderr
        passed = result.exit_code == 0
    else:
        # Fallback: run locally (dev mode)
        await ws.send_log(run_id, "Verifier", "WARN", "Docker unavailable — running tests locally")
        try:
            local_env = dict(os.environ, **env) if env else None
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=repo,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=local_env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=settings.SANDBOX_TIMEOUT)
            output = stdout.decode(errors="replace") + "\n" + stderr.decode(errors="replace")
            passed = proc.returncode == 0
        except Exception as exc:
            output = str(exc)
            passed = False

    await ws.send_step_update(run_id, "running_tests", "completed", {"passed": passed})
    _add_timeline(state, "TESTS_RUN", {"iteration": iteration, "passed": passed})

    return {"test_output": output, "all_passed": passed}


async def analyze_failures_node(state: PipelineState) -> dict:
    """Parse test output, classify bug types, build structured failures list."""
    run_id = state["run_id"]
    await ws.send_step_update(run_id, "analyzing_failures", "running")
    await ws.send_log(run_id, "Detective", "INFO", "Analyzing test failures...")

    test_output = state.get("test_output", "")
    repo_path = state.get("repo_path", "")

    failures = _parse_test_failures(test_output, repo_path)

    logger.info("Parsed failures", count=len(failures),
                files=[f.get("file") for f in failures],
                lines=[f.get("line") for f in failures])

    for f in failures:
        await ws.send_failure(run_id, f["file"], f["bug_type"], f["line"], f["error_message"])

    await ws.send_step_update(run_id, "analyzing_failures", "completed", {"failure_count": len(failures)})
    await ws.send_log(run_id, "Detective", "INFO", f"Found {len(failures)} failure(s)")
    _add_timeline(state, "FAILURES_ANALYZED", {"count": len(failures)})

    return {"failures": failures}


async def generate_fix_node(state: PipelineState) -> dict:
    """Call Agent 2 (Reasoner / LLM) with strict prompt to generate fixes."""
    run_id = state["run_id"]
    failures = state.get("failures", [])
    if not failures:
        return {}

    await ws.send_step_update(run_id, "generating_fix", "running")
    await ws.send_log(run_id, "Reasoner", "INFO", "Generating fixes with LLM...")

    repo_path = state.get("repo_path", "")
    fixes: list = list(state.get("fixes", []))

    for idx, failure in enumerate(failures):
        # Proactive rate-limit delay: wait 13s between LLM calls (5 req/min limit)
        if idx > 0:
            logger.info("Rate-limit delay before next LLM call", delay_seconds=13)
            await asyncio.sleep(13)

        await ws.send_log(
            run_id, "Reasoner", "INFO",
            f"Fixing {failure['bug_type']} in {failure['file']} line {failure['line']}",
        )

        # Build strict prompt
        prompt = _build_strict_fix_prompt(failure, repo_path)
        system = _get_fix_system_prompt()

        try:
            reasoner = ReasonerAgent()
            response = await reasoner._call_llm(system, prompt)
            content = response["content"]

            logger.info("LLM response received",
                        file=failure["file"],
                        content_len=len(content),
                        has_diff="```diff" in content)

            # Parse SUMMARY + PATCH from LLM output
            parsed = _parse_llm_fix_output(content)

            if parsed["diff"]:
                fix_entry = {
                    "file": failure["file"],
                    "bug_type": failure["bug_type"],
                    "line_number": failure["line"],
                    "summary": parsed["summary"],
                    "diff": parsed["diff"],
                    "commit_message": f"[NeverDown-AI] Fix {failure['bug_type']} in {failure['file']} line {failure['line']}",
                    "status": "pending",
                    "confidence": parsed.get("confidence", 0.85),
                    "root_cause": parsed.get("root_cause", ""),
                }
                fixes.append(fix_entry)
                await ws.send_fix(
                    run_id, failure["file"], failure["bug_type"], failure["line"],
                    parsed["diff"], "generated",
                    summary=parsed["summary"],
                    commit_message=f"[AI-AGENT] Fix {failure['bug_type']} in {failure['file']} line {failure['line']}",
                    confidence=parsed.get("confidence", 0.85),
                    root_cause=parsed.get("root_cause", ""),
                    iteration=state.get("iteration", 1),
                )
            else:
                fixes.append({
                    "file": failure["file"],
                    "bug_type": failure["bug_type"],
                    "line_number": failure["line"],
                    "summary": "UNFIXABLE",
                    "diff": "",
                    "commit_message": "",
                    "status": "unfixable",
                    "confidence": 0,
                    "root_cause": parsed.get("root_cause", "Could not determine fix"),
                })
        except Exception as exc:
            logger.exception("LLM fix generation failed", error=str(exc))
            fixes.append({
                "file": failure["file"],
                "bug_type": failure["bug_type"],
                "line_number": failure["line"],
                "summary": "UNFIXABLE",
                "diff": "",
                "commit_message": "",
                "status": "error",
                "confidence": 0,
                "root_cause": str(exc)[:200],
            })

    await ws.send_step_update(run_id, "generating_fix", "completed", {"fixes": len(fixes)})
    _add_timeline(state, "FIXES_GENERATED", {"count": len(fixes)})
    return {"fixes": fixes}


async def apply_fix_node(state: PipelineState) -> dict:
    """Apply generated diffs to the working copy.

    Strategy (in order):
      1. ``git apply --whitespace=fix``
      2. ``git apply --3way``
      3. Direct search-replace fallback (handles non-standard LLM diffs)
    """
    run_id = state["run_id"]
    await ws.send_step_update(run_id, "applying_fix", "running")

    repo_path = state.get("repo_path", "")
    fixes = list(state.get("fixes", []))

    for fix in fixes:
        if fix["status"] not in ("pending", "generated"):
            continue
        diff = fix.get("diff", "")
        if not diff:
            continue

        applied = False
        patch_file = Path(repo_path) / ".neverdown_patch.diff"
        try:
            # ── Strategy 1: git apply ────────────────────────────
            patch_file.write_text(diff, encoding="utf-8")
            proc = subprocess.run(
                ["git", "apply", "--whitespace=fix", str(patch_file)],
                cwd=repo_path, capture_output=True, timeout=30,
            )
            if proc.returncode == 0:
                applied = True
            else:
                # ── Strategy 2: git apply --3way ─────────────────
                proc2 = subprocess.run(
                    ["git", "apply", "--3way", str(patch_file)],
                    cwd=repo_path, capture_output=True, timeout=30,
                )
                if proc2.returncode == 0:
                    applied = True

            # ── Strategy 3: direct search-replace from diff ──────
            if not applied:
                applied = _apply_diff_manually(diff, repo_path, fix["file"])

            if applied:
                fix["status"] = "applied"
                await ws.send_log(run_id, "System", "INFO", f"Patch applied to {fix['file']}")
            else:
                fix["status"] = "apply_failed"
                await ws.send_log(run_id, "System", "WARN",
                    f"Patch failed for {fix['file']} (all strategies exhausted)")
        except Exception as exc:
            fix["status"] = "apply_failed"
            logger.warning("Patch apply error", error=str(exc))
        finally:
            if patch_file.exists():
                patch_file.unlink()

    await ws.send_step_update(run_id, "applying_fix", "completed")
    return {"fixes": fixes}


async def verify_node(state: PipelineState) -> dict:
    """Re-run tests to verify applied fixes; bump iteration."""
    run_id = state["run_id"]
    iteration = state.get("iteration", 1)
    await ws.send_step_update(run_id, "verifying", "running", {"iteration": iteration})
    await ws.send_log(run_id, "Verifier", "INFO", f"Verifying fixes (iteration {iteration})...")

    # Reuse run_tests logic
    result = await run_tests_node(state)
    passed = result.get("all_passed", False)
    new_iteration = iteration + 1

    remaining = 0 if passed else len(state.get("failures", []))
    fixes_applied = sum(1 for f in state.get("fixes", []) if f.get("status") in ("applied", "fixed"))
    await ws.send_iteration(
        run_id, iteration, state.get("max_retries", 5), passed, remaining,
        tests_failed=remaining, fixes_applied=fixes_applied,
    )
    _add_timeline(state, "VERIFICATION", {"iteration": iteration, "passed": passed})

    # Update fix statuses
    fixes = list(state.get("fixes", []))
    if passed:
        for f in fixes:
            if f["status"] == "applied":
                f["status"] = "fixed"

    return {
        "all_passed": passed,
        "test_output": result.get("test_output", ""),
        "iteration": new_iteration,
        "fixes": fixes,
    }


async def publish_node(state: PipelineState) -> dict:
    """Commit fixes and push to the fix branch on GitHub."""
    run_id = state["run_id"]
    await ws.send_step_update(run_id, "publishing", "running")
    await ws.send_log(run_id, "Publisher", "INFO", "Pushing fixes to GitHub...")

    repo_path = state.get("repo_path", "")
    branch = state.get("branch_name", "")
    commit_count = state.get("commit_count", 0)

    logger.info("publish_node started", repo_path=repo_path, branch=branch)

    # Check if there are actually fixes to commit
    fixes = state.get("fixes", [])
    fixed_files = [f["file"] for f in fixes if f.get("status") in ("fixed", "applied")]

    if not fixed_files:
        logger.warning("No fixes to commit — skipping publish")
        await ws.send_log(run_id, "Publisher", "WARN", "No fixes to commit — skipping publish")
        await ws.send_step_update(run_id, "publishing", "completed", {"skipped": True})
        _add_timeline(state, "PUBLISH_SKIPPED", {"reason": "no fixes to commit"})
        return {"status": "completed", "commit_count": commit_count}

    logger.info("Publishing fixes", fixed_count=len(fixed_files), files=fixed_files[:5])

    try:
        # Configure git identity for commit
        _git(repo_path, "config", "user.email", "neverdown-ai@neverdown.app")
        _git(repo_path, "config", "user.name", "NeverDown AI")

        # Create branch (ignore error if it already exists)
        try:
            _git(repo_path, "checkout", "-b", branch)
        except RuntimeError:
            _git(repo_path, "checkout", branch)

        _git(repo_path, "add", "-A")

        # Check if there's actually anything staged
        diff_check = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=repo_path, capture_output=True, timeout=10,
        )
        if diff_check.returncode == 0:
            # Nothing staged — no changes to commit
            await ws.send_log(run_id, "Publisher", "WARN", "No staged changes — skipping commit")
            await ws.send_step_update(run_id, "publishing", "completed", {"skipped": True})
            return {"status": "completed", "commit_count": commit_count}

        # Strict commit format: [NeverDown-AI] Fix ...
        msg = f"[NeverDown-AI] Fix {len(fixed_files)} issue(s) in {', '.join(fixed_files[:5])}"
        _git(repo_path, "commit", "-m", msg)
        commit_count += 1

        # Smart auth for push: GitHub App token > PAT fallback
        push_url = state["repository_url"]
        try:
            import re as _re
            _m = _re.search(r'github\.com[:/]([^/]+)/([^/.]+)', push_url)
            if _m:
                _owner, _repo = _m.group(1), _m.group(2).replace('.git', '')
                from services.github_app_service import get_github_app_service
                _app_svc = get_github_app_service()
                _token, _auth_method = await _app_svc.get_token_for_repo(_owner, _repo)
                await ws.send_log(run_id, "Publisher", "INFO", f"Push auth: {_auth_method}")
            else:
                _token = settings.GITHUB_TOKEN.get_secret_value() if settings.GITHUB_TOKEN else ""
        except Exception as _e:
            logger.warning("Smart auth for push failed, using PAT", error=str(_e))
            _token = settings.GITHUB_TOKEN.get_secret_value() if settings.GITHUB_TOKEN else ""
        
        if _token and push_url.startswith("https://github.com/"):
            push_url = push_url.replace("https://github.com/", f"https://x-access-token:{_token}@github.com/")

        _git(repo_path, "push", push_url, branch, "--force")
        logger.info("Pushed branch to GitHub", branch=branch)
        await ws.send_log(run_id, "Publisher", "INFO", f"Pushed branch {branch}")
        await ws.send_step_update(run_id, "publishing", "completed", {"branch_name": branch})
        _add_timeline(state, "PUBLISHED", {"branch": branch})

        return {"status": "completed", "commit_count": commit_count}
    except Exception as exc:
        logger.exception("Publish failed", error=str(exc))
        await ws.send_step_update(run_id, "publishing", "failed", {"error": str(exc)[:200]})
        return {"status": "failed", "error": str(exc)[:200], "commit_count": commit_count}


async def generate_results_node(state: PipelineState) -> dict:
    """Build and persist results.json."""
    run_id = state["run_id"]
    await ws.send_step_update(run_id, "generating_results", "running")
    end_time = time.time()
    total_time = end_time - state.get("start_time", end_time)

    fixes = state.get("fixes", [])
    total_fixes = sum(1 for f in fixes if f.get("status") in ("fixed", "applied"))
    total_failures = len(state.get("failures", []))
    # PASSED ONLY if tests actually passed (exit code 0).
    # Never use total_failures==0 as a proxy — parser may have missed failures.
    final_status = "PASSED" if state.get("all_passed", False) else "FAILED"

    results = build_results_json(
        repository=state["repository_url"],
        team_name=state["team_name"],
        leader_name=state["leader_name"],
        branch_name=state["branch_name"],
        total_failures=total_failures,
        total_fixes=total_fixes,
        iterations_used=state.get("iteration", 1) - 1,
        max_iterations=state.get("max_retries", 5),
        final_status=final_status,
        total_time_seconds=total_time,
        total_commits=state.get("commit_count", 0),
        fixes=[{
            "file": f["file"],
            "bug_type": f["bug_type"],
            "line_number": f["line_number"],
            "commit_message": f["commit_message"],
            "status": f["status"],
        } for f in fixes],
        timeline=state.get("timeline", []),
    )

    save_results_json(results, run_id, state.get("repo_path"))
    await ws.send_result(run_id, results)
    await ws.send_step_update(run_id, "completed" if final_status == "PASSED" else "failed", "completed", results)

    return {"results_json": results, "end_time": end_time, "status": "completed"}


# ════════════════════════════════════════════════════════════════
# Conditional edges
# ════════════════════════════════════════════════════════════════

def has_failures(state: PipelineState) -> Literal["has_failures", "no_failures"]:
    # Only treat as clean if tests actually passed (exit code 0).
    # If tests failed but parser found no structured failures, we still
    # need to attempt fixes — the raw output itself is evidence of failure.
    if state.get("all_passed", False):
        return "no_failures"
    return "has_failures"


def should_retry(state: PipelineState) -> Literal["retry", "publish", "finish"]:
    if state.get("all_passed", False):
        return "publish"
    if state.get("iteration", 1) > state.get("max_retries", 5):
        # Max retries exhausted — still publish any partial fixes
        fixes = state.get("fixes", [])
        has_applied = any(f.get("status") in ("fixed", "applied") for f in fixes)
        return "publish" if has_applied else "finish"
    return "retry"


# ════════════════════════════════════════════════════════════════
# Graph Builder
# ════════════════════════════════════════════════════════════════

def build_pipeline() -> Any:
    """Construct and compile the LangGraph pipeline.

    Returns a compiled graph that can be invoked with ``await graph.ainvoke(state)``.
    """
    graph = StateGraph(PipelineState)

    # Nodes
    graph.add_node("clone", clone_node)
    graph.add_node("detect_framework", detect_framework_node)
    graph.add_node("install_deps", install_deps_node)
    graph.add_node("run_tests", run_tests_node)
    graph.add_node("analyze_failures", analyze_failures_node)
    graph.add_node("generate_fix", generate_fix_node)
    graph.add_node("apply_fix", apply_fix_node)
    graph.add_node("verify", verify_node)
    graph.add_node("publish", publish_node)
    graph.add_node("generate_results", generate_results_node)

    # Edges: clone → detect_framework → install_deps → run_tests → analyze
    graph.add_edge(START, "clone")
    graph.add_edge("clone", "detect_framework")
    graph.add_edge("detect_framework", "install_deps")
    graph.add_edge("install_deps", "run_tests")
    graph.add_edge("run_tests", "analyze_failures")

    graph.add_conditional_edges("analyze_failures", has_failures, {
        "has_failures": "generate_fix",
        "no_failures": "generate_results",  # Skip straight to results if no failures found
    })

    graph.add_edge("generate_fix", "apply_fix")
    graph.add_edge("apply_fix", "verify")

    graph.add_conditional_edges("verify", should_retry, {
        "retry": "analyze_failures",
        "publish": "publish",
        "finish": "generate_results",
    })

    graph.add_edge("publish", "generate_results")
    graph.add_edge("generate_results", END)

    return graph.compile()


# Singleton compiled graph
pipeline = build_pipeline()


# ════════════════════════════════════════════════════════════════
# Public entry-point
# ════════════════════════════════════════════════════════════════

async def run_pipeline(
    repository_url: str,
    team_name: str,
    leader_name: str,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full healing pipeline end-to-end.

    Args:
        repository_url: GitHub HTTPS URL
        team_name:      Team name (will be uppercased / sanitized)
        leader_name:    Leader name (will be uppercased / sanitized)
        run_id:         Optional pre-assigned run ID

    Returns:
        The final results.json dict
    """
    run_id = run_id or str(uuid4())
    branch_name = make_branch_name(team_name, leader_name)

    initial_state: PipelineState = {
        "run_id": run_id,
        "repository_url": repository_url,
        "team_name": team_name,
        "leader_name": leader_name,
        "branch_name": branch_name,
        "repo_path": "",
        "sanitized_repo_path": "",
        "test_framework": "",
        "test_files": [],
        "deps_installed": False,
        "test_output": "",
        "all_passed": False,
        "failures": [],
        "fixes": [],
        "commit_count": 0,
        "iteration": 1,
        "max_retries": settings.MAX_RETRIES,
        "start_time": time.time(),
        "end_time": 0.0,
        "status": "started",
        "error": "",
        "timeline": [],
        "results_json": {},
    }

    try:
        final_state = await pipeline.ainvoke(initial_state)
        return final_state.get("results_json", {})
    except Exception as exc:
        logger.exception("Pipeline crashed", error=str(exc))
        # Still emit results on crash
        end_time = time.time()
        results = build_results_json(
            repository=repository_url,
            team_name=team_name,
            leader_name=leader_name,
            branch_name=branch_name,
            total_failures=0,
            total_fixes=0,
            iterations_used=0,
            max_iterations=settings.MAX_RETRIES,
            final_status="FAILED",
            total_time_seconds=end_time - initial_state["start_time"],
            total_commits=0,
            fixes=[],
            timeline=[{"state": "ERROR", "timestamp": datetime.now(timezone.utc).isoformat(), "details": {"error": str(exc)[:300]}}],
        )
        save_results_json(results, run_id)
        await ws.send_result(run_id, results)
        return results


# ════════════════════════════════════════════════════════════════
# Internal helpers
# ════════════════════════════════════════════════════════════════

def _add_timeline(state: PipelineState, event: str, details: dict | None = None) -> None:
    """Append a timeline event in-place."""
    tl: list = state.get("timeline", [])
    tl.append({
        "state": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": details or {},
    })


def _git(cwd: str, *args: str) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr[:300]}")
    return result.stdout


def _parse_test_failures(test_output: str, repo_path: str) -> List[Dict[str, Any]]:
    """Parse raw test output into structured failure dicts.

    Each failure dict:
        {bug_type, file, line, error_message, snippet, test_output}

    Uses LogParser for structured parsing, then falls back to
    framework-specific patterns and finally a synthetic fallback so
    that a non-zero exit code is NEVER silently treated as 'clean'.
    """
    from agents.agent_1_detective.log_parser import LogParser

    parser = LogParser()
    errors = parser.parse(test_output)

    failures: list = []
    seen: set = set()

    for err in errors:
        file_path = err.file_path or "unknown"
        line = err.line_number or 0

        # Normalize path relative to repo
        if repo_path and file_path.startswith(repo_path):
            file_path = str(Path(file_path).relative_to(repo_path))

        # Strip Docker sandbox /workspace/ or /app/ prefix
        file_path = re.sub(r'^/?(?:workspace|app)/', '', file_path)
        file_path = file_path.lstrip('/')

        key = (file_path, line, err.error_type)
        if key in seen:
            continue
        seen.add(key)

        bug_type = classify_bug_type(err.error_type, err.message, test_output)

        # Read snippet
        snippet = ""
        abs_path = Path(repo_path) / file_path
        if abs_path.exists() and line > 0:
            try:
                lines = abs_path.read_text(errors="replace").splitlines()
                start = max(0, line - 3)
                end = min(len(lines), line + 3)
                snippet = "\n".join(f"{i+1}: {lines[i]}" for i in range(start, end))
            except Exception:
                pass

        failures.append({
            "bug_type": bug_type,
            "file": file_path,
            "line": line,
            "error_message": f"{err.error_type}: {err.message}",
            "snippet": snippet,
            "test_output": test_output[:2000],
        })

    # ── Jest / Vitest / Mocha specific patterns (FAIL lines, ● markers) ──
    if not failures:
        failures.extend(_parse_jest_failures(test_output, repo_path))

    # ── ESLint-style failures ──
    if not failures:
        failures.extend(_parse_eslint_failures(test_output, repo_path))

    # ── SYNTHETIC FALLBACK ──────────────────────────────────────────────
    # If tests failed (exit code != 0) but no parser could extract
    # structured failures, create one synthetic entry from the raw output.
    # This ensures the pipeline NEVER treats a failing repo as clean.
    if not failures and test_output.strip():
        # Try to find any file mentioned in the output
        file_ref = re.search(r'((?:src|lib|app|test|tests)/\S+\.(?:js|jsx|ts|tsx|py|go|rs))', test_output)
        failures.append({
            "bug_type": classify_bug_type("Error", test_output[:500], test_output),
            "file": file_ref.group(1) if file_ref else "unknown",
            "line": 0,
            "error_message": _extract_first_error_line(test_output),
            "snippet": "",
            "test_output": test_output[:2000],
        })

    return failures


def _parse_jest_failures(test_output: str, repo_path: str) -> List[Dict[str, Any]]:
    """Parse Jest/Vitest/Mocha-style test output.

    Handles:
      FAIL src/App.test.js
      ● test name
      expect(received)...
    """
    failures: list = []
    seen: set = set()

    # Pattern: FAIL <file>
    fail_files = re.findall(r'FAIL\s+(\S+)', test_output)

    # Pattern: ● <test name>  →  followed by assertion error
    test_blocks = re.split(r'●\s+', test_output)
    for block in test_blocks[1:]:  # skip text before first ●
        lines_list = block.strip().splitlines()
        test_name = lines_list[0].strip() if lines_list else "unknown test"

        # Find file/line from "at Object.<anonymous> (src/App.test.js:10:5)" style
        loc_match = re.search(r'at\s+\S+\s+\(([^:)]+):(\d+):\d+\)', block)
        if loc_match and 'node_modules' in loc_match.group(1):
            loc_match = None  # skip node_modules frames

        if not loc_match:
            # Try inline SyntaxError: /workspace/file.js: ... (line:col):
            loc_match = re.search(
                r'SyntaxError:\s*(/?\S+\.(?:js|jsx|ts|tsx))\S*.*?\((\d+):\d+\)',
                block,
            )
        if not loc_match:
            # Try "file.test.js:10:5" anywhere (non-node_modules)
            all_file_refs = re.finditer(r'(?:/workspace/)?(\S+\.(?:js|jsx|ts|tsx)):(\d+):\d+', block)
            for ref in all_file_refs:
                if 'node_modules' not in ref.group(1):
                    loc_match = ref
                    break
        if not loc_match:
            # Fallback: look for file path in FAIL list
            loc_match = re.search(r'((?:src|lib|test|tests|__tests__)/\S+\.(?:js|jsx|ts|tsx))', block)

        file_path = loc_match.group(1) if loc_match else (fail_files[0] if fail_files else "unknown")
        # Strip Docker sandbox mount prefixes (/workspace/, /app/, workspace/, app/)
        file_path = re.sub(r'^/?(?:workspace|app)/', '', file_path)
        file_path = file_path.lstrip('/')
        line = int(loc_match.group(2)) if loc_match and loc_match.lastindex and loc_match.lastindex >= 2 else 0

        # Extract error message (expect/assertion line)
        err_msg = test_name
        expect_match = re.search(r'(expect\(.+?\)\.to\S+\(.*?\))', block)
        if not expect_match:
            expect_match = re.search(r'(Expected .+)', block)
        if not expect_match:
            # React Testing Library: "Unable to find an element..."
            expect_match = re.search(r'(TestingLibraryElementError:\s*.+?)(?:\n\n|\n\s*\n)', block, re.DOTALL)
        if not expect_match:
            # Generic error: "Error: ..." / "SyntaxError: ..."
            expect_match = re.search(r'((?:Syntax|Type|Reference|)Error:\s*.+?)(?:\n\s*at\s|\Z)', block, re.DOTALL)
        if expect_match:
            err_msg = f"{test_name}: {expect_match.group(1).replace(chr(10), ' ')[:200]}"

        key = (file_path, line, err_msg[:50])
        if key in seen:
            continue
        seen.add(key)

        bug_type = classify_bug_type("AssertionError", err_msg, block)

        snippet = ""
        abs_path = Path(repo_path) / file_path
        if abs_path.exists() and line > 0:
            try:
                all_lines = abs_path.read_text(errors="replace").splitlines()
                start = max(0, line - 3)
                end = min(len(all_lines), line + 3)
                snippet = "\n".join(f"{i+1}: {all_lines[i]}" for i in range(start, end))
            except Exception:
                pass

        failures.append({
            "bug_type": bug_type,
            "file": file_path,
            "line": line,
            "error_message": err_msg[:300],
            "snippet": snippet,
            "test_output": block[:2000],
        })

    # If FAIL files exist but no ● blocks were found (e.g., compilation errors)
    if not failures and fail_files:
        for ffile in fail_files:
            key = (ffile, 0, "test_failure")
            if key in seen:
                continue
            seen.add(key)
            failures.append({
                "bug_type": "LOGIC",
                "file": ffile,
                "line": 0,
                "error_message": f"Test suite failed: {ffile}",
                "snippet": "",
                "test_output": test_output[:2000],
            })

    return failures


def _parse_eslint_failures(test_output: str, repo_path: str) -> List[Dict[str, Any]]:
    """Parse ESLint-style output: src/App.js  10:5  error  ... rule-name."""
    failures: list = []
    seen: set = set()

    # ESLint line: /path/to/file.js  line:col  error  message  rule-name
    eslint_pattern = re.compile(
        r'^\s*(\S+\.(?:js|jsx|ts|tsx))\s*$'
        r'|'
        r'^\s+(\d+):(\d+)\s+(error|warning)\s+(.+?)\s+(\S+)\s*$',
        re.MULTILINE,
    )

    current_file = None
    for match in eslint_pattern.finditer(test_output):
        if match.group(1):
            current_file = match.group(1)
        elif match.group(2) and current_file:
            line_num = int(match.group(2))
            severity = match.group(4)
            message = match.group(5)
            rule = match.group(6)

            key = (current_file, line_num, rule)
            if key in seen:
                continue
            seen.add(key)

            failures.append({
                "bug_type": "LINTING",
                "file": current_file,
                "line": line_num,
                "error_message": f"ESLint {severity}: {message} ({rule})",
                "snippet": "",
                "test_output": test_output[:2000],
            })

    return failures


def _extract_first_error_line(output: str) -> str:
    """Pull the first meaningful error line from raw output."""
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()
        if any(kw in low for kw in ["error", "fail", "exception", "traceback", "assert"]):
            return stripped[:300]
    # Fallback: first non-empty line
    for line in output.splitlines():
        if line.strip():
            return line.strip()[:300]
    return "Test process exited with non-zero code"


def _get_fix_system_prompt() -> str:
    """System prompt that forces the exact hackathon output format."""
    return """You are an expert software engineer debugging test failures.
You receive a single bug report and must produce a MINIMAL fix.

You MUST respond in this EXACT format (no deviation):

SUMMARY:
<BUG_TYPE> error in <file_path> line <line_number> → Fix: <short description>

PATCH:
```diff
<unified diff — minimal change only>
```

CONFIDENCE: <0.0-1.0>

ROOT_CAUSE: <one-line explanation>

Rules:
- BUG_TYPE must be one of: LINTING, SYNTAX, LOGIC, TYPE_ERROR, IMPORT, INDENTATION
- Use exact arrow symbol →
- Diff must be a valid unified diff (--- a/ and +++ b/ headers)
- Only minimal patch. No refactoring. No extra comments.
- If truly unfixable, output ONLY the word: UNFIXABLE
- Do NOT modify any <REDACTED_*> placeholders

React Testing Library tips (CRITICAL — read carefully):
- "Found multiple elements" → use getByRole('heading', {name: /text/i}) or getAllByText()[0] instead of getByText()
- Match text to ACTUAL component render — check the source JSX for exact text, emojis, etc.
- BUTTON TEXT: look at the <button> element's children in the JSX component file. Headings (<h2>) have DIFFERENT text than buttons. For example, a heading might say "Add New Note" while the button says "Add Note" — use the BUTTON text when querying for a submit button.
- If a test queries getByText('X') to click a submit button, make sure 'X' matches the <button> text, NOT the <h2> heading text.
- Only fix the TEST file expectations to match the source — do NOT change source files
- If getByText(/pattern/i) matches multiple elements, use a more specific query like getByRole('button', {name: /pattern/i}) or getByRole('heading', {name: /pattern/i})
"""


def _build_strict_fix_prompt(failure: Dict[str, Any], repo_path: str) -> str:
    """Build user prompt for a single failure."""
    parts = [
        f"Bug Type: {failure['bug_type']}",
        f"File: {failure['file']}",
        f"Line: {failure['line']}",
        f"Error: {failure['error_message']}",
    ]

    if failure.get("snippet"):
        parts.append(f"\nCode context:\n```\n{failure['snippet']}\n```")

    # Include full file content if small enough
    abs_path = Path(repo_path) / failure["file"]
    if abs_path.exists():
        try:
            content = abs_path.read_text(errors="replace")
            if len(content) < 5000:
                parts.append(f"\nFull file ({failure['file']}):\n```\n{content}\n```")
        except Exception:
            pass

    # For test files, also include the source file being tested
    # e.g., src/App.test.js → src/App.js, src/utils/helpers.test.js → src/utils/helpers.js
    test_file = failure["file"]
    source_candidates = []
    for suffix in [".test.js", ".test.jsx", ".test.ts", ".test.tsx",
                   ".spec.js", ".spec.jsx", ".spec.ts", ".spec.tsx",
                   "_test.py", "_test.go"]:
        if test_file.endswith(suffix):
            base = test_file[: -len(suffix)]
            for ext in [".js", ".jsx", ".ts", ".tsx", ".py", ".go"]:
                source_candidates.append(base + ext)
            break

    for candidate in source_candidates:
        src_abs = Path(repo_path) / candidate
        if src_abs.exists():
            try:
                src_content = src_abs.read_text(errors="replace")
                if len(src_content) < 8000:
                    parts.append(
                        f"\nSource file being tested ({candidate}):\n```\n{src_content}\n```"
                    )
                    parts.append(
                        "\nIMPORTANT: Fix the TEST file expectations to match what "
                        "the source code actually renders/does. Look at BUG comments "
                        "in the test file. Do NOT modify the source file — only fix "
                        "the test assertions, selectors, and expected values."
                    )

                    # Include imported component files so LLM can see actual rendered output
                    import_pattern = re.compile(r"""import\s+\w+\s+from\s+['"](\.\/[^'"]+)['"]""")
                    for imp_match in import_pattern.finditer(src_content):
                        rel_import = imp_match.group(1)
                        src_dir = str(Path(candidate).parent)
                        for ext in ["", ".js", ".jsx", ".ts", ".tsx"]:
                            comp_path = os.path.normpath(os.path.join(src_dir, rel_import + ext))
                            comp_abs = Path(repo_path) / comp_path
                            if comp_abs.exists():
                                try:
                                    comp_content = comp_abs.read_text(errors="replace")
                                    if len(comp_content) < 3000:
                                        parts.append(
                                            f"\nImported component ({comp_path}):\n```\n{comp_content}\n```"
                                        )
                                except Exception:
                                    pass
                                break
            except Exception:
                pass
            break

    if failure.get("test_output"):
        parts.append(f"\nTest output (truncated):\n```\n{failure['test_output'][:1500]}\n```")

    return "\n".join(parts)


def _parse_llm_fix_output(content: str) -> Dict[str, Any]:
    """Parse the strict-format LLM response."""
    if content.strip() == "UNFIXABLE":
        return {"summary": "UNFIXABLE", "diff": "", "confidence": 0, "root_cause": "Unfixable"}

    result: Dict[str, Any] = {"summary": "", "diff": "", "confidence": 0.85, "root_cause": ""}

    # Extract SUMMARY
    m = re.search(r"SUMMARY:\s*\n(.+)", content)
    if m:
        result["summary"] = m.group(1).strip()

    # Extract PATCH / diff block
    diff_match = re.search(r"```diff\s*\n(.*?)```", content, re.DOTALL)
    if diff_match:
        result["diff"] = diff_match.group(1).strip()

    # Extract CONFIDENCE
    conf_match = re.search(r"CONFIDENCE:\s*([\d.]+)", content)
    if conf_match:
        try:
            result["confidence"] = float(conf_match.group(1))
        except ValueError:
            pass

    # Extract ROOT_CAUSE
    rc_match = re.search(r"ROOT_CAUSE:\s*(.+)", content)
    if rc_match:
        result["root_cause"] = rc_match.group(1).strip()

    return result


def _apply_diff_manually(diff: str, repo_path: str, target_file: str) -> bool:
    """Apply a unified diff by direct search-replace on file content.

    LLM-generated diffs often fail ``git apply`` because of whitespace
    or header mismatches.  This function extracts the ``-`` and ``+``
    lines from each hunk and applies them as a search-replace on the
    target file.

    Returns True if at least one hunk was applied successfully.
    """
    # Determine the target file from diff headers or fall back to the arg
    file_match = re.search(r'^(?:---|\+\+\+)\s+[ab]/(.+)', diff, re.MULTILINE)
    file_path = file_match.group(1) if file_match else target_file

    abs_path = Path(repo_path) / file_path
    if not abs_path.exists():
        # Try target_file directly
        abs_path = Path(repo_path) / target_file
        if not abs_path.exists():
            return False

    try:
        original = abs_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False

    content = original

    # Split diff into hunks
    hunks = re.split(r'^@@[^@]*@@.*$', diff, flags=re.MULTILINE)
    if len(hunks) <= 1:
        # No standard hunk headers — try to treat the entire diff as a single hunk
        hunks = ["", diff]

    applied_any = False
    for hunk in hunks[1:]:  # skip text before first @@
        old_lines: list[str] = []
        new_lines: list[str] = []

        for line in hunk.splitlines():
            if line.startswith("-") and not line.startswith("---"):
                old_lines.append(line[1:])
            elif line.startswith("+") and not line.startswith("+++"):
                new_lines.append(line[1:])
            elif line.startswith(" "):
                old_lines.append(line[1:])
                new_lines.append(line[1:])
            elif not line.startswith(("\\", "diff", "---", "+++")):
                # Context line without leading space (common LLM mistake)
                old_lines.append(line)
                new_lines.append(line)

        if not old_lines and not new_lines:
            continue

        old_block = "\n".join(old_lines)
        new_block = "\n".join(new_lines)

        if old_block and old_block in content:
            content = content.replace(old_block, new_block, 1)
            applied_any = True
        elif old_block:
            # Try with stripped whitespace matching
            stripped_old = "\n".join(l.rstrip() for l in old_lines)
            stripped_content_lines = content.splitlines()
            for i in range(len(stripped_content_lines) - len(old_lines) + 1):
                window = "\n".join(l.rstrip() for l in stripped_content_lines[i:i + len(old_lines)])
                if window == stripped_old:
                    # Found match — replace preserving original structure
                    before = "\n".join(stripped_content_lines[:i])
                    after = "\n".join(stripped_content_lines[i + len(old_lines):])
                    content = before + ("\n" if before else "") + new_block + ("\n" if after else "") + after
                    applied_any = True
                    break

    if applied_any and content != original:
        try:
            abs_path.write_text(content, encoding="utf-8")
            return True
        except Exception:
            return False

    return False


def _ensure_cra_setup_tests(repo_path: str) -> None:
    """Auto-create ``src/setupTests.js`` for CRA projects if missing.

    Create React App expects this file to exist and import
    ``@testing-library/jest-dom`` to enable matchers like
    ``toBeInTheDocument()``.  Many repos miss it, causing all tests
    to fail with ``TypeError: expect(...).toBeInTheDocument is not a function``.
    """
    pkg_json = Path(repo_path) / "package.json"
    if not pkg_json.exists():
        return

    try:
        pkg = json.loads(pkg_json.read_text(errors="replace"))
    except Exception:
        return

    all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

    # Only for projects that use @testing-library/jest-dom
    if "@testing-library/jest-dom" not in all_deps:
        return

    # Only create if the module is actually installed in node_modules
    if not (Path(repo_path) / "node_modules" / "@testing-library" / "jest-dom").exists():
        logger.info("Skipping setupTests.js — @testing-library/jest-dom not in node_modules")
        return

    # Check common setup file locations
    for setup_name in ["src/setupTests.js", "src/setupTests.ts"]:
        if (Path(repo_path) / setup_name).exists():
            return  # Already exists

    # Create the missing setupTests.js
    setup_path = Path(repo_path) / "src" / "setupTests.js"
    setup_path.parent.mkdir(parents=True, exist_ok=True)
    setup_path.write_text(
        "// jest-dom adds custom jest matchers for asserting on DOM nodes.\n"
        "// allows you to do things like:\n"
        "// expect(element).toHaveTextContent(/react/i)\n"
        "// learn more: https://github.com/testing-library/jest-dom\n"
        "import '@testing-library/jest-dom';\n",
        encoding="utf-8",
    )
    logger.info("Auto-created setupTests.js for CRA project", path=str(setup_path))
