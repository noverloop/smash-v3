"""LGA land-capacity guard — no board-to-board joint may overflow.

Wraps ``tools/land_audit.py``. The adaptive land placer assigns one land per
crossing signal first, then power-rail copies, then GND fill; if a joint has
more signals than lands it densifies the pitch, and only as a last resort
warns + drops nets. This test asserts that never happens: every gap in every
config carries all its signal + power lands within its land budget.

It also pins the known-saturated forward joints (wakeup→power,
power→companion) as a tripwire: they run at ~90-98 % utilization, so a change
that pushes a new cross-joint signal through them (instead of the roomy aft
battery gaps) will surface here as an overflow rather than a silent net drop.
"""
import sys

import pytest

from smash.roots import export_dir, git_repo_root

_EXPORT = str(export_dir())
_TOOLS = str(git_repo_root() / "tools")
for _p in (_EXPORT, _TOOLS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import generate_maximalist_system as G          # noqa: E402
import land_audit                               # noqa: E402  (tools/land_audit.py)


@pytest.mark.parametrize("config", list(G.CONFIGS))
def test_no_joint_overflows(config):
    """Every gap fits its crossing signals within its land budget."""
    rows = land_audit.audit(config)
    assert rows, f"{config}: no gaps analysed"
    overflowed = [
        f"{r['lhs']}→{r['rhs']}: {r['sig'] + r['pwr']} signal+power "
        f"lands > {r['lands']} total"
        for r in rows if r["overflow"]
    ]
    assert overflowed == [], (
        f"{config}: LGA joint(s) overflow — signals exceed lands:\n  "
        + "\n  ".join(overflowed)
    )


@pytest.mark.parametrize("config", list(G.CONFIGS))
def test_every_signal_has_a_land(config):
    """Signal-land count never exceeds the joint's total lands (the
    capacity invariant the connectivity audit relies on)."""
    for r in land_audit.audit(config):
        assert r["sig"] <= r["lands"], (
            f"{config} gap {r['gap']} ({r['lhs']}→{r['rhs']}): "
            f"{r['sig']} signals > {r['lands']} lands"
        )
