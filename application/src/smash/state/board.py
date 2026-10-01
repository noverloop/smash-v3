"""Board — one sub-PCB tile in the snake panel.

Merged superset of the old smash_state.Board (stackup, fab, cost
rollups) and the layout.Board (geometry, edges, placements).
"""
from __future__ import annotations

import dataclasses
import pathlib

from smash.state.stackup.layer import Layer
from smash.state.topology.board_edge import BoardEdge
from smash.state.topology.flex import Flex

# Direction-step lookups used by add_<dir>() / panel walkers.
_REVERSE: dict = {"N": "S", "S": "N", "E": "W", "W": "E"}


@dataclasses.dataclass
class Board:
    """One sub-PCB in the snake panel — what system.py calls a "tile"
    (set via `_BOARD_TAG[0] = ...`).

    `kind` distinguishes the three roles a tile can have:
      - "rigid": a populated FR4 tile (carries components + traces)
      - "spacer": a mechanical interposer between two snake-folded
                  rigid tiles (cavities milled for tall chips on both
                  adjacent faces; no signals)
      - "flex":   flex-only sub-board (no rigid substrate, e.g.
                  nfc_antenna_flex)

    `features` is a per-board dict of optional populate flags. The
    board's footprint (pads + routing) is fixed; whether each named
    feature actually gets soldered depends on these flags. False =
    DNP (Do Not Populate), True = populated. Example: companion_io
    carries the WiFi module footprint always, but `features["wifi"]`
    defaults to False and is only flipped to True by `add_wifi()`.
    """
    name: str
    kind: str = "rigid"                       # "rigid" | "spacer" | "flex"
    description: str | None = None
    # Optional snake-chain info — set later by the placer when the
    # accordion-fold order is known.
    snake_index: int | None = None           # position in the chain
    standalone: bool = False                 # True = lives off the chain
    # Per-board optional-feature populate flags (default: DNP).
    features: dict = dataclasses.field(default_factory=dict)
    # Layer stackup, top → bottom. Each entry is a Cu layer; the
    # insulator between adjacent layers is `Layer.dielectric_below`
    # on the upper layer. Empty for boards that haven't declared
    # their stackup yet — populated by the build pipeline.
    stackup: list = dataclasses.field(default_factory=list)
    note: str | None = None             # free-form catch-all

    # ── geometry / outline ───────────────────────────────────────────
    # Single `geometry` value object replaces the old triple
    # (diameter_mm / rect_dimensions / outline_dxf). If left None,
    # `__post_init__` auto-fetches it from
    # `data/board_geometries.json` keyed on `self.name`. Override
    # inline by passing your own `BoardGeometry(...)` to the
    # constructor.
    geometry: object | None = None           # smash.state.board_geometry.BoardGeometry

    # ── materials (per-tile substrate / backing overrides) ──────────
    top_substrate: str = "fr4"               # "fr4" | "rogers_ro4350b_5mil"
    al_backing_mm: float = 0.0               # aluminium thermal spreader
                                              # thickness bonded under the tile
    # Per-board layer-count override for `set_fitted_stackup()`. None →
    # the project default (14L). Setting this lets a structurally-loaded
    # tile (radar, companion_compute) carry a thicker stack to host a
    # tall Cu coin (NCAB Advanced max H = 3 mm needs ≥ ~20L). NCAB
    # Advanced caps board layers at 30.
    copper_layers: int | None = None
    # Explicit fitted-stackup thickness target (mm). None → catalog-natural
    # buildup for `copper_layers`. Set when a tile must hit a specific Z (e.g.
    # the nose_cap at 0.60 mm for the UJ31 mid-mount + the AWR-top alignment).
    target_thickness_mm: float | None = None
    # Per-spacer milled thickness override (mm), for `kind="spacer"` tiles. A
    # spacer's milled thickness is SPACER_THICKNESS_MM (4 mm) by default; set this
    # to size a spacer to just what it needs — the radar↔nose_cap spacer (AWR
    # height − nose_cap thickness) and the battery-compartment thin discs (a
    # sub-fab-limit slice of the cell length, so the holder is a manufacturable
    # stack of thin spacers, not one thick disc). Ignored for non-spacer kinds.
    # None → SPACER_THICKNESS_MM.
    thickness_override_mm: float | None = None

    # ── snake-stack sandwich (set by the panel builder) ─────────────
    # After potting, each rigid tile is bonded above/below to the
    # adjacent spacer's floor via cured Stycast. The bend sim's
    # composite plate adds these as bonded layers (one each face, if
    # non-zero) — they dominate the composite stiffness for interior
    # snake tiles. 0 means "tile not bonded to a spacer on this face"
    # (end-of-chain or branch leaf). `spacer_material` chooses the
    # spacer-floor material: "fr4" (default, milled PCB) or "aluminium"
    # (CNC-milled Al billet — ~3.5× stiffer, ~550× higher thermal κ,
    # +1 g/cm³ mass; needs anodize or polyimide film at PCB contact for
    # electrical isolation).
    spacer_floor_above_mm: float = 0.0
    spacer_floor_below_mm: float = 0.0
    spacer_material: str = "fr4"             # "fr4" | "aluminium"

    # ── per-tile copper-coin inserts (NCAB Copper Coin Design Guide 1.0)
    # Each entry is a `CuCoinInsert` placed in the middle of the rigid
    # tile's stackup for localised structural support of the chip(s)
    # above. The bend sim's `composite_plate` walks any coin under a
    # chip's position to compute the augmented local D.
    cu_coin_inserts: list = dataclasses.field(default_factory=list)
    # Name of the FabProfile this tile is built on (None → the default
    # profile). The anchor the stackup fitter / DRC read; no behaviour
    # change yet.
    fab: str | None = None
    # Board-wide reflow solder alloy (name into the FabProfile catalog;
    # None → the profile's default solder). Solder is assigned per board,
    # not per chip — THT/connector exceptions are a fab-capability concern
    # (FabProfile.supports_multi_alloy), not modelled per joint.
    solder: str | None = None

    # ── graph topology (snake/branch/mate edges to neighbours) ───────
    edges: dict = dataclasses.field(default_factory=dict)  # dir → BoardEdge

    # ── contained items (placer fills) ──────────────────────────────
    # Container owns the placement record — the contained Chip /
    # CavityRegion / KeepoutRegion are position-free templates. Each
    # entry is a `Placement(position_mm, rotation_deg, item)` with
    # position in board-local coords (relative to board centre).
    chip_placements:    list = dataclasses.field(default_factory=list)
    cavity_placements:  list = dataclasses.field(default_factory=list)
    keepout_placements: list = dataclasses.field(default_factory=list)
    # Annotation outlines drawn on this board's silkscreen — e.g. the
    # neighbouring spacer's through-cut window fold-mirrored into THIS
    # board's frame, so face chips can be moved knowing the existing
    # cutout boundary. Entries: (layer, [(x, y), …] board-local
    # math-y-up, label | None).
    silk_overlays:      list = dataclasses.field(default_factory=list)

    # ── routing (Track / Via / Zone, board-local mm, math-y-up) ──────
    # Empty until routed — populated by the .ses importer
    # (smash.state.routing.ingest) or manual authoring. See
    # smash.state.routing.
    tracks: list = dataclasses.field(default_factory=list)
    vias:   list = dataclasses.field(default_factory=list)
    zones:  list = dataclasses.field(default_factory=list)

    # ── derived ──────────────────────────────────────────────────────

    def __post_init__(self):
        """Auto-populate `geometry` from data/board_geometries.json if
        the caller didn't supply one. Lazy import to avoid a circular
        dependency at module load (board_geometry imports
        layout.cavities, which is a sibling subtree)."""
        if self.geometry is None:
            from smash.state.board_geometry import load_board_geometry
            try:
                self.geometry = load_board_geometry(self.name)
            except KeyError:
                # Not in the registry and not a spacer_* fallback:
                # leave geometry=None and let the consumer decide
                # whether that's a hard error. Some test fixtures
                # construct ad-hoc Boards without a JSON entry.
                pass

    @property
    def is_spacer(self) -> bool:
        """True iff `kind == 'spacer'` — convenience for the graph
        walker and the placer."""
        return self.kind == "spacer"

    # ── z-thickness (folded-stack height contribution) ───────────────
    # Every rigid tile is the 14-layer FR4 stack (uniform — good for
    # setback rigidity; Rogers/thin variants not yet modelled). Spacers
    # are the milled 4 mm interposers. Mirrors the export's
    # _STACKUP_BLOCK (14 Cu + 13 dielectric + masks) and
    # SPACER_THICKNESS_MM; duplicated here so smash.state stays free of a
    # smash.layout import.
    RIGID_14L_THICKNESS_MM = 2.226            # fallback when stackup unset
    SPACER_THICKNESS_MM = 4.0
    MASK_FINISH_MM = 0.02                      # two 0.01 mm solder masks

    @property
    def thickness_mm(self) -> float:
        """Physical z-thickness of this tile. Derived from `stackup` when
        populated (Σ copper + Σ dielectric + solder masks + Al backing);
        else the legacy 14L constant. Spacers are the milled interposer."""
        if self.is_spacer:
            return self.thickness_override_mm or self.SPACER_THICKNESS_MM
        if self.stackup:
            cu_um = sum(layer.thickness_um for layer in self.stackup)
            di_um = sum(layer.dielectric_below.thickness_um
                        for layer in self.stackup
                        if getattr(layer, "dielectric_below", None) is not None)
            return (cu_um + di_um) / 1000.0 + self.MASK_FINISH_MM + self.al_backing_mm
        return self.RIGID_14L_THICKNESS_MM + self.al_backing_mm

    def set_fitted_stackup(self, fab=None) -> "Board":
        """Populate `self.stackup` with a buildup fitted from the
        `FabProfile` catalog (substrate / backing taken from this board).
        No-op for non-rigid tiles. Returns self for chaining.

        When no explicit `fab` is passed, the board's own `fab` name (if set)
        is resolved to its profile via the registry — so each tile builds
        against the NCAB tier it was assigned."""
        if self.kind != "rigid":
            return self
        from smash.state.stackup.fit import fit_stackup, StackupSpec
        if fab is None and self.fab is not None:
            from smash.state.fab.ncab import get_fab_profile
            fab = get_fab_profile(self.fab)
        self.stackup = fit_stackup(StackupSpec.for_board(self), fab=fab)
        return self

    # ── geometry conveniences ────────────────────────────────────────

    @property
    def diameter_mm(self) -> float | None:
        """Shortcut for `geometry.diameter_mm` (back-compat for old
        call sites). Returns None for rect/dxf boards."""
        g = self.geometry
        return g.diameter_mm if g is not None else None

    @property
    def rect_dimensions(self) -> tuple | None:
        """Shortcut for `geometry.rect_dimensions`."""
        g = self.geometry
        return g.rect_dimensions if g is not None else None

    @property
    def outline_dxf(self):
        """Shortcut for `geometry.dxf_path`."""
        g = self.geometry
        return g.dxf_path if g is not None else None

    # ── connection API (was smash.layout.board.Board) ────────────────

    def add_north(self, other: "Board", *,
                  flex: "Flex | None" = None,
                  kind: str = "snake") -> "Board":
        return self._connect("N", other, flex, kind)

    def add_south(self, other: "Board", *,
                  flex: "Flex | None" = None,
                  kind: str = "snake") -> "Board":
        return self._connect("S", other, flex, kind)

    def add_east(self, other: "Board", *,
                 flex: "Flex | None" = None,
                 kind: str = "snake") -> "Board":
        return self._connect("E", other, flex, kind)

    def add_west(self, other: "Board", *,
                 flex: "Flex | None" = None,
                 kind: str = "snake") -> "Board":
        return self._connect("W", other, flex, kind)

    def _connect(self, direction: str, other: "Board",
                 flex: "Flex | None", kind: str) -> "Board":
        if direction in self.edges:
            raise ValueError(
                f"{self.name}: {direction} already connected to "
                f"{self.edges[direction].other.name}")
        rev = _REVERSE[direction]
        if rev in other.edges:
            raise ValueError(
                f"{other.name}: {rev} already connected to "
                f"{other.edges[rev].other.name}")
        if kind in ("snake", "branch") and flex is None:
            flex = Flex()
        if kind == "mate" and flex is not None:
            raise ValueError("mate links have no flex strip")
        edge = BoardEdge(direction=direction, other=other,
                         flex=flex, kind=kind)
        self.edges[direction] = edge
        other.edges[rev] = BoardEdge(direction=rev, other=self,
                                     flex=flex, kind=kind)
        return other

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["stackup"] = [layer.to_dict() if isinstance(layer, Layer) else layer
                        for layer in self.stackup]
        for key in ("tracks", "vias", "zones"):
            d[key] = [item.to_dict() if hasattr(item, "to_dict") else item
                      for item in getattr(self, key)]
        return d

    # ── stackup queries ──────────────────────────────────────────────

    def layer(self, name: str) -> Layer:
        """Look up a Layer by name. Raises if not in the stackup."""
        for layer in self.stackup:
            if layer.name == name:
                return layer
        raise KeyError(f"{self.name}: no layer {name!r} in stackup")

    def embedded_cap_pairs(self) -> list:
        """Return every embedded-cap layer pair on this board.
        Each entry is (pwr_layer, gnd_layer, dielectric_between).
        Useful for "which nets get free decoupling?" queries.
        """
        pairs = []
        by_name = {layer.name: layer for layer in self.stackup}
        seen = set()
        for layer in self.stackup:
            if layer.role != "embedded_cap_power" or layer.name in seen:
                continue
            partner = by_name.get(layer.paired_with) if layer.paired_with else None
            if partner is None or partner.role != "embedded_cap_gnd":
                continue
            # The thin dielectric is on whichever of the two has the
            # other as its immediate neighbour below.
            di = (layer.dielectric_below
                  if self.stackup.index(layer) + 1 < len(self.stackup)
                     and self.stackup[self.stackup.index(layer) + 1] is partner
                  else partner.dielectric_below)
            pairs.append((layer, partner, di))
            seen.update({layer.name, partner.name})
        return pairs

    def planes_for_net(self, net_name: str) -> list:
        """Every layer whose `rail` matches `net_name`. Used to figure
        out whether a stackup-absorbed cap on a given net has a
        matching plane pair."""
        return [layer for layer in self.stackup if layer.rail == net_name]

    # ── board-local Z datum (from the buildup) ───────────────────────
    # z = 0 at the board's bottom face (B.Cu side), +Z up to F.Cu — the
    # same convention as export/stackup_step.py. The stackup list is
    # top→bottom (F.Cu first, B.Cu last; each layer's `dielectric_below`
    # separates it from the layer beneath), so elevations accumulate by
    # walking it in reverse. Tolerances stack as RSS (independent
    # variation). This is the Z half of the board-local XYZ frame whose
    # XY (math-y-up, board-centre origin) the routing + placements share.

    def _layer_elevations(self) -> dict:
        """`{name: (z_bottom_mm, z_top_mm, z_tol_mm)}` for every copper
        layer. `z_tol` is the RSS of the thickness tolerances of every
        foil + dielectric below that layer."""
        elev: dict = {}
        z = 0.0
        var = 0.0                       # Σ of (tol)² below the current height
        prev = None
        for layer in reversed(self.stackup):
            if prev is not None:
                # gap between `layer` (upper) and `prev` (lower) is the
                # upper layer's `dielectric_below`
                di = getattr(layer, "dielectric_below", None)
                if di is not None:
                    z += di.thickness_um / 1000.0
                    var += (di.thickness_tol_um / 1000.0) ** 2
            z_bottom = z
            z += layer.thickness_um / 1000.0
            elev[layer.name] = (z_bottom, z, var ** 0.5)
            var += (layer.thickness_tol_um / 1000.0) ** 2
            prev = layer
        return elev

    def layer_z_mm(self, name: str) -> tuple:
        """Copper mid-plane elevation of `name` as `(z_center_mm,
        z_tol_mm)`. Raises KeyError if the layer isn't in the stackup."""
        elev = self._layer_elevations()
        if name not in elev:
            raise KeyError(f"{self.name}: no layer {name!r} in stackup")
        z_bottom, z_top, z_tol = elev[name]
        return ((z_bottom + z_top) / 2.0, z_tol)

    def layer_span_mm(self, name: str) -> tuple:
        """Nominal `(z_bottom_mm, z_top_mm)` of layer `name`'s copper foil
        (for extrusion). Raises KeyError if not in the stackup."""
        elev = self._layer_elevations()
        if name not in elev:
            raise KeyError(f"{self.name}: no layer {name!r} in stackup")
        z_bottom, z_top, _ = elev[name]
        return (z_bottom, z_top)

    # ── cost rollups (sum over chips on this tile) ───────────────────
    # Each chip has a single `price_1pc` / `price_20kpc` in its own
    # `currency`. Rollups can either return per-currency dicts
    # (no FX guesswork) or convert to a target currency given an
    # explicit FX-rate table. DNP'd chips excluded by default.

    def _filter_components(self, design, populated_only):
        """Every chip + battery on this tile (the cost/weight rollups
        treat them as siblings)."""
        comps = (design.chips_on_board(self.name)
                 + design.batteries_on_board(self.name))
        return [c for c in comps if not c.dnp] if populated_only else list(comps)

    def dominant_rails(self, design,
                       populated_only: bool = True) -> list:
        """Return `[(net_name, pin_count), ...]` for every POWER net on
        this tile, sorted by pin count descending.

        Used by the placer to assign embedded-cap PWR planes (top pair
        In2, bottom pair In12 — see AN5724 §6.4 / §6.6) and to drive
        thermal-via heuristics on high-current rails.

        Only nets with `kind=="power"` are counted. Ground (`kind=
        "ground"`) is plane-distributed separately; signal nets aren't
        candidates for the PWR plane. Batteries' chemistry pins are
        included alongside chips. DNP'd parts excluded by default."""
        comps = self._filter_components(design, populated_only)
        refs_on_tile = {c.ref for c in comps}
        counts: dict[str, int] = {}
        for net in design.nets:
            if net.kind != "power":
                continue
            on_tile = sum(1 for ref, _pin in net.pins
                          if ref in refs_on_tile)
            if on_tile:
                counts[net.name] = on_tile
        return sorted(counts.items(), key=lambda t: (-t[1], t[0]))

    def cost_1pc(self, design, *,
                 target: str | None = None,
                 fx_rates: dict | None = None,
                 populated_only: bool = True):
        """Per-piece cost rollup. Two modes:

          - target=None: returns `{currency: total}` dict — caller
            keeps the per-currency split intact.
          - target="EUR", fx_rates={"USD": 0.92, ...}: returns a
            single float in `target` currency. fx_rates maps the
            ORIGIN currency to a multiplier yielding `target`
            (e.g. for target="EUR", `fx_rates["USD"]=0.92` means
            1 USD = 0.92 EUR). Identity (1.0) is assumed for the
            target currency itself.

        Chips with `price_1pc=None` contribute zero; chips with
        a price but no `currency` raise ValueError so missing
        currency tags don't silently corrupt totals.
        """
        return self._rollup_price(design, "price_1pc",
                                  target, fx_rates, populated_only)

    def cost_20kpc(self, design, *,
                   target: str | None = None,
                   fx_rates: dict | None = None,
                   populated_only: bool = True):
        """20k-volume cost rollup. Same shape as cost_1pc()."""
        return self._rollup_price(design, "price_20kpc",
                                  target, fx_rates, populated_only)

    def _rollup_price(self, design, attr, target, fx_rates, populated_only):
        comps = self._filter_components(design, populated_only)
        by_currency: dict = {}
        for c in comps:
            price = getattr(c, attr)
            if price is None:
                continue
            if not c.currency:
                raise ValueError(
                    f"{c.ref}: {attr}={price} but currency is unset; "
                    f"can't be summed")
            by_currency[c.currency] = by_currency.get(c.currency, 0.0) + price
        if target is None:
            return by_currency
        # Convert to target currency
        fx = dict(fx_rates or {})
        fx.setdefault(target, 1.0)
        total = 0.0
        for cur, amount in by_currency.items():
            if cur not in fx:
                raise KeyError(
                    f"missing FX rate {cur!r} → {target!r} in fx_rates")
            total += amount * fx[cur]
        return total

    def weight_g(self, design, populated_only: bool = True) -> float:
        """Sum every populated chip + battery weight on this tile —
        for CG / mass-distribution calcs on the snake panel."""
        comps = self._filter_components(design, populated_only)
        return sum(c.weight_g or 0.0 for c in comps)

