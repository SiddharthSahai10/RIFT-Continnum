"""Test framework detection and test file discovery."""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config.logging_config import get_logger

logger = get_logger(__name__)

# ── Framework detection signals ──────────────────────────────

_FRAMEWORK_FILES: Dict[str, List[str]] = {
    "pytest": ["pytest.ini", "setup.cfg", "pyproject.toml", "conftest.py"],
    "unittest": [],  # fallback if .py test files exist
    "jest": ["jest.config.js", "jest.config.ts", "jest.config.mjs", "jest.config.cjs"],
    "mocha": [".mocharc.yml", ".mocharc.yaml", ".mocharc.json", ".mocharc.js"],
    "vitest": ["vitest.config.ts", "vitest.config.js", "vitest.config.mts"],
    "go_test": ["go.mod"],
    "cargo_test": ["Cargo.toml"],
}

_FRAMEWORK_DEPS: Dict[str, str] = {
    "pytest": "pytest",
    "jest": "jest",
    "mocha": "mocha",
    "vitest": "vitest",
}

# Test file patterns per framework
_TEST_GLOBS: Dict[str, List[str]] = {
    "pytest": ["**/test_*.py", "**/*_test.py", "**/tests/*.py", "**/tests/**/*.py"],
    "unittest": ["**/test_*.py", "**/*_test.py", "**/tests/*.py"],
    "jest": ["**/*.test.js", "**/*.test.ts", "**/*.test.jsx", "**/*.test.tsx",
             "**/*.spec.js", "**/*.spec.ts", "**/*.spec.jsx", "**/*.spec.tsx",
             "**/__tests__/**/*.js", "**/__tests__/**/*.ts"],
    "mocha": ["**/test/**/*.js", "**/test/**/*.ts", "**/*.test.js", "**/*.spec.js"],
    "vitest": ["**/*.test.ts", "**/*.test.js", "**/*.spec.ts", "**/*.spec.js"],
    "go_test": ["**/*_test.go"],
    "cargo_test": ["**/tests/**/*.rs", "**/src/**/*test*.rs"],
}

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", "venv", ".venv",
    "env", ".env", "dist", "build", ".next", ".nuxt",
    "coverage", ".pytest_cache", ".mypy_cache", "htmlcov",
    ".tox", "eggs", "*.egg-info",
}


def detect_test_framework(repo_path: str) -> str:
    """Detect the primary test framework used in a repository.

    Args:
        repo_path: Path to the cloned repository root

    Returns:
        Framework identifier string (e.g. "pytest", "jest", "unittest")
    """
    root = Path(repo_path)

    # 1. Check for framework-specific config files
    for framework, config_files in _FRAMEWORK_FILES.items():
        for cfg in config_files:
            if (root / cfg).exists():
                # Extra check: for pyproject.toml, look for [tool.pytest]
                if cfg == "pyproject.toml" and framework == "pytest":
                    content = (root / cfg).read_text(errors="replace")
                    if "[tool.pytest" in content or "pytest" in content:
                        logger.info("Detected framework via pyproject.toml", framework=framework)
                        return framework
                    continue
                logger.info("Detected framework via config file", framework=framework, file=cfg)
                return framework

    # 2. Check package.json dependencies
    pkg_json = root / "package.json"
    if pkg_json.exists():
        import json
        try:
            pkg = json.loads(pkg_json.read_text(errors="replace"))
            all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            for fw, dep_name in _FRAMEWORK_DEPS.items():
                if dep_name in all_deps:
                    logger.info("Detected framework via package.json", framework=fw)
                    return fw
        except json.JSONDecodeError:
            pass

    # 3. Check for Python test files → default to pytest
    py_test_files = list(root.rglob("test_*.py")) + list(root.rglob("*_test.py"))
    py_test_files = [f for f in py_test_files if not _in_skip_dir(f, root)]
    if py_test_files:
        # Check if pytest is importable in requirements
        req_files = ["requirements.txt", "requirements-dev.txt", "dev-requirements.txt"]
        for req_name in req_files:
            req_file = root / req_name
            if req_file.exists():
                content = req_file.read_text(errors="replace").lower()
                if "pytest" in content:
                    return "pytest"
        return "pytest"  # default for Python

    # 4. Check for JS test files
    js_patterns = ["*.test.js", "*.test.ts", "*.spec.js", "*.spec.ts"]
    for pat in js_patterns:
        matches = [f for f in root.rglob(pat) if not _in_skip_dir(f, root)]
        if matches:
            return "jest"  # default for JS

    # 5. Go
    if list(root.rglob("*_test.go")):
        return "go_test"

    # 6. Rust
    if (root / "Cargo.toml").exists():
        return "cargo_test"

    return "pytest"  # ultimate fallback


def discover_tests(repo_path: str, framework: Optional[str] = None) -> List[str]:
    """Discover all test files in the repository.

    Args:
        repo_path: Repository root path
        framework: Pre-detected framework (auto-detected if None)

    Returns:
        List of relative test file paths
    """
    if framework is None:
        framework = detect_test_framework(repo_path)

    root = Path(repo_path)
    globs = _TEST_GLOBS.get(framework, _TEST_GLOBS["pytest"])

    test_files: List[str] = []
    seen: set = set()

    for pattern in globs:
        # rglob already searches recursively, so strip leading **/ prefix properly
        # NOTE: do NOT use lstrip("**/") — it's char-based and breaks *.test.js → .test.js
        clean = pattern
        while clean.startswith("**/"):
            clean = clean[3:]
        for match in root.rglob(clean):
            if _in_skip_dir(match, root):
                continue
            rel = str(match.relative_to(root))
            if rel not in seen:
                seen.add(rel)
                test_files.append(rel)

    test_files.sort()
    logger.info(
        "Discovered test files",
        framework=framework,
        count=len(test_files),
    )
    return test_files


def get_test_command(framework: str, repo_path: str = "") -> List[str]:
    """Return the shell command to run tests for the given framework.

    For JS/TS projects, reads ``package.json`` ``scripts.test`` so that
    framework wrappers like ``react-scripts test`` are used instead of
    bare ``npx jest``.  This is critical for CRA / Next.js / Vite repos
    that configure Babel/SWC through their own test runner.

    Args:
        framework: Framework identifier
        repo_path: Optional path to the repository root (for package.json lookup)

    Returns:
        Command as list of strings
    """
    # ── JS/TS: prefer the project's own test script ──────────────────
    if repo_path and framework in ("jest", "mocha", "vitest"):
        import json as _json
        pkg_json = Path(repo_path) / "package.json"
        if pkg_json.exists():
            try:
                pkg = _json.loads(pkg_json.read_text(errors="replace"))
                test_script = pkg.get("scripts", {}).get("test", "")
                if test_script:
                    # Strip trailing comments / shell operators for safety
                    test_script = test_script.split("&&")[0].split("||")[0].strip()
                    parts = test_script.split()

                    # react-scripts / craco / next → ensure non-interactive
                    if any(runner in test_script for runner in [
                        "react-scripts", "craco", "react-app-rewired",
                    ]):
                        if "--watchAll=false" not in test_script:
                            parts.append("--watchAll=false")

                    # Use npx to resolve locally-installed binaries
                    if parts and parts[0] not in ("npx", "npm", "node"):
                        parts = ["npx"] + parts

                    logger.info("Using project test script", command=parts, source="package.json")
                    return parts
            except Exception:
                pass

    # ── Fallback: generic commands ───────────────────────────────────
    commands: Dict[str, List[str]] = {
        "pytest": ["python", "-m", "pytest", "-v", "--tb=short", "--no-header", "-q"],
        "unittest": ["python", "-m", "unittest", "discover", "-v"],
        "jest": ["npx", "jest", "--verbose", "--no-coverage", "--forceExit", "--detectOpenHandles"],
        "mocha": ["npx", "mocha", "--recursive"],
        "vitest": ["npx", "vitest", "run", "--reporter=verbose"],
        "go_test": ["go", "test", "./...", "-v"],
        "cargo_test": ["cargo", "test", "--", "--nocapture"],
    }
    return commands.get(framework, commands["pytest"])


def _in_skip_dir(path: Path, root: Path) -> bool:
    """Check if a path is inside a directory that should be skipped."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    parts = rel.parts
    return any(part in SKIP_DIRS for part in parts)
