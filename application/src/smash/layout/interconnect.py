"""Inter-board interconnect topology — which nets cross which LGA gap.

Single source of truth shared by:
  * `smash.parts.connectors.place_lga_lands` — to ASSIGN each gap's crossing
    nets to that joint's LGA lands, and
  * `tools/connectivity_audit.py` — to VERIFY every crossing net is carried.

Driving both off the same computation makes "every board-to-board connection
lands on a board-local LGA" true *by construction*: the placer lands exactly
the nets the audit checks for.

A net "crosses gap g" iff it has real (non-land) pins on tiles on both sides of
the cut between rigid tile g and rigid tile g+1 — i.e. its snake-index span
satisfies ``min <= g`` and ``max >= g+1``.
"""
from __future__ import annotations


def _components(design):
    """Chips + batteries + antennas (the ref-bearing parts)."""
    comps = list(design.chips)
    comps += list(getattr(design, "batteries", []))
    comps += list(getattr(design, "antennas", []))
    return comps


def snake_layout(panel, boards):
    """Map the snake chain to gap indices.

    Returns ``(rigid_idx, spacer_at_gap, rigid_order)``:
      * ``rigid_idx[name]`` — integer position of a rigid tile along the chain.
        A branch leaf inherits its parent tile's index (it folds off that tile,
        so it sits on that tile's side of every snake cut).
      * ``spacer_at_gap[g]`` — the LIST of spacer board names bridging rigid
        gap ``g`` (the gap between rigid tile ``g`` and ``g+1``). Normally one
        spacer per gap; a battery compartment is a *run* of replicated spacers
        in the same gap, so all of them share that gap's crossing nets.
      * ``rigid_order`` — rigid tile names in chain order.
    """
    chain = panel.snake_chain
    rigid_idx, spacer_at_gap, rigid_order = {}, {}, []
    ri = -1
    for nm in chain:
        if getattr(boards[nm], "is_spacer", False):
            # spacer follows rigid index ri; a battery run puts several in the
            # same gap, so collect them all (list per gap).
            spacer_at_gap.setdefault(ri, []).append(nm)
        else:
            ri += 1
            rigid_idx[nm] = ri
            rigid_order.append(nm)
    for parent, leaf in (panel.branches or []):
        if leaf in boards and parent in rigid_idx:
            rigid_idx[leaf] = rigid_idx[parent]
    return rigid_idx, spacer_at_gap, rigid_order


def net_snake_span(design, rigid_idx, *, exclude_refs=frozenset()):
    """``{net_name: set(snake indices the net's real pins touch)}``.

    ``exclude_refs`` drops pads that carry a net but don't originate it (the
    LGA land pads themselves) so they don't widen a net's apparent span."""
    ref2board = {c.ref: (getattr(c, "board_tag", "") or "")
                 for c in _components(design)}
    span = {}
    for n in design.nets:
        idxs = set()
        for ref, _pin in n.pins:
            if ref in exclude_refs:
                continue
            b = ref2board.get(ref, "")
            if b in rigid_idx:
                idxs.add(rigid_idx[b])
        if idxs:
            span[n.name] = idxs
    return span


def crossing_nets_by_gap(design, panel, boards, *, exclude_refs=frozenset()):
    """``({gap: set(net names that cross it)}, spacer_at_gap, rigid_order)``.

    Net ``n`` crosses gap ``g`` iff ``min(span) <= g and max(span) >= g+1``."""
    rigid_idx, spacer_at_gap, rigid_order = snake_layout(panel, boards)
    span = net_snake_span(design, rigid_idx, exclude_refs=exclude_refs)
    n_gaps = max(len(rigid_order) - 1, 0)
    out = {g: set() for g in range(n_gaps)}
    for name, idxs in span.items():
        lo, hi = min(idxs), max(idxs)
        for g in range(n_gaps):
            if lo <= g and hi >= g + 1:
                out[g].add(name)
    return out, spacer_at_gap, rigid_order
