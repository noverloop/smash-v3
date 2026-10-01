"""Board graph traversal — `panel_from_root()`.

The `Board` / `Flex` / `BoardEdge` dataclasses live in
`smash.state.{topology,smash_state}`. This module holds the algorithm
that walks a Board graph and produces a `PanelLayout` — the legacy
dict shape consumed by the tools/-side placer.
"""
from __future__ import annotations

from collections import deque

from smash.layout.panel import PanelLayout


# Direction step in grid cells.
_DELTA: dict[str, tuple[int, int]] = {
    "E": ( 1,  0), "W": (-1, 0),
    "S": ( 0,  1), "N": ( 0, -1),
}


def panel_from_root(
    root: "Board",
    *,
    spacer_edge_keepout_mm: float = 0.0,
    spacer_centre_support_radius_mm: float = 0.0,
) -> PanelLayout:
    """Walk the Board graph from `root` and return a `PanelLayout`.

    BFS starts at (0, 0). Snake-link `Flex` objects with a `spacer`
    Board (or name) materialise that spacer as an inline grid cell
    between the two endpoints. The final coords are normalised so
    `min(col) = min(row) = 0`.

    The output `PanelLayout` carries every field the tools/-side
    placer expects: `tiles`, `snake_chain`, `branches`,
    `branch_flex_lengths`, `tile_outlines`, `tile_diameters`,
    `tile_rect_dimensions`, `tile_top_substrate`, `tile_al_backing_mm`.
    """
    tiles: dict[str, tuple[int, int]] = {root.name: (0, 0)}
    tile_outlines: dict = {}
    tile_diameters: dict = {}
    tile_rect_dims: dict = {}
    tile_substrate: dict = {}
    tile_al: dict = {}
    branches: list = []
    branch_lengths: dict = {}
    branch_s_fold: set = set()
    snake_edges: list[tuple[str, str]] = []

    seen: set[str] = {root.name}
    queue = deque([root])

    def _register(b: "Board", col: int, row: int) -> None:
        tiles[b.name] = (col, row)
        if b.outline_dxf is not None:
            tile_outlines[b.name] = b.outline_dxf
        if b.rect_dimensions is not None:
            tile_rect_dims[b.name] = b.rect_dimensions
        elif b.diameter_mm is not None and b.diameter_mm != 34.0:
            tile_diameters[b.name] = b.diameter_mm
        if b.top_substrate != "fr4":
            tile_substrate[b.name] = b.top_substrate
        if b.al_backing_mm > 0:
            tile_al[b.name] = b.al_backing_mm

    _register(root, 0, 0)

    while queue:
        cur = queue.popleft()
        cur_col, cur_row = tiles[cur.name]
        for direction, edge in cur.edges.items():
            other = edge.other
            if other.name in seen:
                continue

            d_col, d_row = _DELTA[direction]
            sp_board = edge.flex.spacer_board() if (
                edge.kind == "snake" and edge.flex is not None) else None
            step = 2 if sp_board is not None else 1
            other_col = cur_col + d_col * step
            other_row = cur_row + d_row * step

            if sp_board is not None:
                if sp_board.name not in tiles:
                    _register(sp_board, cur_col + d_col, cur_row + d_row)
                    snake_edges.append((cur.name, sp_board.name))
                    snake_edges.append((sp_board.name, other.name))
            elif edge.kind == "snake":
                snake_edges.append((cur.name, other.name))
            elif edge.kind == "branch":
                branches.append((cur.name, other.name))
                if edge.flex and edge.flex.length_mm is not None:
                    branch_lengths[(cur.name, other.name)] = edge.flex.length_mm
                if edge.flex and getattr(edge.flex, "s_fold", False):
                    branch_s_fold.add((cur.name, other.name))

            _register(other, other_col, other_row)
            seen.add(other.name)
            queue.append(other)

    # Normalise so min(col) = min(row) = 0.
    if tiles:
        min_col = min(c for c, _ in tiles.values())
        min_row = min(r for _, r in tiles.values())
        if min_col or min_row:
            tiles = {k: (c - min_col, r - min_row)
                     for k, (c, r) in tiles.items()}

    # Build snake chain as a path through the snake_edges starting at root.
    chain: list[str] = []
    if snake_edges:
        adj: dict[str, list[str]] = {}
        for a, b in snake_edges:
            adj.setdefault(a, []).append(b)
            adj.setdefault(b, []).append(a)
        endpoints = [n for n, nb in adj.items() if len(nb) == 1]
        start = root.name if root.name in adj else (
            endpoints[0] if endpoints else None)
        if start is not None:
            visited = {start}
            chain = [start]
            cur_name = start
            while True:
                nxt = next((n for n in adj.get(cur_name, [])
                            if n not in visited), None)
                if nxt is None:
                    break
                chain.append(nxt)
                visited.add(nxt)
                cur_name = nxt

    return PanelLayout(
        tiles=tiles,
        snake_chain=chain,
        tile_outlines=tile_outlines or None,
        tile_diameters=tile_diameters or None,
        tile_rect_dimensions=tile_rect_dims or None,
        branches=branches or None,
        branch_flex_lengths=branch_lengths or None,
        branch_s_fold=branch_s_fold or None,
        spacer_edge_keepout_mm=spacer_edge_keepout_mm,
        spacer_centre_support_radius_mm=spacer_centre_support_radius_mm,
        tile_top_substrate=tile_substrate or None,
        tile_al_backing_mm=tile_al or None,
    )
