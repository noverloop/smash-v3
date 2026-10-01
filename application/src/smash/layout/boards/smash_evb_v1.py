"""smash_evb_v1 — rigid-flex EVB panel, built with the Board graph API.

Sample reconstruction of `tools/layout_gen/boards/evb_2x.py` using
per-board `add_<direction>()` calls instead of a top-down PanelLayout
dict. The resulting graph projects to the same panel topology:

   7-tile snake (the root, activation_interface, is at one end):

   activation ─ wakeup ─ fins ─ power ─ companion_compute ─ radar ─ nose
       │N/S            │N/S                    │N/S
       nfc          Yagi A / Yagi B         qpd / camera

   (branches S-fold off their parent's snake gap; Yagi A/B sit on the
    body meridian N and S of wakeup_board.)

Run as a smoke test:
    python3 -m smash.layout.boards.smash_evb_v1

It prints the derived PanelLayout and diffs it against the literal
PANEL dict in `tools/layout_gen/boards/evb_2x.py`.
"""
from __future__ import annotations

import math

from smash.layout.board import panel_from_root
from smash.layout.cavities import assign_spacer_backings
from smash.layout.fold  import layout_and_wire, wire_straight
from smash.state        import Board, Flex

# ── battery compartment ─────────────────────────────────────────────────
# The aft battery pack is modeled as a run of PCB spacers between
# cell_floor_board (the THIN battery-floor tile — the cells stand on its top
# face; their side solder-tab − lands sit there) and fin_ble_board (the
# compartment ceiling since the 2026-07-31 stack reorder: cell + contacts
# P_CELL_CONTACTS on its bottom face, which also tucks its embeddable
# passives into the compartment's free trefoil space). activation_interface
# moved DOWN between aft_end and cell_floor the same day, putting the FIRE
# boost one thin gap from the aft_end fire bank. PCB fabs cap board
# thickness, so the holder is N manufacturable thin spacers — one design,
# replicated N times — each ≤ MAX_SPACER_THICKNESS_MM, together summing to
# the compartment depth. Each carries the perimeter LGA lands + filled vias
# + a central cell-bore cavity (added post-place by the generator).
#
# cell_floor_board 2026-07-30 rework: briefly DELETED (side-solder-tab cells
# standing directly on the piezo disc), then REINSTATED THIN the same day —
# with cells on aft_end, the piezo hole + comparator pockets + tab chimneys
# starved the aft LGA joint (59→20 lands, FIRE_ARMED/BAT_RAW dropped), and
# moving the comparator to the bottom face gave PIEZO_P an unwanted via stub.
# The tile is now 6L / ~0.85 mm (was a 20L coin host — the Cu coin is GONE,
# the potted monolith carries the pack load) and carries POTTING pass-through
# holes so the thin aft gaps below it (activation↔cell_floor, and via
# activation's own pass-throughs aft_end↔activation) fill from the
# compartment channels. Since the 2026-07-31 reorder its aft neighbour is
# activation_interface (FIRE boost) and the compartment sits nose-ward, up
# to the fin_ble_board ceiling. Single-cell mode still drops the tile (the
# one horizontal cell lies on aft_end directly).
BATTERY_LENGTH_MM = 21.0           # default (3-cell superset) = TLM-1520HPM/S
                                   # length; cells stand flat on cell_floor.
                                   # Single configs pass 15.1 (the TLM-1530M/S
                                   # Ø, laid horizontal).
MAX_SPACER_THICKNESS_MM = 4.0      # fab board-thickness cap (confirm w/ fab)
_AFT_END = "aft_end_board"
_CELL_FLOOR = "cell_floor_board"


def battery_spacer_count(length_mm: float = BATTERY_LENGTH_MM) -> int:
    return max(1, math.ceil(length_mm / MAX_SPACER_THICKNESS_MM))


def _make_gap_spacers(a: Board, b: Board, battery_pair: frozenset,
                      battery_length_mm: float = BATTERY_LENGTH_MM) -> list:
    """Spacer board(s) bridging the a→b snake gap. Normally one 4 mm spacer;
    the chain's ONE `battery_pair` gap (see _interleave) is the battery
    compartment — a run of N replicated thin spacers (≤ fab max) summing to
    the compartment depth (`battery_length_mm`: the cell LENGTH for
    vertical cells, 21 mm; the cell DIAMETER for the lowprofile horizontal
    single cell, 15.1 mm)."""
    if {a.name, b.name} == battery_pair:
        n = battery_spacer_count(battery_length_mm)
        t = battery_length_mm / n
        # "spacer_battery_*" so they pick up the spacer_* Ø34 geometry
        # fallback and are identifiable as the battery run.
        return [Board(f"spacer_battery_{k + 1}", kind="spacer",
                      thickness_override_mm=t) for k in range(n)]
    return [Board(f"spacer_{a.name}_{b.name}", kind="spacer")]


def _interleave(seq: list, battery_length_mm: float = BATTERY_LENGTH_MM):
    """Build (chain_cells, spacers, edges) by inserting the gap spacer(s)
    between each consecutive pair — a run of N for the battery gap, one
    otherwise. Shared by build_panel + build_config_panel. `battery_length_mm`
    sets the compartment depth (21 mm = 3× vertical TLM-1520 on cell_floor;
    15.1 mm = lowprofile horizontal TLM-1530M).

    The battery gap is cell_floor↔fin_ble when the chain carries the
    cell_floor floor tile (triple mode), else aft_end↔activation (single
    mode — cell on aft_end). The pair must be picked from the WHOLE chain,
    not per-gap: since the 2026-07-31 reorder aft_end and activation are
    adjacent in the triple chain too, and matching that pair by name alone
    would turn their thin gap into a second 21 mm battery run."""
    has_floor = any(b.name == _CELL_FLOOR for b in seq)
    battery_pair = (frozenset({_CELL_FLOOR, "fin_ble_board"}) if has_floor
                    else frozenset({_AFT_END, "activation_interface"}))
    spacers, edges = [], []
    chain_cells = [seq[0]] if seq else []
    for i in range(len(seq) - 1):
        a, b = seq[i], seq[i + 1]
        prev = a
        for sp in _make_gap_spacers(a, b, battery_pair, battery_length_mm):
            spacers.append(sp)
            chain_cells.append(sp)
            edges.append((prev, sp, "snake", Flex()))
            prev = sp
        chain_cells.append(b)
        edges.append((prev, b, "snake", Flex()))
    return chain_cells, spacers, edges


# Copper layers left continuous ABOVE a Cu coin so a central part (a big BGA on
# the coin tile) can fan out on more than the two outer layers. A full-depth
# coin spans In1…In18, leaving only F.Cu/B.Cu routable; lowering its top face
# below the top N layers frees F.Cu + In1…In(N-1) for routing. 
N_TOP_ROUTABLE_LAYERS = 6


def _nth_copper_bottom_z(board, n):
    """z (mm, from B.Cu = 0) of the BOTTOM of the n-th copper layer counted
    from the top — the highest z a coin's top may reach while leaving the top
    n copper layers continuous. None if the fitted stackup is shorter than n."""
    st = getattr(board, "stackup", None) or []
    z = board.thickness_mm
    for i, layer in enumerate(st):
        z -= (getattr(layer, "thickness_um", 0) or 0) / 1000.0
        z_bottom = z
        di = getattr(layer, "dielectric_below", None)
        z -= (getattr(di, "thickness_um", 0) if di else 0) / 1000.0
        if i == n - 1:
            return z_bottom
    return None


def _lower_coins_for_top_routing(boards, n_top=N_TOP_ROUTABLE_LAYERS):
    """Lower each Cu coin's top face below the top `n_top` copper layers so they
    stay routable. Only the top is moved — the coin keeps its bottom face, so it
    still spans the neutral axis (no measured bend-margin loss). Call AFTER
    `set_fitted_stackup` (it reads the fitted layer z's)."""
    for b in boards.values():
        coins = getattr(b, "cu_coin_inserts", None) or []
        if not coins or not getattr(b, "stackup", None):
            continue
        # per-board override: companion_compute keeps SEVEN coppers
        # clear (F.Cu + the In1…In6 §6.5-plus-overflow DDR stack)
        z_cap = _nth_copper_bottom_z(
            b, getattr(b, "n_top_routable_layers", n_top))
        if z_cap is None:
            continue
        for c in coins:
            if c.z_top_mm <= z_cap:
                continue                          # already low enough
            z_bottom = c.z_top_mm - c.thickness_mm
            c.z_top_mm = round(z_cap, 3)
            c.thickness_mm = round(z_cap - z_bottom, 3)


# ── Cu coins: ALL REMOVED ────────────────────────────────────────────────
# There was no need for coins in this design.


def build_panel(*, straight=True, battery_length_mm: float = BATTERY_LENGTH_MM,
                single_cell: bool = False):
    # ── rigid tiles ───────────────────────────────────────────────────
    power_board       = Board("power_board")
    wakeup_board      = Board("wakeup_board")   # also carries the IMU/mag (flight folded in)
    # Fin tile — NEW 2026-07-30 (crowding split off wakeup_board): the
    # 4× DRV8428E fin drivers + G0B1 fin node. The STM32WBA55 cluster +
    # Yagi leaves moved back to wakeup_board 2026-07-31 (wake/arm
    # consolidation); the same day's stack reorder made this the battery
    # compartment CEILING (cell + contacts on its bottom face, embeddable
    # passives tucked into the compartment) and the piezo launch cluster's
    # host (disc + comparator column on its top face) — a CORE tile, in
    # EVERY config, core_radar included (that config stays RF-dark and
    # sheds only the two Yagi leaves). Default 14L stackup like its old
    # wakeup host.
    fin_ble_board     = Board("fin_ble_board")
    # The radar tile uses the Rogers RO4350B top substrate for the
    # AWR2944 SIW launches. Structural support (this is one of the
    # bend-sim bottleneck boards: U_AWR's 12 × 12 mm BGA sits at the
    # board centre and binds the bend envelope) comes from the Cu T-coin
    # below: NCAB-Advanced max H = 3 mm × 20 × 20 mm flange × 16 × 16
    # mm ladder, centred at U_AWR, in a 20L stackup (NCAB-Advanced max
    # = 30L) so the coin fits between F.Cu + dielectric on top and B.Cu
    # + dielectric on bottom. R = 5 mm corner chamfer gives NCAB-
    # Advanced edge clearance U ≈ 5 mm to the Ø34 board outline.
    #
    # Bend envelope: 10 k G bare → 40 k G all modes with the coin (U_AWR
    # gets local stiffening ls = 0.40; 50 k G crosses the m = 0.33 warn
    # threshold by 0.002 — passes in warn, well clear of m = 1.0 actual
    # joint failure). Routing trade: F.Cu + B.Cu remain as the routing
    # layers; the coin replaces In1…In18 in the chip area. The spacers
    # above and below are routable FR4 (soldered to the tile faces) so
    # they can carry signal pass-throughs as well as bonding load.
    # No Rogers: the 77 GHz SIW launches couple directly into the machined
    # aluminium waveguide/horn block bonded above, so the PCB laminate never
    # sees RF — plain FR4 top substrate. The 20L count stays for MECHANICAL
    # stiffness (the setback/bend envelope), not RF.
    radar_module      = Board("radar_module", copper_layers=20)
    # (its Cu T-coin was REMOVED 2026-07-04 — see the coin note above.)
    # companion_compute is the other bend-sim bottleneck — U_MPU
    # (10 × 10 mm BGA at -7.7 mm X) and U_DDR4 (7.5 × 13 mm BGA at +5.8 mm
    # X) both sit close to the Ø34 board edge, so neither can be
    # COVERED by a single coin in a Ø34 bore at NCAB-Advanced U = 5 mm.
    # The 20 × 20 mm × 3 mm coin at the board centre still lifts the
    # bend envelope via global plate-stiffening alone (D_eff_global =
    # area-weighted blend of D_with_coin + D_bare): 30 → 50 k G fwd /
    # rev / impact. Same 20L stackup + 5 mm corner chamfer as the radar
    # coin. F.Cu + B.Cu remain for routing; In1…In18 are absorbed into
    # the coin in the chip cluster area. The two BGAs are routed on
    # F.Cu / B.Cu and via fan-outs going OFF the coin's footprint.
    # (companion_io retired — bulk storage moved here as two SPI-NAND dies.)
    companion_compute = Board("companion_compute", copper_layers=20)
    # (its Cu T-coin was REMOVED 2026-07-04 too, freeing In1…In18 for the
    # EE reference DDR stack — see the coin note above.)
    # Terminal cap (radar forward-end): stacks DIRECTLY on the radar — the
    # radar↔nose_cap spacer is scaffolded for the LGA lands then discarded (see
    # _drop_radar_nose_spacer). A 12-layer disc fitted to 1.455 mm (nearest
    # catalog ≥ AWR 1.234 + 0.13 gap) so the AWR pokes through the nose_cap's
    # enlarged cutout and stops ~0.22 mm below the OUTER face (the waveguide-disk
    # air gap). Carries the USB-C + LEDs and structurally supports the aluminium
    # waveguide disk, which seals the cutout.
    nose_cap          = Board("nose_cap", copper_layers=12,
                              target_thickness_mm=1.4)
    activation_interface = Board("activation_interface")

    # ── branch tiles (off the main fold) ──────────────────────────────
    # All four deploy leaves are reached over a LONG flex — no
    # intermediate connector tile; the flex length is carried on the
    # branch edge and drawn as a long strip by the export. Two KINDS:
    #   • RIGID sensor tiles — camera_module and qpd_module each carry a
    #     real package (image sensor / MT03-092 QPD + 4 AD8603 TIAs +
    #     ADF4351 PLL) that must sit on rigid FR4; the long flex is just
    #     the connector ribbon out to them. They run the rigid bend
    #     solver like any other tile, matching the schema
    #     (smash_state.add_qpd / add_camera both declare kind="rigid").
    #   • FLEX antenna tiles — nfc_antenna_flex and the two Yagi tiles are
    #     thin polyimide carriers, NOT circular rigid plates. kind="flex"
    #     keeps the rigid-plate bend solver off them (it would model them
    #     as Ø34 FR4 boards and report nonsense).
    # nfc_antenna_flex Board REMOVED 2026-07-30 (NFC subsystem deleted)
    camera_module     = Board("camera_module", al_backing_mm=0.5)
    qpd_module        = Board("qpd_module")   # rigid sensor tile (QPD + 4 TIAs + PLL)
    # Two 2.4 GHz meandered-Yagi flex tiles on body meridians (90° apart,
    # 12 o'clock and 3 o'clock) for backward CP telemetry off the WBA52.
    # The metal sonde body acts as the Yagi's back-reflector — feature,
    # not bug. Replaces the prior LoRa-868 monopole flexes; same S-fold
    # branch-off pattern. Per the EM-sim work flagged in the plan, the
    # element meander geometry will be locked when the antenna team's
    # simulation closes; tile dimensions (20×40 mm rect) are a reasonable
    # placeholder envelope.
    yagi_ant_a_flex   = Board("yagi_ant_a_flex", kind="flex")
    yagi_ant_b_flex   = Board("yagi_ant_b_flex", kind="flex")

    # ── snake order (fixed) + compact fold via the solver ─────────────
    # MUST match generate_maximalist_system._MASTER_SNAKE (this panel and the
    # per-config builds share the order; they're maintained in lock-step). Every
    # snake gap carries a spacer (incl. radar→nose). Reordering = edit both.
    # power_board sits next to companion_compute so the PMIC core rails cross
    # only the power↔companion gap (PMIC stays top-side on power); compute is
    # next to radar for the Gigabit-Ethernet link; fins next to power.
    # aft_end_board is the aft-most snake start.activation_interface
    # moved down next to it, then in the 3-cell
    # default cell_floor_board — the THIN (6L, ~0.85 mm, no coin)
    # battery-floor tile with the cells' side solder-tab − lands on its top
    # face — then the compartment up to fin_ble_board, its ceiling (cell +
    # contacts on the bottom face; piezo disc + comparator column on its
    # top). Potting injects from the fin_ble/wakeup-side channels and the
    # pass-through holes on cell_floor + activation fill the two thin aft
    # gaps. Single-cell mode drops cell_floor (horizontal cell on aft_end;
    # see the battery-compartment header).
    aft_end_board = Board(_AFT_END)
    if single_cell:
        cell_floor_board = None
        chain = [
            aft_end_board, activation_interface, fin_ble_board, wakeup_board,
            power_board, companion_compute,
            radar_module, nose_cap,
        ]
    else:
        cell_floor_board = Board(_CELL_FLOOR, copper_layers=6)
        chain = [
            aft_end_board, activation_interface, cell_floor_board,
            fin_ble_board, wakeup_board,
            power_board, companion_compute,
            radar_module, nose_cap,
        ]
    chain_cells, spacers, edges = _interleave(chain, battery_length_mm)

    # Deploy branches (nfc/camera/qpd) all S-fold off their parent's snake
    # flex — round leaves that consume no grid cell. The snake is forced
    # straight past each parent to reserve the lane (fold.layout_and_wire).
    branch_trips = [
        # wakeup_board hosts BOTH Yagi flex tiles — N and S — so its
        # full 4-edge launch budget is committed (E/W = snake, N/S =
        # the Yagi pair; back with the WBA since 2026-07-31 — the pair
        # briefly rode fin_ble_board during the crowding split). The
        # Yagi tiles sit DIRECTLY perpendicular to the snake
        # (s_fold=False) so they land squarely above / below
        # wakeup_board's centre, not tucked alongside a spacer flex.
        # The camera / qpd deploy leaves still S-fold, because they're
        # "deploy" branches that physically run alongside the snake on
        # a long flex, not stacked tiles on the body meridian like the
        # Yagis.
        (wakeup_board,      yagi_ant_a_flex,
            Flex(length_mm=60.0, branch_side="N")),
        (wakeup_board,      yagi_ant_b_flex,
            Flex(length_mm=60.0, branch_side="S")),
        # All deploy branches go DIRECTLY south of their parent
        # (s_fold=False). The S-fold tuck-along-snake routing was
        # eating too much of the parent's perimeter into the merged
        # cutout AND producing broken S-bend polylines on the wider
        # spacer flexes — keeping every branch perpendicular gives
        # one clean chord notch per branch.
        # NFC hangs WEST off activation_interface: it's the snake's root (first
        # tile, no tile to its west), so its west edge is free — that gives NFC
        # its own meridian instead of crowding the south one shared by the Yagi
        # pair + camera. (Only the end tiles can do this; mid-tiles use E/W for
        # the snake.)
        # QPD + camera both branch off companion_compute and are mutually
        # exclusive per-config (S there); but THIS maximalist superset carries
        # BOTH, so QPD goes N here to avoid colliding with the camera on S.
        (companion_compute, qpd_module,
            Flex(length_mm=70.0, branch_side="N")),
        (companion_compute, camera_module,
            Flex(length_mm=70.0, branch_side="S")),
    ]

    if straight:
        wire_straight(chain_cells, branch_trips)
    else:
        layout_and_wire(edges, aft_end_board,
                        sfold_branches=branch_trips)
    # FR4 sandwich for the bend sim: every interior chain tile is bonded
    # above and below to a 4 mm spacer; the two end tiles see one face
    # only. Branch leaves (camera, qpd, nfc, the two Yagis) fold off a
    # flex and stay un-sandwiched.
    assign_spacer_backings(chain)
    # Root the panel at the new aft end (aft_end_board); activation_interface
    # is now mid-snake (battery compartment aft of it, wakeup nose-ward), so
    # the snake-chain path-walk must start from an actual end tile.
    panel = panel_from_root(
        aft_end_board,
        spacer_edge_keepout_mm=0.5,
        spacer_centre_support_radius_mm=1.5,
    )
    # Snake tiles are joined by the board-to-board LGA lands through the
    # spacers — no snake flex strips, no flex-launch chords. Branch/module
    # flexes (nfc/yagi/qpd/camera) are retained.
    panel.snake_flex = False

    boards = {
        "power_board":          power_board,
        "wakeup_board":         wakeup_board,
        "fin_ble_board":        fin_ble_board,
        "radar_module":         radar_module,
        "companion_compute":    companion_compute,
        "nose_cap":             nose_cap,
        "camera_module":        camera_module,
        "qpd_module":           qpd_module,
        "yagi_ant_a_flex":      yagi_ant_a_flex,
        "yagi_ant_b_flex":      yagi_ant_b_flex,
        "activation_interface": activation_interface,
        _AFT_END:               aft_end_board,
    }
    if cell_floor_board is not None:
        boards[_CELL_FLOOR] = cell_floor_board
    for sp in spacers:
        boards[sp.name] = sp
    # Fit each rigid tile's real layer buildup from the FabProfile catalog
    # (radar picks up the Rogers top dielectric, camera the Al backing).
    # Spacers/flex skip — `set_fitted_stackup` is a no-op for them.
    for b in boards.values():
        b.set_fitted_stackup()
    _lower_coins_for_top_routing(boards)   # keep top-N copper layers routable
    return panel, boards


# ── configuration variants ─────────────────────────────────────────────

# Per-board construction kwargs (material/substrate overrides) so a
# config tile matches its full-twin counterpart.
_BOARD_KWARGS = {
    "radar_module": dict(copper_layers=20),  # FR4 top (RF into the Al block); 20L for mechanical stiffness
    "nose_cap": dict(copper_layers=12, target_thickness_mm=1.4),  # thick cap (1.455mm): stacks direct on radar (spacer discarded), AWR pokes through cutout
    "camera_module": dict(al_backing_mm=0.5),
    # 20L for mechanical stiffness (the stackup that used to host the — now
    # removed — structural Cu T-coin).
    "companion_compute": dict(copper_layers=20),
    # THIN battery-floor tile (reinstated 2026-07-30): 6L / ~0.85 mm, no coin
    # — just the cells' − tab lands + the backbone LGA/via pass-through +
    # the potting pass-through holes.
    "cell_floor_board": dict(copper_layers=6),
    # Flex antenna tiles — polyimide carriers, not circular rigid plates.
    # Tagged here so `build_config_panel` builds them with the right
    # `kind` (mirroring the explicit kwargs in `build_panel`). camera_module
    # and qpd_module are RIGID sensor tiles on flex connectors, so they are
    # deliberately NOT in this map.
    "nfc_antenna_flex":  dict(kind="flex"),
    "yagi_ant_a_flex":   dict(kind="flex"),
    "yagi_ant_b_flex":   dict(kind="flex"),
}


def build_config_panel(board_names, *, branches=None, straight=True,
                       battery_length_mm: float = BATTERY_LENGTH_MM):
    """Build a panel for an explicit board *configuration* — a subset of
    the full snake, listed in fold order. Consecutive boards are joined
    by an inline spacer; `branches` is an optional list of
    `(parent_name, leaf_name, flex)` for any off-fold tiles. Returns
    `(panel, boards)`.

    `straight=True` skips the box-minimising planner and lays the snake
    out as one straight East row (`wire_straight`); branch leaves peel
    off the side of the adjacent interconnecting flex with an S-bend
    rather than claiming their own grid cell.
    """
    if not board_names:
        raise ValueError("build_config_panel: empty configuration")
    boards = {n: Board(n, **_BOARD_KWARGS.get(n, {})) for n in board_names}
    seq = [boards[n] for n in board_names]

    chain_cells, spacers, edges = _interleave(seq, battery_length_mm)

    branch_trips = []
    for pname, lname, flex in (branches or []):
        leaf = Board(lname, **_BOARD_KWARGS.get(lname, {}))
        boards[lname] = leaf
        # No S-fold: the S-turn existed only to tuck a deploy branch
        # alongside the parent's SNAKE flex, dodging the spacer it landed
        # on. The snake flex is removed (snake tiles join via the LGA
        # lands), so every branch now launches straight off its parent
        # edge — matching build_panel (which already disabled the S-fold).
        flex.s_fold = False
        branch_trips.append((boards[pname], leaf, flex))

    if straight:
        wire_straight(chain_cells, branch_trips)
    elif edges:
        layout_and_wire(edges, seq[0], sfold_branches=branch_trips)
    assign_spacer_backings(seq)
    panel = panel_from_root(
        seq[0],
        spacer_edge_keepout_mm=0.5,
        spacer_centre_support_radius_mm=1.5,
    )
    panel.snake_flex = False        # LGA lands replace the snake flex (see build_panel)
    for sp in spacers:
        boards[sp.name] = sp
    # Fit each rigid tile's real layer buildup from the FabProfile catalog
    # (radar picks up the Rogers top dielectric, camera the Al backing).
    # Spacers/flex skip — `set_fitted_stackup` is a no-op for them.
    for b in boards.values():
        b.set_fitted_stackup()
    _lower_coins_for_top_routing(boards)   # keep top-N copper layers routable
    return panel, boards


# ── module-level smoke test ────────────────────────────────────────────

def _print_derived() -> int:
    """Print the derived PanelLayout for side-by-side eyeball comparison
    against `tools/layout_gen/boards/evb_2x.py:PANEL`. Importing the
    reference directly would pull in pcbnew (it transitively imports
    the placer), which isn't available outside KiCad's bundled Python."""
    panel, _ = build_panel()

    print("Derived panel — grid (col, row):")
    for tile in sorted(panel.tiles, key=lambda t: panel.tiles[t]):
        print(f"  {panel.tiles[tile]!r:>10}   {tile}")

    print(f"\nSnake chain ({len(panel.snake_chain)} tiles):")
    print("  " + " → ".join(panel.snake_chain))

    print(f"\nBranches ({len(panel.branches or [])}):")
    for src, dst in (panel.branches or []):
        length = (panel.branch_flex_lengths or {}).get((src, dst))
        tag = f" (length {length} mm)" if length else ""
        print(f"  {src} → {dst}{tag}")

    print("\nPer-tile overrides:")
    print(f"  tile_diameters       = {panel.tile_diameters}")
    print(f"  tile_rect_dimensions = {panel.tile_rect_dimensions}")
    print(f"  tile_top_substrate   = {panel.tile_top_substrate}")
    print(f"  tile_al_backing_mm   = {panel.tile_al_backing_mm}")
    print(f"  tile_outlines        = "
          f"{ {k: str(v) for k, v in (panel.tile_outlines or {}).items()} }")
    print(f"\nSpacer keepouts:")
    print(f"  edge_keepout_mm           = {panel.spacer_edge_keepout_mm}")
    print(f"  centre_support_radius_mm  = {panel.spacer_centre_support_radius_mm}")

    return 0


if __name__ == "__main__":
    raise SystemExit(_print_derived())
