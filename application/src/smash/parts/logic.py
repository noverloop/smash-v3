"""Logic-gate factories (AND/OR/NAND/NOR/XOR/buffer)."""

from __future__ import annotations

from smash.state import Chip, Footprint
from smash.parts._artifacts import (
    pads_from_kicad_mod, outline_polygon, build_pins, src, datasheet_ref,
)
from smash.parts._slug import canonical_id


def add_sn74lvc1g08dbvr(design, ref: str, **overrides) -> Chip:
    """TI SN74LVC1G08DBVR — single 2-input positive-AND gate,
    1.65-5.5 V V_CC, 5-V tolerant inputs, ±24 mA output drive at 3.3 V,
    SC-70-5 / SOT-23-5 (DBV) package.

    Used on `flight_board` as the hardware AND gate producing
    `ACTIVATE_CONFIRM = ACTIVATE_SET AND COMP_OUT` — the unforgeable
    confirmation that BOTH firmware (ACTIVATE_SET on PC15) AND the
    piezo comparator (COMP_OUT) agree before the activation board sees
    the activation signal. Single-fault tolerance for the safety-critical signal."""
    pn = "SN74LVC1G08DBVR"
    fp_mod = src(pn, "SOT95P280X145-5N.kicad_mod")
    fields = dict(
        manf="Texas Instruments", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "Single 2-input positive-AND gate, V_CC=1.65..5.5 V, "
            "5 V-tolerant inputs, ±24 mA output drive, SOT-23-5"
        ),
        datasheet=datasheet_ref(pn, "SN74LVC1G08.pdf"),
        package="SOT-23-5 (DBV)",
        size_mm=(2.9, 1.6),
        height_mm=1.45,
        temp_range_c=(-40, 125),         # industrial T_A operating
        voltage_rating_v=6.5,            # V_CC abs max per family
        vcc_nominal_v=3.3,               # supports 1.65-5.5 V; 3.3 typical
        clock_max_hz=None,
        standards=[
            "ESD HBM ±2000 V (JEDEC JS-001 A114-A)",
            "ESD MM ±200 V (JEDEC A115-A)",
            "ESD CDM ±1000 V (JEDEC C101)",
            "Latch-up >100 mA (JESD 78 Class II)",
        ],
        pins=build_pins(
            src(pn, f"{pn}.kicad_sym"),
            types={"A": "input", "B": "input", "Y": "output",
                   "VCC": "power", "GND": "ground"},
        ),
        footprint=Footprint(
            name="SOT95P280X145-5N",
            package_class="SOT-23-5 (DBV)",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.95,
            size_mm=(2.9, 1.6),
            height_mm=1.45,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=(
            "SN74LVC1G08 family — single 2-input AND in many packages "
            "(DBV/SOT-23-5, DCK/SC-70-5, YZP/X2SON, RSE/SON). This "
            "factory targets the DBV (SOT-23-5) variant.\n\n"
            "Key specs (datasheet SCES217Z):\n"
            "  V_CC operating : 1.65 V to 5.5 V\n"
            "  Input voltage  : up to 5.5 V (5 V tolerant on V_CC=3.3)\n"
            "  Down-translation to V_CC supported\n"
            "  t_pd max       : 3.6 ns @ 3.3 V V_CC\n"
            "  I_CC max       : 10 µA\n"
            "  Output drive   : ±24 mA at 3.3 V\n"
            "  I_off          : supports live insertion, partial power\n"
            "                   down, back-drive protection\n\n"
            "Smash use (legacy hardware-confirm topology — RETIRED; the\n"
            "ACTIVATE_SET/CONFIRM interlock is firmware GPIOs on the MP25\n"
            "M33 now, no AND gate). Historical wiring:\n"
            "  Y = ACTIVATE_CONFIRM\n"
            "  A = ACTIVATE_SET   (firmware command from MP25 M33 PE0)\n"
            "  B = COMP_OUT       (TLV3691 piezo comparator output)\n\n"
            "Neither firmware (which controlled A) nor the piezo (which\n"
            "controls B) alone could produce Y — both had to agree, making\n"
            "the AND gate an unforgeable launch confirmation. Kept in the\n"
            "catalog; not instantiated since the interlock moved to firmware."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_sn74lvc1g08dckrg4(design, ref: str, **overrides) -> Chip:
    """TI SN74LVC1G08DCKRG4 — same die as `SN74LVC1G08DBVR` in the
    smaller SC-70-5 (DCK) package. Single 2-input positive-AND gate,
    1.65-5.5 V V_CC, 5-V tolerant inputs, ±24 mA output drive at 3.3 V.

    The `G4` suffix is TI's "Pb-free, NiPdAu lead finish" SKU marker
    (vs the older `E4` marker for the same Pb-free physical part).
    Physical part is identical to plain `DCKR` — modern TI parts are
    all green/Pb-free by default; G4/E4 are only catalogue markers.

    Sn-Pb solder paste at assembly is the standard mil-aero workaround
    to get a leaded solder joint on this Pb-free part: NiPdAu leads
    bond to both Sn63/Pb37 and SAC305 pastes. Pb-free part + Sn-Pb
    joint = "mixed-alloy" assembly; well-characterised for high-G
    shock and thermal-cycle survivability."""
    pn = "SN74LVC1G08DCKRG4"
    fp_mod = src(pn, "SOT65P210X110-5N.kicad_mod")
    fields = dict(
        manf="Texas Instruments", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "Single 2-input positive-AND gate, V_CC=1.65..5.5 V, "
            "5 V-tolerant inputs, ±24 mA output drive, SC-70-5 (DCK)"
        ),
        datasheet=datasheet_ref(pn, "SN74LVC1G08.pdf"),
        package="SC-70-5 (DCK)",
        size_mm=(2.0, 1.25),
        height_mm=1.1,
        temp_range_c=(-40, 125),         # industrial T_A operating
        voltage_rating_v=6.5,            # V_CC abs max per family
        vcc_nominal_v=3.3,               # supports 1.65-5.5 V; 3.3 typical
        clock_max_hz=None,
        standards=[
            "ESD HBM ±2000 V (JEDEC JS-001 A114-A)",
            "ESD MM ±200 V (JEDEC A115-A)",
            "ESD CDM ±1000 V (JEDEC C101)",
            "Latch-up >100 mA (JESD 78 Class II)",
        ],
        pins=build_pins(
            src(pn, f"{pn}.kicad_sym"),
            types={"A": "input", "B": "input", "Y": "output",
                   "VCC": "power", "GND": "ground"},
        ),
        footprint=Footprint(
            name="SOT65P210X110-5N",
            package_class="SC-70-5 (DCK)",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.65,
            size_mm=(2.0, 1.25),
            height_mm=1.1,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=(
            "SN74LVC1G08 family — same single 2-input AND die as the "
            "DBVR factory, in the smaller SC-70-5 package (2.0 x 1.25 "
            "vs 2.9 x 1.6 for SOT-23-5). Pad pitch 0.65 mm (vs 0.95 "
            "for DBV) — less solder volume per joint, lower shock "
            "margin. Acceptable in potted/underfilled Smash assemblies; "
            "use DBVR variant for unfilled high-G surface mounting.\n\n"
            "Key specs (datasheet SCES217Z — same family doc as DBVR):\n"
            "  V_CC operating : 1.65 V to 5.5 V\n"
            "  Input voltage  : up to 5.5 V (5 V tolerant on V_CC=3.3)\n"
            "  Down-translation to V_CC supported\n"
            "  t_pd max       : 3.6 ns @ 3.3 V V_CC\n"
            "  I_CC max       : 10 µA\n"
            "  Output drive   : ±24 mA at 3.3 V\n"
            "  I_off          : supports live insertion, partial power\n"
            "                   down, back-drive protection\n\n"
            "Smash use (legacy hardware-confirm topology — RETIRED; same as\n"
            "DBVR; the ACTIVATE_SET/CONFIRM interlock is firmware GPIOs on the\n"
            "MP25 M33 now, no AND gate). Historical wiring:\n"
            "  Y = ACTIVATE_CONFIRM\n"
            "  A = ACTIVATE_SET   (firmware command from MP25 M33 PE0)\n"
            "  B = COMP_OUT       (TLV3691 piezo comparator output)\n\n"
            "Neither firmware (which controlled A) nor the piezo (which\n"
            "controls B) alone could produce Y — both had to agree, making\n"
            "the AND gate an unforgeable launch confirmation. Kept in the\n"
            "catalog; not instantiated since the interlock moved to firmware.\n\n"
            "Lead-finish note: G4 = TI's Pb-free / NiPdAu marker. The "
            "physical part has no Pb anywhere; assembly with Sn-Pb "
            "solder paste yields a 'mixed-alloy' joint (NiPdAu leads + "
            "Sn63/Pb37 paste) which is better-characterised for shock "
            "than full SAC305. Surface this to sourcing as an assembly-"
            "BOM line, not as a part-pick decision."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ─────────────────────────────────────────────────────────────────────────
# TI CD74HC4514PW — 4-to-16 line decoder/demultiplexer with input latches
# (TSSOP-24 package; superseded the SOIC-24 'M' part to save board area on the
#  Ø34 aft tile — same die/pinout, ~3× smaller footprint, ~½ the height).
#
# Symbol + datasheet ground-truth in parts/sources/CD74HC4514MG4/ (SamacSys zip
# + DS TXII-S-A0003047147-1 → CD74HC4514.pdf); the TSSOP footprint is generated
# in parts/sources/CD74HC4514PW/ (SOP65P640X120-24N.kicad_mod, SamacSys SOP65
# family extended to 24 pins). The aft activation array's sector selector: 4
# address bits (GPIO_EXT_0..3) → one-hot of 16, Y0..Y15 drive 16 select NFETs.
# ─────────────────────────────────────────────────────────────────────────


def add_cd74hc4514pw(design, ref: str, **overrides) -> Chip:
    """TI CD74HC4514PW — high-speed CMOS 4-to-16 line decoder/demux with
    4-bit input latch, V_CC 2..6 V, active-low enable E, active-high
    latch LE, active-high outputs (the 4514; the 4515 is active-low),
    TSSOP-24 (PW package, 7.8×4.4 mm, 1.2 mm tall — vs the SOIC-24 'M' at
    15.4×7.5×2.65 mm). Pinout is identical across packages, so the symbol
    is shared with the MG4 source.

    Aft activation array sector selector. A0..A3 = GPIO_EXT_0..3; the
    selected Y output goes HIGH and drives one DMN6075 low-side gate.
    Powered from BAT_PROT (~3.6-4.2 V): high enough that the ~4 V output
    fully enhances the DMN6075 (whose V_GS(th) runs to 3 V), and low
    enough that HC V_IH (0.7·V_CC ≈ 2.9 V) still reads the 3.3 V GPIO
    address as a valid high. BAT_PROT is eFuse-gated, so the decoder is
    DEAD in shelf/standby — all 16 select NFETs off unless the round is
    armed. In flight: E tied low (always decoding), LE tied high (always
    transparent → outputs track the live address). All 16 outputs Y0..Y15
    drive real sectors (no spare 'no-sector' code), so the safe state is the
    DMP6110 ARM (FIRE_HV gated off); tie ~E high for a hard all-off.

    Truth table (datasheet): LE=1 → outputs follow A0..A3; LE=0 → latched.
    E=0 → selected output active (high for 4514); E=1 → all outputs
    inactive (low)."""
    pn = "CD74HC4514PW"
    src_pn = "CD74HC4514MG4"       # symbol + datasheet (pinout shared across packages)
    fp_pn = "CD74HC4514PW"         # generated TSSOP-24 footprint
    fp_mod = src(fp_pn, "SOP65P640X120-24N.kicad_mod")
    fields = dict(
        manf="Texas Instruments", manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn, value=pn,
        description=(
            "4-to-16 line decoder/demultiplexer with input latches, "
            "V_CC=2..6 V, active-high outputs, TSSOP-24"
        ),
        datasheet=datasheet_ref(src_pn, "CD74HC4514.pdf"),
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None,
        weight_g=None,
        standards=[
            "ESD HBM (JEDEC JS-001)",
            "RoHS", "Pb-Free",
        ],
        eccn=None, itar=None,
        package="TSSOP-24",
        size_mm=(7.8, 4.4),            # TSSOP-24 (PW) nominal body
        height_mm=1.2,
        temp_range_c=(-55, 125),
        voltage_rating_v=7.0,          # V_CC abs max (DS: -0.5..7 V)
        vcc_nominal_v=4.0,             # run from BAT_PROT (~3.6-4.2 V)
        clock_max_hz=None,
        body_material=None, lead_material=None,
        pins=build_pins(
            src(src_pn, f"{src_pn}.kicad_sym"),
            types={
                "A0": "input", "A1": "input", "A2": "input", "A3": "input",
                "~{E}": "input", "~{LE}": "input",
                "VCC": "power", "GND": "ground",
                **{f"Y{i}": "output" for i in range(16)},
            },
            aliases={"~{E}": ["E", "nE", "ENABLE"], "~{LE}": ["LE"]},
            notes={
                "~{E}": "active-low enable; high inhibits all outputs",
                "~{LE}": "active-high transparent latch (high=follow, "
                         "low=hold) per datasheet truth table",
            },
        ),
        footprint=Footprint(
            name="SOP65P640X120-24N",
            package_class="TSSOP-24",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.65,
            size_mm=(7.8, 4.4),
            height_mm=1.2,
            model_3d_path=None,   # no TSSOP .stp sourced yet; export falls back to stock TSSOP
            source="generated",
        ),
        note=(
            "CD74HC4514 (SCHS280) — 4-to-16 decoder/demux + 4-bit input "
            "latch. V_CC 2-6 V; t_pd and drive scale with V_CC. Outputs "
            "active-HIGH (the 4515 is the active-LOW sibling). Smash aft "
            "activation array: A0-A3 = sector address (GPIO_EXT_0..3), "
            "Y0-Y15 → 16 DMN6075 select-NFET gates (full 16-sector array). "
            "Powered from BAT_PROT so it is "
            "dead in shelf/standby and the ~4 V outputs fully drive the "
            "select gates."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
