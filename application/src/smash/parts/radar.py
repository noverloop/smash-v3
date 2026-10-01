"""Automotive radar SoC factories — TI mmWave family."""

from __future__ import annotations

import json
import pathlib

from smash.state import Chip, Footprint, Pin
from smash.parts._artifacts import (
    pads_from_kicad_mod, outline_polygon, build_pins, src, datasheet_ref,
)
from smash.parts._slug import canonical_id


def _radar(*, pn, ds_name, fp_mod_name, fp_class, package, description,
           ball_count, size_mm, pitch_mm, note,
           p_active_w=None, p_max_w=None,
           rth_jc_cw=None, tj_max_c=None, height_mm=1.2, manf_pn=None) -> dict:
    # `pn` keys the sources/<pn>/ artifact folder (symbol/footprint/3D); `manf_pn`
    # is the orderable, defaulting to pn. They differ when a pin-identical variant
    # reuses another orderable's SamacSys lib — e.g. the Secure AWR1843AOP variant
    # built on the General-variant lib (same ALP die/package/pinout).
    manf_pn = manf_pn or pn
    fp_mod = src(pn, fp_mod_name)
    return dict(
        manf="Texas Instruments", manf_pn=manf_pn, canonical_id=canonical_id(manf_pn),
        name=manf_pn, value=manf_pn,
        description=description,
        datasheet=datasheet_ref(pn, ds_name) if ds_name else None,
        package=package,
        size_mm=size_mm, height_mm=height_mm,
        temp_range_c=(-40, 125),     # AEC-Q100 G2 typical
        p_active_w=p_active_w,
        p_max_w=p_max_w,
        rth_jc_cw=rth_jc_cw,
        tj_max_c=tj_max_c,
        standards=["AEC-Q100 Grade 2"],
        pins=build_pins(src(pn, f"{pn}.kicad_sym")),
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


def add_iwr1843arqgalpr(design, ref: str, **overrides) -> Chip:
    """TI IWR1843ARQGALPR — 76-81 GHz industrial single-chip mmWave
    radar sensor, 3 TX × 4 RX, integrated DSP + Cortex-R4F + ARM,
    180-ball FCBGA."""
    fields = _radar(
        pn="IWR1843ARQGALP",
        ds_name="IWR1843ARQGALPR.pdf",
        fp_mod_name="BGA180C80P18X18_1500X1500X96.kicad_mod",
        fp_class="FCBGA-180",
        package="FCBGA-180 (15×15 mm)",
        description=(
            "76-81 GHz mmWave radar, 3 TX × 4 RX, DSP + R4F + Cortex-M4, "
            "FCBGA-180"
        ),
        ball_count=180,
        size_mm=(15.0, 15.0),
        pitch_mm=0.8,
        # ── thermal (TI SWRS228B Sep 2024) ───────────────────────────
        # Datasheet table 7-3 is current-rated maxima; table 7-4 is
        # measured average power per use case. Typical = "Regular mode
        # 6.4 MSps, 25% duty cycle, 1 TX 4 RX, DSP+HWA active" → 1.29 W.
        # Max = same DS table, 50% duty cycle, 3 TX 4 RX → 2.08 W.
        # Note: IWR1843 op'l Tj = -40 to +105°C, abs max Tj = 125°C.
        p_active_w=1.29,                    # 1TX 4RX 25% duty regular mode, DS Tab 7-4 p27
        p_max_w=2.08,                       # 3TX 4RX 50% duty regular mode, DS Tab 7-4 p27
        rth_jc_cw=4.2,                      # FCBGA161 RθJC, DS §7.9 p28
        tj_max_c=125.0,                     # abs max Tj, DS Tab 7-2 p25 (op'l limit 105°C)
        note=(
            "TI IWR1843 = industrial single-chip mmWave radar SoC. "
            "3 TX antennas + 4 RX antennas (MIMO 12-channel virtual "
            "array). Integrated C674x DSP for radar processing, "
            "Cortex-R4F for radar control, Cortex-M4 for user app. "
            "Smash uses this part as the primary radar sensor."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_awr1843aop(design, ref: str, *, secure: bool = False, **overrides) -> Chip:
    """TI AWR1843AOP — automotive 76-81 GHz single-chip FMCW radar SoC with
    **Antennas-On-Package (AoP)**: 3 TX + 4 RX patch antennas integrated on the
    180-ball ALP package (15×15 mm, 0.8 mm pitch). Datasheet **SWRS236C**
    (`awr1843aop.pdf`).

    Two pin-IDENTICAL security tiers (same ALP die/package/pinout; only the OTP
    security eFuse config differs — datasheet Fig 10-1 P/N "Security" field
    G=General / S=Secure), selected by `secure`:
      • secure=False (default) → **AWR1843ARBGALPQ1** (General) — NO secure
        boot. For **prototypes / bring-up**: easier sourcing, plaintext bundles
        OK during dev (firmware_lifecycle.md bring-up state: secure boot off).
      • secure=True → **AWR1843ARBSALPQ1** (Secure) — authenticated + encrypted
        boot (AES-256/SHA/PKA, customer keys in OTP). REQUIRED for **fielded /
        production** units: the AWR1843AOP boots from external SPI flash (no
        host-SPI-to-RAM boot — that's an xWR2xxx feature), so without secure
        boot the firmware sits in flash as extractable PLAINTEXT. IWR secure
        equivalent: IWR1843ARBSALP.
    Both reuse the General-variant SamacSys lib (`sources/AWR1843ARBGALPQ1/`) —
    only the orderable `manf_pn` changes (same pattern as the AWR2944 orderables
    sharing one footprint).

    AoP is the headline architectural fact: the antenna is *on the package*,
    radiating away from the PCB. There are NO discrete TX/RX antenna balls and
    NO RF on the laminate (like the AWR2E44P, opposite of the AWR2944) — so the
    nose_cap becomes an **RF-transparent radome over the package face**, NOT a
    machined waveguide/horn block. The radar board sees only DC + digital, so
    plain FR4 is fine.

    Power rails differ from the AWR2944 family: core `VDDIN`, **1.3 V**
    `VIN_13RF1/2` (RF), `VIN_SRAM`, 1.8 V `VIN_18BB/18VCO/18CLK`, and the
    `VIOIN` I/O domain (1.8 or 3.3 V). Built-in LDO network. No gigabit
    RGMII — the host data path is CAN / 2×SPI / 2×UART / 2-lane LVDS
    (raw ADC). Wired by `build_radar_module_awr1843aop`.
    """
    fields = _radar(
        pn="AWR1843ARBGALPQ1",              # file-key: the (pin-identical) SamacSys lib folder
        manf_pn="AWR1843ARBSALPQ1" if secure else "AWR1843ARBGALPQ1",  # S=Secure (prod) / G=General (proto)
        ds_name="awr1843aop.pdf",
        fp_mod_name="BGA180C80P18X18_1500X1500X96.kicad_mod",
        fp_class="FCBGA-180",
        package="FCBGA-180 AoP (15×15 mm)",
        description=(
            "Automotive 76-81 GHz AoP radar (AWR1843AOP), 3 TX × 4 RX "
            "antennas-on-package, C674x DSP + Cortex-R4F + 2 MB RAM, "
            "FCBGA-180 ALP 15×15 mm"
        ),
        ball_count=180,
        size_mm=(15.0, 15.0),
        pitch_mm=0.8,
        height_mm=0.9,                      # ALP package max height, from the SamacSys 3D model bbox (verify vs SWRS236C mech)
        # ── thermal ──────────────────────────────────────────────────
        # SWRS236C-specific power/RθJC table not yet transcribed; values
        # estimated from the same-die-class IWR1843 family (SWRS228B /
        # SWRS317 AoP, identical 76-81 GHz front-end + C674x+R4F). AoP
        # dissipates slightly more than the bare FCBGA-161 because the
        # PA output drives on-package radiators. Refresh vs SWRS236C §7.
        p_active_w=1.3,                     # est. 1TX 4RX 25% duty, DSP+HWA (≈ IWR1843)
        p_max_w=2.1,                        # est. 3TX 4RX 50% duty, DSP+HWA active
        rth_jc_cw=4.2,                      # est. from IWR1843 §7.9 (same family)
        tj_max_c=125.0,                     # AEC-Q100 abs max Tj (op'l limit per DS)
        note=(
            "TI AWR1843AOP (automotive, SWRS236C) — Antennas-On-Package "
            "77/79 GHz radar. 3 TX + 4 RX patches ON the 180-ball ALP "
            "package; no external antenna, no RF on the PCB → the "
            "nose_cap is a radome, not a waveguide block.\n\n"
            "RF headline (SWRS236C): TX EIRP 16 dBm, RX NF 10 dB "
            "(76-81 GHz), phase noise -95/-93 dBc/Hz @1 MHz. Processing: "
            "C674x DSP + Radar HWA + Cortex-R4F, 2 MB RAM.\n\n"
            "DISTINCT from IWR1843AOP (industrial, SWRS317, SIL-2; secure "
            "orderable IWR1843ARBSALP). Same RF/digital headline + 180-pin "
            "ALP package. Footprint/pinout from the pin-identical General "
            "(ARBGALPQ1) SamacSys lib; orderable = the Secure variant.\n\n"
            "SECURITY tier (selected by `secure`): proto/bring-up = "
            "AWR1843ARBGALPQ1 (General, DEFAULT — no secure boot, easy "
            "sourcing); production = AWR1843ARBSALPQ1 (Secure: encrypted + "
            "authenticated boot, Fig 10-1 G/S field) — REQUIRED for fielded "
            "units because the boot image lives in external flash. T&R = the "
            "…ALPRQ1 suffix. Confirm Secure-variant sourcing + OTP-keywriter "
            "lead time with TI before production.\n\n"
            "Package height 0.9 mm (ALP max, from the SamacSys 3D model "
            "bounding box) — drives the radar↔nose_cap radome standoff via "
            "_set_dynamic_spacer_thickness. Verify vs the SWRS236C "
            "mechanical drawing before fab."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_awr2944abgaltq1(design, ref: str, **overrides) -> Chip:
    """TI AWR2944ABGALTQ1 — automotive 76-81 GHz mmWave radar SoC,
    4 TX × 4 RX (16 virtual MIMO channels), R5F + Cortex-M4,
    **4 MB on-chip RAM** (full AWR2944 variant), FCBGA-266.

    >>> If your design's BOM references `AWR2944ALBGALTRQ1` (the 'AL'
        prefix), that's the **AWR2944LC** variant with **3 MB on-chip
        RAM** — see `add_awr2944albgaltrq1` instead. Same package +
        pin layout; different silicon / memory.
    """
    fields = _radar(
        pn="AWR2944ABGALTQ1",
        ds_name="AWR2943-AWR2944-AWR2944LC-family.pdf",
        fp_mod_name="BGA266C65P18X18_1200X1200X120.kicad_mod",
        fp_class="FCBGA-266",
        package="FCBGA-266 (12×12 mm)",
        description=(
            "Automotive 76-81 GHz radar (AWR2944, 4 MB on-chip RAM), "
            "4 TX × 4 RX (16-ch virtual MIMO), R5F + Cortex-M4, "
            "FCBGA-266"
        ),
        ball_count=266,
        size_mm=(12.0, 12.0),
        pitch_mm=0.65,
        # ── thermal (no AWR2944-specific datasheet in Research/) ──────
        # AWR2944 datasheet (TI SWRS273D) was not in Research/ at
        # build time — values derived from the IWR1843 datasheet (same
        # 76-81 GHz mmWave family, same R5F+M4 architecture) scaled
        # for the smaller FCBGA-266 12×12 mm package vs IWR1843's
        # FCBGA-180 15×15 mm: ΘJC scales with package size, p_active
        # is conservative-mid (4 TX vs 3 TX bumps power slightly but
        # AWR2944 has lower-power silicon for automotive). Refresh
        # these once AWR2944's own datasheet is dropped into Research/.
        p_active_w=0.83,                    # est'd typical run (AWR2944 ref design, 25% duty, 2-3 TX)
        p_max_w=1.65,                       # est'd peak (full 4 TX 4 RX, DSP+HWA active)
        rth_jc_cw=4.2,                      # est'd from IWR1843 §7.9 — same family
        tj_max_c=125.0,                     # AEC-Q100 Grade 2 absolute max Tj
        note=(
            "TI AWR2944 (4 MB RAM variant, 'A' prefix). Cortex-R5F "
            "radar control + Cortex-M4 user MCU. HWA2.1 hardware "
            "accelerator. AEC-Q100 automotive qualified.\n\n"
            "Family order codes (datasheet SWRS273D Device Information "
            "table):\n"
            "  AWR2944ABGALTQ1  : 4 MB RAM (AWR2944), tray packing\n"
            "  AWR2944ABGALTRQ1 : 4 MB RAM (AWR2944), tape & reel\n"
            "  AWR2944ABSALTQ1  : same silicon, different package mark\n"
            "  AWR2944ABSALTRQ1 : same silicon, T&R\n"
            "  AWR2944ALBGALTRQ1: **AWR2944LC** (3 MB RAM, T&R) — different chip\n"
            "  AWR2944ALBSALTRQ1: AWR2944LC, T&R\n"
            "  AWR2944ALBGALTQ1 : AWR2944LC, tray\n\n"
            "Datasheet covers AWR2943 (3 ch, 3.5 MB), AWR2944 (4 ch, "
            "4 MB), and AWR2944LC (4 ch, 3 MB) — all share the same "
            "FCBGA-266 package and pinout."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_awr2944abgaltrq1(design, ref: str, **overrides) -> Chip:
    """TI AWR2944ABGALTRQ1 — automotive 76-81 GHz mmWave radar SoC,
    **full AWR2944 variant** (4 MB on-chip RAM + DSP + Aurora LVDS +
    Ethernet + CSI2 RX), 4 TX × 4 RX, R5F + Cortex-M4, FCBGA-266,
    **tape & reel packing** for production.

    **This is the Smash radar choice.** Same package and pin layout as
    the AWR2944LC (`AWR2944ALBGALTRQ1`); chosen over LC because the
    additional peripherals (DSP, Ethernet, CSI2 RX, Aurora) give
    headroom for firmware growth and feature extensions without a
    PCB respin.

    Compared to `add_awr2944abgaltq1` (tray packing), this differs
    only in shipping format — `R` suffix = tape & reel. Same silicon,
    same datasheet, same footprint.
    """
    fields = _radar(
        pn="AWR2944ABGALTRQ1",
        ds_name="AWR2943-AWR2944-AWR2944LC-family.pdf",
        fp_mod_name="BGA266C65P18X18_1200X1200X120.kicad_mod",
        fp_class="FCBGA-266",
        package="FCBGA-266 (12×12 mm)",
        description=(
            "Automotive 76-81 GHz radar (AWR2944, 4 MB on-chip RAM + "
            "C674x DSP + Aurora + Ethernet + CSI2 RX), 4 TX × 4 RX "
            "(16-ch virtual MIMO), R5F + Cortex-M4, FCBGA-266, "
            "tape & reel"
        ),
        ball_count=266,
        size_mm=(12.0, 12.0),
        pitch_mm=0.65,
        # ── thermal — same silicon as AWR2944ABGALTQ1, see notes there
        p_active_w=0.83,                    # est'd typical run; AWR2944 DS missing from Research/
        p_max_w=1.65,                       # est'd peak (full 4 TX 4 RX)
        rth_jc_cw=4.2,                      # est'd from IWR1843 §7.9 (same family)
        tj_max_c=125.0,                     # AEC-Q100 Grade 2 absolute max Tj
        note=(
            "TI AWR2944 (full 'A' variant) — Smash's chosen radar SoC. "
            "Tape & reel packing ('R' suffix) for production runs. "
            "Same FCBGA-266 package as the AWR2944LC; the LC drops DSP, "
            "Aurora, Ethernet, CSI2 RX, and 1 MB of RAM.\n\n"
            "Functionally vs AWR2944LC (datasheet §X comparison table):\n"
            "  - On-chip RAM   : 4 MB (vs 3 MB on LC)\n"
            "  - DSP (C674x)   : YES (LC has none)\n"
            "  - Aurora LVDS   : YES (LC has none)\n"
            "  - Ethernet      : YES (LC has none)\n"
            "  - CSI2 RX       : YES (LC has none)\n"
            "Common to both:   RF performance, 4 TX × 4 RX, HWA2.1 "
            "hardware accelerator, R5F MCU, HSM, 2× SPI, QSPI, 2× "
            "CAN-FD, I²C, JTAG, GPADC, ePWM, AEC-Q100.\n\n"
            "Footprint and pin list reused from the AWR2944ABGALTQ1 "
            "SamacSys archive — TI explicitly states all AWR294x "
            "orderables share the FCBGA-266 12×12 mm package.\n\n"
            "Sibling factories: `add_awr2944abgaltq1` for the tray-"
            "packing equivalent of this same silicon; "
            "`add_awr2944albgaltrq1` for the LC variant (kept for "
            "reference, NOT the design choice)."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_awr2944albgaltrq1(design, ref: str, **overrides) -> Chip:
    """TI AWR2944ALBGALTRQ1 — AWR2944LC variant (3 MB RAM, no DSP/
    Aurora/Ethernet/CSI2 RX). Kept in the catalog for reference but
    **NOT the Smash radar choice** — the design uses
    `add_awr2944abgaltrq1` (full AWR2944 with DSP + Ethernet + CSI2 RX
    + 4 MB RAM) for firmware-headroom reasons.

    Same FCBGA-266 footprint and ball positions as the full variant;
    only silicon contents differ.
    """
    fields = _radar(
        pn="AWR2944ALBGALTRQ1",
        ds_name="AWR2943-AWR2944-AWR2944LC-family.pdf",
        fp_mod_name="BGA266C65P18X18_1200X1200X120.kicad_mod",
        fp_class="FCBGA-266",
        package="FCBGA-266 (12×12 mm)",
        description=(
            "Automotive 76-81 GHz radar (AWR2944LC, 3 MB on-chip RAM), "
            "4 TX × 4 RX (16-ch virtual MIMO), R5F + Cortex-M4, "
            "FCBGA-266, tape & reel"
        ),
        ball_count=266,
        size_mm=(12.0, 12.0),
        pitch_mm=0.65,
        # ── thermal — LC drops DSP/Ethernet/CSI2 so ~10-15% lower
        # active power than the full AWR2944; AWR2944 DS not in
        # Research/ at build time so values still derived from IWR1843.
        p_active_w=0.72,                    # est'd typical (LC: no DSP, 3 MB RAM)
        p_max_w=1.45,                       # est'd peak (full 4 TX 4 RX, no DSP)
        rth_jc_cw=4.2,                      # est'd from IWR1843 §7.9 (same family)
        tj_max_c=125.0,                     # AEC-Q100 Grade 2 absolute max Tj
        note=(
            "TI AWR2944LC ('AL' prefix) — Low-Cost variant of the "
            "AWR2944 family with **3 MB on-chip RAM** (vs 4 MB on the "
            "standard `A` variant). Same FCBGA-266 package + pinout + "
            "RF spec; the memory reduction is the headline difference. "
            "The HWA2.1 hardware accelerator may also differ slightly "
            "between AWR2944 and AWR2944LC — see datasheet note (7).\n\n"
            "Footprint and pin list reused from the SamacSys "
            "AWR2944ABGALTQ1 archive — TI explicitly states (datasheet "
            "Device Information table) that all orderables in this "
            "family share the same FCBGA-266 12×12 mm package.\n\n"
            "Sibling factory: `add_awr2944abgaltq1` for the full-memory "
            "AWR2944 (4 MB)."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_awr2243abgablq1(design, ref: str, **overrides) -> Chip:
    """TI AWR2243ABGABLQ1 — automotive 76-81 GHz front-end radar
    transceiver (3 TX × 4 RX), no on-chip DSP — pairs with an
    external processor via CSI-2, 161-ball FCBGA, **tray packing**.

    For production (tape & reel), use `add_awr2243abgablrq1` — same
    silicon, T&R packing."""
    fields = _radar(
        pn="AWR2243ABGABLQ1",
        ds_name="AWR2243.pdf",
        fp_mod_name="BGA161C65P15X15_1040X1040X117.kicad_mod",
        fp_class="FCBGA-161",
        package="FCBGA-161 (10.4×10.4 mm)",
        description=(
            "Automotive 76-81 GHz radar front-end, 3 TX × 4 RX, "
            "no on-chip DSP (external proc via CSI-2), FCBGA-161, tray"
        ),
        ball_count=161,
        size_mm=(10.4, 10.4),
        pitch_mm=0.65,
        note=(
            "TI AWR2243 (SWRS223D Feb 2024) — 'transceiver-only' radar "
            "front-end. Unlike AWR2944 (full SoC), this part has NO "
            "integrated DSP — raw ADC samples stream out via CSI-2 to "
            "an external processor (typically TDA4VM or similar).\n\n"
            "Cascade-capable up to 4 chips for 12 TX × 16 RX virtual "
            "MIMO via shared 20 GHz LO sync.\n\n"
            "Datasheet orderables (§Device Information):\n"
            "  AWR2243ABGABLQ1   : tray (this factory)\n"
            "  AWR2243ABGABLRQ1  : tape & reel — see add_awr2243abgablrq1\n"
            "Both use FCBGA-161 (ABL package), 10.4 × 10.4 mm,\n"
            "1.17 mm max height, 0.65 mm pitch.\n\n"
            "Key thermal (datasheet §7.8): R_θJC = 5 °C/W.\n"
            "I/O voltage : dual 3.3 V / 1.8 V supported.\n"
            "Clock source: external 40 MHz crystal or square/sine drive."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_awr2243abgablrq1(design, ref: str, **overrides) -> Chip:
    """TI AWR2243ABGABLRQ1 — same silicon as AWR2243ABGABLQ1, but
    **tape & reel packing** for production. Same FCBGA-161 package,
    pin layout, and datasheet (SWRS223D)."""
    fields = _radar(
        pn="AWR2243ABGABLRQ1",
        ds_name="AWR2243.pdf",
        fp_mod_name="BGA161C65P15X15_1040X1040X117.kicad_mod",
        fp_class="FCBGA-161",
        package="FCBGA-161 (10.4×10.4 mm)",
        description=(
            "Automotive 76-81 GHz radar front-end, 3 TX × 4 RX, "
            "no on-chip DSP (external proc via CSI-2), FCBGA-161, "
            "tape & reel"
        ),
        ball_count=161,
        size_mm=(10.4, 10.4),
        pitch_mm=0.65,
        note=(
            "TI AWR2243 — same silicon as AWR2243ABGABLQ1 but tape & "
            "reel ('R' suffix) for production builds. See sibling "
            "factory `add_awr2243abgablq1` for the tray-packed "
            "equivalent and the full datasheet citations."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_awr2e44pbgamxrq1(design, ref: str, **overrides) -> Chip:
    """TI AWR2E44P — 77 GHz waveguide-coupled radar SoC, FCCSP 13.5×12 mm,
    278-ball (AEC-Q100 automotive). Footprint + ballmap were LIFTED from the
    AWR2E44P EVM (TI design SPRR509 / PROC196A) — TI publishes no standalone
    library for this part. Unlike the AWR2944, the RF couples into the machined
    waveguide/horn block via SIW launches (`VDDA_10RF*` rails + on-package
    launches), so there are NO discrete TX/RX antenna balls.

    CAVEATS (verify before fab): the ball grid is generated at 0.65 mm pitch
    from the EVM ball IDs — confirm exact positions vs the package drawing in
    `awr2944p_family.pdf`; and the SIW waveguide-launch apertures (no balls) are
    NOT yet marked on the footprint — add them from the package drawing.
    """
    pn = "AWR2E44PBGAMXRQ1"
    fp_mod = src(pn, f"{pn}.kicad_mod")
    pads = pads_from_kicad_mod(fp_mod)
    ballmap = json.loads(pathlib.Path(src(pn, "pinmap.json")).read_text())
    pad_nums = {p.num for p in pads}
    pins = [Pin(num=b, name=n) for b, n in ballmap.items()]
    if {p.num for p in pins} != pad_nums:
        raise ValueError(f"{pn}: pin/pad mismatch {set(ballmap) ^ pad_nums}")
    fields = dict(
        manf="Texas Instruments", manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn, value=pn,
        description=(
            "77-81 GHz waveguide-coupled radar SoC (Cortex-R5F MSS + DSP + HWA), "
            "SIW launches into an external horn block, FCCSP 13.5×12 mm, "
            "278-ball, AEC-Q100"
        ),
        datasheet=datasheet_ref(pn, "awr2944p_family.pdf"),
        package="FCCSP (13.5 × 12 mm)",
        size_mm=(13.5, 12.0),
        height_mm=1.234,                    # datasheet AMX outline, 1.234 mm MAX
        temp_range_c=(-40, 125),
        tj_max_c=125.0,
        p_max_w=1.65,
        standards=["AEC-Q100"],
        pins=pins,
        footprint=Footprint(
            name="AWR2E44PBGAMXRQ1", package_class="FCCSP-278",
            pads=pads,
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.65,
            size_mm=(13.5, 12.0),
            height_mm=1.234,                # datasheet AMX outline, 1.234 mm MAX
            source="ti-evm-lift",
            # No AWR2E44P STEP exists yet — use the AWR2944 BGA266 model as a
            # same-height (1.234 mm) visual stand-in for 3D/STEP exports.
            model_3d_path=datasheet_ref(pn, "AWR2944_standin.stp"),
        ),
        note=(
            "Pinmap LIFTED from the AWR2E44P EVM (TI SPRR509 / PROC196A, "
            "30-Aug-2024) — no TI library exists for this part. 278 balls, "
            "rows A-U × cols 1-20, 0.65 mm pitch (grid generated; verify vs the "
            "package drawing). RF couples into the waveguide block via SIW "
            "launches — NO TX/RX antenna balls (unlike AWR2944). The 8 waveguide "
            "launches (TX1-4/RX1-4) are marked on Dwgs.User per datasheet Fig "
            "6-2 with NO balls within (verified); their exact mm extents + ~14 "
            "lower-right depopulated cells still need reconciliation vs "
            "awr2944p_family.pdf before fab. Wired by build_radar_module_awr2e44p "
            "(not the AWR2944 path)."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
