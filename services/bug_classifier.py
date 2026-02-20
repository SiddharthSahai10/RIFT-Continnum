"""Bug type classifier for hackathon-format output.

Maps detected errors to one of the six canonical bug types:
    LINTING | SYNTAX | LOGIC | TYPE_ERROR | IMPORT | INDENTATION
"""

import re
from typing import Dict, List, Optional, Tuple


# Canonical bug types
BUG_TYPES = [
    "LINTING",
    "SYNTAX",
    "LOGIC",
    "TYPE_ERROR",
    "IMPORT",
    "INDENTATION",
]


# ── Mapping tables ──────────────────────────────────────────

_ERROR_TYPE_MAP: Dict[str, str] = {
    # Python
    "SyntaxError": "SYNTAX",
    "IndentationError": "INDENTATION",
    "TabError": "INDENTATION",
    "TypeError": "TYPE_ERROR",
    "ImportError": "IMPORT",
    "ModuleNotFoundError": "IMPORT",
    "NameError": "LOGIC",
    "AttributeError": "LOGIC",
    "ValueError": "LOGIC",
    "KeyError": "LOGIC",
    "IndexError": "LOGIC",
    "ZeroDivisionError": "LOGIC",
    "RuntimeError": "LOGIC",
    "AssertionError": "LOGIC",
    "UnboundLocalError": "LOGIC",
    "RecursionError": "LOGIC",
    "StopIteration": "LOGIC",
    "FileNotFoundError": "LOGIC",
    "PermissionError": "LOGIC",
    "OSError": "LOGIC",
    "IOError": "LOGIC",
    # JavaScript / TypeScript
    "ReferenceError": "LOGIC",
    "SyntaxError": "SYNTAX",
    "TypeError": "TYPE_ERROR",
    "RangeError": "LOGIC",
    "URIError": "LOGIC",
    "EvalError": "LOGIC",
    # Linting tools
    "LintError": "LINTING",
    "StyleError": "LINTING",
    # Test runner failures (from LogParser)
    "TestFailure": "LOGIC",
    "TestSuiteFailure": "LOGIC",
}

_MESSAGE_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Indentation
    (re.compile(r"unexpected indent|IndentationError|TabError|indentation", re.I), "INDENTATION"),
    # Syntax
    (re.compile(r"SyntaxError|invalid syntax|unexpected token|parsing error", re.I), "SYNTAX"),
    # Import
    (re.compile(r"ImportError|ModuleNotFoundError|cannot find module|No module named|Cannot resolve", re.I), "IMPORT"),
    # Type
    (re.compile(r"TypeError|type error|not callable|not iterable|is not a function", re.I), "TYPE_ERROR"),
    # Linting
    (re.compile(r"lint|flake8|pylint|eslint|E\d{3}|W\d{3}|C\d{3}|F\d{3}|unused|trailing whitespace|line too long", re.I), "LINTING"),
    # Logic (catch-all for runtime errors)
    (re.compile(r"NameError|KeyError|IndexError|ValueError|AttributeError|AssertionError|ReferenceError|undefined|is not defined", re.I), "LOGIC"),
]


def classify_bug_type(
    error_type: str,
    error_message: str = "",
    test_output: str = "",
) -> str:
    """Classify a detected error into a canonical bug type.

    Args:
        error_type: Exception/error class name (e.g. "TypeError")
        error_message: The error's descriptive message
        test_output: Full test runner output for additional context

    Returns:
        One of: LINTING, SYNTAX, LOGIC, TYPE_ERROR, IMPORT, INDENTATION
    """
    # 1. Direct mapping by error type name
    normalized = error_type.strip()
    if normalized in _ERROR_TYPE_MAP:
        return _ERROR_TYPE_MAP[normalized]

    # 2. Pattern matching against combined text
    combined = f"{error_type} {error_message} {test_output}"
    for pattern, bug_type in _MESSAGE_PATTERNS:
        if pattern.search(combined):
            return bug_type

    # 3. Fallback
    return "LOGIC"


def format_summary_line(
    bug_type: str,
    file_path: str,
    line_number: int,
    fix_description: str,
) -> str:
    """Format a single SUMMARY line in exact hackathon format.

    Example:
        LINTING error in src/utils.py line 15 → Fix: remove the import statement
    """
    return f"{bug_type} error in {file_path} line {line_number} \u2192 Fix: {fix_description}"
