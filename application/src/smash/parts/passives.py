"""Discrete passive factories.

Two layers:

  - **Specific-PN factories** (single concrete part with full SamacSys
    artifacts) — e.g. `add_we_744043100` below. One factory per
    orderable order code, same discipline as the IC factories.
  - **Family-parameterized factories** for generic R/C/L positions —
    e.g. `add_resistor_0402_vishay(value="4.7k")`. Catalog discipline
    is bent here because passives are families (no per-PN catalog
    feasible). The factory parses `value`, fills the numeric SI field
    (`resistance_ohm` / `capacitance_f` / `inductance_h`), and emits
    a `manf_pn` carrying the family spec.

Datasheets for the family-parameterized factories live under
`parts/sources/<Family>/<doc>.pdf`. Footprints are KiCad-stock
(no per-PN `.kicad_mod` since geometry is IPC-standard).
"""

from __future__ import annotations

from smash.state import Chip, Footprint, Pin, Pad
from smash.parts._artifacts import (
    pads_from_kicad_mod, outline_polygon, build_pins, src, datasheet_ref,
)
from smash.parts._chip_mass import (
    WEIGHT_G_INDUCTOR_WEPD_4848, WEIGHT_G_INDUCTOR_TDK_TMS20,
    WEIGHT_G_TANTALUM_3528B, WEIGHT_G_TANTALUM_7343X,
    weight_g_for_passive,
)
from smash.parts._passives_util import (
    parse_resistance_ohm, parse_capacitance_f, parse_inductance_h,
)
from smash.parts._slug import canonical_id


# ═════════════════════════════════════════════════════════════════════════
# Würth Elektronik 744043100 — WE-PD shielded SMD power inductor, 10 µH
# ═════════════════════════════════════════════════════════════════════════

def add_we_744043100(design, ref: str, **overrides) -> Chip:
    """Würth Elektronik 744043100 — WE-PD shielded SMD power inductor.
    Nominal inductance 10 µH (per Würth `7440431xx` order code:
    `10` → 10 µH, suffix `0`). 4.8×4.8 mm body.

    Datasheet placed at parts/sources/744043100/. Pin assignment + footprint
    parsed from SamacSys artifacts directly.
    """
    pn = "744043100"
    fp_mod = src(pn, "INDPM4848X280N.kicad_mod")
    fields = dict(
        manf="Würth Elektronik",
        manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn,
        value="10uH",
        description="Shielded power inductor, 10 µH, WE-PD 4848 (4.8×4.8 mm)",
        datasheet=datasheet_ref(pn, f"{pn}.pdf"),
        package="WE-PD 4848",
        size_mm=(4.8, 4.8),
        height_mm=2.8,
        inductance_h=10e-6,
        weight_g=WEIGHT_G_INDUCTOR_WEPD_4848,   # Würth 744043 datasheet typical
        pins=build_pins(src(pn, f"{pn}.kicad_sym")),
        footprint=Footprint(
            name="INDPM4848X280N",
            package_class="SMD-Inductor",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            size_mm=(4.8, 4.8), height_mm=2.8,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=(
            "Würth Elektronik 744043 series — WE-PD shielded SMD power "
            "inductors. Order code 744043100 = 10 µH, 4.8×4.8 mm "
            "package. See Würth product page for full DCR / I_sat "
            "ratings (not transcribed — fetch from Mouser/Würth)."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# Coilcraft LPS4018-103MRB — 10 µH shielded power inductor, 3.9 × 3.9 × 1.8
# ═════════════════════════════════════════════════════════════════════════

def add_lps4018_103mrb(design, ref: str, **overrides) -> Chip:
    """Coilcraft LPS4018-103MRB — 10 µH shielded SMD power inductor,
    3.9 × 3.9 × 1.8 mm max (IPC INDPM3939X180N). I_sat ≈ 1.1-1.2 A,
    DCR ≈ 200 mΩ typ (Coilcraft).

    (2026-11-21, user) Low-profile swap for Würth 744043100 (WE-PD 4848,
    2.8 mm, I_sat ≈ 1.0 A, DCR ≈ 110 mΩ) on L_ACTIVATE / L_BOOST_COMP:
    1.0 mm lower, about the same saturation current, ~2× the DCR (more
    copper loss). ⚠ L_BOOST_COMP's peak current (fin pulses, TPS61175
    3.8 A switch limit) is well above ~1.2 A for BOTH parts — re-check."""
    pn = "LPS4018-103MRB"
    fp_mod = src(pn, "INDPM3939X180N.kicad_mod")
    fields = dict(
        manf="Coilcraft",
        manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn,
        value="10uH",
        description="Shielded power inductor, 10 µH, LPS4018 (3.9×3.9×1.8 mm)",
        datasheet=None,
        package="LPS4018",
        size_mm=(3.9, 3.9),
        height_mm=1.8,
        inductance_h=10e-6,
        pins=build_pins(src(pn, f"{pn}.kicad_sym")),
        footprint=Footprint(
            name="INDPM3939X180N",
            package_class="SMD-Inductor",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            size_mm=(3.9, 3.9), height_mm=1.8,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note="SamacSys LIB_LPS4018-103MRB v3.1 (2019-02-04).",
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# Coilcraft XGL5020-472MEC — 4.7 µH shielded molded inductor, 5.3 A Isat(30 %)
# ═════════════════════════════════════════════════════════════════════════

# Coilcraft Doc 1620 (rev 02/19/26) table rows used here: code → (L µH, DCR typ,
# DCR max mΩ, Isat 10/20/30 % A, Irms 20 °C-rise A). Same body / land pattern.
XGL5020_TABLE = {
    "472": (4.7, 36.0, 41.5, (2.2, 3.6, 5.3), 5.7),
    "682": (6.8, 55.0, 63.5, (2.0, 3.2, 4.5), 3.6),
    "822": (8.2, 64.0, 73.6, (1.8, 2.9, 4.1), 3.3),
}


def add_xgl5020_822mec(design, ref: str, **overrides) -> Chip:
    """Coilcraft XGL5020-822MEC — 8.2 µH member of the XGL5020 family (same
    body / land pattern as add_xgl5020_472mec). DCR 64 typ / 73.6 max mΩ;
    Isat 1.8 / 2.9 / 4.1 A at 10 / 20 / 30 % drop; Irms 3.3 A (20 °C rise).
    (2026-11-21) L_ACTIVATE: the 5 → 33 V boost runs at D ≈ 0.85-0.87, where
    the TPS61175's slope compensation needs L comfortably ABOVE its 4.7 µH
    minimum (DS §7.3.1); 8.2 µH keeps the steady-state peak (1.6-1.7 A)
    under the 10 %-drop point."""
    return add_xgl5020_472mec(design, ref, _code="822", **overrides)


def add_xgl5020_472mec(design, ref: str, _code: str = "472", **overrides) -> Chip:
    """Coilcraft XGL5020-472MEC — 4.7 µH ±20 % composite molded shielded
    power inductor, AEC-Q200, 5.28 × 5.48 × 2.1 mm max (Doc 1620, rev
    02/19/26, vendored as XGL5020_Doc1620.pdf).

    DCR 36.0 typ / 41.5 max mΩ; Isat 2.2 / 3.6 / 5.3 A at 10 / 20 / 30 %
    inductance drop (soft saturation); Irms 5.7 A (20 °C rise) / 7.9 A
    (40 °C rise); SRF 20 MHz; 0.30-0.33 g.

    (2026-11-21, user) L_BOOST_COMP: the TPS61175 limits the switch at
    3.0 / 3.8 / 5.0 A (min / typ / max), and the fin pulses run the boost
    into that limit — the 30 % point (5.3 A) covers the 5 A max; the earlier
    744043100 / LPS4018 saturated at ~1-1.2 A. 4.7 µH is the bottom of the
    DS 4.7-47 µH window: ripple ≈ 0.43 A at V_IN 3.0 V / 600 kHz.

    Footprint from the datasheet "Recommended Land Pattern" (no SamacSys
    model exists for it): two 1.18 × 4.7 mm pads, 3.31 mm between their
    inner edges (≈ the 3.28 mm between the part's own 1.0 mm terminals),
    so pad centres at ±2.245 mm. Body 5.28 (terminal axis) × 5.48 mm.
    No 3D model (none supplied); height from the datasheet."""
    pn = f"XGL5020-{_code}MEC"
    L_uh, dcr_typ, dcr_max, isat, irms = XGL5020_TABLE[_code]
    cx = 3.31 / 2 + 1.18 / 2
    pads = [
        Pad(num="1", position_mm=(-cx, 0.0), size_mm=(1.18, 4.7), shape="rect"),
        Pad(num="2", position_mm=(cx, 0.0), size_mm=(1.18, 4.7), shape="rect"),
    ]
    bx, by = 5.28 / 2, 5.48 / 2
    body = [(-bx, -by), (bx, -by), (bx, by), (-bx, by)]
    fields = dict(
        manf="Coilcraft",
        manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn,
        value=f"{L_uh:g}uH",
        description=(f"Shielded molded power inductor, {L_uh:g} µH, Isat {isat[2]:g} A (30 %), "
                     f"DCR {dcr_max:g} mΩ max, 5.3×5.5×2.1 mm"),
        datasheet=datasheet_ref("XGL5020-472MEC", "XGL5020_Doc1620.pdf"),   # family datasheet
        package="XGL5020",
        size_mm=(5.28, 5.48),
        height_mm=2.1,
        inductance_h=L_uh * 1e-6,
        weight_g=0.33,
        temp_range_c=(-40, 125),
        voltage_rating_v=80.0,
        i_rms_a=irms,
        standards=["RoHS", "Halogen-Free", "AEC-Q200"],
        pins=[Pin(num="1", name="1", type="passive"), Pin(num="2", name="2", type="passive")],
        footprint=Footprint(
            name="Coilcraft_XGL5020", package_class="SMD-Inductor",
            pads=pads, body_outline=body, courtyard=[],
            pitch_mm=2 * cx, size_mm=(5.28, 5.48), height_mm=2.1,
            source="datasheet",
            note="Coilcraft Doc 1620 recommended land pattern; no vendor 3D model.",
        ).ensure_courtyard_clearance(),
        note=("Pin 1 = the terminal marked by the top-side bar (start lead) — the "
              "datasheet asks to connect the high-dV/dt node (SW) there for lowest EMI."),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# Murata BLM18PG221SN1D — chip ferrite bead, 220 Ω @ 100 MHz, 0603
# ═════════════════════════════════════════════════════════════════════════

def add_blm18pg221sn1d(design, ref: str, **overrides) -> Chip:
    """Murata BLM18PG221SN1D — chip ferrite bead for power lines, 0603
    (1608M), 220 Ω ±25 % at 100 MHz, rated 1400 mA at 85 °C / 1000 mA at
    125 °C, DCR ≤ 0.10 Ω (initial). Murata reference spec JENF243A-0003AJ-01
    (vendored). Footprint + symbol from SamacSys LIB v1.3 (2023-03-07); the
    SamacSys footprint file is named for the shared BLM18 land pattern."""
    pn = "BLM18PG221SN1D"
    fp_mod = src(pn, "BLM18SP221SN1B.kicad_mod")
    fields = dict(
        manf="Murata",
        manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn,
        value="220R@100MHz",
        description="Chip ferrite bead, 220 Ω @ 100 MHz, 1.4 A, 0603 (BLM18PG)",
        datasheet=datasheet_ref(pn, f"{pn}.pdf"),
        package="0603 (1608M)",
        size_mm=(1.6, 0.8),
        height_mm=0.8,
        temp_range_c=(-55, 125),
        i_rms_a=1.4,
        pins=_two_pin(),
        footprint=Footprint(
            name="BLM18SP221SN1B",
            package_class="SMD-FerriteBead",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            size_mm=(1.6, 0.8), height_mm=0.8,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=(
            "BLM18PG = power-line ferrite bead. Rated current 1400 mA at "
            "85 °C, 1000 mA at 125 °C (derate between); DCR 0.10 Ω max "
            "initial / 0.14 Ω after testing. Used as the LR2021 VBAT input "
            "filter (Semtech LR20xx reference design FB14)."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# Family-parameterized factories — generic R/C/L positions
# ═════════════════════════════════════════════════════════════════════════


def _stock_smd_2pad(name: str, size_mm: tuple, height_mm: float,
                     pad_size: tuple, pad_pitch_mm: float,
                     package_class: str) -> Footprint:
    """Generic 2-pad SMD passive footprint, IPC nominal land pattern.

    Pads centred on ±pad_pitch_mm/2 from origin. Body outline is the
    nominal size_mm rectangle. Used for all KiCad-stock passive
    footprints (R/C/L 0402/0603/0805 etc.) where SamacSys isn't
    needed because the package is fully IPC-standard.
    """
    half = pad_pitch_mm / 2.0
    pads = [
        Pad(num="1", position_mm=(-half, 0.0), size_mm=pad_size, shape="rect"),
        Pad(num="2", position_mm=(+half, 0.0), size_mm=pad_size, shape="rect"),
    ]
    w, h = size_mm
    body = [(-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2), (-w/2, -h/2)]
    fp = Footprint(
        name=name, pads=pads, body_outline=body,
        package_class=package_class, pitch_mm=pad_pitch_mm,
        size_mm=size_mm, height_mm=height_mm, source="kicad-stock",
    )
    # Stock IPC land patterns omit F.CrtYd, so the packer's extent would
    # collapse to the bare pad bbox and a dense decap field abuts pad-to-pad
    # (a DRC short). The clearance ring makes abutting parts hold >=100 um.
    # (Per-footprint long/short-axis growth is applied centrally in
    # Design.add_chip via Footprint.COURTYARD_GROW_MM.)
    return fp.ensure_courtyard_clearance()


def _two_pin(p1: str = "1", p2: str = "2") -> list:
    return [Pin(num="1", name=p1, type="io"),
            Pin(num="2", name=p2, type="io")]


# ── resistor: Vishay CRCW 0402 ──────────────────────────────────────────


def add_resistor_0402_vishay(design, ref: str, *, value: str, **overrides) -> Chip:
    """Vishay CRCW0402 thick-film chip resistor, 1 % tolerance.

    1.0 × 0.5 × 0.45 mm, 0.063 W, 50 V, ±100 ppm/°C, -55..+155 °C.
    Doc: Vishay 20035 (CRCW e3). RoHS / Pb-free / halogen-free.
    """
    family = "Vishay_CRCW0402"
    fp = _stock_smd_2pad(
        name="Resistor_SMD:R_0402_1005Metric",
        size_mm=(1.0, 0.5), height_mm=0.45,
        pad_size=(0.55, 0.6), pad_pitch_mm=0.95,
        package_class="0402",
    )
    fields = dict(
        manf="Vishay",
        manf_pn=f"CRCW0402 {value} 1% e3",
        value=value,
        name=f"R_0402_{value}",
        description=f"Vishay CRCW0402 thick-film resistor, {value}, 1%, 0.063W, 50V",
        datasheet=datasheet_ref(family, "vishay_crcw_e3.pdf"),
        package="0402",
        size_mm=(1.0, 0.5),
        height_mm=0.45,
        temp_range_c=(-55, 155),
        voltage_rating_v=50.0,
        power_rating_w=0.063,
        resistance_ohm=parse_resistance_ohm(value),
        tolerance_pct=1.0,
        weight_g=weight_g_for_passive("0402"),    # Vishay CRCW datasheet typical
        fab_country="DE",
        standards=["RoHS", "Pb-Free", "Halogen-Free"],
        pins=_two_pin(),
        footprint=fp,
        note=(
            "CRCW0402 standard thick-film 0402. Use for all general digital "
            "/ pull-up / current-sense / divider positions. For precision "
            "0.5%-TCR positions a thin-film series (PNP / TNPW) would be "
            "more appropriate — separate factory."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ── capacitor: 0402 X7R ECM placeholder ─────────────────────────────────


def add_capacitor_x7r_0402_kemet(design, ref: str, *, value: str, **overrides) -> Chip:
    """KEMET 0402 X7R ceramic — ECM-absorbed placeholder for the
    ≤100 nF per-IC HF decoupling positions.

    Stays in the netlist for ratsnest connectivity but is DNP'd by
    the BOM writer when `embedded_cap_absorbs=True` is set on the
    `cap_to_gnd` helper. 1.0 × 0.5 × 0.5 mm.
    """
    family = "KEMET_C-Series_X7R"
    fp = _stock_smd_2pad(
        name="Capacitor_SMD:C_0402_1005Metric",
        size_mm=(1.0, 0.5), height_mm=0.50,
        pad_size=(0.55, 0.6), pad_pitch_mm=0.95,
        package_class="0402",
    )
    fields = dict(
        manf="KEMET",
        manf_pn=f"C0402 X7R {value}",
        value=value,
        name=f"C_0402_{value}",
        description=f"KEMET 0402 X7R ceramic, {value} (EVB placeholder; ECM-absorbed on flight)",
        datasheet=datasheet_ref(family, "kemet_c-series_mil-prf-32535_x7r.pdf"),
        package="0402",
        dielectric="X7R",
        size_mm=(1.0, 0.5),
        height_mm=0.50,
        capacitance_f=parse_capacitance_f(value),
        voltage_rating_v=25.0,
        temp_range_c=(-55, 125),
        weight_g=weight_g_for_passive("0402"),    # KEMET 0402 X7R datasheet typical
        fab_country="USA/CZ",
        standards=["RoHS", "Pb-Free"],
        pins=_two_pin(),
        footprint=fp,
        note=(
            "Per-IC HF decoupling placeholder. On flight build with the "
            "3M ECM / FaradFlex embedded-cap laminate, these are DNP'd "
            "(plane absorbs the bypass). On EVB they populate normally."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ── capacitor: 0603 X7R MIL-PRF-32535 ───────────────────────────────────


def add_capacitor_x7r_0603_kemet_mil(design, ref: str, *, value: str, **overrides) -> Chip:
    """KEMET MIL-PRF-32535 X7R BME 0603 — 1.6 × 0.8 × 0.95 mm max.

    DLA-qualified high-rel ceramic with base-metal-electrode process.
    Use for 220 nF – 1 µF positions, and as the array element when
    `cap_to_gnd` parallelises N×0603 for the 2.2–10 µF range
    (lower Z + ESR/ESL + solder-joint redundancy under shock).
    """
    family = "KEMET_C-Series_X7R"
    fp = _stock_smd_2pad(
        name="Capacitor_SMD:C_0603_1608Metric",
        size_mm=(1.6, 0.8), height_mm=0.95,
        pad_size=(0.85, 0.95), pad_pitch_mm=1.60,
        package_class="0603",
    )
    fields = dict(
        manf="KEMET",
        manf_pn=f"C-Series MIL-PRF-32535 X7R 0603 {value}",
        value=value,
        name=f"C_0603_{value}",
        description=f"KEMET 0603 MIL-PRF-32535 X7R BME, {value}, DLA QPL",
        datasheet=datasheet_ref(family, "kemet_c-series_mil-prf-32535_x7r.pdf"),
        package="0603",
        dielectric="X7R BME",
        size_mm=(1.6, 0.8),
        height_mm=0.95,
        capacitance_f=parse_capacitance_f(value),
        voltage_rating_v=50.0,
        temp_range_c=(-55, 125),
        weight_g=weight_g_for_passive("0603"),    # KEMET 0603 X7R datasheet typical
        fab_country="USA",
        standards=["MIL-PRF-32535", "RoHS", "Pb-Free", "DLA QPL"],
        pins=_two_pin(),
        footprint=fp,
        note=(
            "MIL-PRF-32535 BME X7R. Use for 220 nF – 1 µF single positions, "
            "and as the array element when `cap_to_gnd` parallelises N×0603 "
            "for 2.2–10 µF (replaces the 1206 X7R that system.py originally "
            "specified — lower Z + lower ESR + solder-joint redundancy "
            "under launch shock). Embedded into ECP layer on flight build."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ── capacitor: 0603 X7R 1 µF commercial (KEMET C0603C105K3RACTU) ────────


def add_capacitor_x7r_0603_kemet_c0603c105k3ractu(design, ref: str, *, value: str = "1uF",
                                                   **overrides) -> Chip:
    """KEMET C0603C105K3RACTU — 1 µF ±10 % 25 V X7R 0603, AEC-Q200
    (commercial C-series, not MIL-PRF-32535: no 0603 1 µF in that QPL).
    Thickness code CJ: 0.80 ± 0.15 → 0.95 mm max (DS Table 2A).

    (2026-11-20, user) Replaces the 1.45 mm-max 0805 MIL part at 1 µF
    positions — those caps set four of the five core gaps. Note the DC-bias
    derating of a 25 V 0603 at 5 V (≈ −30 %) vs the 0805."""
    fp = _stock_smd_2pad(
        name="Capacitor_SMD:C_0603_1608Metric",
        size_mm=(1.6, 0.8), height_mm=0.95,
        pad_size=(0.85, 0.95), pad_pitch_mm=1.60,
        package_class="0603",
    )
    fields = dict(
        manf="KEMET", manf_pn="C0603C105K3RACTU", value=value,
        name="C_0603_1uF_25V",
        description="KEMET 0603 X7R 1 µF 25 V ±10 %, AEC-Q200",
        datasheet=datasheet_ref("KEMET_C-Series_X7R", "kemet_c-series_x7r_commercial.pdf"),
        package="0603", dielectric="X7R BME",
        size_mm=(1.6, 0.8), height_mm=0.95,
        capacitance_f=parse_capacitance_f(value),
        voltage_rating_v=25.0, temp_range_c=(-55, 125),
        weight_g=weight_g_for_passive("0603"),
        standards=["AEC-Q200", "RoHS"],
        pins=_two_pin(), footprint=fp,
        note="1 µF 0603 X7R 25 V (thickness CJ, 0.95 max).",
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ── capacitor: 0805 X7R MIL-PRF-32535 ───────────────────────────────────


def add_capacitor_x7r_0805_kemet_mil(design, ref: str, *, value: str, **overrides) -> Chip:
    """KEMET MIL-PRF-32535 X7R BME 0805 — 2.0 × 1.25 × 1.45 mm max.

    Same MIL-PRF-32535 BME family as 0603, larger package. Used at
    1 µF – 2.2 µF positions where Z allows or the array-of-0603
    alternative would cost too much board area.
    """
    family = "KEMET_C-Series_X7R"
    fp = _stock_smd_2pad(
        name="Capacitor_SMD:C_0805_2012Metric",
        size_mm=(2.0, 1.25), height_mm=1.45,
        pad_size=(1.15, 1.45), pad_pitch_mm=1.95,
        package_class="0805",
    )
    fields = dict(
        manf="KEMET",
        manf_pn=f"C-Series MIL-PRF-32535 X7R 0805 {value}",
        value=value,
        name=f"C_0805_{value}",
        description=f"KEMET 0805 MIL-PRF-32535 X7R BME, {value}",
        datasheet=datasheet_ref(family, "kemet_c-series_mil-prf-32535_x7r.pdf"),
        package="0805",
        dielectric="X7R BME",
        size_mm=(2.0, 1.25),
        height_mm=1.45,
        capacitance_f=parse_capacitance_f(value),
        voltage_rating_v=25.0,
        temp_range_c=(-55, 125),
        weight_g=weight_g_for_passive("0805"),    # KEMET 0805 X7R datasheet typical
        fab_country="USA",
        standards=["MIL-PRF-32535", "RoHS", "Pb-Free", "DLA QPL"],
        pins=_two_pin(),
        footprint=fp,
        note="MIL X7R 0805 — for 1 µF–2.2 µF single positions where Z permits.",
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ── capacitor: 0603 C0G RF (AVX SQCS) ───────────────────────────────────


def add_capacitor_c0g_0603_avx_sqcs(design, ref: str, *, value: str, **overrides) -> Chip:
    """AVX SQCS RF/microwave C0G ceramic MLC — 1.6 × 0.8 × 0.76 mm.

    **Mis-labelled as "silver mica" in system.py.** The actual SQCS
    is a C0G/NP0 ceramic MLC (TCC = 0±30 ppm/°C). Ultra-low ESR,
    high Q, high SRF. 0.1 pF – 240 pF, 250 V.

    Use for all pF-range positions: LoRa pi-network, ADF4351 4.4 GHz
    match, NFC AC0/AC1 trim, QPD TIA feedback.
    """
    family = "AVX_SQCS"
    fp = _stock_smd_2pad(
        name="Capacitor_SMD:C_0603_1608Metric",
        size_mm=(1.6, 0.8), height_mm=0.76,
        pad_size=(0.85, 0.95), pad_pitch_mm=1.60,
        package_class="0603",
    )
    fields = dict(
        manf="AVX (KYOCERA AVX)",
        manf_pn=f"SQCSVA {value}",
        value=value,
        name=f"C_0603_RF_{value}",
        description=f"AVX SQCS 0603 RF/microwave C0G MLC, {value}, 250 V",
        datasheet=datasheet_ref(family, "SQCS_SQCF_Series_DS.pdf"),
        package="0603",
        dielectric="C0G/NP0",
        size_mm=(1.6, 0.8),
        height_mm=0.76,
        capacitance_f=parse_capacitance_f(value),
        voltage_rating_v=250.0,
        temp_range_c=(-55, 125),
        tolerance_pct=1.0,
        weight_g=weight_g_for_passive("0603"),    # AVX SQCS 0603 ~ KEMET 0603 mass
        fab_country="USA",
        standards=["RoHS", "Pb-Free"],
        pins=_two_pin(),
        footprint=fp,
        note=(
            "AVX SQCS = RF/microwave **C0G MLC**, not silver mica. "
            "System.py's `FP_C_MICA` was misnamed (0±30 ppm/°C TCC matches "
            "silver mica's stability, hence the historical confusion). "
            "Use for all pF-range positions on Smash: LoRa pi-network, "
            "ADF4351 match, NFC trim, QPD TIA feedback."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ── capacitor: case-B MnO₂ tantalum (KEMET T491) ───────────────────────


def add_capacitor_tantalum_3528_kemet_t491(design, ref: str, *, value: str, **overrides) -> Chip:
    """KEMET T491 MnO₂ tantalum, case-B 3528-12 (thinnest variant) —
    3.5 × 2.8 × **1.10 mm**.

    Industrial-grade solid tantalum with MnO₂ counter-electrode.
    Used for 22 µF bulk decoupling positions. system.py originally
    specified case code 3528-21 (1.90 mm Z); this factory uses the
    thinner -12 variant for a 42% Z reduction at the same value/voltage.
    """
    family = "KEMET_T491"
    fp = _stock_smd_2pad(
        name="Capacitor_Tantalum_SMD:CP_EIA-3528-12_Kemet-T",
        size_mm=(3.5, 2.8), height_mm=1.10,
        pad_size=(1.4, 2.3), pad_pitch_mm=2.4,
        package_class="case-B (EIA-3528-12)",
    )
    fields = dict(
        manf="KEMET",
        manf_pn=f"T491T {value} (3528-12 thinnest variant)",
        value=value,
        name=f"C_3528_TANT_{value}",
        description=f"KEMET T491 MnO₂ tantalum, {value}, case-B 3528-12 (1.10 mm Z)",
        datasheet=datasheet_ref(family, "kemet_t491_tantalum.pdf"),
        package="case-B (EIA-3528-12)",
        dielectric="Tantalum oxide (MnO₂ counter-electrode)",
        size_mm=(3.5, 2.8),
        height_mm=1.10,
        capacitance_f=parse_capacitance_f(value),
        voltage_rating_v=16.0,
        temp_range_c=(-55, 125),
        weight_g=WEIGHT_G_TANTALUM_3528B,         # KEMET T491 case-B datasheet
        fab_country="USA/MX",
        standards=["RoHS", "Pb-Free"],
        pins=_two_pin("+", "-"),
        footprint=fp,
        note=(
            "T491 case-B-12 (1.10 mm Z) — thinnest variant of 3528. "
            "system.py originally specified -21 (1.90 mm); catalog "
            "switches to -12 for free Z reduction at same C/V.\n\n"
            "MnO₂ counter-electrode has known ignite-on-overvoltage "
            "failure mode. Smash 22 µF positions are well below rated "
            "voltage — risk negligible. Polarized; + (pin 1) marked."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ── capacitor: case-X polymer (KEMET T528) ─────────────────────────────


def add_capacitor_polymer_7343_kemet_t528(design, ref: str, *, value: str, **overrides) -> Chip:
    """KEMET T528 KO-CAP polymer-Al, case-X 7343-15 (thinnest W
    variant) — 7.3 × 4.3 × **1.40 mm**.

    Polymer-tantalum hybrid (KO-CAP): low ESR, low ESL, no ignite-
    on-failure mode. Used for ≥47 µF bulk decoupling. Smash benefits
    from polymer here because shock-induced regulator transients need
    low ESR to absorb. system.py originally specified 7343-43 (4.30 mm Z);
    this factory uses the thinner W-variant for a 3× Z reduction.
    """
    family = "KEMET_T528"
    fp = _stock_smd_2pad(
        name="Capacitor_Tantalum_SMD:CP_EIA-7343-15_Kemet-W",
        size_mm=(7.3, 4.3), height_mm=1.40,
        pad_size=(2.5, 3.5), pad_pitch_mm=4.5,
        package_class="case-X (EIA-7343-15)",
    )
    fields = dict(
        manf="KEMET",
        manf_pn=f"T528W {value} (7343-15 thinnest variant)",
        value=value,
        name=f"C_7343_POLY_{value}",
        description=f"KEMET T528 KO-CAP polymer-Al, {value}, case-X 7343-15 (1.40 mm Z)",
        datasheet=datasheet_ref(family, "kemet_t528_polymer.pdf"),
        package="case-X (EIA-7343-15)",
        dielectric="Ta₂O₅ + conductive polymer (KO-CAP)",
        size_mm=(7.3, 4.3),
        height_mm=1.40,
        capacitance_f=parse_capacitance_f(value),
        voltage_rating_v=6.3,
        temp_range_c=(-55, 105),
        weight_g=WEIGHT_G_TANTALUM_7343X,         # KEMET T528 case-X datasheet
        fab_country="USA/MX",
        standards=["RoHS", "Pb-Free", "MSL3"],
        pins=_two_pin("+", "-"),
        footprint=fp,
        note=(
            "T528 KO-CAP polymer = low ESR + low ESL + no ignite-on-failure "
            "mode (unlike MnO₂ tantalum). Right choice for shock-induced "
            "regulator transient absorption. Case-X-W = 1.40 mm Z (thinnest "
            "7343 polymer); system.py originally specified -43 (4.30 mm). "
            "MSL3 — moisture-barrier bag required, 168h floor at 30°C/60%RH. "
            "Polarized; + marked."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ── capacitor: Panasonic SVPF conductive-polymer aluminium (V-chip) ─────


def add_capacitor_svpf_25v_330uf_panasonic(design, ref: str, **overrides) -> Chip:
    """Panasonic 25SVPF330M — SVPF-series conductive-polymer aluminium
    solid capacitor, 330 µF / 25 V, ESR 14 mΩ, ripple 1650 mA, size
    code F12: a vertical V-chip can, øD 10.0 mm × **12.6 mm tall**.

    Polymer-aluminium (no ignite-on-failure mode, low ESR) rated to 50 V
    / 1000 µF across the family. Kept in the catalog. It used to be the
    reservoir on ACTIVATE_HV for the aft parachute-cutter wires; the live
    circuit current-sources each nichrome restraint from the TPS61175
    directly, so this can is not instantiated.

    The old bias was ~19.7 V (150k/10k FB), about 79 % of the 25 V
    rating. The live cutter rail is 33 V and does not use this can. The
    12.6 mm height was absorbed by mounting it in the annular dead-space
    beside the cell.

    Ground-truth in parts/sources/25SVPF330M/ (SamacSys zip + DS
    PANA-S-A0027325923-1 → SVPF.pdf). Polarized; + = pin 1."""
    pn = "25SVPF330M"
    fp_mod = src(pn, "16SVF1000M.kicad_mod")
    fields = dict(
        manf="Panasonic", manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn, value="330uF",
        description=(
            "Conductive-polymer Al capacitor, 330 µF / 25 V, ESR 14 mΩ, "
            "V-chip F12 (10.0 × 12.6 mm)"
        ),
        datasheet=datasheet_ref(pn, "SVPF.pdf"),
        package="V-chip F12 (10.0 × 12.6 mm)",
        dielectric="Al₂O₃ + conductive polymer (SVPF)",
        size_mm=(10.3, 10.3),
        height_mm=12.6,
        capacitance_f=parse_capacitance_f("330uF"),
        voltage_rating_v=25.0,
        temp_range_c=(-55, 105),
        weight_g=None, fab_country=None,
        standards=["RoHS", "Halogen-Free"],
        pins=build_pins(
            src(pn, f"{pn}.kicad_sym"),
            types={"+": "io", "-": "io"},
            aliases={"+": ["1", "P"], "-": ["2", "N"]},
        ),
        footprint=Footprint(
            name="CP_Panasonic_SVPF_F12",
            package_class="V-chip F12 (EIA-?)",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            # The SamacSys F.CrtYd is the generic V-chip courtyard (12.4 ×
            # 16.3 mm, asymmetric — it includes a large seating/anode-band
            # margin). The actual keepout for the øD 10.0 mm can is the
            # body + IPC clearance ≈ 11 mm square; use that so the part
            # packs against its real footprint, not the conservative pad.
            courtyard=[(-5.5, -5.5), (5.5, -5.5), (5.5, 5.5), (-5.5, 5.5)],
            size_mm=(10.3, 10.3),
            height_mm=12.6,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=(
            "Panasonic SVPF polymer-Al, 105 °C/5000 h, 50 V / 1000 µF max "
            "family. 25SVPF330M = F12 V-chip, øD 10.0 × 12.6 mm, ESR "
            "14 mΩ, ripple 1650 mA. Retired parachute-cutter reservoir "
            "(the live restraints are current-sourced from the 33 V "
            "boost). Polarized; + = pin 1."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ── inductor: Würth WE-KI 0402 ──────────────────────────────────────────


def add_inductor_we_ki_0402_wurth(design, ref: str, *, value: str, **overrides) -> Chip:
    """Würth WE-KI 0402 multilayer ceramic inductor — 1.0 × 0.5 × 0.55 mm.

    RF range 1–120 nH, high-Q, SRF up to 12.5 GHz. Use for RF matching
    + low-current signal-path 0402 positions. For switching-regulator
    inductors at higher current, use TMS201210ALM or 744043100.
    """
    family = "Wurth_WE-KI_0402"
    fp = _stock_smd_2pad(
        name="Inductor_SMD:L_0402_1005Metric",
        size_mm=(1.0, 0.5), height_mm=0.55,
        pad_size=(0.55, 0.6), pad_pitch_mm=0.95,
        package_class="0402",
    )
    fields = dict(
        manf="Würth Elektronik",
        manf_pn=f"WE-KI 0402 {value} (74479xxxxx family)",
        value=value,
        name=f"L_0402_{value}",
        description=f"Würth WE-KI 0402 multilayer RF inductor, {value}",
        datasheet=datasheet_ref(family, "wurth_we-ki_0402.pdf"),
        package="0402",
        size_mm=(1.0, 0.5),
        height_mm=0.55,
        inductance_h=parse_inductance_h(value),
        temp_range_c=(-40, 125),
        weight_g=weight_g_for_passive("0402"),   # WE-KI 0402 multilayer ~ stock 0402 mass
        fab_country="DE",
        standards=["RoHS", "Pb-Free", "Halogen-Free"],
        pins=_two_pin(),
        footprint=fp,
        note="WE-KI 0402 ceramic — RF range (1–120 nH). High-Q, SRF up to 12.5 GHz.",
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ── inductor: TDK TMS201210ALM ──────────────────────────────────────────


def add_inductor_tms201210alm_tdk(design, ref: str, *, value: str, **overrides) -> Chip:
    """TDK TMS201210ALM thin-film metal magnetic power inductor —
    2.0 × 1.25 × **1.0 mm**.

    Metal-magnetic-material wound power inductor. Used for the four
    STPMIC25 buck rails and the LMR10510/TPS61085 buck/boost outputs.
    """
    family = "TDK_TMS201210ALM"
    fp = _stock_smd_2pad(
        name="Inductor_SMD:L_2012_2.0x1.25mm",
        size_mm=(2.0, 1.25), height_mm=1.0,
        pad_size=(0.6, 1.3), pad_pitch_mm=1.6,
        package_class="2012 metric (0805 imperial)",
    )
    # Isat max per datasheet table
    isat_table = {
        0.24e-6: 4.6, 0.33e-6: 3.9, 0.47e-6: 3.4, 0.56e-6: 3.0,
        1.0e-6: 2.7, 1.5e-6: 2.0, 2.2e-6: 1.2,
    }
    l_h = parse_inductance_h(value)
    isat = None
    for v, i in isat_table.items():
        if abs(l_h - v) < 1e-9:
            isat = i; break
    fields = dict(
        manf="TDK",
        manf_pn=f"TMS201210ALM-{_tms_sku(value)}MTAA",
        value=value,
        name=f"L_2012_{value}",
        description=f"TDK TMS201210ALM thin-film metal power inductor, {value}",
        datasheet=datasheet_ref(family, "inductor_commercial_power_tms201210alm_en.pdf"),
        package="2012 metric (0805 imperial)",
        size_mm=(2.0, 1.25),
        height_mm=1.0,
        inductance_h=l_h,
        i_sat_a=isat,
        temp_range_c=(-40, 105),
        voltage_rating_v=20.0,
        weight_g=WEIGHT_G_INDUCTOR_TDK_TMS20,    # TDK TMS20 wirewound 2.0×1.25×1.0
        fab_country="JP",
        standards=["RoHS", "Pb-Free", "Halogen-Free"],
        pins=_two_pin(),
        footprint=fp,
        note=(
            "TDK TMS-ALM = thin-film metal magnetic, metal core, closed "
            "magnetic circuit. Low-profile 1.0 mm Z.\n\n"
            "Isat max by L (datasheet table):\n"
            "  0.24 µH → 4.6 A    0.33 µH → 3.9 A    0.47 µH → 3.4 A\n"
            "  0.56 µH → 3.0 A    1.0 µH → 2.7 A     1.5 µH → 2.0 A\n"
            "  2.2 µH → 1.2 A\n\n"
            "Smash use: 1.0 µH for the four STPMIC25 buck rails. BUCK1 "
            "(3 A peak) is marginal vs 2.4 A Itemp — fine for burst loads. "
            "If prototype thermal data tightens, switch BUCK1 to 0.47 µH "
            "(3.4 A Isat) — same package, same factory, different value."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def _tms_sku(value: str) -> str:
    """Format a TMS201210ALM inductance value as the TDK SKU code:
    '0.47uH' → 'R47', '1.0uH' → '1R0', '2.2uH' → '2R2'."""
    l_h = parse_inductance_h(value)
    uh = l_h * 1e6
    if uh < 1.0:
        # sub-µH: leading R
        return f"R{int(round(uh * 100)):02d}"
    whole = int(uh)
    frac = int(round((uh - whole) * 10))
    return f"{whole}R{frac}"


# ═════════════════════════════════════════════════════════════════════════
# (2026-11-21) Orderable replacements found by the BOM / Mouser pass:
#   T528W 470 µF only exists at 1.8 V and T528W 100 µF does not exist →
#   KEMET T545W / T520W polymers in the same W case (7343-15, 1.5 mm);
#   WE-KI 0402 has no 1.3 / 1.8 nH → Murata LQG15HS 1.3 nH, Würth WE-MK
#   1.8 nH; the 33 V activation rail needs a 50 V 2.2 µF → 0805.
# SamacSys libraries vendored in parts/sources/<PN>/ (user, 2026-11-21);
# C0805C225K5RACTU and 744784018A came with a 3D model only → KiCad stock
# IPC footprint + the vendor model.
# ═════════════════════════════════════════════════════════════════════════

def _samacsys_2pin_fp(pn: str, mod: str, package_class: str, size_mm: tuple,
                      height_mm: float) -> Footprint:
    fp_mod = src(pn, mod)
    return Footprint(
        name=mod.rsplit(".", 1)[0], package_class=package_class,
        pads=pads_from_kicad_mod(fp_mod),
        body_outline=outline_polygon(fp_mod, "F.Fab"),
        courtyard=outline_polygon(fp_mod, "F.CrtYd"),
        size_mm=size_mm, height_mm=height_mm,
        model_3d_path=datasheet_ref(pn, f"{pn}.stp"), source="samacsys",
    ).ensure_courtyard_clearance()


def _polymer_w(design, ref, *, pn, value, mod, series, **overrides) -> Chip:
    fields = dict(
        manf="KEMET", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=value,
        description=f"KEMET {series} polymer tantalum, {value}, 6.3 V, W case 7343-15 (1.5 mm)",
        package="case-W (EIA-7343-15)", dielectric="Ta₂O₅ + conductive polymer",
        size_mm=(7.3, 4.3), height_mm=1.5, capacitance_f=parse_capacitance_f(value),
        voltage_rating_v=6.3, temp_range_c=(-55, 105), weight_g=WEIGHT_G_TANTALUM_7343X,
        standards=["RoHS", "Pb-Free"], pins=_two_pin("+", "-"),
        footprint=_samacsys_2pin_fp(pn, mod, "case-W (EIA-7343-15)", (7.3, 4.3), 1.5),
        note=(f"{series} polymer, W case — replaces a T528W value that is not made "
              "(2026-11-21). ESR differs from the T528: re-check the buck loops."),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_capacitor_polymer_t545w477m006ate035(design, ref: str, *, value: str = "470uF", **overrides) -> Chip:
    """KEMET T545W477M006ATE035 — 470 µF 6.3 V polymer, W case 7343-15."""
    return _polymer_w(design, ref, pn="T545W477M006ATE035", value=value, mod="T545W.kicad_mod",
                      series="T545", **overrides)


def add_capacitor_polymer_t520w107m006ate040(design, ref: str, *, value: str = "100uF", **overrides) -> Chip:
    """KEMET T520W107M006ATE040 — 100 µF 6.3 V polymer, W case 7343-15."""
    return _polymer_w(design, ref, pn="T520W107M006ATE040", value=value, mod="T520W.kicad_mod",
                      series="T520", **overrides)


def add_capacitor_c0805c225k5ractu(design, ref: str, *, value: str = "2.2uF", **overrides) -> Chip:
    """KEMET C0805C225K5RACTU — 2.2 µF 50 V X7R 0805 (KiCad stock footprint + vendor 3D)."""
    pn = "C0805C225K5RACTU"
    fp = _stock_smd_2pad(name="Capacitor_SMD:C_0805_2012Metric", size_mm=(2.0, 1.25),
                         height_mm=1.45, pad_size=(1.15, 1.45), pad_pitch_mm=1.95,
                         package_class="0805")
    fp.model_3d_path = datasheet_ref(pn, f"{pn}.stp")
    # vendor STEP hangs below z = 0 with a corner at the origin: flip about X, centre
    fp.model_rotate_deg = (180.0, 0.0, 0.0)
    fp.model_offset_mm = (-1.1, 0.725, 0.0)
    fields = dict(
        manf="KEMET", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=value,
        description="KEMET 0805 X7R 2.2 µF 50 V", package="0805", dielectric="X7R",
        size_mm=(2.0, 1.25), height_mm=1.45, capacitance_f=parse_capacitance_f(value),
        voltage_rating_v=50.0, temp_range_c=(-55, 125), weight_g=weight_g_for_passive("0805"),
        standards=["RoHS", "Pb-Free"], pins=_two_pin(), footprint=fp,
        note="50 V 2.2 µF X7R (0603 tops out at 10 V). DC bias at 33 V leaves well under 2.2 µF.",
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_inductor_murata_lqg15hs1n3s02d(design, ref: str, *, value: str = "1.3nH", **overrides) -> Chip:
    """Murata LQG15HS1N3S02D — 1.3 nH multilayer 0402 (no 1.3 nH in Würth WE-KI/WE-MK)."""
    pn = "LQG15HS1N3S02D"
    fields = dict(
        manf="Murata", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=value,
        description="Murata LQG15HS multilayer RF inductor 0402, 1.3 nH", package="0402",
        size_mm=(1.0, 0.5), height_mm=0.55, inductance_h=parse_inductance_h(value),
        weight_g=weight_g_for_passive("0402"), standards=["RoHS", "Pb-Free"], pins=_two_pin(),
        footprint=_samacsys_2pin_fp(pn, "LQG15WH0N7B02D.kicad_mod", "0402", (1.0, 0.5), 0.55),
        note="RF match value (XV PA input). SamacSys LQG15 land pattern.",
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_inductor_we_mk_744784018a(design, ref: str, *, value: str = "1.8nH", **overrides) -> Chip:
    """Würth WE-MK 744784018A — 1.8 nH multilayer 0402 (WE-KI has no 1.8 nH)."""
    pn = "744784018A"
    fp = _stock_smd_2pad(name="Inductor_SMD:L_0402_1005Metric", size_mm=(1.0, 0.5),
                         height_mm=0.55, pad_size=(0.6, 0.6), pad_pitch_mm=1.0,
                         package_class="0402")
    fp.model_3d_path = datasheet_ref(pn, f"{pn}.stp")
    fp.model_rotate_deg = (-90.0, 0.0, 0.0)      # vendor STEP is Y-up, centred
    fields = dict(
        manf="Würth Elektronik", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=value,
        description="Würth WE-MK multilayer RF inductor 0402, 1.8 nH", package="0402",
        size_mm=(1.0, 0.5), height_mm=0.55, inductance_h=parse_inductance_h(value),
        weight_g=weight_g_for_passive("0402"), standards=["RoHS", "Pb-Free"], pins=_two_pin(),
        footprint=fp, note="RF bias / match value (XV LNA). KiCad stock 0402 land + Würth 3D.",
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# (2026-11-22) BOM-sourcing swaps (availability/decisions.csv)
# ═════════════════════════════════════════════════════════════════════════

def add_inductor_murata_lqg15hs1n8s02d(design, ref: str, *, value: str = "1.8nH", **overrides) -> Chip:
    """Murata LQG15HS1N8S02D — 1.8 nH multilayer 0402 (replaces Würth WE-MK
    744784018A, China lots). Same LQG15 land as the 1.3 nH part."""
    pn = "LQG15HS1N8S02D"
    fp_mod = src("LQG15HS1N3S02D", "LQG15WH0N7B02D.kicad_mod")
    fp = Footprint(name="LQG15HS1N8S02D", package_class="0402", pads=pads_from_kicad_mod(fp_mod),
                   body_outline=outline_polygon(fp_mod, "F.Fab"), courtyard=outline_polygon(fp_mod, "F.CrtYd"),
                   size_mm=(1.0, 0.5), height_mm=0.55, source="samacsys").ensure_courtyard_clearance()
    fields = dict(
        manf="Murata", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=value,
        description="Murata LQG15HS multilayer RF inductor 0402, 1.8 nH", package="0402",
        size_mm=(1.0, 0.5), height_mm=0.55, inductance_h=parse_inductance_h(value),
        weight_g=weight_g_for_passive("0402"), standards=["RoHS", "Pb-Free"], pins=_two_pin(),
        footprint=fp, note="RF bias / match value (XV LNA). Replaces 744784018A (China lots), 2026-11-22.",
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_capacitor_grm31cr60j476me19l(design, ref: str, *, value: str = "47uF", **overrides) -> Chip:
    """Murata GRM31CR60J476ME19L — 47 µF 6.3 V X5R 1206, 1.6 ± 0.2 mm. Two in
    parallel replace the 100 µF T520W107 polymer (China lots, 2026-11-22);
    +0.3 mm face rise accepted by the user. DC bias at ~4 V costs ~half."""
    fp = _stock_smd_2pad(name="Capacitor_SMD:C_1206_3216Metric", size_mm=(3.2, 1.6), height_mm=1.8,
                         pad_size=(1.05, 1.75), pad_pitch_mm=2.95, package_class="1206")
    pn = "GRM31CR60J476ME19L"
    fields = dict(
        manf="Murata", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=value,
        description="Murata 1206 X5R 47 µF 6.3 V", package="1206", dielectric="X5R",
        size_mm=(3.2, 1.6), height_mm=1.8, capacitance_f=parse_capacitance_f(value),
        voltage_rating_v=6.3, temp_range_c=(-55, 85), weight_g=weight_g_for_passive("1206"),
        standards=["RoHS", "Pb-Free"], pins=_two_pin(), footprint=fp,
        note="2 × 47 µF replaces 100 µF polymer (availability/decisions.csv).",
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


add_capacitor_grm31cr60j476me19l.array_value = "47uF"


def _grm21_22u(design, ref, *, pn, volts, value="22uF", **overrides) -> Chip:
    fp = _stock_smd_2pad(name="Capacitor_SMD:C_0805_2012Metric", size_mm=(2.0, 1.25), height_mm=1.25,
                         pad_size=(1.15, 1.45), pad_pitch_mm=1.95, package_class="0805")
    fields = dict(
        manf="Murata", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=value,
        description=f"Murata 0805 X5R 22 µF {volts} V", package="0805", dielectric="X5R",
        size_mm=(2.0, 1.25), height_mm=1.25, capacitance_f=parse_capacitance_f(value),
        voltage_rating_v=float(volts), temp_range_c=(-55, 85), weight_g=weight_g_for_passive("0805"),
        standards=["RoHS", "Pb-Free"], pins=_two_pin(), footprint=fp,
        note="(2026-11-22) ceramic bank replacing a polymer (height round 16, availability/decisions.csv).",
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_capacitor_grm21br61a226me44l(design, ref: str, *, value: str = "22uF", **overrides) -> Chip:
    """Murata GRM21BR61A226ME44L — 22 µF 10 V X5R 0805, 1.25 mm max. Bank
    element for the battery rails (BAT_RAW / BAT_PROT); ~50-60 % left at 4 V bias."""
    return _grm21_22u(design, ref, pn="GRM21BR61A226ME44L", volts=10, value=value, **overrides)


add_capacitor_grm21br61a226me44l.array_value = "22uF"


def add_capacitor_grm21br61e226me44l(design, ref: str, *, value: str = "22uF", **overrides) -> Chip:
    """Murata GRM21BR61E226ME44L — 22 µF 25 V X5R 0805, 1.25 mm max (5 V rails)."""
    return _grm21_22u(design, ref, pn="GRM21BR61E226ME44L", volts=25, value=value, **overrides)


def add_inductor_we_mapi_74438356047(design, ref: str, **overrides) -> Chip:
    """Würth WE-MAPI 4020 74438356047 — 4.7 µH ±20 %, 4.1 × 4.1 × 2.1 mm max,
    AEC-Q200 grade 1. Isat 3.05 A (10 %) / 5.75 A (30 %) typ, IRP 4 A (ΔT 40 K),
    RDC 63 typ / 76 max mΩ, SRF 22 MHz (Würth DS 2026-09-01). The 30 % point
    covers the TPS61175's 5 A max switch limit like the XGL5020's 5.3 A did.
    Land = Würth's recommended 0.98 × 3.7 mm pads at 2.37 mm pitch, identical
    to the vendored WE-MAPI 4030 land (parts/sources/74438357047)."""
    pn = "74438356047"
    fp_mod = src("74438357047", "WE-MAPI_4030.kicad_mod")
    fp = Footprint(name="WE-MAPI_4020", package_class="WE-MAPI 4020", pads=pads_from_kicad_mod(fp_mod),
                   body_outline=[(-2.05, -2.05), (2.05, -2.05), (2.05, 2.05), (-2.05, 2.05), (-2.05, -2.05)],
                   size_mm=(4.1, 4.1), height_mm=2.1, source="wurth-ds").ensure_courtyard_clearance()
    fields = dict(
        manf="Würth Elektronik", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value="4.7uH",
        description="Würth WE-MAPI 4020 4.7 µH power inductor, Isat(30 %) 5.75 A, 63 mΩ",
        package="WE-MAPI 4020", size_mm=(4.1, 4.1), height_mm=2.1, inductance_h=4.7e-6,
        standards=["AEC-Q200", "RoHS"], pins=[Pin(num="1", name="1", type="io"), Pin(num="2", name="2", type="io")],
        footprint=fp, note="Replaces Coilcraft XGL5020-472MEC (Coilcraft-only) — height round 16 (2026-11-22).",
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_capacitor_tdk_c2012x7r1h225k125ac(design, ref: str, *, value: str = "2.2uF", **overrides) -> Chip:
    """TDK C2012X7R1H225K125AC — 2.2 µF 50 V X7R 0805, 1.25 mm thickness
    (vs the 1.45 mm KEMET C0805C225K5RACTU): smaller-parts round 17
    (2026-11-22), all 3 suppliers, Japan. KiCad stock 0805 land."""
    pn = "C2012X7R1H225K125AC"
    fp = _stock_smd_2pad(name="Capacitor_SMD:C_0805_2012Metric", size_mm=(2.0, 1.25),
                         height_mm=1.25, pad_size=(1.15, 1.45), pad_pitch_mm=1.95,
                         package_class="0805")
    fields = dict(
        manf="TDK", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=value,
        description="TDK 0805 X7R 2.2 µF 50 V, 1.25 mm", package="0805", dielectric="X7R",
        size_mm=(2.0, 1.25), height_mm=1.25, capacitance_f=parse_capacitance_f(value),
        voltage_rating_v=50.0, temp_range_c=(-55, 125), weight_g=weight_g_for_passive("0805"),
        standards=["RoHS", "Pb-Free"], pins=_two_pin(), footprint=fp,
        note="50 V 2.2 µF X7R on the 33 V rail; DC bias at 33 V leaves well under 2.2 µF.",
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_capacitor_samsung_cl10a106kp8nnnc(design, ref: str, *, value: str = "10uF", **overrides) -> Chip:
    """Samsung CL10A106KP8NNNC — 10 µF 10 V X5R 0603, 0.8 mm. Pairs replace
    the 1.1 mm KEMET T491T 22 µF tantalum on rails ≤ 3.3 V (round 19,
    2026-11-22: Digi-Key 75,367, Philippines; single stocked supplier,
    user-accepted exception). Not used ≥ 5 V (DC-bias loss)."""
    pn = "CL10A106KP8NNNC"
    fp = _stock_smd_2pad(name="Capacitor_SMD:C_0603_1608Metric", size_mm=(1.6, 0.8),
                         height_mm=0.8, pad_size=(0.85, 0.95), pad_pitch_mm=1.60,
                         package_class="0603")
    fields = dict(
        manf="Samsung Electro-Mechanics", manf_pn=pn, canonical_id=canonical_id(pn), name=pn,
        value=value, description="Samsung 0603 X5R 10 µF 10 V, 0.8 mm", package="0603",
        dielectric="X5R", size_mm=(1.6, 0.8), height_mm=0.8,
        capacitance_f=parse_capacitance_f(value), voltage_rating_v=10.0, temp_range_c=(-55, 85),
        weight_g=weight_g_for_passive("0603"), standards=["RoHS", "Pb-Free"], pins=_two_pin(),
        footprint=fp,
        note="2 × 10 µF replace one 22 µF T491T on ≤ 3.3 V rails (smaller and 0.3 mm lower).",
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


add_capacitor_samsung_cl10a106kp8nnnc.array_value = "10uF"
