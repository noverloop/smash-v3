"""Battery — primary / secondary cell, parallel to Chip."""
from __future__ import annotations

import dataclasses

from smash.state.pin import Pin


@dataclasses.dataclass
class Battery:
    """A primary or secondary cell — first-class citizen, parallel to
    Chip. Used because batteries carry battery-specific structured
    state (chemistry, capacity, pulse-current rating, shelf life,
    hazmat class) that doesn't fit cleanly onto Chip.

    **Naming convention: transcribe verbatim from the cell datasheet.**
    Same rule as Chip — every string mirrors the PDF.

    Cost / weight rollups iterate both `design.chips` and
    `design.batteries`. BOM tools should treat them as siblings.
    """
    # ── identity ─────────────────────────────────────────────────────
    ref: str                          # KiCad ref ("BT1", "BAT_CELL_1")
    name: str | None = None
    manf: str | None = None
    manf_pn: str | None = None        # "TLM-1520HPM/S"
    canonical_id: str | None = None   # stable slug — same join key as
                                      # Chip.canonical_id (see Chip)
    description: str | None = None
    datasheet: str | None = None

    # ── chemistry / electrical ───────────────────────────────────────
    chemistry: str | None = None      # "Li-MnO2 organic", "Li-SOCl2",
                                      # "LiFePO4", "Li-ion polymer",
                                      # "alkaline", "NiMH"
    capacity_mah: float | None = None
    nominal_voltage_v: float | None = None     # 4.0 for Li-MnO2 organic,
                                               # 3.6 for Li-SOCl2,
                                               # 1.5 for alkaline
    ocv_min_v: float | None = None    # open-circuit voltage range,
    ocv_max_v: float | None = None    # fresh cell at +20 °C
    ccv_min_v: float | None = None    # min CCV @ rated pulse current
    i_continuous_a: float | None = None
    i_pulse_a: float | None = None
    pulse_duration_s: float | None = None      # how long the pulse rating
                                               # holds (typically 1 s)
    impedance_mohm: float | None = None        # internal impedance @ 1 kHz
    self_discharge_pct_per_year: float | None = None
                                               # primary cells <1 %/yr
    shelf_life_years: float | None = None      # rated shelf life at +20 °C

    # ── sourcing / BOM ───────────────────────────────────────────────
    fab_country: str | None = None
    fab_location: str | None = None
    distributor: str | None = None    # often relevant for cells (not
                                      # always stocked by Mouser/DigiKey)
    currency: str | None = None
    price_1pc: float | None = None
    price_20kpc: float | None = None
    weight_g: float | None = None
    critical: bool | None = None

    # ── compliance + hazmat ──────────────────────────────────────────
    standards: list = dataclasses.field(default_factory=list)
                                      # ["UN 38.3", "IEC 60086"]
    hazmat_class: str | None = None   # "UN3090" (Li metal), "UN3480"
                                      # (Li-ion), etc.
    eccn: str | None = None
    itar: bool | None = None
    export_notes: str | None = None

    # ── mechanical / material ────────────────────────────────────────
    package: str | None = None        # form factor token, e.g. "AA",
                                      # "1/6D wafer", "coin CR2032",
                                      # "Ø14.8×21"
    size_mm: tuple | None = None      # (diameter, height) for cyl,
                                      # (width, height) for prismatic
    height_mm: float | None = None
    temp_range_c: tuple | None = None
    body_material: str | None = None  # "stainless steel can",
                                      # "Al-laminate pouch"
    lead_material: str | None = None  # "Ni solder tab",
                                      # "Au-plated terminal"
    density_g_cm3: float | None = None
    youngs_modulus_gpa: float | None = None
    cte_ppm_k: float | None = None

    # ── footprint / placement ────────────────────────────────────────
    footprint: "Footprint | None" = None  # inline first-class geometry

    # ── assembly / config ────────────────────────────────────────────
    board_tag: str | None = None
    feature: str | None = None
    dnp: bool = False

    # ── pack notation ───────────────────────────────────────────────
    # Tadiran TLM-1520HPM/S × 3 in parallel forms the Smash pack. We
    # leave this as descriptive metadata; the actual pack is built by
    # placing N Battery records on the same nets. Validators or BOM
    # tools that need "this is part of a 3P pack" can read these.
    pack_count: int | None = None     # number of cells in this logical pack
    pack_config: str | None = None    # "single", "Np" (parallel),
                                      # "Ns" (series), "NpMs" (mixed)

    # ── electrical (pins) ───────────────────────────────────────────
    pins: list = dataclasses.field(default_factory=list)
                                      # typically [Pin("+"), Pin("-")]

    # Layout state — position, rotation, mount face — lives on the
    # parent Board's `chip_placements` list as `Placement` records, not
    # on the Battery itself. Same model as Chip.

    # ── free-form ────────────────────────────────────────────────────
    note: str | None = None

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["pins"] = [p.to_dict() if isinstance(p, Pin) else p
                     for p in self.pins]
        if self.size_mm is not None:
            d["size_mm"] = list(self.size_mm)
        if self.temp_range_c is not None:
            d["temp_range_c"] = list(self.temp_range_c)
        return d

    def pin(self, key: str) -> "Pin":
        """Same lookup semantics as Chip.pin — by num, name, or alias."""
        for p in self.pins:
            if p.num == key:
                return p
        matches = [p for p in self.pins
                   if p.name == key or key in p.aliases]
        if not matches:
            raise KeyError(
                f"{self.ref}: no pin with num/name/alias {key!r}")
        if len(matches) > 1:
            raise KeyError(
                f"{self.ref}: name/alias {key!r} matches "
                f"{len(matches)} pins")
        return matches[0]


