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
    / 1000 µF across the family. This is the aft activation array's
    activation CAPACITOR on ACTIVATE_HV: the boost (TPS61175) trickle-charges it,
    and on fire it dumps the ~1 A / 10 ms pulse into the selected
    nichrome burn-wire so the cell never sees the pulse power.

    ACTIVATE_HV runs at ~19.7 V (150k/10k FB) = ~79 % of the 25 V rating —
    proper polymer derating. The 12.6 mm height is absorbed by mounting
    the can in the annular dead-space BESIDE the cell (its length
    overlaps the battery compartment, costing ~0 added stack height).

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
            "14 mΩ, ripple 1650 mA. Smash: FIRE_HV firing cap (charged to "
            "~19.7 V, ~79 % derated); mounts beside the cell so its height "
            "overlaps the battery compartment. Polarized; + = pin 1."
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
