"""Shared storage path resolution for analyses artifacts.

This centralizes the canonical analyses root so every runtime/profile reads and
writes the same on-disk store instead of defaulting to the checkout-local
`analyses/` directory.
"""

from __future__ import annotations

import os
from pathlib import Path

ANALYSES_DIR_ENV_VAR = "SA_ANALYSES_DIR"
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ANALYSES_DIR = (REPO_ROOT / "analyses").resolve()


def _read_dotenv_value(key: str) -> str | None:
    """Read one value from the repo .env without loading every variable globally."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return None

    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            current_key, value = line.split("=", 1)
            if current_key.strip() != key:
                continue
            cleaned = value.strip().strip('"').strip("'")
            return cleaned or None
    except OSError:
        return None

    return None


def _raw_analyses_dir() -> str | None:
    return os.getenv(ANALYSES_DIR_ENV_VAR) or _read_dotenv_value(ANALYSES_DIR_ENV_VAR)


def get_analyses_dir(*, create: bool = True) -> Path:
    """Return the canonical analyses root for this runtime."""
    raw = _raw_analyses_dir()
    if raw:
        candidate = Path(raw).expanduser()
        path = (candidate if candidate.is_absolute() else REPO_ROOT / candidate).resolve()
    else:
        path = DEFAULT_ANALYSES_DIR

    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def get_preload_root(*, create: bool = True) -> Path:
    """Return the canonical preload root under analyses/."""
    path = get_analyses_dir(create=create) / "preload"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path
