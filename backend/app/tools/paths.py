"""Path allowlisting for file tools.

Every path a tool touches is resolved (following symlinks) and must land inside
one of the approved roots. Sensitive names (keys, credentials, env files, VCS
internals) are refused even inside an approved root.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from .registry import ToolError

# Never read or list these, even inside an approved directory.
DENIED_NAME_PATTERNS = (
    ".env",
    ".env.*",
    ".ssh",
    ".gnupg",
    ".aws",
    ".azure",
    ".kube",
    ".docker",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".git-credentials",
    ".git",
    "id_rsa*",
    "id_dsa*",
    "id_ecdsa*",
    "id_ed25519*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.keychain",
    "*.keychain-db",
    "credentials",
    "credentials.json",
    "secrets.json",
    "*.kdbx",
)
# Allowed even though they match a pattern above.
ALLOWED_OVERRIDES = (".env.example", ".env.sample", ".env.template")

# Skipped while walking (noise, not secrets).
SKIP_DIRS = frozenset(
    {
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".next",
        ".cache",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".turbo",
        ".Trash",
    }
)


def is_denied_name(name: str) -> bool:
    if name in ALLOWED_OVERRIDES:
        return False
    lowered = name.lower()
    return any(fnmatch.fnmatchcase(lowered, pat) for pat in DENIED_NAME_PATTERNS)


def display_path(path: Path) -> str:
    home = Path.home()
    try:
        return "~/" + str(path.relative_to(home))
    except ValueError:
        return str(path)


def resolve_allowed(raw: str, roots: list[Path], *, expect: str | None = None) -> Path:
    """Resolve a model-supplied path and verify it is inside an approved root.

    ``expect`` may be "file" or "dir". Relative paths are accepted only when
    exactly one root is approved (they are taken relative to it).
    """
    if not roots:
        raise ToolError(
            "No directories are approved for file access. Set NEXUS_ALLOWED_DIRS in "
            "backend/.env and restart the backend.",
            "no_approved_dirs",
        )
    if not raw or "\x00" in raw:
        raise ToolError("Path is empty or contains invalid characters.", "invalid_path")

    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        if len(roots) != 1:
            raise ToolError(
                "Use an absolute path; several directories are approved.", "invalid_path"
            )
        candidate = roots[0] / candidate

    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError:
        raise ToolError(f"Path not found: {raw}", "not_found") from None
    except (OSError, RuntimeError):
        raise ToolError(f"Cannot resolve path: {raw}", "invalid_path") from None

    root = next((r for r in roots if resolved == r or resolved.is_relative_to(r)), None)
    if root is None:
        raise ToolError(
            f"Access denied: {raw} is outside the approved directories.", "path_not_allowed"
        )
    rel_parts = resolved.relative_to(root).parts
    # Check both the resolved location and the path as written (symlink names).
    written_parts = candidate.parts[-len(rel_parts) :] if rel_parts else ()
    if any(is_denied_name(p) for p in (*rel_parts, *written_parts)):
        raise ToolError(f"Access denied: {raw} matches a protected name.", "path_denied")

    if expect == "file" and not resolved.is_file():
        raise ToolError(f"Not a file: {raw}", "not_a_file")
    if expect == "dir" and not resolved.is_dir():
        raise ToolError(f"Not a directory: {raw}", "not_a_directory")
    return resolved


def within_roots(path: Path, roots: list[Path]) -> bool:
    """True if ``path`` (already resolved) is inside an approved root."""
    return any(path == r or path.is_relative_to(r) for r in roots)
