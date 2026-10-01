"""`place_design()` — top-level placement orchestrator.

Stitches the three placer phases together:
  1. **Locks**  — read `locked_placements.json`; for every chip in the
                  design whose ref appears in the locks file, add a
                  `Placement(..., locked=True)` to its board.
  2. **Pack**   — for each board, run `pack_radial` on the unlocked
                  chips assigned to it (by `chip.board_tag`).
  3. **Cavities** — walk the panel snake chain and attach `CavityRegion`
                  records to each spacer based on the now-placed
                  neighbour chips.

Chips are routed to boards via `chip.board_tag`. Chips with no
board_tag, or a tag that doesn't appear in `boards`, are skipped with
a record in the stats dict — the caller decides whether to escalate.

The orchestrator is intentionally *idempotent*: re-running it clears
`chip_placements` and `cavity_placements` on every board first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from smash.layout.locked import load_locked_placements
from smash.layout.placer.cavities import attach_cavities_to_spacers, _flex_chords
from smash.layout.placer.face_split import goes_to_bottom
from smash.layout.placer.pack import pack_radial
from smash.state.board import Board
from smash.state.chip import Chip
from smash.state.topology.placement import Placement


@dataclass
class PlacementStats:
    """Per-board placement diagnostics. The orchestrator returns one of
    these per board it touches, plus a top-level summary."""
    board_name: str
    n_locked:           int   = 0
    n_packed_top:       int   = 0
    n_packed_bottom:    int   = 0
    n_unplaced:         int   = 0    # chips with this board_tag but no
                                     # footprint / otherwise un-packable
    max_reach_top_mm:   float = 0.0
    max_reach_bot_mm:   float = 0.0
    overflow_top:       bool  = False
    overflow_bot:       bool  = False

    @property
    def n_packed(self) -> int:
        return self.n_packed_top + self.n_packed_bottom

    @property
    def overflow(self) -> bool:
        return self.overflow_top or self.overflow_bot

    @property
    def max_reach_mm(self) -> float:
        return max(self.max_reach_top_mm, self.max_reach_bot_mm)


@dataclass
class DesignPlacementReport:
    """Summary returned by `place_design`."""
    per_board:           list = field(default_factory=list)  # list[PlacementStats]
    untagged_refs:       list = field(default_factory=list)  # chip.ref with board_tag=None
    unknown_board_refs:  list = field(default_factory=list)  # (ref, board_tag) not in boards
    locked_refs_not_in_design: list = field(default_factory=list)
                                                  # ref appears in locks but not in design
    n_cavities_added:    int = 0

    @property
    def any_overflow(self) -> bool:
        return any(s.overflow for s in self.per_board)


def _chips_by_board_tag(design) -> dict:
    """Group every placeable component (`chips + batteries + antennas`)
    by `.board_tag`. Components without a tag end up under the sentinel
    key `None`. The packer treats all three families uniformly — same
    footprint surface, same placement logic — so it sees them all here.
    """
    by_tag: dict = {}
    for chip in design.chips:
        by_tag.setdefault(chip.board_tag, []).append(chip)
    for bat in getattr(design, "batteries", []):
        by_tag.setdefault(bat.board_tag, []).append(bat)
    for ant in getattr(design, "antennas", []):
        by_tag.setdefault(ant.board_tag, []).append(ant)
    return by_tag


def _flex_dirs_for_board(panel, name: str) -> list[tuple[float, float]]:
    """Unit vectors (placement frame, y-up) from a board's centre toward
    each flex launch — its snake neighbours + any branch it's an endpoint
    of. Grid rows grow South (canvas y-down), so the row delta is negated
    into the y-up placement frame. Used to weight cavity cutouts near
    flex meridians (the rim is already thinned there)."""
    import math
    tiles = getattr(panel, "tiles", None) or {}
    if name not in tiles:
        return []
    col, row = tiles[name]
    dirs: list[tuple[float, float]] = []

    def _add(nbr: str) -> None:
        if nbr in tiles:
            vx = float(tiles[nbr][0] - col)
            vy = float(-(tiles[nbr][1] - row))
            n = math.hypot(vx, vy)
            if n > 1e-9:
                dirs.append((vx / n, vy / n))

    chain = getattr(panel, "snake_chain", None) or []
    if name in chain:
        i = chain.index(name)
        if i > 0:
            _add(chain[i - 1])
        if i < len(chain) - 1:
            _add(chain[i + 1])
    for (p, c) in (getattr(panel, "branches", None) or []):
        if p == name:
            _add(c)
        elif c == name:
            _add(p)
    return dirs


def place_design(
    design,
    panel,
    boards: dict,
    *,
    n_random_orderings: int = 40,
    seed: int = 42,
    extra_locks: dict | None = None,
) -> DesignPlacementReport:
    """Place every chip in `design` onto its target board.

    `boards` must include every board referenced by `chip.board_tag`
    in the design AND every spacer in `panel.snake_chain` (the cavity
    walker iterates spacers). For the canonical EVB,
    `smash.layout.boards.smash_evb_v1.build_panel()` returns the
    correct dict.

    Mutates each Board's `chip_placements` + `cavity_placements`
    in-place. Returns a `DesignPlacementReport` for diagnostics — the
    caller decides whether `overflow=True` is fatal.

    `extra_locks` maps chip ref → an entry with `position_mm`,
    `rotation_deg` and `face` (same shape as `locked_placements.json`
    entries) that is locked EXACTLY like a file lock. The config builds
    pass the maximalist build's final placements here so every shared
    board packs identically in every configuration (economies of
    scale); file locks take precedence on conflict. Refs not present
    in this design are silently ignored (a config may omit chips).
    """
    report = DesignPlacementReport()

    # Per-link flex widths — needed up front so the packer can hold chips
    # inside the same flex-chord keep-region the cavity clip enforces.
    from smash.layout.placer.flex_sizing import compute_link_widths
    link_widths, _ = compute_link_widths(design, panel)
    chain = getattr(panel, "snake_chain", None) or []
    tiles = getattr(panel, "tiles", None) or {}

    def _board_flex_chords(name: str, face: str):
        """Flex chords (placement frame) whose keep-region the cavity clip
        applies to this board's `face`. A board's top-face chips are milled
        into the NEXT spacer, its bottom-face chips into the PREV spacer —
        and that spacer's cavity is clipped by BOTH of its flex chords (the
        one toward this board AND the one toward its other neighbour). The
        chip projects across the fold, so un-fold the spacer's chords (x-
        mirror for an E-W fold, y-mirror for N-S) back into this board's
        frame."""
        if name not in chain or name not in tiles:
            return ()
        i = chain.index(name)
        si = i + 1 if face == "top" else i - 1
        if not (0 <= si < len(chain)) or chain[si] not in tiles:
            return ()
        spacer = chain[si]
        same_row = (tiles[spacer][1] == tiles[name][1])
        out = []
        for ang, w in _flex_chords(panel, spacer, si, chain, link_widths):
            out.append((180.0 - ang if same_row else -ang, w))
        return out

    # ── 0. clear any prior placements (idempotency) ──────────────────
    for b in boards.values():
        b.chip_placements.clear()
        b.cavity_placements.clear()

    # ── 1. locks ─────────────────────────────────────────────────────
    locks = load_locked_placements()
    by_tag = _chips_by_board_tag(design)

    # Build a quick ref→chip index across the design for the
    # "locked-but-missing-from-design" warning.
    chip_by_ref = {c.ref: c for c in design.chips}
    for locked_ref in locks:
        if locked_ref not in chip_by_ref:
            report.locked_refs_not_in_design.append(locked_ref)

    # ── 2. lock + pack each board ────────────────────────────────────
    for board_name, board in boards.items():
        chips = by_tag.get(board_name, [])
        if not chips:
            # Board has no chips assigned — record empty stats and skip
            report.per_board.append(PlacementStats(board_name=board_name))
            continue

        stats = PlacementStats(board_name=board_name)
        locked_for_pack: list[Placement] = []
        unlocked: list[Chip] = []

        for chip in chips:
            entry = locks.get(chip.ref)
            if entry is None and extra_locks is not None:
                entry = extra_locks.get(chip.ref)
            if entry is not None:
                pl = Placement(
                    position_mm=entry.position_mm,
                    rotation_deg=entry.rotation_deg,
                    item=chip,
                    face=entry.face,
                    locked=True,
                )
                board.chip_placements.append(pl)
                locked_for_pack.append(pl)
                stats.n_locked += 1
            else:
                unlocked.append(chip)

        # Pack only chips that have a footprint to size; un-packable
        # chips (e.g. project pads with manf='project' and no footprint)
        # are recorded but skipped.
        packable: list[Chip] = []
        for chip in unlocked:
            if chip.footprint is None:
                stats.n_unplaced += 1
                continue
            packable.append(chip)

        # Declarative face split: see smash.layout.placer.face_split
        # — mating pads, test points, and embeddable passives go to
        # the bottom; everything else stays on top. The Ø34 tiles
        # depend on this to fit.
        top_chips = [c for c in packable if not goes_to_bottom(c)]
        bot_chips = [c for c in packable if     goes_to_bottom(c)]
        flex_dirs = _flex_dirs_for_board(panel, board_name)

        if top_chips:
            new_placements, max_reach, overflow = pack_radial(
                chips_to_place=top_chips,
                board=board,
                already_placed=locked_for_pack,
                face="top",
                n_random_orderings=n_random_orderings,
                seed=seed,
                flex_dirs=flex_dirs,
                flex_chords=_board_flex_chords(board_name, "top"),
            )
            board.chip_placements.extend(new_placements)
            stats.n_packed_top     = len(new_placements)
            stats.max_reach_top_mm = max_reach
            stats.overflow_top     = overflow

        if bot_chips:
            new_placements, max_reach, overflow = pack_radial(
                chips_to_place=bot_chips,
                board=board,
                already_placed=locked_for_pack,
                face="bottom",
                n_random_orderings=n_random_orderings,
                seed=seed,
                flex_dirs=flex_dirs,
                flex_chords=_board_flex_chords(board_name, "bottom"),
            )
            board.chip_placements.extend(new_placements)
            stats.n_packed_bottom  = len(new_placements)
            stats.max_reach_bot_mm = max_reach
            stats.overflow_bot     = overflow

        report.per_board.append(stats)

    # ── 3. catch chips whose board_tag is None or unknown ────────────
    for chip in by_tag.get(None, []):
        report.untagged_refs.append(chip.ref)
    for tag, chips in by_tag.items():
        if tag is None:
            continue
        if tag not in boards:
            for c in chips:
                report.unknown_board_refs.append((c.ref, tag))

    # ── 4. cavities ──────────────────────────────────────────────────
    # Reuse the link widths computed up front (same flex-chord geometry).
    report.n_cavities_added = attach_cavities_to_spacers(
        panel, boards, link_widths)

    return report
