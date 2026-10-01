"""Antenna — RF radiator, parallel to Chip and Battery.

Antennas don't fit the Chip model cleanly: they're not silicon, they
don't have alternate functions or per-pin AF maps, but they DO have
structured RF properties (pass-band, polarization, gain pattern, port
impedance) that callers want to query like any other component.

Mirroring `Battery`, Antenna is a first-class citizen — cost / weight
/ placement rollups iterate `design.chips + design.batteries +
design.antennas`. BOM tools should treat all three as siblings.

Naming convention is the same as Chip and Battery: every string here
mirrors the manufacturer datasheet exactly. For project-built (printed
or etched) antennas, transcribe from the EM-sim / antenna-team spec
sheet — never paraphrase, never normalise.

Layout state (`board_tag`, `chip_placements` entry, face) lives on the
parent Board's `chip_placements` list as `Placement` records, not on
the Antenna itself — same model as Chip and Battery.
"""
from __future__ import annotations

import dataclasses

from smash.state.pin import Pin


@dataclasses.dataclass
class Antenna:
    """A radiating element. Carries the antenna's identity, RF
    properties, mechanical body, and feed pins. Placement on a Board
    is recorded separately via the parent's `chip_placements` list.
    """
    # ── identity ─────────────────────────────────────────────────────
    ref: str                          # KiCad ref (ANT_NFC, ANT_YAGI_A, …)
    name: str | None = None
    manf: str | None = None
    manf_pn: str | None = None
    canonical_id: str | None = None   # stable slug — same key family as
                                      # Chip.canonical_id / Battery.canonical_id
    description: str | None = None
    datasheet: str | None = None

    # ── RF — pass-band + polarisation + gain ─────────────────────────
    # Frequency range over which VSWR / gain figures hold. Transcribe
    # from the datasheet's "operating band" or the EM-sim spec.
    frequency_band_hz: tuple | None = None     # (f_low, f_high) in Hz
    centre_frequency_hz: float | None = None   # nominal centre / design freq
    bandwidth_hz: float | None = None          # -3 dB or -10 dB BW (note in
                                               # `note` which definition)
    polarization: str | None = None            # "linear-V", "linear-H",
                                               # "linear-tilted", "RHCP",
                                               # "LHCP", "circular",
                                               # "dual-linear", "elliptical".
                                               # Tag both polarisations of a
                                               # crossed-dipole pair on the
                                               # same Antenna record via
                                               # "dual-linear".
    pattern: str | None = None                 # high-level radiation pattern
                                               # family: "omni", "monopole",
                                               # "dipole", "yagi-uda",
                                               # "patch", "chip", "helical",
                                               # "slot", "PIFA", "loop",
                                               # "spiral".
    peak_gain_dbi: float | None = None         # boresight gain over isotrope
    front_to_back_db: float | None = None      # directionality metric for
                                               # directive antennas; None for
                                               # omni-class
    half_power_beamwidth_deg: float | None = None
                                               # -3 dB beamwidth, axial cut
                                               # (for directive antennas)
    efficiency: float | None = None            # 0..1 — total efficiency
                                               # (mismatch + radiation +
                                               # material losses)
    impedance_ohm: float | None = None         # nominal port impedance
                                               # (typically 50 in this design)
    vswr_max: float | None = None              # max VSWR across the band

    # Optional pointer to a measured / simulated radiation-pattern file
    # (e.g. CST .ffd, HFSS .ffe, custom YAML). Tools that visualise
    # range link budgets can load this; None when no pattern is on file
    # yet (e.g. placeholder pre-EM-sim antennas).
    pattern_3d_path: str | None = None

    # ── sourcing / BOM ───────────────────────────────────────────────
    fab_country: str | None = None
    fab_location: str | None = None
    distributor: str | None = None
    currency: str | None = None
    price_1pc: float | None = None
    price_20kpc: float | None = None
    weight_g: float | None = None
    critical: bool | None = None

    # ── compliance / regulatory ──────────────────────────────────────
    # Antennas sometimes carry their own regulatory ID (e.g. "modular
    # FCC ID" for certified chip antennas; CE / RED markings for EU
    # sale). Free-form — tools just surface it on the BOM, no validator.
    standards: list = dataclasses.field(default_factory=list)
    eccn: str | None = None
    itar: bool | None = None
    export_notes: str | None = None

    # ── mechanical / material ────────────────────────────────────────
    package: str | None = None        # form factor: "SMD-1206 chip",
                                      # "printed-flex Yagi", "wire helix",
                                      # "PIFA cut from sheet metal", etc.
    size_mm: tuple | None = None      # (W, L) footprint envelope OR full
                                      # tile dimensions for a printed
                                      # antenna tile (in which case the
                                      # `Antenna` lives ON its own tile)
    height_mm: float | None = None
    temp_range_c: tuple | None = None
    body_material: str | None = None  # "LTCC ceramic", "polyimide flex",
                                      # "FR4 microstrip", "alumina"
    lead_material: str | None = None
    density_g_cm3: float | None = None
    youngs_modulus_gpa: float | None = None
    cte_ppm_k: float | None = None

    # ── footprint / placement ────────────────────────────────────────
    footprint: "Footprint | None" = None  # inline first-class geometry;
                                          # for printed antennas the
                                          # `copper_lines` carry the actual
                                          # radiator pattern and `pads` the
                                          # feed point(s).

    # ── tile membership ──────────────────────────────────────────────
    # `board_tag` says which tile the antenna lives on. A printed flex
    # antenna whose tile IS the antenna sets board_tag = that tile name
    # — then the placer puts the Antenna footprint at the tile centre
    # and the rendered tile shows the radiator pattern directly.
    board_tag: str | None = None
    feature: str | None = None       # name of the populate flag, if any
    dnp: bool = False

    # ── electrical (pins) ────────────────────────────────────────────
    # Most antennas have a single feed pin; balanced antennas have two
    # (differential feed); steered arrays have N. Naming follows the
    # same Pin conventions as Chip.
    pins: list = dataclasses.field(default_factory=list)

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
        if self.frequency_band_hz is not None:
            d["frequency_band_hz"] = list(self.frequency_band_hz)
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
