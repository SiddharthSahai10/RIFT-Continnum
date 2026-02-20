"""GitHub App Service — Installation + Access Token management.

Yeh service GitHub App ke through authentication handle karti hai.
Webhook nahi use karti — instead polling + redirect-based flow hai.

Flow:
1. User ko GitHub App install page pe redirect karo
2. Installation callback pe installation_id milta hai
3. Installation Access Token (IAT) banao via JWT → GitHub API
4. IAT ko use karo repo clone, push, PR create ke liye

Falls back to PAT (Personal Access Token) agar App configure nahi hai.
"""

import time
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx
import jwt  # PyJWT

from config.logging_config import get_logger
from config.settings import get_settings

logger = get_logger(__name__)


class GitHubAppService:
    """GitHub App ke through repo access manage karta hai.

    PRIMARY: GitHub App (developer-owned)
    SECONDARY: Fine-grained PAT (fallback)

    Bina webhook ke kaam karta hai — polling + redirect approach.
    """

    GITHUB_API = "https://api.github.com"

    def __init__(self):
        self.settings = get_settings()

        # GitHub App credentials (from .env)
        self.app_id: Optional[str] = self.settings.GITHUB_APP_ID
        self.private_key_raw: Optional[str] = None
        self.client_id: Optional[str] = self.settings.GITHUB_APP_CLIENT_ID
        self.client_secret: Optional[str] = None
        self.app_slug: Optional[str] = self.settings.GITHUB_APP_SLUG

        # Load private key
        if self.settings.GITHUB_APP_PRIVATE_KEY:
            self.private_key_raw = self.settings.GITHUB_APP_PRIVATE_KEY.get_secret_value()
        elif self.settings.GITHUB_APP_PRIVATE_KEY_PATH:
            key_path = Path(self.settings.GITHUB_APP_PRIVATE_KEY_PATH)
            # Agar relative path hai, toh project root se resolve karo
            if not key_path.is_absolute():
                key_path = Path(__file__).parent.parent / key_path
            if key_path.exists():
                self.private_key_raw = key_path.read_text()
                logger.info("GitHub App private key loaded from file", path=str(key_path))
            else:
                logger.warning("GitHub App private key file not found", path=str(key_path))

        # Load client secret
        if self.settings.GITHUB_APP_CLIENT_SECRET:
            self.client_secret = self.settings.GITHUB_APP_CLIENT_SECRET.get_secret_value()

        # In-memory cache for installation tokens
        # {installation_id: {"token": str, "expires_at": datetime}}
        self._token_cache: Dict[int, Dict[str, Any]] = {}

        # Installation ID cache per repo
        # {"owner/repo": installation_id}
        self._installation_cache: Dict[str, int] = {}

    # ═══════════════════════════════════════════════════════════
    # Availability Check
    # ═══════════════════════════════════════════════════════════

    @property
    def is_app_configured(self) -> bool:
        """Check karo ki GitHub App properly configure hai ya nahi."""
        return bool(self.app_id and self.private_key_raw)

    @property
    def has_pat_fallback(self) -> bool:
        """PAT token available hai ya nahi."""
        return bool(self.settings.GITHUB_TOKEN)

    def get_auth_method(self) -> str:
        """Current authentication method return karo."""
        if self.is_app_configured:
            return "github_app"
        elif self.has_pat_fallback:
            return "pat"
        else:
            return "none"

    # ═══════════════════════════════════════════════════════════
    # JWT Generation (GitHub App ke liye)
    # ═══════════════════════════════════════════════════════════

    def _generate_jwt(self) -> str:
        """GitHub App ke liye JWT token generate karo.

        JWT 10 minute ke liye valid hota hai.
        Ise use karte hain Installation Access Token lene ke liye.
        """
        if not self.app_id or not self.private_key_raw:
            raise ValueError("GitHub App ID aur Private Key dono chahiye JWT ke liye")

        now = int(time.time())
        payload = {
            "iat": now - 60,          # Issued at: 60 sec pehle (clock skew handle)
            "exp": now + (9 * 60),     # Expires: 9 min mein (max 10 min allowed)
            "iss": self.app_id,        # Issuer: App ID
        }

        token = jwt.encode(payload, self.private_key_raw, algorithm="RS256")
        logger.debug("JWT generated for GitHub App", app_id=self.app_id)
        return token

    # ═══════════════════════════════════════════════════════════
    # Installation URL (User ko redirect karne ke liye)
    # ═══════════════════════════════════════════════════════════

    def get_installation_url(
        self,
        repo_full_name: Optional[str] = None,
        state: Optional[str] = None,
    ) -> str:
        """GitHub App install karne ka URL generate karo.

        Args:
            repo_full_name: "owner/repo" — specific repo ke liye install karna ho toh
            state: CSRF protection ke liye random state string

        Returns:
            Install page ka URL
        """
        if not self.app_slug:
            raise ValueError("GITHUB_APP_SLUG set nahi hai .env mein")

        base_url = f"https://github.com/apps/{self.app_slug}/installations/new"

        params = {}
        if state:
            params["state"] = state

        # Specific repo ke liye suggested for installation
        if repo_full_name:
            params["suggested_target_id"] = ""  # GitHub will show the repo suggestion
            # Actually GitHub uses this URL pattern for specific repos:
            # https://github.com/apps/{slug}/installations/new/permissions
            #   ?target_id=OWNER_ID&suggested_target_id=OWNER_ID
            # But simpler approach: just add the repo path in state so callback
            # knows which repo the user intended

        if params:
            return f"{base_url}?{urlencode(params)}"
        return base_url

    # ═══════════════════════════════════════════════════════════
    # Installation Callback (Redirect ke baad)
    # ═══════════════════════════════════════════════════════════

    async def handle_installation_callback(
        self,
        installation_id: int,
        setup_action: str = "install",
    ) -> Dict[str, Any]:
        """Installation callback handle karo.

        Jab user GitHub App install karta hai, GitHub redirect karta hai
        hamari callback URL pe installation_id ke saath.

        Args:
            installation_id: GitHub dwara diya gaya installation ID
            setup_action: "install" ya "update"

        Returns:
            Installation details dict
        """
        logger.info(
            "GitHub App installation callback received",
            installation_id=installation_id,
            setup_action=setup_action,
        )

        # Installation ki details fetch karo
        try:
            details = await self._get_installation_details(installation_id)
            return {
                "status": "success",
                "installation_id": installation_id,
                "setup_action": setup_action,
                "account": details.get("account", {}).get("login", "unknown"),
                "repositories": details.get("repository_selection", "all"),
                "permissions": details.get("permissions", {}),
            }
        except Exception as e:
            logger.error("Installation callback failed", error=str(e))
            return {
                "status": "error",
                "installation_id": installation_id,
                "error": str(e),
            }

    async def _get_installation_details(self, installation_id: int) -> Dict[str, Any]:
        """Installation ki details GitHub API se fetch karo."""
        jwt_token = self._generate_jwt()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.GITHUB_API}/app/installations/{installation_id}",
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            if response.status_code != 200:
                raise RuntimeError(
                    f"Installation details fetch failed: {response.status_code} - {response.text}"
                )

            return response.json()

    # ═══════════════════════════════════════════════════════════
    # Installation Access Token (IAT)
    # ═══════════════════════════════════════════════════════════

    async def get_installation_token(self, installation_id: int) -> str:
        """Installation Access Token (IAT) lo.

        Token 1 hour ke liye valid hota hai.
        Cache me rakha jaata hai, expire hone se pehle refresh hota hai.

        Args:
            installation_id: GitHub App installation ID

        Returns:
            Installation Access Token string
        """
        # Check cache first
        cached = self._token_cache.get(installation_id)
        if cached:
            expires_at = cached["expires_at"]
            # 5 min pehle hi refresh kar lenge
            if datetime.now(timezone.utc) < expires_at:
                logger.debug("Using cached installation token", installation_id=installation_id)
                return cached["token"]

        # Naya token generate karo
        jwt_token = self._generate_jwt()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.GITHUB_API}/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            if response.status_code != 201:
                raise RuntimeError(
                    f"Installation token fetch failed: {response.status_code} - {response.text}"
                )

            data = response.json()
            token = data["token"]
            expires_str = data["expires_at"]  # e.g., "2024-01-01T01:00:00Z"

            # Parse expiry aur cache mein daal do
            from dateutil.parser import isoparse
            expires_at = isoparse(expires_str)
            # 5 minute pehle expire karo safety ke liye
            from datetime import timedelta
            safe_expiry = expires_at - timedelta(minutes=5)

            self._token_cache[installation_id] = {
                "token": token,
                "expires_at": safe_expiry,
            }

            logger.info(
                "Installation token generated",
                installation_id=installation_id,
                expires_at=expires_str,
            )

            return token

    # ═══════════════════════════════════════════════════════════
    # Find Installation for a Repo (Polling-based, no webhook)
    # ═══════════════════════════════════════════════════════════

    async def find_installation_for_repo(
        self, owner: str, repo: str
    ) -> Optional[int]:
        """Kisi repo ke liye GitHub App installation ID find karo.

        Yeh polling-based approach hai — webhook ki zaroorat nahi.
        GitHub API call karke dekhte hain ki App install hai ya nahi.

        Args:
            owner: Repo owner (e.g., "SiddharthSahai10")
            repo: Repo name (e.g., "RIFT-Continnum")

        Returns:
            installation_id agar App install hai, None agar nahi
        """
        cache_key = f"{owner}/{repo}"

        # Check cache
        if cache_key in self._installation_cache:
            return self._installation_cache[cache_key]

        if not self.is_app_configured:
            return None

        jwt_token = self._generate_jwt()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.GITHUB_API}/repos/{owner}/{repo}/installation",
                    headers={
                        "Authorization": f"Bearer {jwt_token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    installation_id = data["id"]
                    self._installation_cache[cache_key] = installation_id
                    logger.info(
                        "Found GitHub App installation for repo",
                        repo=cache_key,
                        installation_id=installation_id,
                    )
                    return installation_id
                elif response.status_code == 404:
                    logger.info(
                        "GitHub App not installed on repo — will use PAT fallback",
                        repo=cache_key,
                    )
                    return None
                else:
                    logger.warning(
                        "Unexpected response checking installation",
                        status=response.status_code,
                        body=response.text[:200],
                    )
                    return None

        except Exception as e:
            logger.warning("Error checking installation for repo", error=str(e))
            return None

    # ═══════════════════════════════════════════════════════════
    # Smart Token Resolver (App Token > PAT — automatic fallback)
    # ═══════════════════════════════════════════════════════════

    async def get_token_for_repo(self, owner: str, repo: str) -> Tuple[str, str]:
        """Kisi repo ke liye best available token return karo.

        Priority:
        1. GitHub App Installation Token (agar app installed hai)
        2. PAT (Personal Access Token — fallback)

        Args:
            owner: Repo owner
            repo: Repo name

        Returns:
            Tuple of (token, auth_method) where auth_method is "github_app" or "pat"
        """
        # Try GitHub App first
        if self.is_app_configured:
            installation_id = await self.find_installation_for_repo(owner, repo)
            if installation_id:
                try:
                    token = await self.get_installation_token(installation_id)
                    return token, "github_app"
                except Exception as e:
                    logger.warning(
                        "GitHub App token failed, falling back to PAT",
                        error=str(e),
                    )

        # Fallback to PAT
        if self.has_pat_fallback:
            token = self.settings.GITHUB_TOKEN.get_secret_value()
            return token, "pat"

        raise RuntimeError(
            "Na GitHub App configure hai, na PAT token hai. "
            "Kuch toh set karo .env mein bhai!"
        )

    # ═══════════════════════════════════════════════════════════
    # List All Installations (admin overview)
    # ═══════════════════════════════════════════════════════════

    async def list_all_installations(self) -> List[Dict[str, Any]]:
        """GitHub App ke saare installations list karo.

        Returns:
            List of installation dicts
        """
        if not self.is_app_configured:
            return []

        jwt_token = self._generate_jwt()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.GITHUB_API}/app/installations",
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            if response.status_code != 200:
                logger.error("Failed to list installations", status=response.status_code)
                return []

            installations = response.json()
            return [
                {
                    "id": inst["id"],
                    "account": inst.get("account", {}).get("login", "unknown"),
                    "repository_selection": inst.get("repository_selection", "unknown"),
                    "created_at": inst.get("created_at"),
                    "updated_at": inst.get("updated_at"),
                }
                for inst in installations
            ]

    # ═══════════════════════════════════════════════════════════
    # List Installation Repos
    # ═══════════════════════════════════════════════════════════

    async def list_installation_repos(self, installation_id: int) -> List[Dict[str, str]]:
        """Installation ke accessible repos list karo.

        Args:
            installation_id: GitHub App installation ID

        Returns:
            List of {name, full_name, url} dicts
        """
        token = await self.get_installation_token(installation_id)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.GITHUB_API}/installation/repositories",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            if response.status_code != 200:
                logger.error("Failed to list repos", status=response.status_code)
                return []

            data = response.json()
            return [
                {
                    "name": r["name"],
                    "full_name": r["full_name"],
                    "url": r["html_url"],
                    "private": r.get("private", False),
                }
                for r in data.get("repositories", [])
            ]

    def clear_cache(self):
        """Token aur installation cache clear karo."""
        self._token_cache.clear()
        self._installation_cache.clear()
        logger.info("GitHub App caches cleared")


# ════════════════════════════════════════════════════════════════
# Singleton
# ════════════════════════════════════════════════════════════════

_github_app_service: Optional[GitHubAppService] = None


def get_github_app_service() -> GitHubAppService:
    """Singleton GitHub App service instance laao."""
    global _github_app_service
    if _github_app_service is None:
        _github_app_service = GitHubAppService()
    return _github_app_service
