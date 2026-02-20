"""Git service for repository cloning and management."""

import asyncio
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config.logging_config import get_logger
from config.settings import get_settings

logger = get_logger(__name__)


@dataclass
class CloneResult:
    """Result of cloning a repository."""
    success: bool
    path: Optional[str] = None
    error: Optional[str] = None


class GitService:
    """Service for git operations.
    
    SECURITY:
    - Uses GitHub token for private repo access
    - Clones to isolated directories
    - Cleans up on failure
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.base_clone_dir = Path(self.settings.CLONE_DIR)
        self.base_clone_dir.mkdir(parents=True, exist_ok=True)
    
    async def clone_repository(
        self,
        repo_url: str,
        incident_id: str,
        branch: Optional[str] = None,
        depth: int = 1,
    ) -> CloneResult:
        """Clone a repository.
        
        Args:
            repo_url: Repository URL (https or ssh)
            incident_id: Incident ID for directory naming
            branch: Optional specific branch to clone
            depth: Clone depth (default: 1 for shallow)
            
        Returns:
            CloneResult with path or error
        """
        # Ensure base clone directory exists (macOS /tmp can be cleaned)
        self.base_clone_dir.mkdir(parents=True, exist_ok=True)
        
        # Prepare clone directory
        clone_path = self.base_clone_dir / f"repo-{incident_id}"
        
        # Clean if exists
        if clone_path.exists():
            shutil.rmtree(clone_path)
        
        # Prepare URL with token if needed
        clone_url = self._prepare_clone_url(repo_url)
        
        # Build clone command
        cmd = ["git", "clone"]
        
        if depth > 0:
            cmd.extend(["--depth", str(depth)])
        
        if branch:
            cmd.extend(["--branch", branch])
        
        cmd.extend([clone_url, str(clone_path)])
        
        try:
            # Run clone in subprocess
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._get_git_env(),
            )
            
            _, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=120,
            )
            
            if proc.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='replace')
                # Redact any token from error message
                error_msg = self._redact_token(error_msg)
                
                return CloneResult(
                    success=False,
                    error=f"Git clone failed: {error_msg[:500]}",
                )
            
            logger.info("Repository cloned", path=str(clone_path))
            
            return CloneResult(
                success=True,
                path=str(clone_path),
            )
        
        except asyncio.TimeoutError:
            # Cleanup on timeout
            if clone_path.exists():
                shutil.rmtree(clone_path, ignore_errors=True)
            
            return CloneResult(
                success=False,
                error="Git clone timed out",
            )
        
        except Exception as e:
            # Cleanup on error
            if clone_path.exists():
                shutil.rmtree(clone_path, ignore_errors=True)
            
            return CloneResult(
                success=False,
                error=f"Clone error: {str(e)}",
            )
    
    def _prepare_clone_url(self, url: str, token: Optional[str] = None) -> str:
        """Prepare clone URL with authentication if needed.
        
        Args:
            url: Repo URL
            token: Optional explicit token (e.g., from GitHub App).
                   If not provided, falls back to PAT from settings.
        """
        # Explicit token (GitHub App ya manual)
        if token and url.startswith("https://github.com/"):
            return url.replace(
                "https://github.com/",
                f"https://x-access-token:{token}@github.com/",
            )
        
        # PAT fallback
        if not token and self.settings.GITHUB_TOKEN:
            pat = self.settings.GITHUB_TOKEN.get_secret_value()
            if url.startswith("https://github.com/"):
                return url.replace(
                    "https://github.com/",
                    f"https://x-access-token:{pat}@github.com/",
                )
        
        return url
    
    async def clone_with_smart_auth(
        self,
        repo_url: str,
        incident_id: str,
        branch: Optional[str] = None,
        depth: int = 0,
    ) -> CloneResult:
        """Smart clone — GitHub App token pehle try karta hai, phir PAT.
        
        Yeh method GitHubAppService use karta hai best token find karne ke liye.
        Agar GitHub App installed hai repo pe → App token use hoga.
        Warna PAT fallback mein use hoga.
        
        Args:
            repo_url: GitHub HTTPS URL
            incident_id: Clone directory naming ke liye
            branch: Optional branch
            depth: Clone depth (0 = full)
            
        Returns:
            CloneResult with auth_method info
        """
        import re
        
        # Parse owner/repo
        match = re.search(r'github\.com[:/]([^/]+)/([^/.]+)', repo_url)
        if not match:
            # Fallback to normal clone agar URL parse nahi ho raha
            return await self.clone_repository(repo_url, incident_id, branch, depth)
        
        owner, repo = match.group(1), match.group(2).replace('.git', '')
        
        try:
            from services.github_app_service import get_github_app_service
            app_svc = get_github_app_service()
            
            token, auth_method = await app_svc.get_token_for_repo(owner, repo)
            
            logger.info(
                "Clone using smart auth",
                repo=f"{owner}/{repo}",
                auth_method=auth_method,
            )
            
            # Clone with resolved token
            self.base_clone_dir.mkdir(parents=True, exist_ok=True)
            clone_path = self.base_clone_dir / f"repo-{incident_id}"
            
            if clone_path.exists():
                shutil.rmtree(clone_path)
            
            clone_url = self._prepare_clone_url(repo_url, token=token)
            
            cmd = ["git", "clone"]
            if depth > 0:
                cmd.extend(["--depth", str(depth)])
            if branch:
                cmd.extend(["--branch", branch])
            cmd.extend([clone_url, str(clone_path)])
            
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._get_git_env(),
            )
            
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            
            if proc.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='replace')
                error_msg = self._redact_token(error_msg, extra_token=token)
                return CloneResult(success=False, error=f"Clone failed ({auth_method}): {error_msg[:500]}")
            
            logger.info(
                "Repository cloned with smart auth",
                path=str(clone_path),
                auth_method=auth_method,
            )
            
            return CloneResult(success=True, path=str(clone_path))
            
        except Exception as e:
            logger.warning(
                "Smart auth clone failed, falling back to standard clone",
                error=str(e),
            )
            return await self.clone_repository(repo_url, incident_id, branch, depth)
    
    def _get_git_env(self) -> dict:
        """Get environment for git commands."""
        env = os.environ.copy()
        
        # Disable interactive prompts
        env["GIT_TERMINAL_PROMPT"] = "0"
        
        return env
    
    def _redact_token(self, message: str, extra_token: Optional[str] = None) -> str:
        """Redact any tokens from error messages."""
        if self.settings.GITHUB_TOKEN:
            token = self.settings.GITHUB_TOKEN.get_secret_value()
            message = message.replace(token, "<REDACTED_TOKEN>")
        if extra_token:
            message = message.replace(extra_token, "<REDACTED_TOKEN>")
        return message
    
    def cleanup_clone(self, path: str) -> None:
        """Remove a cloned repository.
        
        Args:
            path: Path to repository to remove
        """
        try:
            clone_path = Path(path)
            if clone_path.exists():
                shutil.rmtree(clone_path)
                logger.info("Cleaned up clone", path=path)
        except Exception as e:
            logger.warning("Failed to cleanup clone", path=path, error=str(e))
    
    def checkout_branch(
        self,
        repo_path: str,
        branch: str,
        create: bool = False,
    ) -> bool:
        """Checkout a branch in a repository.
        
        Args:
            repo_path: Path to repository
            branch: Branch name
            create: Whether to create the branch if it doesn't exist
            
        Returns:
            True if successful
        """
        try:
            cmd = ["git", "checkout"]
            if create:
                cmd.append("-b")
            cmd.append(branch)
            
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                timeout=30,
            )
            
            return result.returncode == 0
        
        except Exception:
            return False
    
    def get_current_branch(self, repo_path: str) -> Optional[str]:
        """Get the current branch of a repository.
        
        Args:
            repo_path: Path to repository
            
        Returns:
            Current branch name or None
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        
        except Exception:
            return None
    
    def get_commit_sha(self, repo_path: str, ref: str = "HEAD") -> Optional[str]:
        """Get the SHA of a commit.
        
        Args:
            repo_path: Path to repository
            ref: Git reference (default: HEAD)
            
        Returns:
            Commit SHA or None
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", ref],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        
        except Exception:
            return None
