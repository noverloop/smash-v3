"""Tests for smash.layout.fold — the compact panel-layout solver."""
from __future__ import annotations

import pytest

from smash.state import Board, Flex
from smash.layout.fold import solve_tree, layout_and_wire
from smash.layout.board import panel_from_root


def _extent(panel):
    cols = [c for c, _ in panel.tiles.values()]
    rows = [r for _, r in panel.tiles.values()]
    return max(cols) + 1, max(rows) + 1


# ── solve_tree (pure grid solver) ─────────────────────────────────────

def test_straight_chain_folds_to_min_box():
    """A 9-node chain must fold to the tightest box (3×3 = 9), not a line."""
    order = [f"n{i}" for i in range(9)]
    parent = {order[0]: None}
    for i in range(1, 9):
        parent[order[i]] = order[i - 1]
    pos, (a, b) = solve_tree(order, parent, frozenset())
    assert a * b == 9
    assert len(set(pos.values())) == 9          # no overlaps


def test_prefer_square_breaks_area_ties():
    """At equal area the squarer box wins (4×6, not 2×12, for 24)."""
    order = [f"n{i}" for i in range(24)]
    parent = {order[0]: None}
    for i in range(1, 24):
        parent[order[i]] = order[i - 1]
    _pos, (a, b) = solve_tree(order, parent, frozenset())
    assert a * b == 24
    assert abs(a - b) == 2                       # 4×6


def test_forced_straight_stub_stays_collinear():
    """A forced-straight grandchild continues the parent's direction."""
    order = ["root", "p", "q"]
    parent = {"root": None, "p": "root", "q": "p"}
    pos, _ = solve_tree(order, parent, forced_straight={"q"})
    rx, ry = pos["root"]
    px, py = pos["p"]
    qx, qy = pos["q"]
    assert (px - rx, py - ry) == (qx - px, qy - py)   # collinear, same step


# ── layout_and_wire (Board graph integration) ─────────────────────────

def test_layout_and_wire_no_overlap():
    boards = [Board(f"b{i}") for i in range(6)]
    edges = [(boards[i], boards[i + 1], "snake", Flex()) for i in range(5)]
    layout_and_wire(edges, boards[0])
    panel = panel_from_root(boards[0])
    assert len(set(panel.tiles.values())) == len(panel.tiles)


def test_layout_and_wire_branch_stub():
    """A straight 2-cell branch stub lands collision-free off the chain."""
    chain = [Board(f"b{i}") for i in range(4)]
    conn = Board("conn", kind="flex",
                 geometry=None)  # geometry irrelevant to the solver
    leaf = Board("leaf")
    edges = [(chain[i], chain[i + 1], "snake", Flex()) for i in range(3)]
    edges += [(chain[1], conn, "branch", Flex()),
              (conn, leaf, "branch", Flex())]
    layout_and_wire(edges, chain[0], forced_straight={leaf.name})
    panel = panel_from_root(chain[0])
    assert {"conn", "leaf"} <= set(panel.tiles)
    assert len(set(panel.tiles.values())) == len(panel.tiles)


def test_unsatisfiable_raises():
    """Five stubs off one node can't all fit (only four neighbours)."""
    hub = Board("hub")
    leaves = [Board(f"l{i}") for i in range(5)]
    edges = [(hub, lf, "branch", Flex()) for lf in leaves]
    with pytest.raises(RuntimeError):
        layout_and_wire(edges, hub)


# ── co-share: two same-axis branch leaves may stack on one cell ───────

def test_coshare_stacks_same_axis_branches():
    """Two co-shareable leaves whose parents flank a common cell on the
    same axis collapse onto that cell (their parallel flexes don't
    cross)."""
    from smash.layout.fold import _fits
    order = ["R", "Pw", "t1", "t2", "Pe", "Lw", "Le"]
    parent = {"R": None, "Pw": "R", "t1": "R", "t2": "t1",
              "Pe": "t2", "Lw": "Pw", "Le": "Pe"}
    sol = _fits(2, 3, order, parent, frozenset(), coshare={"Lw", "Le"})
    assert sol is not None
    assert sol["Lw"] == sol["Le"]            # stacked on one cell


def test_coshare_rejects_cross_axis():
    """Without the same-axis match, the cell stays single-occupant."""
    from smash.layout.fold import _fits
    # Pw west of C, Pe north of C → different axes → must NOT stack.
    order = ["R", "Pw", "t1", "Pe", "Lw", "Le"]
    parent = {"R": None, "Pw": "R", "t1": "R", "Pe": "t1",
              "Lw": "Pw", "Le": "Pe"}
    sol = _fits(3, 3, order, parent, frozenset(), coshare={"Lw", "Le"})
    if sol is not None:
        assert sol["Lw"] != sol["Le"]
