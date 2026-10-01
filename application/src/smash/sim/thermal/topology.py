"""Thermal RC graph built from real `Board` + `FabProfile` data.

Ports the legacy (now-removed) `thermal_sim/topology.py` standalone
CSV+positions.json reader into the smash library: instead of parsing
exported artifacts,
it walks `Board.chip_placements` and pulls per-chip dissipation /
thermal-resistance straight off the `Chip` objects, with material
conductivities resolved through the `FabProfile` catalog.

Graph nodes
-----------
  - one per chip with non-zero dissipation (the "die" node)
  - one per non-spacer tile carrying chips (the "tile body" node)
  - one per spacer (the "spacer body" node — represents the axial
    stack-up path through the snake)
  - one "housing" node (boundary, T = T_amb)

Edges (thermal resistance R, K/W)
---------------------------------
  die → tile_body              Rth_jc + R_pad_spread  (per-chip;
                                                       optional ∥ R_underfill
                                                       for BGAs / CSPs)
  tile_body[k] → spacer_body[k+1]    via spacer axial conduction
  tile_body[k] → tile_body[k+1]      via flex Cu (parallel path across
                                       a spacer)
  tile_body → housing                R via Stycast lateral conduction
                                       (potting) ∥ optional Al-backing
                                       direct-to-housing path

The spacer-axial path keys κ off `Board.spacer_material` — the FR-4
default carries ~0.3 W/(m·K), aluminium ~167 W/(m·K). That's the heat
removal payoff for picking Al spacers; the bend-sim picked them for
stiffness, the thermal sim sees them as the dominant tile-to-tile
conduction path.
"""
from __future__ import annotations

import dataclasses
import math
import typing as _t


# ── Material constants — fixed physics, NOT in FabProfile ───────────────
# Copper conductivity is a physics constant; the fab profile has copper
# foils but the κ doesn't vary across rolls. Same logic as the bend-sim
# treating Cu youngs_modulus as a constant.
KAPPA_CU_W_PER_MK = 400.0


# ── Geometry defaults — used when the Board doesn't expose them ─────────
# Flex strip Cu cross-section: 4 layers × 17 µm (0.5 oz) Cu, 15 mm fold
# length. Widths per-link can be overridden by the panel's flex strip
# definitions; we fall back to 12 mm — the median snake link.
FLEX_LAYER_COUNT_DEFAULT = 4
FLEX_CU_THICKNESS_M = 17e-6
FLEX_BEND_LENGTH_M_DEFAULT = 15e-3
FLEX_WIDTH_M_DEFAULT = 12e-3

# Lumped chip-pad spread on F.Cu down through vias + inner pours +
# laterally across the tile. Estimated analytically for a 4 mm chip on a
# Ø34 tile with 4 inner Cu sheets at 17 µm + 4 FR-4 layers at 200 µm.
TILE_SPREAD_K_PER_W_DEFAULT = 8.0

# BGA underfill standoff (typical SAC305 ball collapse). Used for the
# UF-path cross section; UF conductivity comes from the FabProfile
# adhesive entry.
UNDERFILL_THICKNESS_M = 0.4e-3

# Default housing geometry — Ø50 inner ID, Ø34 tile OD → 8 mm radial
# gap filled with Stycast.
POTTING_GAP_MM_DEFAULT = 8.0
T_AMBIENT_C_DEFAULT = 25.0

# Legacy fixed R when --no-potting is requested (air-gap assembly).
TILE_TO_HOUSING_K_PER_W_DEFAULT = 30.0

# Thermal-interface paste between an Al-backing plate and the housing
# wall. Bench-test typical 0.5-1 K/W for thin grease.
TIM_R_K_PER_W_DEFAULT = 1.0


# ── Material lookup helpers ────────────────────────────────────────────
def _fab_kappa(fab, kind: str, name: str | None = None,
               default: float = 0.0) -> float:
    """Look up a thermal conductivity in the FabProfile catalog.

    `kind` ∈ {"adhesive_encapsulant", "adhesive_underfill", "metal_al",
    "laminate_fr4"}. Falls back to `default` if the catalog doesn't
    populate the field (older profiles without thermal data).
    """
    if fab is None:
        return default
    if kind == "adhesive_encapsulant":
        for ad in fab.adhesives:
            if ad.role == "encapsulant" and (name is None or ad.name == name):
                if ad.thermal_w_mk:
                    return ad.thermal_w_mk
                break
    elif kind == "adhesive_underfill":
        for ad in fab.adhesives:
            if ad.role == "underfill" and (name is None or ad.name == name):
                if ad.thermal_w_mk:
                    return ad.thermal_w_mk
                break
    elif kind == "metal_al":
        for m in fab.metal_options:
            if m.material == "aluminium" and m.role == "backing":
                if m.thermal_w_mk:
                    return m.thermal_w_mk
                break
    elif kind == "laminate_fr4":
        for lam in fab.laminates:
            if lam.material == "FR4":
                if lam.thermal_w_mk:
                    return lam.thermal_w_mk
                break
    return default


def _spacer_material_kappa(board, fab) -> float:
    """κ for the spacer-floor material on `board`. Defaults to FR-4
    catalog value (0.3 W/(m·K) if the catalog doesn't quote it)."""
    mat = getattr(board, "spacer_material", "fr4") or "fr4"
    if mat == "aluminium":
        return _fab_kappa(fab, "metal_al", default=167.0)
    return _fab_kappa(fab, "laminate_fr4", default=0.3)


# ── BGA classifier ──────────────────────────────────────────────────────
# Mirrors `tools/layout/placer` so we underfill the same chips the
# placer + bend-sim do.
_BGA_PATTERNS = ("BGA", "CSSM", "FBGA", "TFBGA", "UFBGA", "VFBGA", "WLCSP",
                 "FCBGA", "ODCSP", "FCCSP", "WL-CSP")
_NON_BGA_PATTERNS = ("LFCSP", "QFN", "TSSOP", "SOIC", "SOT", "DFN",
                     "TQFP", "LQFP", "WQFN", "VQFN", "PDFN")


def _is_underfilled(chip) -> bool:
    """True iff this chip's footprint family is BGA/CSP — gets capillary
    underfill in assembly + a parallel UF conduction path in the model."""
    fp = getattr(chip, "footprint", None)
    name = (getattr(fp, "name", "") or "").upper()
    pkg = (getattr(fp, "package_class", "") or "").upper()
    text = f"{name} {pkg}"
    if any(p in text for p in _NON_BGA_PATTERNS):
        return False
    return any(p in text for p in _BGA_PATTERNS)


# ── Resistance helpers ─────────────────────────────────────────────────
def r_flex_link(width_mm: float,
                bend_length_m: float = FLEX_BEND_LENGTH_M_DEFAULT,
                cu_layers: int = FLEX_LAYER_COUNT_DEFAULT,
                cu_thickness_m: float = FLEX_CU_THICKNESS_M) -> float:
    """Conduction through a flex strip's copper. `width_mm` in millimetres
    matches the panel's flex-strip definitions."""
    a_cu_m2 = (width_mm * 1e-3) * cu_layers * cu_thickness_m
    if a_cu_m2 <= 0:
        return float("inf")
    return bend_length_m / (KAPPA_CU_W_PER_MK * a_cu_m2)


def r_spacer_axial(area_m2: float, thickness_m: float,
                   kappa_w_per_mk: float) -> float:
    """Through-thickness conduction through a spacer disc — material `κ`
    keyed to the spacer-floor choice (FR-4 or Al)."""
    if area_m2 <= 0 or kappa_w_per_mk <= 0:
        return float("inf")
    return thickness_m / (kappa_w_per_mk * area_m2)


def r_chip_to_tile(chip, tile_spread: float = TILE_SPREAD_K_PER_W_DEFAULT
                   ) -> float:
    """Junction-to-case + die-attach + via-stitch + lateral pour spread.

    `chip.rth_jc_cw` is the datasheet junction-to-case figure; we lump a
    fixed `tile_spread` in series for the via-stitch + inner-pour spread.
    A chip without a populated `rth_jc_cw` defaults to 30 K/W (mid-range
    SOIC/QFN typical) — flag those in the report."""
    rjc = getattr(chip, "rth_jc_cw", None)
    rjc = 30.0 if rjc is None else rjc
    return rjc + tile_spread


# Cu coin embedded in the tile stackup (NCAB Copper Coin Design Guide
# 1.0) acts as a low-R shortcut from F.Cu under the chip to B.Cu — bulk
# κ_Cu = 400 W/(m·K) replaces the FR-4 (~0.3) + Cu-foil (17 µm × few
# inner layers) sandwich the default `TILE_SPREAD_K_PER_W_DEFAULT` lumps
# at 8 K/W. For a 3 mm thick coin under a chip footprint, the through-
# thickness R is sub-millikelvin; the binding R becomes the chip-to-coin
# top-face spreading + the coin-to-spacer interface. We lump these
# together at a much lower default.
KAPPA_CU_W_PER_MK = 400.0
TILE_SPREAD_OVER_COIN_K_PER_W_DEFAULT = 0.5      # chip directly on coin
TILE_SPREAD_NEAR_COIN_K_PER_W_DEFAULT = 4.0      # chip off coin, same board


def _coin_under_chip(board, position_mm: tuple, footprint):
    """Return the first `CuCoinInsert` whose flange covers a chip at
    `position_mm` (board-local). Coverage uses the chip's corner-reach
    (bounding-circle radius) so the whole body sits over the coin, not
    just the centre. Returns None if no coin or no coverage."""
    coins = getattr(board, "cu_coin_inserts", None) or []
    if not coins or footprint is None:
        return None
    size = getattr(footprint, "size_mm", None)
    if not size:
        return None
    import math
    w, h = size
    corner_reach = math.sqrt((w / 2.0) ** 2 + (h / 2.0) ** 2)
    x, y = position_mm
    for coin in coins:
        if coin.covers_position(x, y, clearance_mm=corner_reach):
            return coin
    return None


def _board_has_coin(board) -> bool:
    return bool(getattr(board, "cu_coin_inserts", None))


def r_chip_to_tile_coin(chip, position_mm, board) -> tuple[float, str]:
    """Variant of `r_chip_to_tile` that picks the appropriate tile-spread
    R based on whether a Cu coin sits under the chip. Returns
    (R_K_per_W, label) where label is appended to the edge kind for the
    report so coin-pathed chips are auditable.

      - chip body sits OVER a coin → ~0.5 K/W (Cu κ 1300× FR-4 — the
        binding spread becomes top-face contact + coin-spacer interface,
        not the FR-4 through-board path).
      - chip on a board that carries a coin but body sits OFF it →
        ~4 K/W (the coin acts as a lateral heat-spreader for nearby
        chips via the inner Cu pours; partial benefit).
      - no coin on the board → the legacy 8 K/W default.
    """
    fp = getattr(chip, "footprint", None)
    coin = _coin_under_chip(board, position_mm, fp)
    if coin is not None:
        return r_chip_to_tile(chip, TILE_SPREAD_OVER_COIN_K_PER_W_DEFAULT), \
               "+coin(over)"
    if _board_has_coin(board):
        return r_chip_to_tile(chip, TILE_SPREAD_NEAR_COIN_K_PER_W_DEFAULT), \
               "+coin(near)"
    return r_chip_to_tile(chip), ""


def r_underfill(chip_body_area_mm2: float, thickness_m: float,
                kappa_w_per_mk: float) -> float:
    """Conduction R through the underfill from chip die bottom to PCB
    top Cu. `chip_body_area_mm2` from the footprint outline; UF κ comes
    from the FabProfile adhesive (Eccobond UF 1173 typically)."""
    area_m2 = chip_body_area_mm2 * 1e-6
    if area_m2 <= 0 or kappa_w_per_mk <= 0:
        return float("inf")
    return thickness_m / (kappa_w_per_mk * area_m2)


def r_tile_to_housing_via_potting(perimeter_m: float, thickness_m: float,
                                  gap_m: float,
                                  kappa_w_per_mk: float) -> float:
    """Lateral conduction through the encapsulant from a tile's outer
    edge to the housing inner wall. R = gap / (κ · A) with A = edge
    perimeter × tile thickness — the surface area presented to the
    radial potting annulus."""
    a_edge_m2 = perimeter_m * thickness_m
    if a_edge_m2 <= 0 or kappa_w_per_mk <= 0:
        return float("inf")
    return gap_m / (kappa_w_per_mk * a_edge_m2)


def r_tile_to_housing_via_al(tile_radius_m: float, al_thickness_m: float,
                             kappa_al_w_per_mk: float,
                             tim_r_k_per_w: float = TIM_R_K_PER_W_DEFAULT
                             ) -> float:
    """Through-thickness Al backing + TIM-paste contact to housing wall.
    Area = full tile face (π r²)."""
    a_m2 = math.pi * tile_radius_m ** 2
    if a_m2 <= 0 or kappa_al_w_per_mk <= 0:
        return float("inf")
    r_al = al_thickness_m / (kappa_al_w_per_mk * a_m2)
    return r_al + tim_r_k_per_w


# ── Graph data classes ──────────────────────────────────────────────────
@dataclasses.dataclass
class Node:
    name: str
    kind: str                       # "die" | "tile_body" | "spacer_body" | "housing"
    parent_tile: str = ""
    chip: object | None = None      # Chip (die nodes only)
    p_input_w: float = 0.0
    t_fixed_c: float | None = None  # None = unknown, value = boundary


@dataclasses.dataclass
class Edge:
    a: str
    b: str
    r_k_per_w: float
    kind: str


@dataclasses.dataclass
class ThermalGraph:
    nodes: dict = dataclasses.field(default_factory=dict)
    edges: list = dataclasses.field(default_factory=list)

    def add_node(self, node: Node) -> None:
        if node.name in self.nodes:
            raise ValueError(f"duplicate node {node.name}")
        self.nodes[node.name] = node

    def add_edge(self, a: str, b: str, r: float, kind: str = "") -> None:
        if a not in self.nodes or b not in self.nodes:
            raise KeyError(f"unknown nodes in edge ({a}, {b})")
        self.edges.append(Edge(a=a, b=b, r_k_per_w=r, kind=kind))


# ── Builder ─────────────────────────────────────────────────────────────
def _tile_radius_m(board) -> float:
    """Outer radius of a circular tile in metres. Falls back to 17 mm
    (Ø34 tile) if the geometry doesn't pin a diameter."""
    g = getattr(board, "geometry", None)
    if g is not None:
        d = getattr(g, "diameter_mm", None)
        if d:
            return d / 2000.0
        rect = getattr(g, "rect_dimensions", None)
        if rect:
            # Equivalent circle (same area) — approximation for rect tiles
            return math.sqrt(rect[0] * rect[1] / math.pi) / 1000.0
    return 0.017


def _chip_body_area_mm2(chip) -> float:
    fp = getattr(chip, "footprint", None)
    if fp is None:
        return 0.0
    size = getattr(fp, "size_mm", None)
    if size and len(size) >= 2 and size[0] > 0 and size[1] > 0:
        return float(size[0]) * float(size[1])
    return 0.0


def _chip_power_w(chip, use_p_max: bool) -> float:
    p_active = getattr(chip, "p_active_w", None) or 0.0
    p_max = getattr(chip, "p_max_w", None) or p_active
    return float(p_max if use_p_max else p_active)


def build_graph(chain: list, boards: dict, *, fab=None,
                use_p_max: bool = False,
                flex_width_overrides_mm: dict | None = None,
                tile_thickness_mm: float = 1.6,
                spacer_thickness_mm: float = 4.0,
                t_ambient_c: float = T_AMBIENT_C_DEFAULT,
                potting: bool = True,
                potting_gap_mm: float = POTTING_GAP_MM_DEFAULT,
                tile_to_housing_k_per_w: float = TILE_TO_HOUSING_K_PER_W_DEFAULT,
                ) -> ThermalGraph:
    """Build the steady-state thermal graph for a snake `chain` of Boards.

    `chain`: list of `Board.name` strings in fold order (tiles + spacers
        interleaved — same shape as the snake the bend-sim consumes).
    `boards`: dict[name → Board] from `build_panel()`.
    `fab`: `FabProfile` for material-κ lookups. If None, falls back to
        documented defaults (Stycast 2651MM 0.6, Eccobond UF1173 0.55,
        Al 167, FR-4 0.3 W/(m·K)).
    `use_p_max`: inject each chip's `p_max_w` instead of `p_active_w`
        (worst-case burst dissipation).
    `flex_width_overrides_mm`: dict keyed by (a_name, b_name) tile pair
        giving the link width if it differs from the 12 mm default.
    `potting`: True applies the Stycast lateral-edge conduction model.
        False uses the legacy fixed `tile_to_housing_k_per_w` (air gap).
    """
    # Look up the encapsulant + underfill κ ONCE — these don't change
    # across the graph, only the per-tile geometry does.
    k_potting = _fab_kappa(fab, "adhesive_encapsulant", default=0.6)
    k_underfill = _fab_kappa(fab, "adhesive_underfill", default=0.55)
    k_al = _fab_kappa(fab, "metal_al", default=167.0)

    g = ThermalGraph()
    g.add_node(Node(name="housing", kind="housing", t_fixed_c=t_ambient_c))

    # ── tile + spacer body nodes, dies, body→housing edges ──────────
    for tile_name in chain:
        board = boards.get(tile_name)
        if board is None:
            continue
        is_spacer = getattr(board, "kind", "") == "spacer"
        node_kind = "spacer_body" if is_spacer else "tile_body"
        g.add_node(Node(name=f"body:{tile_name}", kind=node_kind))

        radius_m = _tile_radius_m(board)
        al_mm = (getattr(board, "al_backing_mm", 0.0) or 0.0) if not is_spacer else 0.0

        # body → housing
        if al_mm > 0:
            r_via_al = r_tile_to_housing_via_al(
                tile_radius_m=radius_m, al_thickness_m=al_mm * 1e-3,
                kappa_al_w_per_mk=k_al,
            )
            if potting:
                perimeter_m = 2.0 * math.pi * radius_m
                t_m = (spacer_thickness_mm if is_spacer
                       else tile_thickness_mm) * 1e-3
                r_via_pot = r_tile_to_housing_via_potting(
                    perimeter_m, t_m, gap_m=potting_gap_mm * 1e-3,
                    kappa_w_per_mk=k_potting,
                )
                r_housing = 1.0 / (1.0 / r_via_al + 1.0 / r_via_pot)
                kind = (f"tile_to_housing({tile_name}, Al {al_mm:.1f}mm "
                        f"∥ potting)")
            else:
                r_housing, kind = r_via_al, (
                    f"tile_to_housing({tile_name}, Al backing {al_mm:.1f}mm)")
        elif potting:
            perimeter_m = 2.0 * math.pi * radius_m
            t_m = (spacer_thickness_mm if is_spacer
                   else tile_thickness_mm) * 1e-3
            r_housing = r_tile_to_housing_via_potting(
                perimeter_m, t_m, gap_m=potting_gap_mm * 1e-3,
                kappa_w_per_mk=k_potting,
            )
            kind = (f"tile_to_housing({tile_name}, potting "
                    f"{potting_gap_mm:.1f}mm, A_edge="
                    f"{perimeter_m * t_m * 1e6:.0f}mm²)")
        else:
            r_housing = tile_to_housing_k_per_w
            kind = f"tile_to_housing({tile_name}, air gap default)"
        g.add_edge(f"body:{tile_name}", "housing", r=r_housing, kind=kind)

        # Die nodes — skip spacers (no chips there)
        if is_spacer:
            continue
        for pl in board.chip_placements:
            chip = pl.item
            power_w = _chip_power_w(chip, use_p_max)
            if power_w <= 0:
                continue
            die_name = f"die:{tile_name}/{chip.ref}"
            g.add_node(Node(
                name=die_name, kind="die",
                parent_tile=tile_name, chip=chip, p_input_w=power_w,
            ))
            r_normal, coin_tag = r_chip_to_tile_coin(
                chip, pl.position_mm, board)
            kind_label = f"jc+spread{coin_tag}({chip.ref})"
            if _is_underfilled(chip):
                body_area = _chip_body_area_mm2(chip)
                if body_area > 0:
                    r_uf = r_underfill(body_area, UNDERFILL_THICKNESS_M,
                                       k_underfill)
                    r_eff = 1.0 / (1.0 / r_normal + 1.0 / r_uf)
                    kind_label = (f"jc+spread{coin_tag}∥UF({chip.ref}, "
                                  f"area={body_area:.0f}mm²)")
                    r_normal = r_eff
            g.add_edge(die_name, f"body:{tile_name}",
                       r=r_normal, kind=kind_label)

    # ── snake-chain tile-to-tile edges ──────────────────────────────
    # Two parallel paths exist between every real tile pair:
    #   1. Axial path through the spacer between them — material depends
    #      on Board.spacer_material (FR-4 ~0.3, Al ~167 W/(m·K)).
    #   2. Flex Cu wrapping around the spacer (independent of spacer
    #      material). We add both as separate edges; the solver handles
    #      parallel conductance correctly.
    for k in range(len(chain) - 1):
        a, b = chain[k], chain[k + 1]
        if (f"body:{a}" not in g.nodes or f"body:{b}" not in g.nodes):
            continue
        a_board = boards.get(a)
        b_board = boards.get(b)
        a_spacer = getattr(a_board, "kind", "") == "spacer"
        b_spacer = getattr(b_board, "kind", "") == "spacer"
        if a_spacer or b_spacer:
            sp_board = a_board if a_spacer else b_board
            other_board = b_board if a_spacer else a_board
            kappa = _spacer_material_kappa(other_board, fab)
            r = r_spacer_axial(
                area_m2=math.pi * _tile_radius_m(sp_board) ** 2,
                thickness_m=spacer_thickness_mm * 1e-3,
                kappa_w_per_mk=kappa,
            )
            mat = (getattr(other_board, "spacer_material", "fr4")
                   or "fr4").upper()
            g.add_edge(f"body:{a}", f"body:{b}", r=r,
                       kind=f"spacer_{mat}")
        else:
            width = (flex_width_overrides_mm or {}).get(
                (a, b), FLEX_WIDTH_M_DEFAULT * 1e3)
            g.add_edge(f"body:{a}", f"body:{b}",
                       r=r_flex_link(width),
                       kind=f"flex({width:.1f}mm)")

    # Parallel flex-Cu link between consecutive REAL tiles (skipping the
    # intervening spacer node). The flex strip wraps around the spacer;
    # its Cu path is roughly the same length whether or not the spacer
    # is there. This is the dominant tile-to-tile conduction for FR-4
    # spacers and ~peer with Al spacers' axial path.
    real_tiles = [t for t in chain if getattr(boards.get(t), "kind", "")
                  != "spacer"]
    for k in range(len(real_tiles) - 1):
        a, b = real_tiles[k], real_tiles[k + 1]
        if (f"body:{a}" not in g.nodes or f"body:{b}" not in g.nodes):
            continue
        width_mm = (flex_width_overrides_mm or {}).get(
            (a, b), FLEX_WIDTH_M_DEFAULT * 1e3)
        g.add_edge(f"body:{a}", f"body:{b}", r=r_flex_link(width_mm),
                   kind=f"flex_cu({a}↔{b}, {width_mm:.1f}mm)")

    return g
