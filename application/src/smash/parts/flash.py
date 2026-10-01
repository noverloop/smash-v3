"""Flash and DRAM memory factories.

(EEPROM lives in memory.py; this module is for the larger non-volatile
+ volatile memories that need their own page.)
"""

from __future__ import annotations

from smash.state import Chip, Footprint
from smash.parts._artifacts import (
    pads_from_kicad_mod, outline_polygon, build_pins, src, datasheet_ref,
)
from smash.parts._slug import canonical_id


def _namespace_ball_collisions(pins: list, prefix: str = "BALL_") -> list:
    """Prefix pin numbers that collide with another pin's name or alias.

    Required for DDR3-style BGA symbols where ball coords ("A0".."A9")
    collide with logical pin names (address bits A0..A9 on different
    pads). Without namespacing, `chip.pin("A9")` resolves to whichever
    pin matched first — silently wrong. After this helper runs, ball
    coords get prefixed (e.g. ball A9 → `BALL_A9`), so callers can use
    `chip.pin("A9")` for the address bit and `chip.pin("BALL_A9")` for
    the ground pad unambiguously.

    EDA writers (canonical netlist, Allegro, PADS, KiCad netlist) strip
    the prefix when emitting pad numbers — KiCad sees raw "A9".
    """
    names = {p.name for p in pins} | {a for p in pins for a in p.aliases}
    for p in pins:
        if p.num in names:
            p.num = f"{prefix}{p.num}"
    return pins


def _flash_factory(*, manf, pn, ds_name, fp_mod_name, fp_class,
                   description, memory_bits, package,
                   height_mm=None, pitch_mm=None, size_mm=None,
                   p_active_w=None, p_max_w=None,
                   rth_jc_cw=None, tj_max_c=None,
                   note="", manf_pn=None) -> dict:
    """Shared kw dict for flash/DRAM chip factories. Caller passes
    `**_flash_factory(...)` to `design.add_chip`.

    `pn` keys the sources/<pn>/ artifact folder; `manf_pn` is the orderable
    (defaults to pn). They differ when a pin-identical variant reuses another
    orderable's SamacSys lib — e.g. the SST26WF080B (1 MB) built on the
    SST26WF040B/NP lib (same /NP USON die/package/pinout, just more density).

    Per-chip thermal kwargs are passed straight through. Most flash
    and DRAM datasheets do NOT quote ΘJC or a junction-temp limit
    separately — they spec T_C (case temperature) or T_A only. In
    those cases callers pass `None` and the thermal sim falls back to
    the components.md overlay.
    """
    manf_pn = manf_pn or pn
    fp_mod = src(pn, fp_mod_name)
    return dict(
        manf=manf, manf_pn=manf_pn, canonical_id=canonical_id(manf_pn),
        name=manf_pn, value=manf_pn,
        description=description,
        datasheet=datasheet_ref(pn, ds_name),
        package=package,
        temp_range_c=(-40, 85),
        p_active_w=p_active_w,
        p_max_w=p_max_w,
        rth_jc_cw=rth_jc_cw,
        tj_max_c=tj_max_c,
        memory_capacity_bits=memory_bits,
        pins=_namespace_ball_collisions(
            build_pins(src(pn, f"{pn}.kicad_sym"))
        ),
        footprint=Footprint(
            name=fp_mod_name.replace(".kicad_mod", ""),
            package_class=fp_class,
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=pitch_mm, size_mm=size_mm, height_mm=height_mm,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=note,
    )


def add_s25hl512tfamhi010(design, ref: str, **overrides) -> Chip:
    """Infineon (formerly Cypress) S25HL512TFAMHI010 — 512-Mbit
    QSPI/octal HyperRAM-class NOR flash, SOIC-16 (300mil)."""
    fields = _flash_factory(
        manf="Infineon",
        pn="S25HL512TFAMHI010",
        ds_name="S25HL512TDPMHI010.pdf",       # Research/ has the TDP variant
        fp_mod_name="SOIC127P1030X265-16N.kicad_mod",
        fp_class="SOIC-16 (300mil)",
        description=(
            "512 Mbit (64 MB) NOR flash, HyperRAM-compatible serial "
            "interface, SOIC-16 wide"
        ),
        memory_bits=512_000_000,
        package="SOIC-16 W (300mil)",
        pitch_mm=1.27,
        # ── thermal (Cypress/Infineon DS 002-23880 Rev *A) ───────────
        # Research/ has the product-brief PDF only — no thermal R, no
        # absolute-max Tj. We use the typical-current-consumption
        # table from p2 against VCC=3.0V (HL = 3.0V variant). Industrial
        # temp grade gives -40 to +85 °C Top, no Tj quoted.
        p_active_w=0.159,                   # 53 mA × 3.0V — SDR Read 166 MHz (DS p2)
        p_max_w=0.165,                      # 50 mA × 3.3V — Program/Erase, worst-case Vcc (DS p2)
        rth_jc_cw=25.0,                     # *estimate (NOT DS) — SOIC-16 W
                                            # package-class typical (300mil
                                            # body, leaded → lossy thermal path)
        tj_max_c=125.0,                     # *estimate (NOT DS) — industrial
                                            # NOR flash Si junction limit; DS
                                            # quotes only Top max 85 °C
        note=(
            "S25HL512T = SEMPER HyperRAM 512-Mbit NOR flash, octal "
            "interface, 1.8 V V_CC. The 'TF' family suffix indicates "
            "Industrial temp range and AEC-Q100 qualification. The "
            "Research/ datasheet filename is `S25HL512TDPMHI010.pdf` "
            "(TDP variant) — verify on next datasheet refresh; the "
            "SamacSys part is `S25HL512TFAMHI010` (TFA suffix)."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_sst26wf080b(design, ref: str, **overrides) -> Chip:
    """Microchip SST26WF080B — 8 Mbit (1 MB), 1.8 V, x1/x2/x4 SQI NOR flash,
    8-contact USON (2×3 mm). The AWR1843AOP radar's boot flash (used in plain
    single-bit SPI: CE#/SCK/SI/SO, WP#/HOLD# tied off). 1 MB comfortably holds
    the radar code image (~≤832 KB program). Datasheet Microchip DS20005283C
    (`20005283C.pdf`, covers SST26WF040B/080B).

    From its own SamacSys lib (`sources/SST26WF080BT-104I_NP/`). The SamacSys
    folder uses `_NP`; the orderable is `…/NP`, so `manf_pn` carries the slash
    form. The 9-pin symbol names the two grounds VSS_1 (pin 4) and VSS_2 (pin 9
    = the exposed pad) — both tie to GND.
    """
    fields = _flash_factory(
        manf="Microchip",
        pn="SST26WF080BT-104I_NP",          # SamacSys lib folder (uses _; orderable uses /)
        manf_pn="SST26WF080BT-104I/NP",     # orderable: 8 Mbit (1 MB), /NP USON-8
        ds_name="20005283C.pdf",
        fp_mod_name="SST26WF080BT104INP.kicad_mod",   # /NP USON-8 (2×3 mm), 8 pads + EP
        fp_class="USON-8 (2×3 mm)",
        description=(
            "8 Mbit (1 MB) 1.8 V SQI NOR flash (x1/x2/x4), USON-8 2×3 mm — "
            "AWR1843AOP boot flash (wired single-SPI)"
        ),
        memory_bits=8_000_000,
        package="USON-8 (2×3 mm)",
        pitch_mm=0.5,
        size_mm=(2.0, 3.0),                 # USON-8 body — needed so the nose_cap cutout includes the flash
        # ── thermal (DS20005283C p1) — NOR DS quotes no ΘJC/Tj ───────────────
        p_active_w=0.027,                   # 15 mA active read @104 MHz × 1.8 V
        p_max_w=0.045,                      # ~25 mA program/erase × 1.8 V (est)
        note=(
            "Microchip SST26WF080B (8 Mbit/1 MB, 1.8 V, SQI). Used SINGLE-bit "
            "SPI for radar boot — the AWR1843AOP boots from this flash during "
            "ground staging (Chambered bore-look pulses + Ready); not accessed "
            "after launch (resume from RAM). Holds the encrypted radar image "
            "(MP25-provisioned). x2/x4 available but unused (single suffices; "
            "boot latency is ground-side, not flight-critical).\n\n"
            "Pin-identical to the SST26WF040B (4 Mbit) sibling. Grounds VSS_1 "
            "(pin 4) + VSS_2 (pin 9 = exposed pad) both tie to GND."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_sst26vf080a(design, ref: str, **overrides) -> Chip:
    """Microchip SST26VF080A — 8 Mbit (1 MB), **2.7-3.6 V**, x1/x2/x4 SQI NOR
    flash, 8-contact WDFN (6x5 mm, SON127P600X500X80-9N). The 3.3 V sibling of
    the SST26WF080B — swapped in when the AWR1843AOP's VIOIN domain moved to
    3.3 V (the TI EVM configuration): the QSPI bus rides VIOIN, so the boot
    flash must match. Datasheet Microchip DS20006203C (`20006203C.pdf`, also
    in Research/): 2.7-3.6 V = 104 MHz; same SQI command family.

    From its own SamacSys lib (`sources/SST26VF080A-104I_MF/`). Pin map is
    1:1 with the WF (CE#/SO/WP#/VSS/SI/SCK/pin7/VDD + EP) — pin 7 gains a
    RESET# alternate (RESET#/HOLD#/SIO3); tied high = inactive, identical
    behavior to the WF's HOLD#."""
    fields = _flash_factory(
        manf="Microchip",
        pn="SST26VF080A-104I_MF",           # SamacSys lib folder (uses _; orderable uses /)
        manf_pn="SST26VF080A-104I/MF",      # orderable: 8 Mbit (1 MB), /MF WDFN-8
        ds_name="20006203C.pdf",
        fp_mod_name="SON127P600X500X80-9N-D.kicad_mod",   # WDFN-8 (6x5 mm), 8 pads + EP
        fp_class="WDFN-8 (6x5 mm)",
        description=(
            "8 Mbit (1 MB) 2.7-3.6 V SQI NOR flash (x1/x2/x4), WDFN-8 "
            "6x5 mm — AWR1843AOP boot flash (wired single-SPI, 3.3 V "
            "VIOIN domain)"
        ),
        memory_bits=8_000_000,
        package="WDFN-8 (6x5 mm)",
        pitch_mm=1.27,
        size_mm=(6.0, 5.0),                 # WDFN-8 body — sizes a top-face nose_cap cutout / bottom spacer cavity
        # ── thermal (DS20006203C) — NOR DS quotes no ΘJC/Tj ─────────────────
        p_active_w=0.050,                   # 15 mA active read @104 MHz x 3.3 V
        p_max_w=0.083,                      # ~25 mA program/erase x 3.3 V (est)
        note=(
            "Microchip SST26VF080A (8 Mbit/1 MB, 2.7-3.6 V, SQI). Used "
            "SINGLE-bit SPI for radar boot — the AWR1843AOP boots from this "
            "flash during ground staging (Chambered bore-look pulses + "
            "Ready); not accessed after launch (resume from RAM). Holds the "
            "encrypted radar image (MP25-provisioned). x2/x4 available but "
            "unused.\n\n"
            "Replaced the 1.8 V SST26WF080B when VIOIN moved to 3.3 V. Pin 7 "
            "= RESET#/HOLD#/SIO3 — tied high (inactive). VSS (pin 4) + EP "
            "(pin 9) both tie to GND."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_mt29f4g01abafdwb_it_f(design, ref: str, **overrides) -> Chip:
    """Micron MT29F4G01ABAFDWB-IT/F — 4 Gbit (512 MB) serial SPI NAND
    flash, 8-pad WSON, industrial temp -40..+85 °C."""
    fields = _flash_factory(
        manf="Micron",
        pn="MT29F4G01ABAFDWB-IT_F",
        ds_name="MT29F4G01ABAFDWB-IT_F.pdf",
        fp_mod_name="SON127P800X600X65-8N.kicad_mod",
        fp_class="WSON-8 (6×8 mm)",
        description="4 Gbit Serial NAND flash, SPI interface, WSON-8",
        memory_bits=4 * 1024 * 1024 * 1024,    # 4 Gbit
        package="WSON-8 (6×8 mm)",
        pitch_mm=1.27,
        # ── thermal (Micron product page only, no full DS in Research/) ──
        # The Research/ file is a Micron product page (not the full
        # datasheet) — no current consumption, no thermal R, no Tj
        # quoted. Industrial Op temp = -40 to +85 °C only. Falls back
        # to components.md overlay for thermal numbers.
        p_active_w=None,                    # not in DS — overlay applies
        p_max_w=None,                       # not in DS — overlay applies
        rth_jc_cw=None,                     # not in DS
        tj_max_c=None,                      # not in DS; Top max = 85°C (industrial)
        note=(
            "Micron MT29F4G01ABA family — 4 Gbit SPI NAND, "
            "industrial temperature, 1-bit/page ECC required. "
            "8-pad WSON package, 6×8 mm body."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_mt29f4g01abafd12_aat_f(design, ref: str, **overrides) -> Chip:
    """Micron MT29F4G01ABAFD12-AAT/F — 4 Gbit SPI NAND flash,
    automotive-qualified (AEC-Q100), 24-ball VFBGA."""
    fields = _flash_factory(
        manf="Micron",
        pn="MT29F4G01ABAFD12-AAT_F",
        ds_name="MT29F4G01ABAFDWB-IT_F.pdf",   # shared family DS
        fp_mod_name="BGA24C100P5X5_600X800X120.kicad_mod",
        fp_class="VFBGA-24 (6×8 mm)",
        description=(
            "4 Gbit Serial NAND flash, SPI, AEC-Q100 automotive, "
            "VFBGA-24"
        ),
        memory_bits=4 * 1024 * 1024 * 1024,
        package="VFBGA-24 (6×8 mm)",
        pitch_mm=1.0,
        # ── thermal — same DS reference / lack thereof as the WSON
        # sibling above. Automotive variant probably has tighter
        # specs in the full DS, but Research/ has only the product
        # page. Overlay applies.
        p_active_w=None,
        p_max_w=None,
        rth_jc_cw=None,
        tj_max_c=None,
        note=(
            "Automotive (AAT) variant of the MT29F4G01ABA family. "
            "VFBGA-24 package, 1.0 mm pitch, 5×5 ball matrix."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_mt29f8g08abacah4_it_c_tr(design, ref: str, **overrides) -> Chip:
    """Micron MT29F8G08ABACAH4-IT:C — 8 Gbit parallel NAND flash,
    63-ball VFBGA, industrial."""
    fields = _flash_factory(
        manf="Micron",
        pn="MT29F8G08ABACAH4-IT_C_TR",
        ds_name="MT29F8G08ABACAH4-IT_C.pdf",
        fp_mod_name="BGA63C80P10X12_900X1100X100.kicad_mod",
        fp_class="VFBGA-63 (9×11 mm)",
        description=(
            "8 Gbit parallel NAND flash, x8 async/sync interface, "
            "VFBGA-63"
        ),
        memory_bits=8 * 1024 * 1024 * 1024,
        package="VFBGA-63 (9×11 mm)",
        pitch_mm=0.8,
        # ── thermal (Micron MT29F8G08ABA datasheet) ──────────────────
        # DC Characteristics, Table 27 (page ~102) gives ICC1 (read),
        # ICC2 (program), ICC3 (erase) = 25 mA typ / 35 mA max with
        # Vcc=3.3V. No ΘJC, no Tj specified — DS only spec'd T_A
        # (industrial -40 to +85 °C). Storage T_STG -65 to +150 °C.
        p_active_w=0.083,                   # 25 mA × 3.3V — sequential READ typ (DS Tab 27)
        p_max_w=0.116,                      # 35 mA × 3.3V — program/erase max (DS Tab 27)
        rth_jc_cw=5.0,                      # *estimate (NOT DS) — VFBGA-63 BGA-
                                            # class typical (good thermal path
                                            # through die-attach to PCB)
        tj_max_c=95.0,                      # *estimate (NOT DS) — Micron NAND
                                            # family uses T_C not T_J; treating
                                            # T_C max 95 °C as Tj limit (DS p102)
        note=(
            "Micron MT29F8G08ABA family — 8 Gbit parallel x8 NAND. "
            "Async (timing mode 0) up to 50 ns, ONFI sync mode "
            "available. Industrial temp."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_mt29f8g08abacawp_it_c(design, ref: str, **overrides) -> Chip:
    """Micron MT29F8G08ABACAWP-IT:C — 8 Gbit parallel NAND flash,
    48-pin TSOP-48 (legacy)."""
    fields = _flash_factory(
        manf="Micron",
        pn="MT29F8G08ABACAWP-IT_C",
        ds_name="MT29F8G08ABACAH4-IT_C.pdf",   # shared family DS
        fp_mod_name="SOP50P2000X120-48N.kicad_mod",
        fp_class="TSOP-48",
        description=(
            "8 Gbit parallel NAND flash, x8 async/sync, TSOP-48"
        ),
        memory_bits=8 * 1024 * 1024 * 1024,
        package="TSOP-48",
        pitch_mm=0.5,
        # ── thermal — same die as the VFBGA-63 variant above; ICC
        # values from DS Tab 27 apply identically.
        p_active_w=0.083,                   # 25 mA × 3.3V — sequential READ typ (DS Tab 27)
        p_max_w=0.116,                      # 35 mA × 3.3V — program/erase max (DS Tab 27)
        rth_jc_cw=None,                     # not quoted; TSOP-48 typically ~50-80 °C/W (overlay applies)
        tj_max_c=None,                      # not quoted; Top max = 85°C (industrial)
        note=(
            "TSOP-48 (legacy) package variant of MT29F8G08ABA. "
            "Prefer the VFBGA-63 variant for new designs — smaller "
            "footprint, better signal integrity. The TSOP-48 is kept "
            "for legacy boards."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_mt41k256m16tw_107_ptr(design, ref: str, **overrides) -> Chip:
    """Micron MT41K256M16TW-107:P TR — 4 Gbit DDR3L SDRAM (256M × 16),
    933 MT/s, VFBGA-96. (Alternate to AS4C512M16D3LC.)"""
    fields = _flash_factory(
        manf="Micron",
        pn="MT41K256M16TW-107_PTR",
        ds_name="MT41K256M16TW-107_P_TR.pdf",
        fp_mod_name="BGA96C80P9X16_800X1400X120.kicad_mod",
        fp_class="VFBGA-96 (8×14 mm)",
        description=(
            "4 Gbit DDR3L SDRAM (256M × 16), DDR3-1866 (-107E speed "
            "grade), 1.35 V, VFBGA-96"
        ),
        memory_bits=4 * 1024 * 1024 * 1024,
        package="VFBGA-96 (8×14 mm)",
        pitch_mm=0.8,
        # ── thermal (Micron MT41K family DS, Table 22 Rev P, x16 -107) ─
        # IDD values are quoted at Vdd=1.35V for the L variant. Active
        # standby (IDD3N) ≈ 23 mA, burst write (IDD4W) ≈ 130 mA peak,
        # burst refresh (IDD5B) ≈ 156 mA peak — peak is the worst we
        # ever sustain (refresh) so use that for p_max. Micron specifies
        # T_C max = 95 °C (industrial) — DDR3 datasheets don't spec
        # Tj separately; use T_C as the thermal-headroom limit.
        p_active_w=0.031,                   # 23 mA × 1.35V — active standby IDD3N (DS Tab 22 p46)
        p_max_w=0.211,                      # 156 mA × 1.35V — burst refresh IDD5B (DS Tab 22 p46)
        rth_jc_cw=None,                     # not quoted in Micron DDR3 DS
        tj_max_c=95.0,                      # T_C max industrial; DS uses T_C not Tj (DS p163)
        note=(
            "Micron MT41K = DDR3L (low-voltage 1.35 V) family. "
            "-107 speed grade = 933 MHz / DDR3-1866. The 256M16TW "
            "variant is 256M × 16, total 4 Gbit. **This part is the "
            "secondary option to AS4C512M16D3LC-12BIN** which is "
            "currently in the design (8 Gbit, larger). Switch only "
            "if 4 Gbit suffices."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_mx60lf8g28ad_xki_t(design, ref: str, **overrides) -> Chip:
    """Macronix MX60LF8G28AD-XKI/T — 3 V, 8 Gbit SLC NAND flash,
    x8 async ONFI 1.0 interface, 63-ball VFBGA (9×11×1.0 mm).

    The SamacSys archive doesn't carry this part, so the pin map is
    transcribed by hand from datasheet `MX60LF_full_datasheet.pdf`
    Section 3 (PIN CONFIGURATIONS — 63-ball 9mmx11mm VFBGA). The
    JEDEC/ONFI VFBGA-63 ball positions are identical to the Micron
    MT29F8G08ABACAH4-IT/C-TR (same package class), so we reuse that
    SamacSys-generated footprint here.
    """
    from smash.state import Pin

    pn = "MX60LF8G28AD-XKI-T"
    # JEDEC/ONFI VFBGA-63 ball-position footprint, identical to the
    # Micron MT29F8G08ABACAH4 — sourced from that part's directory.
    fp_mod = src("MT29F8G08ABACAH4-IT_C_TR",
                 "BGA63C80P10X12_900X1100X100.kicad_mod")

    # Pin map transcribed from MX60LF datasheet Section 3 ball diagram.
    # Layout: outer 4-corner balls are NC (A1,A2,A9,A10 / B1,B9,B10 /
    # L1,L2,L9,L10 / M1,M2,M9,M10). Functional balls in inner block
    # (rows C-K × cols 3-8). Datasheet Note 1: some "NC" balls might
    # not be internally connected but should be tied to power/ground
    # for ONFI compatibility.
    pin_map = {
        # Row C (control signals)
        "C3":  ("WP\\#",   "input"),   # Write Protect, active low
        "C4":  ("ALE",     "input"),
        "C5":  ("Vss",     "ground"),
        "C6":  ("CE\\#",   "input"),   # Chip Enable, active low
        "C7":  ("WE\\#",   "input"),
        "C8":  ("R/B\\#",  "output"),  # Ready/Busy, open-drain
        # Row D
        "D3":  ("Vcc",     "power"),
        "D4":  ("RE\\#",   "input"),
        "D5":  ("CLE",     "input"),
        "D6":  ("NC",      "nc"),
        "D7":  ("NC",      "nc"),
        "D8":  ("NC",      "nc"),
        # Row E — all NC
        **{f"E{c}": ("NC", "nc") for c in "345678"},
        # Row F — NC except F7=Vss (Note 1 / ONFI compatibility)
        "F3":  ("NC",      "nc"),
        "F4":  ("NC",      "nc"),
        "F5":  ("NC",      "nc"),
        "F6":  ("NC",      "nc"),
        "F7":  ("Vss",     "ground"),
        "F8":  ("NC",      "nc"),
        # Row G
        "G3":  ("NC",      "nc"),
        "G4":  ("Vcc",     "power"),
        "G5":  ("DNU",     "reserved"),  # Do Not Use
        "G6":  ("NC",      "nc"),
        "G7":  ("NC",      "nc"),
        "G8":  ("NC",      "nc"),
        # Row H
        "H3":  ("NC",      "nc"),
        "H4":  ("I/O0",    "io"),
        "H5":  ("NC",      "nc"),
        "H6":  ("NC",      "nc"),
        "H7":  ("NC",      "nc"),
        "H8":  ("Vcc",     "power"),
        # Row J
        "J3":  ("NC",      "nc"),
        "J4":  ("I/O1",    "io"),
        "J5":  ("NC",      "nc"),
        "J6":  ("Vcc",     "power"),
        "J7":  ("I/O5",    "io"),
        "J8":  ("I/O7",    "io"),
        # Row K
        "K3":  ("Vss",     "ground"),
        "K4":  ("I/O2",    "io"),
        "K5":  ("I/O3",    "io"),
        "K6":  ("I/O4",    "io"),
        "K7":  ("I/O6",    "io"),
        "K8":  ("Vss",     "ground"),
        # Outer-corner NC balls (orientation key + mechanical balls)
        **{b: ("NC", "nc") for b in
           ["A1", "A2", "A9", "A10",
            "B1", "B9", "B10",
            "L1", "L2", "L9", "L10",
            "M1", "M2", "M9", "M10"]},
    }

    pads = pads_from_kicad_mod(fp_mod)
    pad_nums = {p.num for p in pads}
    pin_nums = set(pin_map)
    if pin_nums != pad_nums:
        raise ValueError(
            f"{pn}: pin/pad mismatch. Missing from map: "
            f"{pad_nums - pin_nums}; extra: {pin_nums - pad_nums}")

    pins = []
    for ball, (name, ptype) in pin_map.items():
        aliases = []
        if "\\#" in name:
            # Add un-bar-noted alias for ergonomic lookup
            aliases.append(name.replace("\\#", "#"))
            aliases.append(name.replace("\\#", ""))
        pins.append(Pin(
            num=ball, name=name, type=ptype, aliases=aliases,
            note=("Per datasheet Note 1: tie to power/ground for ONFI compat"
                  if ptype == "nc" and ball.startswith(("F", "G")) else None),
        ))

    fields = dict(
        manf="Macronix", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "8 Gbit SLC NAND flash, x8 async ONFI 1.0, 3 V supply, "
            "63-ball VFBGA (9×11×1.0 mm), industrial -40..+85 °C"
        ),
        datasheet=datasheet_ref(pn, "MX60LF_full_datasheet.pdf"),
        package="VFBGA-63 (9×11×1.0 mm)",
        size_mm=(9.0, 11.0),
        height_mm=1.0,
        temp_range_c=(-40, 85),
        memory_capacity_bits=8 * 1024 * 1024 * 1024,
        vcc_nominal_v=3.0,           # 2.7-3.6 V range, 3.0 V typ
        voltage_rating_v=3.6,        # V_CC max per datasheet
        pins=pins,
        footprint=Footprint(
            name="BGA63C80P10X12_900X1100X100",
            package_class="VFBGA-63 (ONFI standard)",
            pads=pads,
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.8, size_mm=(9.0, 11.0), height_mm=1.0,
            model_3d_path=None,      # no STEP for MX60LF — use Micron's via reuse
            source=("reused from Micron MT29F8G08ABACAH4 SamacSys archive "
                    "— same JEDEC/ONFI VFBGA-63 package"),
            note=("Footprint shared with the Micron MT29F8G08 family: "
                  "same JEDEC/ONFI VFBGA-63 ball pattern (12×10 grid "
                  "with corner cluster + central 8×6 block). 63 balls "
                  "total. Coverage verified against MX60LF datasheet "
                  "ball diagram."),
        ),
        note=(
            "Macronix MX60LF8G28AD-XKI/T — 8 Gbit SLC NAND, 3 V single "
            "supply (2.7-3.6 V), x8 async ONFI 1.0. Stacked dual 4-Gbit "
            "die. Page size 4096+256 byte, block size 256K+16K byte, "
            "1024 blocks/plane × 2 planes/die.\n\n"
            "Pin map transcribed verbatim from datasheet Section 3 "
            "ball diagram. Footprint REUSED from the Micron "
            "MT29F8G08ABACAH4 SamacSys archive — both parts use the "
            "JEDEC/ONFI standard VFBGA-63 (9×11×1.0 mm, 0.8 mm pitch). "
            "Coverage verified: every datasheet ball coord maps to a "
            "footprint pad and vice versa.\n\n"
            "Key features (datasheet §1):\n"
            "  - 25 µs latency array-to-register\n"
            "  - 20 ns sequential read\n"
            "  - 320 µs typ page program time\n"
            "  - 4 ms typ block erase time\n"
            "  - Endurance: 60K cycles typ (with 8-bit ECC per 512+32 B)\n"
            "  - Retention: 10 years\n"
            "  - Block 0-7 valid with ECC at shipping\n"
            "  - Hardware WP# protection, Unique ID, Secure OTP\n\n"
            "ONFI compatibility (Note 1): some NC pins should be tied "
            "to power/ground for cross-vendor compatibility — see "
            "datasheet for exact recommendations."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_as4c512m16d3lc_12bin(design, ref: str, **overrides) -> Chip:
    """Alliance AS4C512M16D3LC-12BIN — 8 Gbit DDR3 SDRAM (512M × 16),
    1600 MT/s (-12 speed grade), industrial -40..+95 °C, VFBGA-96.
    This is the DDR3 currently in the Smash design."""
    pn = "AS4C512M16D3LC-12BIN"
    fp_mod = src(pn, "BGA96C80P9X16_900X1300X120.kicad_mod")

    # DDR3 address-bit pin names ("A0".."A15") collide with VFBGA ball
    # coords ("A1".."A9"). See `_namespace_ball_collisions` for the
    # full rationale; same collision class hits every DDR3 SamacSys
    # symbol with this naming convention.
    raw_pins = _namespace_ball_collisions(
        build_pins(src(pn, f"{pn}.kicad_sym"))
    )

    fields = dict(
        manf="Alliance Memory", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "8 Gbit DDR3 SDRAM (512M × 16), DDR3-1600 (-12 speed), "
            "1.5 V, industrial -40..+95 °C, VFBGA-96"
        ),
        datasheet=datasheet_ref(pn, "AS4C512M16D3LC.pdf"),
        package="VFBGA-96 (9×13 mm)",
        size_mm=(9.0, 13.0),
        temp_range_c=(-40, 95),
        memory_capacity_bits=8 * 1024 * 1024 * 1024,
        vcc_nominal_v=1.5,
        pins=raw_pins,
        footprint=Footprint(
            name="BGA96C80P9X16_900X1300X120",
            package_class="VFBGA-96",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.8, size_mm=(9.0, 13.0), height_mm=1.2,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=(
            "Alliance Memory AS4C512M16D3LC — 8 Gbit DDR3 SDRAM, "
            "currently the DDR3 chip placed in the Smash design "
            "(per system.py audit). -12 speed grade = DDR3-1600 "
            "(800 MHz). 'L' = industrial temp, 'C' = commercial Vdd. "
            "Routing follows AN5724 (STM32MP25 DDR3 guidelines). "
            "Datasheet (Alliance rev 1.0) lives in the part's sources/ dir."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_ktdm4g4b626bgieat(design, ref: str, **overrides) -> Chip:
    """SMARTsemi KTDM4G4B626BGIEAT — 4 Gbit DDR4 SDRAM (256M × 16),
    DDR4-2666 (1333 MHz), industrial -40..+95 °C, 96-ball FBGA (7.5×13 mm),
    1.2 V VDD/VDDQ + ~2.5 V VPP. The DDR4 replacement for the AS4C DDR3L."""
    pn = "KTDM4G4B626BGIEAT"
    fp_mod = src(pn, "BGA96C80P9X16_750X1300X100.kicad_mod")

    # DDR4 address-bit names ("A0".."A13") collide with VFBGA ball coords
    # ("A1".."A9") — same class as the DDR3 part; namespace the colliding
    # balls with the "BALL_" prefix (stripped on EDA export).
    raw_pins = _namespace_ball_collisions(
        build_pins(src(pn, f"{pn}.kicad_sym"))
    )

    fields = dict(
        manf="SMARTsemi", manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn, value=pn,
        description=(
            "4 Gbit DDR4 SDRAM (256M × 16), DDR4-2666 (1333 MHz), "
            "1.2 V + VPP 2.5 V, industrial -40..+95 °C, FBGA-96 (7.5×13 mm)"
        ),
        datasheet=datasheet_ref(pn, f"{pn}.pdf"),
        package="FBGA-96 (7.5×13 mm)",
        size_mm=(7.5, 13.0),
        temp_range_c=(-40, 95),
        memory_capacity_bits=4 * 1024 * 1024 * 1024,
        vcc_nominal_v=1.2,
        pins=raw_pins,
        footprint=Footprint(
            name="BGA96C80P9X16_750X1300X100",
            package_class="FBGA-96",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.8, size_mm=(7.5, 13.0), height_mm=1.0,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=(
            "SMARTsemi KTDM4G4B626BGIEAT — 4 Gbit DDR4 SDRAM, the DDR4 "
            "replacement for the AS4C DDR3L (FC consolidation onto the MP25 "
            "Cortex-M33). '4G'=4 Gbit, '4'=DDR4, 'B'=1.2 V, '6'=x16, "
            "'26'=DDR4-2666, 'I'=industrial. Needs VPP 2.375-2.75 V in "
            "addition to 1.2 V VDD/VDDQ; VREFDQ is internal (no external "
            "VREFDQ divider). Routing per ST AN5724 DDR4 guidelines. "
            "Datasheet (SMARTsemi rev 1.0) in the part's sources/ dir."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
