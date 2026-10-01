"""Chip — the canonical component dataclass."""
from __future__ import annotations

import dataclasses

from smash.state.footprint import Footprint
from smash.state.pad import Pad        # noqa: F401 — used in Chip.to_dict surface
from smash.state.pin import Pin


@dataclasses.dataclass
class Chip:
    """Canonical record of one component. Carries every fact about it
    that's independent of the PCB layout: identity, sourcing,
    mechanical, thermal, BOM/cost, and electrical pin list.

    **Naming convention: the data model mirrors the datasheet
    exactly.** `manf_pn`, `package`, pin numbers, pin names, voltage
    rail names, bus / signal names — every string here should be
    transcribed verbatim from the chip's datasheet (or the relevant
    application note, e.g. AN5724 for STM32MP25 DDR3 routing). Don't
    paraphrase, simplify, or normalize names. This makes a Chip
    record directly cross-referenceable to its PDF.

    Layout state (position, rotation, pad bbox, per-pad routing state)
    is filled in when the chip is placed by `board_state.build_chip()`;
    until then the layout fields keep their defaults.
    """
    # ── identity ─────────────────────────────────────────────────────
    ref: str                          # KiCad reference (U_MPU, R23, ...)
    name: str | None = None           # short label
    manf: str | None = None
    manf_pn: str | None = None        # canonical part number
    canonical_id: str | None = None   # stable slug — join key into
                                      # smash/data/assumptions.json so
                                      # uncertain sourcing data (price,
                                      # fab_country, ...) can be layered
                                      # in without polluting factory code
    value: str | None = None
    footprint: "Footprint | None" = None  # inline first-class geometry
    description: str | None = None
    datasheet: str | None = None      # path under Research/

    # ── sourcing / BOM ───────────────────────────────────────────────
    fab_country: str | None = None
    fab_location: str | None = None
    # Price stored in a single field per quantity tier with an
    # explicit currency tag. FX conversion happens at cost-rollup
    # time (the rollup function takes fx_rates + a target currency).
    # Never guess a conversion rate at chip-definition time.
    currency: str | None = None         # ISO 4217: "EUR", "USD", ...
    price_1pc: float | None = None      # in `currency`
    price_20kpc: float | None = None    # in `currency`
    weight_g: float | None = None
    critical: bool | None = None

    # ── compliance / standards / export control ──────────────────────
    # These are per-chip facts transcribed from the datasheet's
    # qualification / compliance section. Validators use them for rules
    # like "munitions-zone parts must be AEC-Q100 Grade 1 or MIL spec"
    # or "no ITAR-controlled parts in EU-shipped configs".
    standards: list = dataclasses.field(default_factory=list)
                                       # qualification standards the
                                       # part is rated/tested against,
                                       # e.g. ["MIL-PRF-32535","AEC-Q100",
                                       # "RoHS","REACH"]
    eccn: str | None = None            # US Export Control Classification
                                       # Number (e.g. "EAR99", "3A001",
                                       # "5A002")
    itar: bool | None = None           # on US Munitions List?
    export_notes: str | None = None    # free-form sourcing / export
                                       # restrictions ("EU-only supply
                                       # chain", "no end-use in CN/TW")

    # ── mechanical / material ───────────────────────────────────────
    package: str | None = None
    size_mm: tuple | None = None       # (W, H) footprint envelope
    height_mm: float | None = None
    temp_range_c: tuple | None = None  # (min, max)
    # Material data — feeds structural analysis (FEM shock sim, CG
    # estimation, thermal-stress modelling). Transcribe from the
    # package section of the datasheet; leave None when not yet
    # available, structural sim treats unknowns conservatively.
    body_material: str | None = None
                                       # e.g. "epoxy mold compound",
                                       # "ceramic alumina", "LCP"
    lead_material: str | None = None
                                       # e.g. "SAC305 solder balls",
                                       # "Sn-Bi", "Au-coated Cu leads"
    underfill: str | None = None       # capillary/molded underfill material
                                       # (name into FabProfile.adhesives);
                                       # None = not underfilled. Per chip —
                                       # only BGAs/CSPs that need it.
    dielectric: str | None = None
                                       # for caps: "X7R BME", "C0G/NP0",
                                       # "tantalum oxide", "polymer film".
                                       # None for non-caps.
    density_g_cm3: float | None = None
                                       # bulk density — for CG / mass
                                       # distribution maps
    youngs_modulus_gpa: float | None = None
                                       # elastic modulus — for FEM shock
                                       # simulation (1000+ G launch event)
    cte_ppm_k: float | None = None
                                       # coefficient of thermal expansion —
                                       # for solder-joint stress at temp
                                       # extremes

    # ── thermal (from datasheet) ─────────────────────────────────────
    p_active_w: float | None = None
    p_max_w: float | None = None
    rth_jc_cw: float | None = None     # junction → case
    rth_ja_cw: float | None = None     # junction → ambient
    tj_max_c: float | None = None

    # ── assembly / config ────────────────────────────────────────────
    board_tag: str | None = None       # tile this chip lives on
    feature: str | None = None         # name of the populate flag, if any
    dnp: bool = False                  # Do Not Populate
    role: str | None = None            # declarative role tag, e.g.
                                       # "main_mcu", "wake_controller",
                                       # "ddr_dram", "pmic", "can_phy".
                                       # Use for structured queries
                                       # ("find the SoC on this board");
                                       # description is for humans.
    substitutes: list = dataclasses.field(default_factory=list)
                                       # [(manf_pn, reason), ...] —
                                       # design-time substitution
                                       # decisions: "this design uses
                                       # LDL112PV33R because AP2112K is
                                       # CN-fab and forbidden by
                                       # sourcing policy."

    # ── electrical (passives + power-component ratings) ─────────────
    # Numeric value fields in SI base units. For passives the legacy
    # `value` string ("100nF", "10k", "10uH") is kept for readability,
    # but validators read these numeric fields ("is this cap ≥ 1 µF?").
    # Power-component fields (i_sat_a, esr_mohm, voltage_rating_v, ...)
    # only apply to the parts that have those ratings; left None for
    # the rest.
    capacitance_f: float | None = None    # caps (in farads)
    resistance_ohm: float | None = None   # resistors
    inductance_h: float | None = None     # inductors (in henries)
    tolerance_pct: float | None = None    # ±tolerance for R/L/C
    voltage_rating_v: float | None = None # cap DCV / diode VR / FET VDS
                                          # (MAXIMUM allowable voltage)
    vcc_nominal_v: float | None = None    # nominal supply voltage (TYPICAL
                                          # operating Vcc — e.g. 1.35 for
                                          # DDR3L, 3.3 for STM32G0B1)
    power_rating_w: float | None = None   # resistor P_max, regulator P_max
    i_sat_a: float | None = None          # inductor saturation current
    i_rms_a: float | None = None          # inductor RMS current, FET ID
    esr_mohm: float | None = None         # cap equivalent series resistance

    # ── digital / memory ratings ─────────────────────────────────────
    # For MCUs / SoCs / memory chips, the headline datasheet numbers
    # that validators want without parsing description text.
    clock_max_hz: float | None = None     # MCU max core / system clock
                                          # (550e6 = 550 MHz for H562)
    clock_freq_hz: float | None = None    # oscillator / crystal nominal
                                          # output frequency (8e6 for an
                                          # 8 MHz HSE, 32768 for a 32.768
                                          # kHz LSE). DISTINCT from
                                          # `clock_max_hz` — that's an
                                          # MCU's ceiling; this is a
                                          # clock-source's headline spec.
    memory_capacity_bits: int | None = None
                                          # for memory chips: total
                                          # storage in BITS (not bytes,
                                          # matches datasheet convention:
                                          # "4 Gb DDR3", "512 Mb NAND").
                                          # Tools that want bytes divide
                                          # by 8.

    pins: list = dataclasses.field(default_factory=list)   # list[Pin]

    # ── note ────────────────────────────────────────────────────────
    # Free-form catch-all for anything not yet modelled (extended
    # description, compliance side-notes, supply-chain caveats,
    # bring-up reminders). Use this rather than overloading
    # `description` so the structured fields stay clean. When a piece
    # of state shows up in `note` often enough across chips, promote
    # it to a real field.
    note: str | None = None

    # Layout state — position, rotation, mount face, per-pad routing —
    # lives on the parent Board's `chip_placements` list as `Placement`
    # records, not on the Chip itself. The Chip is a position-free
    # template: identity + footprint + pins.

    @property
    def is_bga(self) -> bool:
        """True iff this chip is a Ball Grid Array (any sub-flavor:
        BGA / VFBGA / DSBGA / ODCSP BGA / etc.). Computed from the
        chip-level `package` descriptor with a footprint-level fallback
        — `package` is the canonical source of truth, but factories
        that only populate `footprint.package_class` still resolve."""
        pkg = self.package or ""
        if "BGA" in pkg:
            return True
        return bool(self.footprint and self.footprint.is_bga)

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["pins"] = [p.to_dict() if isinstance(p, Pin) else p for p in self.pins]
        if self.size_mm is not None:
            d["size_mm"] = list(self.size_mm)
        if self.temp_range_c is not None:
            d["temp_range_c"] = list(self.temp_range_c)
        return d

    def pin(self, key: str) -> "Pin":
        """Look up a Pin on this chip by any name the datasheet uses
        for it. Resolution order:

          1. exact match on `num` (datasheet ball position, e.g. 'J4')
          2. exact match on `name` (datasheet primary name, e.g. 'PD0')
          3. exact match in `aliases` (datasheet alt-function names,
             e.g. 'UART4_RX')

        Returns the Pin object directly so callers can pass it to
        `Design.connect()`. Raises if not found, or if the key matches
        more than one pin (catches typos / collisions).

        For power / ground pins that legitimately share a name across
        many balls (a BGA has 8× VDD, 16× VSS), use `pins_by_name()`
        instead — that returns the full list without raising.

        Cross-namespace collisions (a pin number that equals another
        pin's name or alias) are not possible here — they're caught at
        chip-construction time by `validate_pin_namespaces()`.
        """
        # 1. By pad-number (unique by construction)
        for p in self.pins:
            if p.num == key:
                return p
        # 2 + 3. By name or alias — collect to detect ambiguity
        matches = [p for p in self.pins
                   if p.name == key or key in p.aliases]
        if not matches:
            raise KeyError(
                f"{self.ref}: no pin with num/name/alias {key!r}")
        if len(matches) > 1:
            raise KeyError(
                f"{self.ref}: name/alias {key!r} matches "
                f"{len(matches)} pins ({[p.num for p in matches]}); "
                f"use chip.pins_by_name() for power / ground pins")
        return matches[0]

    def pins_by_name(self, name: str) -> list:
        """Return every Pin on this chip whose `name` (or alias)
        matches. For power / ground pins that legitimately share a
        name across many balls (e.g. a BGA with 8× VDD balls).

        Returns [] if no pin matches — never raises. Use `pin()` for
        signal pins where ambiguity is a bug; use this for power
        rails where multi-match is expected.
        """
        return [p for p in self.pins
                if p.name == name or name in p.aliases]


