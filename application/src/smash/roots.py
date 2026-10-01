"""Filesystem roots for the smash package.

The package lives at ``Export/application/src/smash``. The generator and
its ``dist/`` output live in ``Export/``. Repo-wide assets such as
``library_kicad/`` and ``documentation/`` stay at the git root.
"""
from __future__ import annotations

from pathlib import Path

_SMASH_DIR = Path(__file__).resolve().parent


def application_dir() -> Path:
    """``Export/application`` — pyproject, src, tests."""
    return _SMASH_DIR.parents[1]


def export_dir() -> Path:
    """``Export/`` — generator script, application package, dist/."""
    return _SMASH_DIR.parents[2]


def git_repo_root() -> Path:
    """Smash electronics git root (``library_kicad/``, ``tools/``, …)."""
    for p in _SMASH_DIR.parents:
        if (p / "library_kicad").is_dir():
            return p
        if (p / ".git").exists() and (p / "tools").is_dir():
            return p
    return export_dir().parent


def resolve_repo_path(rel: str | Path) -> Path:
    """Resolve a path stored relative to Export/ or the git root.

    Artifact strings like ``application/src/smash/parts/sources/…`` are
    relative to ``Export/``. ``library_kicad/…`` is relative to the git
    root. Tries Export first, then the git root.
    """
    p = Path(rel)
    if p.is_absolute():
        return p
    for root in (export_dir(), git_repo_root()):
        cand = (root / p).resolve()
        if cand.exists():
            return cand
    return (git_repo_root() / p).resolve()
