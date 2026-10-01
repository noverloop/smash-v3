"""Microcontroller factories — STM32 family.

All pin lists are parsed directly from the SamacSys-generated KiCad
symbol; per-pin metadata (power-rail names, alt-function notes) is
overlaid via the `build_pins(..., types=, aliases=, ...)` helper.
"""

from __future__ import annotations

from smash.state import Chip, Footprint
from smash.parts._artifacts import (
    pads_from_kicad_mod, outline_polygon, build_pins, src, datasheet_ref,
)
from smash.parts._cubemx import (
    alt_functions_by_position, alt_functions_by_pin_name,
)
import os.path
from smash.parts._slug import canonical_id


def _overlay_cubemx_af(pn: str, pins: list, *,
                       af_source_pn: str | None = None) -> list:
    """Mutate `pins` to populate `alt_functions` from the part's
    vendored `cubemx.xml`. Join key is ball position because SamacSys
    uses simplified pin names (`PA14`) where CubeMX uses the fused
    datasheet form (`PA14(JTCK/SWCLK)`).

    `af_source_pn` names a sibling variant whose `cubemx.xml` carries the
    AF table when this part ships without its own — same die, different
    package (e.g. STM32MP255DAL3 reuses STM32MP255FAK3). Ball positions
    differ across packages, so that fallback joins by pin NAME (`PA0`),
    which is package-independent at the die level.

    No-op when no AF table is available — non-STM32 chips simply skip it.
    """
    cubemx_xml = src(pn, "cubemx.xml")
    if os.path.exists(cubemx_xml):
        af_by_pos = alt_functions_by_position(cubemx_xml)
        for p in pins:
            if p.num in af_by_pos:
                p.alt_functions = list(af_by_pos[p.num])
    elif af_source_pn:
        sib_xml = src(af_source_pn, "cubemx.xml")
        if os.path.exists(sib_xml):
            af_by_name = alt_functions_by_pin_name(sib_xml)
            for p in pins:
                if p.name in af_by_name:
                    p.alt_functions = list(af_by_name[p.name])
    return pins


def _stm32(*, pn, ds_name, fp_mod_name, fp_class, package,
           description,
           clock_max_hz, vcc_nominal_v,
           size_mm=None, height_mm=None, pitch_mm=None,
           temp_range_c=(-40, 85),
           p_active_w=None, p_max_w=None,
           rth_jc_cw=None, tj_max_c=None,
           note="", standards=None) -> dict:
    """Shared kw-dict builder for STM32 factories.

    Pin list comes from the SamacSys-generated KiCad symbol; per-pin
    alternate-function tables are loaded from the vendored CubeMX MCU
    XML (`<part-dir>/cubemx.xml`) and joined by ball position.

    Per-chip thermal kwargs (`p_active_w`, `p_max_w`, `rth_jc_cw`,
    `tj_max_c`) are forwarded straight to `Chip(...)`; pass them from
    the per-orderable factory with a datasheet-page reference in the
    inline comment so a future reader can audit them against the DS.
    """
    fp_mod = src(pn, fp_mod_name)
    pins = _overlay_cubemx_af(pn, build_pins(src(pn, f"{pn}.kicad_sym")))
    return dict(
        manf="STMicroelectronics", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=description,
        datasheet=datasheet_ref(pn, ds_name),
        package=package,
        size_mm=size_mm, height_mm=height_mm,
        temp_range_c=temp_range_c,
        voltage_rating_v=4.0,         # typical Vdd abs max for STM32
        vcc_nominal_v=vcc_nominal_v,
        clock_max_hz=clock_max_hz,
        p_active_w=p_active_w,
        p_max_w=p_max_w,
        rth_jc_cw=rth_jc_cw,
        tj_max_c=tj_max_c,
        standards=standards or [],
        pins=pins,
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


# ─── STM32G0B1 family — Cortex-M0+ 64 MHz ────────────────────────────────

def add_stm32g0b1kct6n(design, ref: str, **overrides) -> Chip:
    """ST STM32G0B1KCT6N — Cortex-M0+ 64 MHz, 256 KB flash + 144 KB SRAM,
    32-pin LQFP. Includes FDCAN, dual USB-PD, OPAMP/COMP, 12-bit ADC."""
    fields = _stm32(
        pn="STM32G0B1KCT6N",
        ds_name="STM32G0B1KCT6N.pdf",
        fp_mod_name="QFP80P900X900X160-32N.kicad_mod",
        fp_class="LQFP-32 (7×7 mm)",
        package="LQFP-32",
        description=(
            "STM32G0B1, Cortex-M0+ 64 MHz, 256 KB flash, 144 KB SRAM, "
            "FDCAN, USB-PD, LQFP-32"
        ),
        clock_max_hz=64e6,
        vcc_nominal_v=3.3,
        size_mm=(7.0, 7.0), height_mm=1.6, pitch_mm=0.8,
        # ── thermal (datasheet DS13560 Rev 6) ────────────────────────
        # IDD(Run) @ 64 MHz Range 1, Flash, Tj=25°C, Table 28 p141 →
        # 8.6 mA typ; max @ Tj=130°C = 9.7 mA. With Vdd=3.3V.
        p_active_w=0.028,                   # 8.6 mA × 3.3V @ 64 MHz Run typ (DS Tab 28)
        p_max_w=0.032,                      # 9.7 mA × 3.3V @ 64 MHz max @ Tj=130°C (DS Tab 28)
        rth_jc_cw=13.0,                     # LQFP32 ΘJC, DS Table 97 p159
        tj_max_c=150.0,                     # absolute max TJ, DS Table 23 p126
        note=(
            "STM32G0B1 = value-line Cortex-M0+ with FDCAN. The 'T6N' "
            "suffix decodes: T = LQFP, 6 = 32 pins (in this order code "
            "convention), N = -40..+85 °C industrial. Smash uses the "
            "G0B1 as a CAN bridge / IO-expander companion to the WLE5."
        ),
        standards=["RoHS", "ECOPACK2"],
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_stm32g0b1kcu6n(design, ref: str, **overrides) -> Chip:
    """ST STM32G0B1KCU6N — same die as KCT6N but UFQFPN-32 (5×5 mm,
    QFN with exposed pad). 33 'pins' = 32 functional + EP."""
    fields = _stm32(
        pn="STM32G0B1KCU6N",
        ds_name="STM32G0B1KCT6N.pdf",
        fp_mod_name="QFN50P500X500X60-33N-D.kicad_mod",
        fp_class="UFQFPN-32 (5×5 mm)",
        package="UFQFPN-32 (with EP)",
        description=(
            "STM32G0B1, Cortex-M0+ 64 MHz, 256 KB flash, 144 KB SRAM, "
            "UFQFPN-32"
        ),
        clock_max_hz=64e6,
        vcc_nominal_v=3.3,
        size_mm=(5.0, 5.0), height_mm=0.6, pitch_mm=0.5,
        # ── thermal (datasheet DS13560 Rev 6) ────────────────────────
        # Same die as KCT6N — IDD same.
        p_active_w=0.028,                   # 8.6 mA × 3.3V @ 64 MHz Run typ (DS Tab 28)
        p_max_w=0.032,                      # 9.7 mA × 3.3V @ 64 MHz max @ Tj=130°C (DS Tab 28)
        rth_jc_cw=14.0,                     # UFQFPN32 ΘJC (with EP), DS Tab 97 p159
        tj_max_c=150.0,                     # absolute max TJ, DS Tab 23 p126
        note=(
            "UFQFPN-32 variant of STM32G0B1. Same die as KCT6N but "
            "smaller footprint (5×5 vs 7×7 mm). Exposed pad must be "
            "tied to GND. The 'U' in KCU6N denotes UFQFPN package."
        ),
        standards=["RoHS", "ECOPACK2"],
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_stm32g0b1rei6n(design, ref: str, **overrides) -> Chip:
    """ST STM32G0B1REI6N — same die family but 64-ball UFBGA, 5×5 mm,
    0.5 mm pitch. Higher pin count for more I/O."""
    fields = _stm32(
        pn="STM32G0B1REI6N",
        ds_name="STM32G0B1KCT6N.pdf",
        fp_mod_name="BGA64C50P8X8_500X500X60.kicad_mod",
        fp_class="UFBGA-64 (5×5 mm)",
        package="UFBGA-64 (5×5 mm)",
        description=(
            "STM32G0B1, Cortex-M0+ 64 MHz, 64-ball UFBGA, more I/O"
        ),
        clock_max_hz=64e6,
        vcc_nominal_v=3.3,
        size_mm=(5.0, 5.0), height_mm=0.6, pitch_mm=0.5,
        # ── thermal (datasheet DS13560 Rev 6) ────────────────────────
        # Same die — but more I/O pins. IDD scales similarly.
        p_active_w=0.028,                   # 8.6 mA × 3.3V @ 64 MHz Run typ (DS Tab 28)
        p_max_w=0.032,                      # 9.7 mA × 3.3V @ 64 MHz max @ Tj=130°C (DS Tab 28)
        rth_jc_cw=32.0,                     # UFBGA64 5×5 ΘJC, DS Tab 97 p159
        tj_max_c=150.0,                     # absolute max TJ, DS Tab 23 p126
        note=(
            "UFBGA-64 variant of STM32G0B1. The 'R' = 64 pins, "
            "'E' = UFBGA, 'I' = ... per ST order-code convention."
        ),
        standards=["RoHS", "ECOPACK2"],
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ─── STM32WLE5 — Cortex-M4 with sub-GHz LoRa radio ───────────────────────

def add_stm32wle5jci6(design, ref: str, **overrides) -> Chip:
    """ST STM32WLE5JCI6 — Cortex-M4 48 MHz + sub-GHz LoRa/(G)FSK radio
    in a single SiP, 256 KB flash, 64 KB SRAM, 73-ball UFBGA."""
    fields = _stm32(
        pn="STM32WLE5JCI6",
        ds_name="STM32WLE5JCIx.pdf",
        fp_mod_name="BGA73C50P9X9_500X500X60.kicad_mod",
        fp_class="UFBGA-73 (5×5 mm)",
        package="UFBGA-73 (5×5 mm)",
        description=(
            "Cortex-M4 48 MHz + sub-GHz LoRa/(G)FSK radio, "
            "256 KB flash, 64 KB SRAM, UFBGA-73"
        ),
        clock_max_hz=48e6,
        vcc_nominal_v=3.3,
        size_mm=(5.0, 5.0), height_mm=0.6, pitch_mm=0.5,
        # ── thermal (datasheet DS13105 Rev 12) ───────────────────────
        # Smash use case: RX (LoRa downlink) most of the time, brief
        # TX bursts at +22 dBm high-power for the RF44 telemetry.
        # IDD includes all supplies — VDDRF, VDDSMPS, VDD, VDDA, VBAT.
        p_active_w=0.018,                   # 5.46 mA × 3.3V — RX-boosted LoRa 125 kHz, SMPS (DS Tab 28 p70)
        p_max_w=0.396,                      # 120 mA × 3.3V — TX +22 dBm high-power (DS Tab 29 p71)
        rth_jc_cw=11.0,                     # UFBGA73 5×5 ΘJC, DS Tab 99 p142
        tj_max_c=125.0,                     # absolute max TJ, DS Tab 23 (suffix 6 op'l limit is 85°C)
        note=(
            "STM32WLE5 = Cortex-M4 with an integrated SX126x-class "
            "sub-GHz radio on the same die. LoRa, (G)FSK, (G)MSK, "
            "BPSK modulations. RF I/O pins (RFO_HP, RFO_LP, RFI) "
            "require external matching network — see ST AN5457. "
            "Smash uses this part for the LoRa downlink (RF44 telemetry)."
        ),
        standards=["RoHS", "ECOPACK2"],
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ─── STM32WBA52 — Cortex-M33 100 MHz with BLE 5.4 + 802.15.4 ─────────────

def add_stm32wba52cgu7tr(design, ref: str, **overrides) -> Chip:
    """ST STM32WBA52CGU7TR — Cortex-M33 100 MHz with TrustZone + 2.4 GHz
    BLE 5.4 / 802.15.4 / proprietary radio on the same die, 1 MB flash,
    128 KB SRAM, UFQFPN-48 (7×7 mm). Extended-temperature variant
    (suffix 7 = −40 to +105 °C).

    Replaces the STM32WLE5JCI6 as Smash's wake orchestrator and 2.4 GHz
    radio:
      • RTC + EXTI wake from STM32WBA52 Standby (~0.93 µA with retention)
      • BLE Coded scan (backup wake from shelf if NFC reader unavailable)
      • Proprietary 2 Mbps PHY for in-flight directional telemetry via the
        side-meridian Yagi pair
      • Antenna selection between the nose chip antenna (programming) and
        the Yagi pair (in-flight) via an external SPDT switch

    No FDCAN on WBA52 — the STM32G0B1 next to it still bridges WBA52
    LPUART ↔ system CAN-FD (datasheet Table 2 confirms).

    The 32 MHz HSE is implemented as a MEMS resonator (DSC1001CI5-032.0000
    or equivalent) rather than a crystal, for shock survival under launch
    setback (Smash takes 1000+ g). The 32.768 kHz LSE is dropped — internal
    LSI (±5 %) is sufficient for BLE periodic-scan timing."""
    fields = _stm32(
        pn="STM32WBA52CGU7TR",
        ds_name="STM32WBA52CGU7TR.pdf",
        fp_mod_name="QFN50P700X700X65-49N-D.kicad_mod",
        fp_class="UFQFPN-48 (7×7 mm, with thermal pad)",
        package="UFQFPN-48 (7×7 mm)",
        description=(
            "Cortex-M33 100 MHz w/ TrustZone + 2.4 GHz BLE 5.4 / 802.15.4, "
            "1 MB flash, 128 KB SRAM, UFQFPN-48"
        ),
        clock_max_hz=100e6,
        vcc_nominal_v=3.3,
        size_mm=(7.0, 7.0), height_mm=0.65, pitch_mm=0.5,
        temp_range_c=(-40, 105),
        note=(
            "STM32WBA52CGU7TR = Cortex-M33 wireless MCU with integrated "
            "2.4 GHz radio (BLE 5.4, 802.15.4, proprietary 1M/2M/Coded PHYs). "
            "The 'CGU7TR' suffix decodes: CG = 1 MB flash + 128 KB SRAM, "
            "U = UFQFPN, 7 = extended-temperature (−40 to +105 °C), TR = "
            "tape & reel. No FDCAN peripheral (G0B1 bridges to system CAN). "
            "Standby min 0.37 µA (ULPMEN=1), 0.93 µA with 64 KB RAM ret. "
            "Max TX +9.5 dBm at VDDRFPA ≥ 2.5 V."
        ),
        standards=["RoHS", "ECOPACK2"],
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ─── STM32WBA55HG — Cortex-M33 100 MHz, BLE + 802.15.4, WLCSP41 ─────────

def add_stm32wba55hgf6tr(design, ref: str, **overrides) -> Chip:
    """ST STM32WBA55HGF6TR — Cortex-M33 100 MHz with TrustZone + 2.4 GHz
    BLE 5.4 / 802.15.4 / proprietary radio on the same die, 1 MB flash,
    128 KB SRAM, **Thin WLCSP41 (2.76 × 2.98 mm)**. Commercial-temp
    variant (suffix 6 = -40 to +85 °C).

    Versus the WBA52CG family this die adds:
      • SMPS (lower Run current; VDDSMPS / VLXSMPS / VSSSMPS pins + an
        external L+C network must be wired)
      • Native antenna-switch outputs (RF_ANTSW0 on PA12, RF_ANTSW1 on
        PA11) — radio hardware drives the SPDT directly, no firmware
        timing required
      • IEEE 802.15.4 + Packet Traffic Arbitration (PTA) for radio
        coexistence
      • External PA support (RF_EXTPABYP on PB15 / PH3-BOOT0)
      • BLE direction-finding (AoA / AoD)
      • SAI peripheral

    Versus the WBA52CG it drops:
      • 15 GPIOs (35 → 20). Wake-up pins 15 → 8 (we only need 2 in this
        design). Pin-out forces SPI**3** for the HCI link instead of
        SPI1; LSE pins (PC14/PC15) are reused as plain GPIOs because
        we run on internal LSI per the rearch plan.

    **Underfill is MANDATORY.** This is a wafer-level chip-scale
    package — bare silicon with 0.23 mm solder balls at 0.40 mm pitch
    and no overmould. Smash's 1000+ g setback would shear unprotected
    WLCSP joints; Hysol FP4549 (or equivalent capillary underfill)
    under the entire die is the standard mitigation and is rated
    >5000 g. Documented also in `components.md` as a process step
    alongside the H562 + MP25 + Micron NAND BGAs."""
    fields = _stm32(
        pn="STM32WBA55HGF6TR",
        ds_name="STM32WBA55HGF6TR.pdf",
        fp_mod_name="BGA41C35P13X7_298X276X50.kicad_mod",
        fp_class="WLCSP-41 (2.98 × 2.76 mm, 0.40 mm pitch)",
        package="Thin WLCSP41",
        description=(
            "Cortex-M33 100 MHz w/ TrustZone + 2.4 GHz BLE 5.4 / "
            "802.15.4 / direction-finding, integrated SMPS, 1 MB flash, "
            "128 KB SRAM, Thin WLCSP41"
        ),
        clock_max_hz=100e6,
        vcc_nominal_v=3.3,
        size_mm=(2.98, 2.76), height_mm=0.50, pitch_mm=0.40,
        temp_range_c=(-40, 85),
        note=(
            "STM32WBA55HGF6TR = Cortex-M33 wireless MCU with integrated "
            "2.4 GHz radio (BLE 5.4, 802.15.4, proprietary 1M/2M/Coded "
            "PHYs). The 'HGF6TR' suffix decodes: HG = 1 MB flash + "
            "128 KB SRAM, F = Thin WLCSP, 6 = commercial -40 to +85 °C, "
            "TR = tape & reel. No FDCAN peripheral (G0B1 bridges to "
            "system CAN). Standby min 0.37 µA (ULPMEN=1), 0.93 µA with "
            "64 KB RAM ret. Max TX +9.5 dBm at VDDRFPA ≥ 2.5 V. Native "
            "RF_ANTSW0/1 antenna-switch outputs on PA12/PA11 — drives "
            "the SPDT directly from radio hardware. "
            "**WLCSP shock note:** mandatory die-area underfill (Hysol "
            "FP4549 or equivalent capillary epoxy) — without it the "
            "WLCSP joints will shear under Smash's 1000+ g launch "
            "setback. Underfill process is already in the assembly "
            "flow for the H562 / MP25 / Micron NAND BGAs."
        ),
        standards=["RoHS", "ECOPACK2"],
    )
    # Tag the underfill so structural / assembly tooling can pick it up.
    fields["underfill"] = "Hysol_FP4549_capillary_die_area"
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ─── STM32H562 — Cortex-M33 250 MHz ──────────────────────────────────────

def add_stm32h562aii6(design, ref: str, **overrides) -> Chip:
    """ST STM32H562AII6 — Cortex-M33 250 MHz with TrustZone, 2 MB
    flash, 640 KB SRAM, 169-ball UFBGA (7×7 mm, 0.5 mm pitch)."""
    fields = _stm32(
        pn="STM32H562AII6",
        ds_name="STM32H562AIIx.pdf",
        fp_mod_name="BGA169C50P13X13_700X700X60.kicad_mod",
        fp_class="UFBGA-169 (7×7 mm)",
        package="UFBGA-169 (7×7 mm)",
        description=(
            "Cortex-M33 250 MHz w/ TrustZone, 2 MB flash, 640 KB SRAM, "
            "UFBGA-169"
        ),
        clock_max_hz=250e6,
        vcc_nominal_v=3.3,
        size_mm=(7.0, 7.0), height_mm=0.6, pitch_mm=0.5,
        # ── thermal (datasheet DS14258 Rev 6) ────────────────────────
        # Active-mode use: CoreMark from flash, all peripherals
        # disabled, 250 MHz, LDO regulator path, instr cache 2-way,
        # prefetch on → IDD typ 32.1 mA (DS Tab 32 p141). With Vdd=3.3V.
        # p_max: worst-case rated 200 MHz LDO @ Tj=130°C = 90 mA — the
        # DS doesn't quote a 250 MHz Tj=130°C number so we use the
        # 200 MHz row as the conservative bound for our use.
        p_active_w=0.106,                   # 32.1 mA × 3.3V CoreMark @ 250 MHz LDO (DS Tab 32 p141)
        p_max_w=0.297,                      # 90 mA × 3.3V @ 200 MHz LDO Tj=130°C (DS Tab 30 p140)
        rth_jc_cw=11.2,                     # UFBGA169 7×7 ΘJC, DS Tab 142 p270
        tj_max_c=130.0,                     # absolute max TJ, DS Tab 19 p128
        note=(
            "STM32H562 = high-performance Cortex-M33 with TrustZone, "
            "DSP/FPU, 250 MHz max. AII suffix = UFBGA-169 industrial. "
            "Smash uses this part as the flight computer."
        ),
        standards=["RoHS", "ECOPACK2"],
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ─── STM32MP255 — Cortex-A35 + M33 application processor ─────────────────

def add_stm32mp255fak3(design, ref: str, **overrides) -> Chip:
    """ST STM32MP255FAK3 — Dual Cortex-A35 (1.5 GHz) + Cortex-M33
    + Cortex-M0+, integrated 3D GPU + dual NPU, DDR3/DDR4/LPDDR4
    controller, 424-ball VFBGA (13×13 mm, 0.5 mm pitch)."""
    pn = "STM32MP255FAK3"
    fp_mod = src(pn, f"{pn}.kicad_mod")
    fields = dict(
        manf="STMicroelectronics", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "Application processor: dual Cortex-A35 1.5 GHz + Cortex-M33 + "
            "Cortex-M0+, 3D GPU, dual NPU, DDR3/DDR4/LPDDR4 controller, "
            "424-ball VFBGA"
        ),
        datasheet=datasheet_ref(pn, f"{pn}.pdf"),
        package="VFBGA-424 (13×13 mm)",
        size_mm=(13.0, 13.0), height_mm=1.2,
        temp_range_c=(-40, 85),
        clock_max_hz=1.5e9,
        vcc_nominal_v=1.2,            # core supply; many other rails
        # ── thermal (datasheet DS14284 Rev 5) ────────────────────────
        # NB: catalog records the package as 13×13 but DS14284 Tab 135
        # lists VFBGA424 at 14×14 mm — flagged for review. Thermal
        # values below come from the 14×14 VFBGA424 row. p_active /
        # p_max are aggregate package dissipation estimates with full
        # A35+M33+M0+GPU running (sum of IDD across all VDDCORE/CPU/
        # GPU/CPU0_AON/A18 rails per DS Tables 22-27).
        p_active_w=1.19,                    # aggregate run-mode active, all rails
        p_max_w=1.65,                       # aggregate peak (full A35+M33+M0+GPU @ Tj=125°C)
        rth_jc_cw=5.5,                      # VFBGA424 14×14 ΘJC, DS Tab 135 p226
        tj_max_c=125.0,                     # absolute max TJ for suffix 3 die, DS Tab 16 p102
        standards=["RoHS", "ECOPACK2"],
        pins=_overlay_cubemx_af(pn, build_pins(src(pn, f"{pn}.kicad_sym"))),
        footprint=Footprint(
            name=pn, package_class="VFBGA-424",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.5, size_mm=(13.0, 13.0), height_mm=1.2,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=(
            "STM32MP25 = ST application-processor SoC: A35 cluster "
            "(2× cores @ 1.5 GHz) + M33 (real-time) + M0+ (low-power). "
            "On-die accelerators: 3D GPU, dual NPU, H.264/H.265 codec. "
            "Routing follows ST AN5724 (DDR3/DDR4/LPDDR4 guidelines). "
            "424-ball VFBGA, 0.5 mm pitch — requires HDI escape with "
            "VIPs (handled by Smash placer)."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_stm32mp255dal3(design, ref: str, **overrides) -> Chip:
    """ST STM32MP255DAL3 — same dual Cortex-A35 (1.5 GHz) + Cortex-M33 +
    Cortex-M0+ compute, 3D GPU and 1.35 TOPS NPU as the MP255F, in the
    smaller 361-ball VFBGA (10×10 mm, 0.5 mm pitch).

    Package vs the MP255FAK3 (VFBGA-424, 14×14): the AL/VFBGA361 keeps
    the full 144-GPIO breakout and CSI-2/FMC/3×FDCAN, dropping only the
    32-bit DDR option — this design runs 16-bit DDR3L, which AL supports
    (up to 1 GByte single rank). The A/D product group is the standard
    (non-C/F) line; the D variant matches the F's 1.5 GHz / 1.35 TOPS.
    The 10×10 body fits the Ø34 companion_compute tile with wide edge
    margin (vs the 14×14 part's ~0.35 mm). DDR3 routing must be redone
    against this ballout (ST VFBGA361/AL length-equalization data)."""
    pn = "STM32MP255DAL3"
    fp_mod = src(pn, f"{pn}.kicad_mod")
    fields = dict(
        manf="STMicroelectronics", manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn, value=pn,
        description=(
            "Application processor: dual Cortex-A35 1.5 GHz + Cortex-M33 + "
            "Cortex-M0+, 3D GPU, 1.35 TOPS NPU, DDR3L/DDR4/LPDDR4 "
            "controller (16-bit on this package), 361-ball VFBGA"
        ),
        datasheet=datasheet_ref(pn, f"{pn}.pdf"),
        package="VFBGA-361 (10×10 mm)",
        size_mm=(10.0, 10.0), height_mm=1.16,
        temp_range_c=(-40, 85),
        clock_max_hz=1.5e9,
        vcc_nominal_v=1.2,            # core supply; many other rails
        # ── thermal (datasheet DS14284 Rev 5) ────────────────────────
        # Same silicon as MP255FAK3 — power dissipation is dominated by
        # the A35+M33+M0+GPU+NPU compute; the smaller 10×10 package is
        # only thermally tighter (higher ΘJC). Smash splits the A35
        # pair off-die for active flight — `p_active_w` accounts for
        # the typical "A35-on + GPU/NPU on, M33+M0 idle" mix.
        p_active_w=1.19,                    # aggregate run-mode active (DS Tabs 22-27)
        p_max_w=1.65,                       # aggregate peak (full A35+M33+M0+GPU+NPU @ Tj=125°C)
        rth_jc_cw=5.7,                      # VFBGA361 10×10 ΘJC, DS Tab 135 p226
        tj_max_c=125.0,                     # absolute max TJ for suffix 3 die, DS Tab 16 p102
        standards=["RoHS", "ECOPACK2"],
        # DAL3 ships no cubemx.xml; reuse the FAK3 table by pin name (same die).
        pins=_overlay_cubemx_af(pn, build_pins(src(pn, f"{pn}.kicad_sym")),
                                af_source_pn="STM32MP255FAK3"),
        footprint=Footprint(
            name=pn, package_class="VFBGA-361",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.5, size_mm=(10.0, 10.0), height_mm=1.16,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=(
            "STM32MP255 SoC in the 10×10 VFBGA-361 (AL) package — A35 "
            "cluster (2× @ 1.5 GHz) + M33 + M0+, 3D GPU, 1.35 TOPS NPU, "
            "H.264/H.265 codec. 16-bit DDR3L only (no 32-bit on AL). "
            "Routing follows ST AN5724; the AL ballout differs from the "
            "VFBGA-424 (AK) reference, so DDR length-match data is "
            "package-specific. 361-ball, 0.5 mm pitch — HDI/VIP escape."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
