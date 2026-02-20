"""GitHub App installation routes — bina webhook ke.

Yeh routes handle karte hain:
1. GET  /github-app/install     — User ko redirect karo App install karne ke liye
2. GET  /github-app/callback    — Installation complete hone ke baad callback
3. GET  /github-app/status      — GitHub App auth status check karo
4. GET  /github-app/check-repo  — Kisi repo pe App installed hai ya nahi
5. GET  /github-app/installations — Saari installations list karo
6. POST /github-app/token       — Manual token test karo kisi repo pe
"""

import re
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from config.logging_config import get_logger
from config.settings import get_settings
from services.github_app_service import get_github_app_service

router = APIRouter()
logger = get_logger(__name__)
settings = get_settings()


# ── Request / Response Schemas ──────────────────────────────

class TokenTestRequest(BaseModel):
    """Manual token test - kisi repo ke liye token resolve karo."""
    owner: str = Field(..., description="GitHub repo owner")
    repo: str = Field(..., description="GitHub repo name")


class TokenTestResponse(BaseModel):
    """Token test ka result."""
    auth_method: str
    token_preview: str  # Sirf pehle 8 chars dikhayenge
    installation_id: Optional[int] = None


class InstallationCallbackResponse(BaseModel):
    """Installation callback ka response."""
    status: str
    installation_id: int
    account: str = ""
    setup_action: str = ""
    message: str = ""


# ── In-memory state storage (CSRF protection) ──────────────

_pending_states: Dict[str, Dict[str, Any]] = {}


# ═══════════════════════════════════════════════════════════════
# Route: Check Repo Auth (Frontend calls this when user types a URL)
# ═══════════════════════════════════════════════════════════════

@router.get("/github-app/check-repo")
async def check_repo_auth(
    repo: str = Query(..., description="Repo URL ya owner/repo format"),
    fresh: bool = Query(False, description="Cache clear karke fresh check karo"),
):
    """Kisi repo ke liye auth status check karo.

    Frontend jab user repo URL type karta hai tab yeh call hota hai.
    Batata hai:
    - App installed hai ya nahi
    - PAT available hai ya nahi
    - Konsa auth method use hoga
    - Install URL agar App available nahi hai

    fresh=true: install callback ke baad use karo — cache clear karke fresh API call karta hai

    Example: /api/v1/github-app/check-repo?repo=https://github.com/RohanTewariIIITS/simple_notes_app
    """
    svc = get_github_app_service()

    # Agar fresh=true hai, toh installation cache clear karo for this repo
    if fresh:
        svc._installation_cache.clear()

    # Parse owner/repo from URL or direct format
    match = re.search(r'github\.com[:/]([^/]+)/([^/.]+)', repo)
    if not match:
        # Try direct owner/repo format
        parts = repo.strip().split("/")
        if len(parts) == 2:
            owner, repo_name = parts[0], parts[1]
        else:
            raise HTTPException(status_code=400, detail="Invalid repo format. Use owner/repo or full GitHub URL")
    else:
        owner, repo_name = match.group(1), match.group(2).replace('.git', '')

    full_name = f"{owner}/{repo_name}"

    result: Dict[str, Any] = {
        "repo": full_name,
        "owner": owner,
        "repo_name": repo_name,
        "app_configured": svc.is_app_configured,
        "pat_available": svc.has_pat_fallback,
    }

    # Check if App is installed on this repo
    if svc.is_app_configured:
        installation_id = await svc.find_installation_for_repo(owner, repo_name)
        result["app_installed"] = installation_id is not None
        result["installation_id"] = installation_id

        if installation_id:
            result["auth_method"] = "github_app"
            result["auth_ready"] = True
        elif svc.has_pat_fallback:
            result["auth_method"] = "pat"
            result["auth_ready"] = True
        else:
            result["auth_method"] = "none"
            result["auth_ready"] = False

        # Install URL — agar App install nahi hai toh user ko redirect kar sakte hain
        if not installation_id and svc.app_slug:
            result["install_url"] = f"/api/v1/github-app/install?repo={full_name}"
    else:
        result["app_installed"] = False
        result["installation_id"] = None
        if svc.has_pat_fallback:
            result["auth_method"] = "pat"
            result["auth_ready"] = True
        else:
            result["auth_method"] = "none"
            result["auth_ready"] = False

    return result


# ═══════════════════════════════════════════════════════════════
# Route: GitHub App Status
# ═══════════════════════════════════════════════════════════════

@router.get("/github-app/status")
async def github_app_status():
    """GitHub App ka current authentication status dikhao.

    Batao ki App configure hai, PAT available hai, ya kuch nahi hai.
    """
    svc = get_github_app_service()

    result = {
        "auth_method": svc.get_auth_method(),
        "github_app_configured": svc.is_app_configured,
        "pat_available": svc.has_pat_fallback,
        "app_id": svc.app_id,
        "app_slug": svc.app_slug,
    }

    # Agar app configured hai, toh installations bhi count karo
    if svc.is_app_configured:
        try:
            installations = await svc.list_all_installations()
            result["total_installations"] = len(installations)
            result["installations"] = installations
        except Exception as e:
            result["total_installations"] = 0
            result["installations_error"] = str(e)

    return result


# ═══════════════════════════════════════════════════════════════
# Route: Redirect to Install GitHub App
# ═══════════════════════════════════════════════════════════════

@router.get("/github-app/install")
async def install_github_app(
    request: Request,
    repo: Optional[str] = Query(None, description="Target repo (e.g., owner/repo)"),
):
    """User ko GitHub App install page pe redirect karo.

    Optional: `repo` query param de sakte ho specific repo ke liye.
    Example: /api/v1/github-app/install?repo=SiddharthSahai10/RIFT-Continnum
    """
    svc = get_github_app_service()

    if not svc.app_slug:
        raise HTTPException(
            status_code=500,
            detail="GitHub App configure nahi hai. GITHUB_APP_SLUG set karo .env mein.",
        )

    # CSRF state generate karo
    state = str(uuid4())
    _pending_states[state] = {
        "repo": repo,
        "created_at": str(request.scope.get("app", "")),
    }

    install_url = svc.get_installation_url(
        repo_full_name=repo,
        state=state,
    )

    logger.info(
        "Redirecting user to GitHub App install",
        repo=repo,
        state=state[:8] + "...",
    )

    return RedirectResponse(url=install_url, status_code=302)


# ═══════════════════════════════════════════════════════════════
# Route: Installation Callback
# ═══════════════════════════════════════════════════════════════

@router.get("/github-app/callback")
async def github_app_callback(
    request: Request,
    installation_id: int = Query(..., description="GitHub dwara diya gaya installation ID"),
    setup_action: str = Query("install", description="install ya update"),
    state: Optional[str] = Query(None, description="CSRF state"),
):
    """GitHub App install hone ke baad yeh route call hota hai.

    GitHub yahan redirect karta hai jab user App install kar leta hai.
    installation_id query param mein aata hai.

    Flow:
    1. installation_id receive karo
    2. Installation details fetch karo
    3. Installation token generate karo (verify ke liye)
    4. User ko frontend pe redirect karo success message ke saath
    """
    logger.info(
        "GitHub App callback received",
        installation_id=installation_id,
        setup_action=setup_action,
    )

    svc = get_github_app_service()

    # Validate installation
    result = await svc.handle_installation_callback(
        installation_id=installation_id,
        setup_action=setup_action,
    )

    # State check (optional — agar state available hai toh repo bhi pata hoga)
    intended_repo = None
    if state and state in _pending_states:
        pending = _pending_states.pop(state)
        intended_repo = pending.get("repo")

    if result["status"] == "success":
        # Token test karo — verify karo ki installation kaam kar raha hai
        try:
            token = await svc.get_installation_token(installation_id)
            result["token_valid"] = True
            result["token_preview"] = token[:8] + "..."

            # Agar specific repo tha, toh uski access verify karo
            if intended_repo:
                result["intended_repo"] = intended_repo
        except Exception as e:
            result["token_valid"] = False
            result["token_error"] = str(e)

        # Redirect to frontend with success
        frontend_url = settings.FRONTEND_URL or "http://localhost:5173"
        redirect_params = (
            f"?github_app=installed"
            f"&installation_id={installation_id}"
            f"&account={result.get('account', 'unknown')}"
        )
        # Agar specific repo tha toh usse bhi URL mein daal do
        if intended_repo:
            redirect_params += f"&repo={intended_repo}"
        redirect_url = f"{frontend_url}/{redirect_params}"

        logger.info(
            "GitHub App installed successfully",
            installation_id=installation_id,
            account=result.get("account"),
        )

        return RedirectResponse(url=redirect_url, status_code=302)

    # Error case
    raise HTTPException(
        status_code=400,
        detail=f"Installation failed: {result.get('error', 'Unknown error')}",
    )


# ═══════════════════════════════════════════════════════════════
# Route: List All Installations
# ═══════════════════════════════════════════════════════════════

@router.get("/github-app/installations")
async def list_installations():
    """GitHub App ke saare installations list karo.

    Admin endpoint — shows which accounts/repos have the app installed.
    """
    svc = get_github_app_service()

    if not svc.is_app_configured:
        raise HTTPException(
            status_code=400,
            detail="GitHub App configure nahi hai",
        )

    installations = await svc.list_all_installations()
    return {
        "total": len(installations),
        "installations": installations,
    }


# ═══════════════════════════════════════════════════════════════
# Route: Test Token for Repo
# ═══════════════════════════════════════════════════════════════

@router.post("/github-app/token-test", response_model=TokenTestResponse)
async def test_token_for_repo(body: TokenTestRequest):
    """Kisi repo ke liye token resolve karo aur test karo.

    Batayega ki App token use ho raha hai ya PAT.
    """
    svc = get_github_app_service()

    try:
        token, auth_method = await svc.get_token_for_repo(body.owner, body.repo)

        # Check installation_id agar App use hua
        installation_id = None
        if auth_method == "github_app":
            installation_id = await svc.find_installation_for_repo(body.owner, body.repo)

        return TokenTestResponse(
            auth_method=auth_method,
            token_preview=token[:8] + "...",
            installation_id=installation_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Token resolve failed: {str(e)}",
        )


# ═══════════════════════════════════════════════════════════════
# Route: Installation repos for an installation
# ═══════════════════════════════════════════════════════════════

@router.get("/github-app/installations/{installation_id}/repos")
async def list_installation_repos(installation_id: int):
    """Ek installation ke accessible repos dikhao."""
    svc = get_github_app_service()

    if not svc.is_app_configured:
        raise HTTPException(status_code=400, detail="GitHub App configure nahi hai")

    repos = await svc.list_installation_repos(installation_id)
    return {
        "installation_id": installation_id,
        "total": len(repos),
        "repositories": repos,
    }
