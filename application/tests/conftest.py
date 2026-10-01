"""Shared roots for smash tests.

After the package move, tests live at ``Export/application/tests``.
``EXPORT_ROOT`` is where ``generate_maximalist_system.py`` lives.
``GIT_ROOT`` is the smash-electronics checkout (``tools/``, ``library_kicad/``).
"""
from __future__ import annotations

import sys
from pathlib import Path

APPLICATION_DIR = Path(__file__).resolve().parent.parent
EXPORT_ROOT = APPLICATION_DIR.parent
GIT_ROOT = EXPORT_ROOT.parent

if str(EXPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(EXPORT_ROOT))
