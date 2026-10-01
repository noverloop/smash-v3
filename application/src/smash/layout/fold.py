"""Compact panel-layout solver — the flex-connector "packer".

A port of `tools/solver.py` into the library. The panel is a TREE: a main
snake chain (boards interleaved with spacer cells) plus straight branch
stubs (qpd/camera each reach their tile through a flex-connector cell;
nfc is a single cell). Every cell — board, spacer, or connector — takes
one grid slot, and a tree edge means two cells are orthogonal grid
neighbours.

Goal: embed the tree so the bounding box `span_x * span_y` is minimal.
The trick that makes it instant: **iterative-deepening on the box shape**
— enumerate `a×b` boxes by increasing area and ask "does the tree fit in
this box?". Confining cells to the box prunes hard, and the first box that
fits is optimal. Branch stubs continue straight (`forced_straight`).

The chain *order* is fixed by the caller (see build_panel) — reordering is
done by editing that list, exactly as in tools/solver.py.
"""
from __future__ import annotations

from collections import defaultdict, deque

from smash.state import Flex

# Direction step per compass dir. Row grows downward (matches
# panel_from_root); the solver's own y-orientation is irrelevant since the
# panel is normalised, so a vertical mirror is harmless.
_DELTA = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}
_DELTA_INV = {v: k for k, v in _DELTA.items()}
_ADD = {"N": "add_north", "S": "add_south", "E": "add_east", "W": "add_west"}
_DIRS4 = [(1, 0), (-1, 0), (0, 1), (0, -1)]


def _fits(a, b, order, parent, forced_straight, coshare=frozenset()):
    """Backtracking placement confined to an `a×b` box. Returns
    `{node: (x, y)}` or None. `order` lists nodes parent-before-child;
    `forced_straight` nodes continue the grandparent→parent direction.

    `coshare` is a set of node names allowed to STACK on one cell with
    each other — used for the long deploy-flex branches (camera, qpd):
    two may share a cell iff their flex directions are on the same axis
    (both horizontal or both vertical), so the parallel flexes never
    cross. They're drawn side-by-side at export time."""
    pos: dict = {}
    occ: dict = {}        # (x, y) → list of (node, axis ∈ {'h','v',None})
    n = len(order)

    def place(i):
        node = order[i]
        if i == 0:
            cands = [(x, y) for x in range(a) for y in range(b)]
        elif node in forced_straight:
            p = parent[node]
            gp = parent[p]
            dx, dy = pos[p][0] - pos[gp][0], pos[p][1] - pos[gp][1]
            cands = [(pos[p][0] + dx, pos[p][1] + dy)]
        else:
            px, py = pos[parent[node]]
            cands = [(px + dx, py + dy) for dx, dy in _DIRS4]
        for (x, y) in cands:
            if not (0 <= x < a and 0 <= y < b):
                continue
            pn = parent.get(node)
            axis = None if pn is None else ("h" if y == pos[pn][1] else "v")
            here = occ.get((x, y))
            if here is not None:
                # Cell taken — only co-shareable branch leaves on a
                # matching axis may stack.
                if (node not in coshare or axis is None
                        or any(nm not in coshare or ax != axis
                               for nm, ax in here)):
                    continue
                here.append((node, axis))
                created = False
            else:
                occ[(x, y)] = [(node, axis)]
                created = True
            pos[node] = (x, y)
            if i + 1 == n or place(i + 1):
                return True
            del pos[node]
            if created:
                del occ[(x, y)]
            else:
                occ[(x, y)].pop()
        return False

    return dict(pos) if place(0) else None


def solve_tree(order, parent, forced_straight, *, prefer_square=True,
               coshare=frozenset()):
    """Minimal-area embedding of the tree. Sweeps box shapes by area
    (ties broken toward square when `prefer_square`, so the optimum comes
    out as e.g. 4×6 rather than the thin 2×12) and returns the first that
    fits: `(pos_dict, (w, h))`. Raises if nothing fits."""
    n = len(order)
    # Reject degenerate strips (a pure chain's min-area box is 1×N, a
    # terrible panel aspect). Cap b/a so a slot-free chain folds into a
    # blob (e.g. 4×5) while compact ratios (4×6) stay optimal. Relax the
    # cap if nothing fits (tiny n).
    for aspect_cap in (3.0, float("inf")):
        cands = []
        for a in range(1, n + 1):
            for b in range(a, n + 1):
                if a * b >= n and (b / a) <= aspect_cap:
                    tie = abs(a - b) if prefer_square else a
                    cands.append((a * b, tie, a, b))
        cands.sort()
        for _area, _tie, a, b in cands:
            sol = _fits(a, b, order, parent, forced_straight, coshare)
            if sol is not None:
                return sol, (a, b)
    raise RuntimeError("solve_tree: no collision-free embedding found")


def wire_straight(chain_cells, branches, *, branch_side="S"):
    """Wire a COMPLETELY STRAIGHT snake — no box-minimising planner.

    `chain_cells` is the snake in order, boards interleaved with their
    spacers (`[board0, spacer0, board1, spacer1, …]`). They're wired as
    one row marching East, so the folded tower is just that row read off
    left-to-right.

    `branches` is a list of `(parent_board, leaf, flex)`. Each deploy
    leaf attaches INDEPENDENTLY to its own parent board (no coshare) on a
    free perpendicular edge so it gets a nominal grid slot. The physical
    flex exit, though, runs alongside the board's *snake* flex (same
    direction) and `flex.s_fold` tells the export to draw the short
    S-turn that dodges the spacer the snake flex lands on before the
    long straight run out to the leaf — see kicad_pcb._emit_s_fold_flex.

    `branch_side` is the preferred N/S edge for every deploy branch.
    Default "S" sends every branch off the south edge of its parent —
    the whole tree lies on one side of the snake, so multiple branches
    off adjacent parents don't fight for the same axial corridor when
    the fold collapses east-to-west. Pass `"N"` to mirror, or `"alt"`
    to fall back to the old N/S alternating placement.

    Clears existing edges first. Returns `pos_by_name` (grid cells)."""
    for c in chain_cells:
        c.edges.clear()
    for parent, leaf, _flex in branches:
        parent.edges.clear()
        leaf.edges.clear()

    # March the interleaved chain East.
    for a, b in zip(chain_cells, chain_cells[1:]):
        a.add_east(b, flex=Flex(), kind="snake")

    # Each branch leaf gets a free perpendicular edge on its parent board.
    # Pick the preferred side first; if it's already in use on this
    # parent (e.g. two branches share one parent), fall through to the
    # opposite side rather than dropping the branch on the floor.
    # `Flex.branch_side` is a per-branch override: when set, this branch
    # picks that side explicitly (still falling back to the opposite if
    # the preferred side is already claimed). N/S are free on every tile;
    # E/W are the snake axis, so they're only free on the snake's END tiles
    # (the root's W edge, the tail's E edge) — an E/W override on a mid-tile
    # finds that side taken by the snake and falls through to a perpendicular
    # N/S edge. This lets an end tile give a branch its own meridian (e.g. NFC
    # off the activation_interface root's free west edge).
    fallback = {"S": "N", "N": "S", "W": "N", "E": "S"}
    for i, (parent, leaf, flex) in enumerate(branches):
        flex_pref = getattr(flex, "branch_side", None)
        if flex_pref in ("N", "S", "E", "W"):
            order = (flex_pref, fallback[flex_pref])
        elif branch_side == "alt":
            order = ("N", "S") if i % 2 == 0 else ("S", "N")
        else:
            order = (branch_side, fallback[branch_side])
        for d in order:
            if d not in parent.edges:
                getattr(parent, _ADD[d])(leaf, flex=flex, kind="branch")
                break

    pos = {c.name: (k, 0) for k, c in enumerate(chain_cells)}
    return pos


_PERP = {"E": ("N", "S"), "W": ("N", "S"), "N": ("E", "W"), "S": ("E", "W")}


def layout_and_wire(edges, root, forced_straight=frozenset(), *,
                    prefer_square=True, coshare=frozenset(),
                    sfold_branches=()):
    """Solve the layout for `edges` (each `(parent, child, kind, flex)`)
    and wire the Board graph in the solved directions.

    `root` is the snake start. `forced_straight` is the set of child Board
    *names* whose stub must continue straight off their parent.

    `sfold_branches` is a list of `(parent, leaf, flex)` S-fold deploy
    branches. They consume NO grid cell; instead the snake is forced
    straight for the two cells past each parent (reserving the lane the
    branch flex runs down), and the leaf is wired onto the parent's free
    perpendicular side that points OUTWARD from the fold (so leaves
    deploy away from the cluster and don't collide). The export draws the
    S-turn parallel to the snake axis. Returns `(pos_by_name, (w, h))`."""
    children: dict = defaultdict(list)
    edge_by_child: dict = {}
    boards: dict = {root.name: root}
    for p, c, kind, flex in edges:
        children[p.name].append(c)
        edge_by_child[c.name] = (p, c, kind, flex)
        boards[p.name] = p
        boards[c.name] = c

    # BFS gives a parent-before-child placement order.
    order = [root.name]
    parent_name = {root.name: None}
    q = deque([root])
    while q:
        cur = q.popleft()
        for c in children[cur.name]:
            if c.name in parent_name:
                continue
            parent_name[c.name] = cur.name
            order.append(c.name)
            q.append(c)

    # Reserve each S-fold branch's lane: force the snake straight for the
    # two cells following its parent.
    fs = set(forced_straight)
    for p, _leaf, _flex in sfold_branches:
        if p.name in order:
            i = order.index(p.name)
            for j in (i + 1, i + 2):
                if 0 <= j < len(order):
                    fs.add(order[j])

    pos, (w, h) = solve_tree(order, parent_name, fs,
                             prefer_square=prefer_square)

    all_boards = dict(boards)
    for p, leaf, _flex in sfold_branches:
        all_boards[p.name] = p
        all_boards[leaf.name] = leaf
    for b in all_boards.values():
        b.edges.clear()
    for cname in order[1:]:
        p, c, kind, flex = edge_by_child[cname]
        delta = (pos[cname][0] - pos[p.name][0],
                 pos[cname][1] - pos[p.name][1])
        getattr(p, _ADD[_DELTA_INV[delta]])(c, flex=flex, kind=kind)

    # Wire each S-fold leaf onto the parent's free perpendicular side that
    # points outward from the fold centroid (run-direction heuristic — the
    # leaf deploys away from the cluster).
    cx = sum(p[0] for p in pos.values()) / len(pos)
    cy = sum(p[1] for p in pos.values()) / len(pos)
    occupied = set(pos.values())   # snake cells the run must not cross
    RUN_CELLS = 3                  # ~flex_len / pitch corridor length

    def _corridor_free(px, py, side, axis_delta):
        """The offset cell + RUN_CELLS along the snake axis (both ways)
        must be clear of snake cells and previously-claimed corridors."""
        ox, oy = px + _DELTA[side][0], py + _DELTA[side][1]
        cells = {(ox, oy)}
        for s in (1, -1):
            for k in range(1, RUN_CELLS + 1):
                cells.add((ox + s * axis_delta[0] * k,
                           oy + s * axis_delta[1] * k))
        if cells & occupied:
            return None
        return cells

    for p, leaf, flex in sfold_branches:
        snake_dirs = [d for d, e in p.edges.items() if e.kind == "snake"]
        axis = snake_dirs[0] if snake_dirs else "E"
        axis_delta = _DELTA[axis]
        px, py = pos[p.name]
        # Outward-first ranking of the free perpendicular sides.
        sides = sorted(
            (d for d in _PERP[axis] if d not in p.edges),
            key=lambda d: -((px + _DELTA[d][0] - cx) * _DELTA[d][0]
                            + (py + _DELTA[d][1] - cy) * _DELTA[d][1]))
        chosen, claim = None, None
        for d in sides:
            cells = _corridor_free(px, py, d, axis_delta)
            if cells is not None:
                chosen, claim = d, cells
                break
        if chosen is None and sides:        # all corridors blocked — least-bad
            chosen = sides[0]
        if chosen is not None:
            if claim:
                occupied |= claim           # reserve so the next branch dodges
            getattr(p, _ADD[chosen])(leaf, flex=flex, kind="branch")
    return pos, (w, h)
