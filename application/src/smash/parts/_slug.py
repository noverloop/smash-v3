"""Canonical-id slug helper.

Same mapping used by `build_assumptions.py` so JSON entries seeded from
`output/system_bom.csv` join cleanly to factory output.
"""
from __future__ import annotations

import re


def canonical_id(manf_pn: str) -> str:
    """Lowercase manf_pn, non-alphanumeric → underscore, collapsed."""
    s = manf_pn.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")
