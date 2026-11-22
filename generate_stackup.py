#!/usr/bin/env python3
"""Smash design generator — builds the full Smash design using nothing
but the `smash` library and emits the KiCad panels + per-config variants.

Smash is a high-speed emergency airdrop of a sensor package — sonar,
infrared, or a radio — onto an illuminated point, so missing people can
be found while the window is still open. `PARACHUTE_CUTTER_SET` arms the
aft nichrome bank; `PARACHUTE_CUTTER_ACTIVATE` feeds the selected
parachute restraint.

Originally a twin of the legacy SKiDL `system.py` (now frozen under
`archive/`; see archive/README.md). The `smash` library is the sole
authority — parity with `system.py` is no longer maintained, so the old
byte-diff verification loop is retired. Run:

    python3 generate_stackup.py                # full twin + configs

Boards are built bottom-up — smallest first. Cross-board nets are
get-or-create via `_net()`; whichever board's builder runs first
creates the net, subsequent boards connect onto it.

Status (boards implemented):
    [x] qpd_module               (1 part)
    [x] nfc_antenna_flex         (1 part)
    [ ] nose_connector           (5 parts)
    [ ] camera_module            (9 parts)
    [ ] activation_interface    (22 parts)
    [ ] radar_module            (33 parts)
    [ ] companion_compute       (44 parts + 2 SPI-NAND, ex-companion_io storage)
    [x] wakeup_board            (88 parts)
    [x] power_board             (91 parts)
    [x] flight_board           (108 parts)
"""
from __future__ import annotations

import csv
import functools
import os
import json
import pathlib
import re
import shutil
import sys

REPO = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "application" / "src"))

from smash.state import (                                              # noqa: E402
    Design, NetHandle, Footprint, Pad, Pin, Flex,
)
from smash.parts.mechanical import (                                   # noqa: E402
    add_mt03_092_qpd, add_nfc_antenna_flex_27x50,
    add_pogo_pad, add_clamp_tab, add_cell_contacts_3, add_cell_solder_tab, add_cell_lead_pth, add_piezo_disc_smd10t04r111,
    add_mechanical_spacer_34mm,
)
from smash.parts.castellations import (place_castellations,             # noqa: E402
                                       board_fold_transforms)
from smash.parts.connectors import (place_lga_lands,                    # noqa: E402
                                    place_branch_flex_launches)
from smash.parts.batteries import add_tlm_1520hpms                      # noqa: E402
from smash.parts.cameras import add_ar0234cssm00suka0_cp               # noqa: E402
from smash.parts.radar import (                                        # noqa: E402
    add_awr2944abgaltrq1, add_awr2e44pbgamxrq1, add_awr1843aop,
)
from smash.parts.regulators import (                                    # noqa: E402
    add_lmr10510xmfe_nopb, add_mcp1640ct_i_chy, add_tps61175pwpr, add_mcp1640_dfn,
)
from smash.parts.motor_drivers import add_drv8428epwpr, add_drv8428erter  # noqa: E402
from smash.parts.diodes import (add_mbrs340t3g, add_mbrs540t3g,  # noqa: E402
                                add_pmeg040v050epe_qz,
                                add_bas40_02l, add_stps1l60zf, add_pmeg6010cej)
from smash.parts.ldos import (                                          # noqa: E402
    add_ldl112pv18r, add_ldl112pv33r, add_stlq020c33r,
    add_lp5907mfx_1_2_nopb, add_lp5907mfx_2_8_nopb, add_tps7a0233pdbvr, add_tps7a0233pdqnr,
)
from smash.parts.pmics import add_stpmic25apqr                          # noqa: E402
from smash.parts.sensors import add_h3lis331dltr, add_tmp117maidrvr     # noqa: E402
from smash.parts.transceivers import add_tcan1042gvdq1, add_tcan1042gvdrbrq1                  # noqa: E402
from smash.parts.mcus import (                                          # noqa: E402
    add_stm32mp255fal3, add_stm32g0b1rei6n,
    add_stm32wba55hgf6tr, add_stm32wba55ugi7, add_stm32h562aii6,

)
from smash.parts.flash import (                                         # noqa: E402
    add_ktdm4g4b626bgieat, add_mt41k256m16tw_107_ptr,
    add_mt29f4g01abafdwb_it_f, add_s25hl512tfamhi010, add_sst26wf080b,
    add_sst26vf080a,
)
from smash.parts.mosfets import (                                        # noqa: E402
    add_irlml6402trpbf, add_bss138lt1g, add_dmn6075sq_7, add_dmp6110svt_7,
    add_bss138akm_qyl, add_buk6d120_60px,
)
from smash.parts.logic import add_cd74hc4514pw                           # noqa: E402
from smash.parts.oscillators import (                                    # noqa: E402
    add_sit1630ae_s6_dcc_32_768e, add_sit1533ai_h4_dcc_32_768e, add_dsc1001ci5_008_0000,
    add_dsc1001ci5_032_0000, add_dsc1001ci5_040_0000, add_dsc1001ci5_027_0000,
)
from smash.parts.passives import (
    add_capacitor_x7r_0805_kemet_mil,                                       # noqa: E402
    add_capacitor_c0g_0603_avx_sqcs, add_capacitor_x7r_0402_kemet,
    add_we_744043100, add_lps4018_103mrb, add_xgl5020_472mec, add_xgl5020_822mec,
    add_blm18pg221sn1d,
)
from smash.parts.sensors import add_iis2mdctr, add_ism330dhcxtr           # noqa: E402
from smash.parts.swaps_2026_11 import (                                  # noqa: E402
    add_stm32mp257fal3, add_adf4351bcpz_rl7, add_dsc1001ci1_027_0000, add_sit1602bi_12_xxe_40,
    add_mx25v8035fzni, add_ssm3j372r_lf, add_ru1j002yntcl, add_rb160vam_60, add_vemd5110x01,
    add_lmr10510ysde_nopb, add_ssm3k35ctc_l3f, add_ssm3k7002kfu_lf, add_ihlp2020bzer100m01,
    add_ncs1_292p, add_pe64904d_z, add_tlv7031dpwr, add_s1318d33_a4t2u4,
    add_xc6504a331mr_g, add_xc6220b181mr_g, add_tja1462btk_0z, add_ism330dlctr, add_usblc6_4sc6,
    add_stm32u545rei6q, add_tc78h653ftg, add_mcp9808t_e_mc, add_bmm350,
    add_sit5356aecfq_33n0_32, add_mcp6541t_e_ot)
from smash.parts.opamps import add_ad8603aujz_r2_single_supply             # noqa: E402
from smash.parts.comparators import add_tlv3691idpfr                      # noqa: E402
from smash.parts.optical import add_vbpw34fas, add_vsmb1940x01           # noqa: E402
from smash.parts.coils import add_health_coil                            # noqa: E402
from smash.parts.hall_sensors import add_drv5032fcdbzt, add_drv5032ajdmrr, add_rr123_1h02_612  # noqa: E402
from smash.parts.usb import (add_uj20_c_h_g_msmt_1a_p16_tr_67,              # noqa: E402
                             add_uj20_c_v_g_smt_23b_p16_tr_x5)
from smash.parts.rf import (add_lr2021imltrt, add_tcxo_32m_2016,          # noqa: E402
                            add_bgs12p2l6e6327xtsa1, add_pe64906b_z,
                            add_adf4351bcpz, add_ltc5549iudb, add_ltc5552iudb, add_grf5126,
                            add_grf2073w)
from smash.netlist import cap_to_gnd, res_between, ind_between          # noqa: E402
from smash.parts.passives import add_inductor_we_mapi_74438356047     # noqa: E402
from smash.export.canonical_netlist import write_canonical_netlist     # noqa: E402
from smash.export import (                                              # noqa: E402
    write_kicad_pcb, write_kicad_panel, write_all_spacer_steps,
    write_kicad_step, find_kicad_cli, KiCadCliNotFound,
    write_blank_drawing_sheet, write_stackup_step,
    write_stackup_components_step,
    write_consolidated_stackup_stl, write_housing_stl,
    write_gerbers, write_kicad_schematic, write_board_schematic,
    write_panel_schematic,
    write_board_protel_netlist,
)
from smash.export.kicad_sch import relink_multi_unit_footprints   # noqa: E402
from smash.export._common import (                                     # noqa: E402
    all_components, board_refdes, component_value, stack_letter,
)
from smash.layout.boards.smash_evb_v1 import (                          # noqa: E402
    build_panel, build_config_panel,
)
from smash.layout.placer import place_design, size_backbone_spacers     # noqa: E402


# ── get-or-create net helper ─────────────────────────────────────────────

# Auto-classification of well-known power-rail names. Anything matching
# this map is created as `kind="power"` with the listed nominal voltage,
# so the `_v_pin_type_vs_net_kind` validator passes without every call
# site needing to spell out `kind="power", voltage_v=...`. Anything
# NOT in this map stays `kind="signal"` and a mistakenly-connected
# power pin will be caught by the validator.
_AUTO_POWER_RAILS: dict[str, float] = {
    "3V3":          3.3,
    "FLEX_3V3":     3.3,
    "COMP_5V":      5.0,
    "COMP_5V_RAW":  5.0,    # boost output, fin/VM side of the LC filter (rule-sweep F6 — was kind="signal")
    "COMP_3V3":     3.3,    # PMIC BUCK2 — MP25 IO ring (rule-sweep F6 — was kind="signal")
    "COMP_1V8":     1.8,
    "COMP_1V35":    1.35,   # (2026-11-22) DDR3L VDD/VDDQ (was COMP_1V2 DDR4 + COMP_VPP 2.5 V)
    "COMP_0V9":     0.9,
    "COMP_0V82":    0.82,   # MP25 VDDCORE domain (PMIC BUCK5; DS ROC 0.79–0.842 V)
    "3V3_AON":      3.3,    # nanopower standby domain (TPS7A02 off BAT_RAW; WBA+H3LIS+ST25DV+TLV3691)
    "COMP_2V8":     2.8,
    "AWR_1V0":      1.0,    # AWR2944/2E44P core (legacy builders)
    "AWR_1V2":      1.2,    # AWR1843 core (VDDIN/VIN_SRAM/VNWA, SWRS236)
    "AWR_1V3":      1.3,    # AWR1843 RF front-end (VIN_13RF)
    "AWR_1V8":      1.8,
    "BAT_RAW":      4.0,
    "BAT_PROT":     4.0,
    "ACTIVATE_HV":      33.0,   # aft activation rail (TPS61175 boost off COMP_5V); cap-free, boost sources the wire directly
    "USB_VBUS":     5.0,    # depot USB-C input; the Q_USB_OR ideal diode sits ON the USB nose (2026-11-20), so the 3 A comes up as BAT_PROT and VBUS crosses only as a presence signal
    "REG_IN_MAIN":  4.0,
    "BOOST_OUT":    3.87,
    "VCAP1":        1.2,    # legacy / unused (orphaned — H562 retired)
    "VCAP2":        1.2,
    "WBA_VDD11":    1.1,    # WBA55 SMPS output → core supply
    "CAM_PHY_REG":  1.2,    # AR0234CS internal LDO output (MIPI PHY)
    "XV_5V":        5.0,    # S4 transverter PA rail (MCP1640D boost off REG_IN_MAIN, on only for TX)
    "XV_LO_3V3":    3.3,    # S4 transverter LO (ADF4351) supply, ferrite-isolated from 3V3
}

# Ground nets — anything matching here gets kind="ground". Aliases are
# handled via merge_nets, so e.g. "GND" merges into FLEX_GND but the
# initial creation still needs the right kind.
_AUTO_GROUND_NETS: set[str] = {"GND", "FLEX_GND"}


def _net(d: Design, name: str, *, kind: str | None = None,
         voltage_v: float | None = None) -> NetHandle:
    """Return a NetHandle for `name`, creating the net if it doesn't
    exist yet. Idempotent — multiple boards can call this with the
    same net name and chain `.connect()` onto the result.

    Also handles the alias case: if `name` doesn't exist as a primary
    net name but does exist as an alias on a merged net (after
    `Design.merge_nets`), return a handle to that merged net rather
    than creating a fresh net with a colliding name.

    `kind` defaults to `None`, which triggers auto-classification:
      - known power-rail names → `kind="power"`, voltage from map
      - known ground-net names → `kind="ground"`
      - everything else        → `kind="signal"`
    Pass an explicit `kind` to override."""
    existing = d.net_by_name(name)
    if existing is None:
        for n in d.nets:
            if name in n.aliases:
                return NetHandle(d, n)
        if kind is None:
            if name in _AUTO_GROUND_NETS:
                kind = "ground"
            elif name in _AUTO_POWER_RAILS:
                kind = "power"
                if voltage_v is None:
                    voltage_v = _AUTO_POWER_RAILS[name]
            else:
                kind = "signal"
        if kind == "ground":
            return d.add_ground_net(name)
        if kind == "power":
            assert voltage_v is not None, \
                f"_net({name!r}, kind='power') requires voltage_v"
            return d.add_power_net(name, voltage_v=voltage_v)
        return d.add_signal_net(name)
    return NetHandle(d, existing)


def _add_antenna_pad(d: Design, *, ref: str, value: str, description: str,
                     board_tag: str):
    """Single-pin TestPoint pad standing in for a flex-etched antenna.
    SKiDL uses `Part("Device", "Antenna")` with a `TestPoint:` footprint;
    smash has no antenna factory yet so we synthesise the Chip inline.
    """
    fp = Footprint(
        name="TestPoint:TestPoint_Pad_1.0x1.0mm",
        package_class="TestPoint pad",
        pads=[Pad(num="1", position_mm=(0.0, 0.0),
                  size_mm=(1.0, 1.0), shape="rect", layer="F.Cu")],
        size_mm=(1.0, 1.0),
        source="kicad",
    )
    fp.ensure_courtyard_clearance()       # ring the lone pad so it can't abut
    return d.add_chip(
        ref=ref, manf_pn=None, footprint=fp, board_tag=board_tag,
        name=value, value=value, description=description,
        pins=[Pin(num="1", name="1", type="passive")],
    )


# PCB-surface dielectric foreshortening for a quarter-wave monopole
# printed on F.Cu of an FR4 board. ≈ 0.72 × free-space λ/4 (effective
# εr ~2 for surface micro-strip-like traces with mostly-air above).
_PCB_FORESHORTEN = 0.72

# Speed of light, mm per ns. Used to size printed antennas: free-space
# λ/4 (mm) = (c · ns/mm) / (4 · f_GHz).
_C_MM_PER_NS = 299.79


def _add_printed_pcb_monopole(d: Design, *, ref: str, board_tag: str,
                              freq_ghz: float, description: str | None = None,
                              note: str | None = None) -> Chip:
    """Printed quarter-wave monopole etched directly on the host board's
    F.Cu — no flex extension, no discrete radiating component.

    Trace geometry: L-shape from the feed pad, leg length sized to
    ¼ λ in air × `_PCB_FORESHORTEN` (FR4-surface dielectric loading),
    split half-and-half across two perpendicular legs so the radiator
    fits within ~`leg × leg` mm.

    Mirrors the NFC spiral pattern in `add_nfc_antenna_flex_27x50` —
    the radiator rides as `Footprint.copper_lines` on F.Cu.

    `weight_g = 0`, `height_mm = 0` so the bend / lateral-impact sim
    correctly treats it as a zero-body feature (it flexes WITH the
    PCB; there's no chip-body corner whose lever arm pulls on a
    solder joint). The footprint envelope is set to the radiator's
    real bounding box + IPC-7351 courtyard so the placer keeps other
    chips off the antenna area.

    Used for the bring-up / programming radios (WiFi 2.4 GHz, RF44
    4.4 GHz) where some loss / mismatch is acceptable. The LoRa-868
    radios still need real flex monopoles — λ/4 at 868 MHz is
    ~62 mm even with foreshortening, too long for the Ø34 nose tile.
    """
    leg_mm = (_C_MM_PER_NS / (4.0 * freq_ghz) * _PCB_FORESHORTEN) / 2.0

    # The body envelope is centred at the footprint origin (same
    # convention as `add_nfc_antenna_flex_27x50`) — the placer's
    # bbox calc reaches |W/2| from the placement centre. Feed pad
    # sits just inside one corner; the L-shape trace runs along
    # two perpendicular edges.
    W = H = round(leg_mm + 0.2, 2)              # +0.2 mm body margin around trace
    inset = 0.5                                 # pad/trace inset from edge
    feed_xy = (-W / 2 + inset, -H / 2 + inset)
    feed_pad = Pad(num="1", position_mm=feed_xy,
                   size_mm=(1.0, 1.0), shape="rect", layer="F.Cu")
    monopole_pts = [
        feed_xy,
        (W / 2 - inset, -H / 2 + inset),
        (W / 2 - inset, +H / 2 - inset),
    ]
    crt = 0.25                                  # IPC-7351 courtyard clearance
    # Footprint name embeds frequency for clarity ("PCB_Monopole_2G4",
    # "PCB_Monopole_4G4") — matches the naming style of the SamacSys
    # footprints already in the catalogue.
    tag = f"{freq_ghz:.1f}".replace(".", "G")
    fp = Footprint(
        name=f"PCB_Monopole_{tag}",
        package_class="Printed PCB monopole (F.Cu trace)",
        pads=[feed_pad],
        copper_lines=[{"layer": "F.Cu", "width_mm": 0.5,
                       "points": monopole_pts}],
        body_outline=[(-W/2, -H/2), (+W/2, -H/2), (+W/2, +H/2), (-W/2, +H/2)],
        courtyard=[(-W/2 - crt, -H/2 - crt), (+W/2 + crt, -H/2 - crt),
                   (+W/2 + crt, +H/2 + crt), (-W/2 - crt, +H/2 + crt)],
        size_mm=(W, H),
        height_mm=0.0,
        source="project",
    )
    return d.add_chip(
        ref=ref, manf_pn=None, footprint=fp, board_tag=board_tag,
        name=f"PCB_MONOPOLE_{tag}", value=f"PCB_MONOPOLE_{tag}",
        description=description or (
            f"{freq_ghz:.1f} GHz quarter-wave monopole — printed on "
            f"F.Cu of the host board, ~{2 * leg_mm:.0f} mm L-shape "
            "trace. Lossy / poorly-matched on purpose; acceptable for "
            "bring-up / programming radios where a real flex antenna "
            "isn't worth the assembly cost."),
        pins=[Pin(num="1", name="1", type="passive")],
        weight_g=0.0, height_mm=0.0,
        note=note,
    )


def _add_testpoint(d: Design, *, ref: str, board_tag: str):
    """1.5 mm-Ø round TestPoint pad. SKiDL uses Part("Connector", "TestPoint",
    footprint=FP_TP) with FP_TP="TestPoint:TestPoint_Pad_D1.5mm"."""
    fp = Footprint(
        name="TestPoint:TestPoint_Pad_D1.5mm",
        package_class="TestPoint pad (1.5 mm Ø)",
        pads=[Pad(num="1", position_mm=(0.0, 0.0),
                  size_mm=(1.5, 1.5), shape="circle", layer="F.Cu")],
        size_mm=(1.5, 1.5),
        source="kicad",
    )
    fp.ensure_courtyard_clearance()       # ring the lone pad so it can't abut
    return d.add_chip(
        ref=ref, manf_pn=None, footprint=fp, board_tag=board_tag,
        name="TestPoint", value="TestPoint",
        description="1.5 mm Ø round TestPoint pad",
        pins=[Pin(num="1", name="1", type="passive")],
    )


# ── boards ────────────────────────────────────────────────────────────────

def build_qpd_module(d: Design) -> None:
    """Marktech MT03-092 quadrant photodiode behind a 1064 nm bandpass
    lens. Photovoltaic mode: each anode → TIA on the same flex tile,
    common cathode → QPD_VREF (1.65 V) — the SAME potential the TIAs
    servo the anodes to, so every quadrant sits at TRUE zero bias.
    (Tying the cathode to GND with the anodes held at the 1.65 V
    virtual ground forward-biased all four junctions and railed the
    TIAs — the bug fixed in the datasheet audit.) Datasheet pin map
    (DS p2, verified): pin 2 = common cathode (backside butt weld),
    pin 5 = NC, anodes Q1→4, Q2→6, Q3→3, Q4→1 — so QPD_A..D = Q1..Q4
    (clockwise from top-left looking into the window).

    Net names are the *natural* per-board names from system.py. When
    flight_board's TIA wiring later connects to the same pins under
    different names (e.g. `QPD_TIA_A_INM`), smash auto-merges and
    keeps both names as aliases on the resulting net."""
    qpd = add_mt03_092_qpd(d, ref="U_QPD", board_tag="qpd_module")
    # (2026-11-18) Ø34 tile now (was Ø20): carries its own IR service-link pair.
    _add_ir_service_link(d, "qpd_module", "_Q")

    _net(d, "QPD_A").connect(qpd.pin("4"))
    _net(d, "QPD_VREF").connect(qpd.pin("2"))   # cathode common = the anodes' virtual-ground potential
    _net(d, "QPD_C").connect(qpd.pin("3"))
    _net(d, "QPD_B").connect(qpd.pin("6"))
    _net(d, "QPD_D").connect(qpd.pin("1"))


def build_companion_compute(d: Design) -> None:
    """STM32MP255 — the SINGLE system brain (consolidation): the Cortex-M33
    runs ArduPilot as the autonomous flight controller (M33-TD boot) + is the
    firmware root; the A35 + NPU run perception/planning; FC↔companion comms are
    on-chip (RPMsg). It owns the flight sensors, radar SPI, fins bus, CAN
    gateway, launch-detect ADC, WBA55 link, and power supervision — all wired in
    the M33 flight block below. Plus SMARTsemi KTDM4G4B626BGIEAT DDR4
    (4 Gbit, 512 MB) + 2× SPI-NAND storage + decoupling. The DQ bus uses the
    ST AN5724 DDR4 reference swizzle verbatim (within-byte, hardware-transparent
    — matches the ST footprint 1:1); the A/C bus keeps the ST reference mapping
    where it carries over. DDR4-specific A/C signals (ACT_n, BG0, muxed A14-16,
    PAR, ALERT_n) are DERIVED — cross-check vs the DDR4 reference."""
    # (2026-11-18) NO compute-rim IR copy: the VBPW34FAS courtyard (9.4 × 4.4 mm)
    # finds no rim spot clear of the EE-placed MPU / DDR4 / NAND_A / NAND_B, so
    # the payload-less `core` config has no IR link yet (open item — smaller
    # photodiode, or the layout EE frees a rim arc). Magnetic + piezo still cover it.

    BTAG = "companion_compute"

    # ── STM32MP255 — VFBGA-361 (10×10 mm), the AL/FAL3 variant (secure boot + crypto) ──────
    # Wired against the DAL3 SamacSys ballout (FAL3 identical) (per-package authority).
    # vs the FAK3 (VFBGA-424): pin names use single underscores
    # (DDR_Ax / CSI_x), DQS drops the underscore-N (DDR_DQS0N), and the
    # power-rail balls differ in count — so power/ground are wired by
    # whatever balls the package exposes rather than fixed loops.
    mpu = add_stm32mp257fal3(d, ref="U_MPU", board_tag=BTAG)   # (2026-11-22) sourcing swap, availability/decisions.csv: MP255FAL3 → MP257FAL3 (same balls, + NPU)

    # Supply rails — the FULL power tree (closes the long-deferred
    # "STPMIC2 power-tree pass": VDDCORE + 49 other power/strap balls
    # were floating, and DS14284 §3.9.1 requires VDD + VDDA18AON +
    # VDDCPU + VDDCORE just to START).
    for p in mpu.pins:
        if re.fullmatch(r"VDD_\d+", p.name):
            _net(d, "COMP_3V3").connect(mpu.pin(p.num))
        elif re.fullmatch(r"VDDCPU_\d+", p.name):
            _net(d, "COMP_0V9").connect(mpu.pin(p.num))   # 0.87–0.935 V hi-perf point ✓
        elif (re.fullmatch(r"VDDCORE_\d+", p.name)
              or p.name in ("VDDCSI", "VDDDSI", "VDDLVDS", "VDDCOMBOPHY",
                            "VDDCOMBOPHYTX", "VDDPCIECLK")):
            # 0.82 V core (ROC 0.79–0.842 V — the 0.9 V CPU rail is OUT of
            # range → dedicated PMIC BUCK5 rail). The six PHY domains ride
            # it per DS: "VDDCSI, VDDDSI, VDDLVDS, VDDCOMBOPHY,
            # VDDCOMBOPHYTX and VDDPCIECLK are usually connected to
            # VDDCORE" — this also powers the camera config's CSI PHY.
            _net(d, "COMP_0V82").connect(mpu.pin(p.num))
        elif re.fullmatch(r"VDDGPU_\d+", p.name):
            # GPU/NPU domain (perception runs on the NPU): 0.8 V typ →
            # shares the 0.82 V core rail (low DVFS point). Give it its
            # own buck later if NPU throughput needs the 0.9 V point.
            _net(d, "COMP_0V82").connect(mpu.pin(p.num))
        elif re.fullmatch(r"VDDQDDR_\d+", p.name):
            _net(d, "COMP_1V35").connect(mpu.pin(p.num))   # DDR3L I/O = 1.35 V
        elif p.name in ("VDDA18AON", "VDDA18PLL1", "VDDA18PLL2", "VDDA18PLL3",
                        "VDDA18DDR", "VDDA18ADC", "VDDA18CSI", "VDDA18DSI",
                        "VDDA18LVDS", "VDDA18COMBOPHY", "PDR_ON"):
            # (2026-11-21) PDR_ON: "must always be connected at board level
            # to VDDA18AON" (DS14285 p.78 Table 11 note 9) — it was floating
            _net(d, "COMP_1V8").connect(mpu.pin(p.num))   # 1.8 V analog domains
        elif re.fullmatch(r"VDDIO[1234](_\d+)?", p.name):
            # VDDIO2 = the NAND OSPI bank (PE8..15 — 3.3 V parts);
            # VDDIO4 = the PB bank (SYS_SPI / WBA HCI / I2C2, all 3.3 V).
            # ⚠ VDDIO1 (PE2/3/4) + VDDIO3 (PD0..11) carry the AWR SPI,
            # whose VIOIN runs 1.8 V — at 3.3 V this bank mismatches the
            # radar interface (open decision: re-pin the radar SPI into a
            # dedicated 1.8 V bank, or flip the AWR VIOIN+QSPI flash to
            # 3.3 V per the TI EVM). 3.3 V chosen meanwhile because the
            # PD bank's OTHER tenants (PWR_HOLD, COMP_OUT, SYS_SPI_CS,
            # IMU3_INT) are all 3.3 V signals.
            _net(d, "COMP_3V3").connect(mpu.pin(p.num))
        elif re.fullmatch(r"VSS_\d+", p.name) or p.name in ("VSSA", "VSSAON"):
            _net(d, "GND").connect(mpu.pin(p.num))
    _net(d, "COMP_3V3").connect(mpu.pin("VBAT"))
    _net(d, "COMP_3V3").connect(mpu.pin("VDD33UCPD"))   # UCPD unused — powered-safe
    # ADC reference (QPD + sensor channels): buffer-off input mode —
    # VREF+ = VDDA18ADC level, VREF− to analog ground.
    _net(d, "COMP_1V8").connect(mpu.pin("VREF+"))
    _net(d, "GND")     .connect(mpu.pin("VREF-"))
    # USB2 PHY impedance calibration (depot USB rides USB3DR): RTXRTUNE =
    # 200 Ω ±1 % to GND per DS. The unused USBH PHY (DP/DM open) keeps
    # its TXRTUNE open.
    res_between(d, "USB_TXRTUNE", "GND", "200",
                ref="R_MPU_TXRTUNE", board_tag=BTAG)
    _net(d, "USB_TXRTUNE").connect(mpu.pin("USB3DR_TXRTUNE"))
    _net(d, "V08_CAP") .connect(mpu.pin("V08CAP"))
    cap_to_gnd(d, "V08_CAP", "2.2uF", ref="C_MPU_V08CAP", board_tag=BTAG, pin=mpu.pin("V08CAP"))
    # Local decoupling for the newly-wired domains (bulk lives at the
    # PMIC; HF bypass pairs ride the ECM laminate). Local bulk is a
    # single 0603 2.2 µF (a 22 µF tantalum cost too much joint area at
    # the saturated power↔companion gap, 53 crossing nets in core_radar).
    cap_to_gnd(d, "COMP_0V82", "2.2uF", ref="C_MPU_0V82_BULK", board_tag=BTAG, pin=(mpu.ref, None))
    cap_to_gnd(d, "COMP_0V82", "100nF", ref="C_MPU_0V82_1",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=(mpu.ref, None))
    cap_to_gnd(d, "COMP_0V82", "100nF", ref="C_MPU_0V82_2",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=(mpu.ref, None))
    cap_to_gnd(d, "COMP_1V8",  "100nF", ref="C_MPU_18A_1",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=(mpu.ref, None))
    cap_to_gnd(d, "COMP_1V8",  "100nF", ref="C_MPU_18A_2",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=(mpu.ref, None))
    cap_to_gnd(d, "COMP_1V35", "100nF", ref="C_MPU_QDDR_1",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=(mpu.ref, None))
    cap_to_gnd(d, "COMP_1V35", "100nF", ref="C_MPU_QDDR_2",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=(mpu.ref, None))

    # ── System clocks — shock-tolerant MEMS oscillators in bypass mode ──
    # The MP25 needs an external HSE + LSE; both are MEMS clipped-sine
    # parts (no quartz — survives rapid deceleration) driving the IN pin
    # with the OUT pin left NC (HSEBYP/LSEBYP=1, no crystal feedback path),
    # mirroring the WBA55 HSE on the wakeup tile.
    #
    # HSE — 40 MHz into OSC_IN (R1); OSC_OUT (R2) NC.
    # feature="clock": rides the bottom face beneath the MP25's OSC balls
    # (the top face is full with the BGA + DDR4 + NAND).
    hse_osc = add_sit1602bi_12_xxe_40(d, ref="Y_MPU_HSE", board_tag=BTAG, vdd="33",   # (2026-11-22) 3.3 V code
                                      feature="clock")
    _net(d, "COMP_3V3")   .connect(hse_osc.pin("1"))  # STANDBY# tied high
    _net(d, "GND")        .connect(hse_osc.pin("2"))
    _net(d, "COMP_HSE_IN").connect(hse_osc.pin("3"))  # OUT
    _net(d, "COMP_3V3")   .connect(hse_osc.pin("4"))  # VDD
    _net(d, "COMP_HSE_IN").connect(mpu.pin("OSC_IN"))   # R1
    cap_to_gnd(d, "COMP_3V3", "100nF", ref="C_MPU_HSE_VDD",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=hse_osc.pin("4"))
    #
    # LSE — 32.768 kHz into OSC32_IN (M2); OSC32_OUT (M1) NC. Real LSE
    # (not internal LSI) so the Linux/flight RTC keeps accurate wall-clock
    # time for logs + cert validity. SiT1630 pins: 1=GND, 2/3=NC(→GND),
    # 4=VDD, 5=OUT.
    # (2026-11-20, user) SiT1533 2.0×1.2×0.55 mm instead of the 1.45 mm SiT1630
    lse_osc = add_sit1533ai_h4_dcc_32_768e(d, ref="Y_MPU_LSE", board_tag=BTAG,
                                           feature="clock")
    _net(d, "GND")        .connect(lse_osc.pin("GND"))
    _net(d, "COMP_3V3")   .connect(lse_osc.pin("VDD"))
    _net(d, "COMP_LSE_IN").connect(lse_osc.pin("CLK_OUT"))
    _net(d, "COMP_LSE_IN").connect(mpu.pin("OSC32_IN"))  # M2
    cap_to_gnd(d, "COMP_3V3", "100nF", ref="C_MPU_LSE_VDD",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=lse_osc.pin("VDD"))

    # FC↔companion links (UART4 console + SWD to the H562) REMOVED — the M33
    # IS the flight controller now, so M33↔A35 comms are on-chip (RPMsg / shared
    # SRAM). PD11/PD10/PA13/PA14/PA15 are freed for the flight wiring below.

    # OCTOSPI → two 512 MB Micron SPI NAND dies (1 GB total) co-located on
    # THIS tile (storage bus entirely on-tile — crosses no board-to-board
    # joint). Shared quad bus (CLK + IO0-3) with a per-die chip-select; the
    # two physical dies give die-level A/B rootfs redundancy. Replaces the
    # parallel x8 NAND that used to sit on companion_io.
    _net(d, "NAND_OSPI_CLK").connect(mpu.pin("PD13"))
    _net(d, "NAND_OSPI_IO0").connect(mpu.pin("PE15"))
    _net(d, "NAND_OSPI_IO1").connect(mpu.pin("PE12"))
    _net(d, "NAND_OSPI_IO2").connect(mpu.pin("PE11"))
    _net(d, "NAND_OSPI_IO3").connect(mpu.pin("PE8"))
    _net(d, "NAND_OSPI_CS0").connect(mpu.pin("PB12"))
    _net(d, "NAND_OSPI_CS1").connect(mpu.pin("PE9"))
    for die, cs in (("A", "NAND_OSPI_CS0"), ("B", "NAND_OSPI_CS1")):
        nand = add_mt29f4g01abafdwb_it_f(d, ref=f"U_NAND_{die}",
                                         board_tag=BTAG,
                                         height_mm=0.65)   # U-PDFN-8 8×6 (IPC SON127P800X600X65): factory left it unset
        _net(d, cs)             .connect(nand.pin("1"))   # CS#
        _net(d, "NAND_OSPI_IO1").connect(nand.pin("2"))   # SO/IO1
        _net(d, "NAND_OSPI_IO2").connect(nand.pin("3"))   # WP#/IO2
        _net(d, "GND")          .connect(nand.pin("4"))   # VSS
        _net(d, "NAND_OSPI_IO0").connect(nand.pin("5"))   # SI/IO0
        _net(d, "NAND_OSPI_CLK").connect(nand.pin("6"))   # SCK
        _net(d, "NAND_OSPI_IO3").connect(nand.pin("7"))   # HOLD#/IO3
        _net(d, "COMP_3V3")     .connect(nand.pin("8"))   # VCC
        cap_to_gnd(d, "COMP_3V3", "100nF", ref=f"C_NAND_{die}_VCC",
                   embedded_cap_absorbs=True, board_tag=BTAG, pin=nand.pin("8"))
        cap_to_gnd(d, "COMP_3V3", "1uF", ref=f"C_NAND_{die}_BULK",
                   board_tag=BTAG, pin=nand.pin("8"))

    # MIPI CSI-2 (DCMIPP, 2-lane)
    _net(d, "CAM_CSI_CLK_P").connect(mpu.pin("CSI_CKP"))
    _net(d, "CAM_CSI_CLK_N").connect(mpu.pin("CSI_CKN"))
    _net(d, "CAM_CSI_D0_P") .connect(mpu.pin("CSI_D0P"))
    _net(d, "CAM_CSI_D0_N") .connect(mpu.pin("CSI_D0N"))
    _net(d, "CAM_CSI_D1_P") .connect(mpu.pin("CSI_D1P"))
    _net(d, "CAM_CSI_D1_N") .connect(mpu.pin("CSI_D1N"))
    _net(d, "CSI_REXT").connect(mpu.pin("CSI_REXT"))
    res_between(d, "CSI_REXT", "GND", "12k", ref="R_MPU_CSI_REXT", board_tag=BTAG)
    # (2026-11-21) CAM_EXTCLK no longer from PA8 (3.3 V bank into the sensor's
    # 1.8 V input): the camera board has its own 27 MHz DSC1001 at 1.8 V.
    _net(d, "CAM_NRST").connect(mpu.pin("PA9"))        # (2026-11-21) open-drain → AR0234 RESET_BAR

    # ═══════════════════════════════════════════════════════════════════════
    # FLIGHT CONTROL — Cortex-M33. Consolidation: the M33 is the autonomous
    # flight controller (M33-TD boot) and firmware root, replacing the former
    # H562; the A35 + NPU run perception/planning; FC↔companion is on-chip
    # RPMsg. Pins are RIF-assignable to the M33 secure domain. The allocation
    # is AF-validated against the DAL3 table (reused from the FAK3 by name).
    # ═══════════════════════════════════════════════════════════════════════

    # System control / sensor / payload bus (SYS_I2C = I2C1)
    _net(d, "SYS_I2C_SCL").connect(mpu.pin("PG13"))   # I2C1_SCL
    _net(d, "SYS_I2C_SDA").connect(mpu.pin("PI1"))    # I2C1_SDA

    # Radar host SPI (SPI1) — control + host-SPI boot stream + detections in
    # from the AWR1843AOP. The radar runs its own detection chain on-chip
    # (C674x DSP + HWA) and returns a point cloud / object list over this link;
    # AWR_DRDY is its data-ready interrupt. See build_radar_module_awr1843aop.
    _net(d, "AWR_SPI_CLK") .connect(mpu.pin("PD11"))  # SPI1_SCK
    _net(d, "AWR_SPI_MISO").connect(mpu.pin("PE2"))   # SPI1_MISO
    _net(d, "AWR_SPI_MOSI").connect(mpu.pin("PE4"))   # SPI1_MOSI
    _net(d, "AWR_SPI_CS")  .connect(mpu.pin("PD2"))   # SPI1_NSS
    _net(d, "AWR_NRESET").connect(mpu.pin("PI6"))
    _net(d, "AWR_FAULT") .connect(mpu.pin("PI7"))
    _net(d, "RADAR_EN")  .connect(mpu.pin("PE10"))
    _net(d, "AWR_DRDY")  .connect(mpu.pin("PF1"))     # radar detections-ready IRQ (EXTI)

    # No gigabit RGMII to the radar: the AWR1843AOP streams *detections*, not
    # raw range-Doppler frames, over the SPI link above. The former MP25 GMAC
    # pins (PA15/PC1/PH10/PH11/PA13/PC0 + PC2/PH12/PH13/PA11/PA14) are freed.
    # (AWR2944/2E44P range-Doppler-over-RGMII path retired with the AoP swap.)

    # (Nose contact switch deleted — impact is sensed by the piezo disk
    # (fin_ble_board top since the 2026-07-31 stack reorder), which reads
    # the deceleration. PD10 has since been taken by H3LIS_INT1.)
    # (Nose status LEDs RETIRED with the IR-link change — PG7/PG8 freed;
    # muzzle state is queried over the IR service link now.)
    # (2026-11-18) PG7/PG8 re-used for the "healthy and running" beacons:
    # PG7 keys the embedded aft_end coil driver, PG8 drives the piezo
    # vibration coupling (see the piezo block).
    _net(d, "HEALTH_COIL_TX").connect(mpu.pin("PG7"))
    _net(d, "PIEZO_TX")      .connect(mpu.pin("PG8"))

    # Fins/actuator node bus (SYS_SPI master, SPI2)
    _net(d, "SYS_SPI_SCLK")  .connect(mpu.pin("PB0"))   # SPI2_SCK
    _net(d, "SYS_SPI_MISO")  .connect(mpu.pin("PB6"))   # SPI2_MISO
    _net(d, "SYS_SPI_MOSI")  .connect(mpu.pin("PB2"))   # SPI2_MOSI
    _net(d, "SYS_SPI_CS_FIN").connect(mpu.pin("PD6"))   # GPIO chip-select

    # Flight sensors (mag + 3× IMU) — I²C masters on the M33; the sensors live
    # on the sensor tile and reach here over the LGA backbone.
    _net(d, "I2C2_SCL").connect(mpu.pin("PB5"))   # I2C2: mag + IMU1
    _net(d, "I2C2_SDA").connect(mpu.pin("PB4"))
    _net(d, "I2C3_SCL").connect(mpu.pin("PH6"))   # I2C3: IMU2 + IMU3 (SA0 split)
    _net(d, "I2C3_SDA").connect(mpu.pin("PH2"))
    _net(d, "MAG_DRDY").connect(mpu.pin("PE1"))    # EXTI
    _net(d, "IMU1_INT").connect(mpu.pin("PE5"))
    _net(d, "IMU2_INT").connect(mpu.pin("PE7"))
    _net(d, "IMU3_INT").connect(mpu.pin("PD7"))
    _net(d, "H3LIS_INT1").connect(mpu.pin("PD10"))  # EXTI10 — ±400 g launch
    # witness (moved off the WBA with the IR-wake change; alive from
    # Ready (merged stage), quantitative rapid deceleration beside the piezo's COMP_OUT edge)

    # Aim-point steering (QPD TIAs) for the sensor drop, plus the drop-shock
    # piezo and the parachute cutters.
    # PARACHUTE_CUTTER_SET arms the high side; ACTIVATE_CONFIRM reads the 33 V rail.
    _net(d, "QPD_TIA_A").connect(mpu.pin("PB11"))  # ADC1
    _net(d, "QPD_TIA_B").connect(mpu.pin("PG15"))  # ADC1
    _net(d, "QPD_TIA_C").connect(mpu.pin("PI11"))  # ADC1
    _net(d, "QPD_TIA_D").connect(mpu.pin("PG11"))  # ADC2
    _net(d, "COMP_OUT").connect(mpu.pin("PD5"))         # TLV3691 piezo comparator EXTI
    _net(d, "PARACHUTE_CUTTER_SET").connect(mpu.pin("PE0"))
    _net(d, "ACTIVATE_CONFIRM").connect(mpu.pin("PD9"))

    # WBA55 wake/BLE radio: HCI (SPI3 host) + LPUART (firmware/console) + boot
    # straps. The M33 is the firmware root that flashes the WBA55.
    _net(d, "WBA_HCI_SCK") .connect(mpu.pin("PE3"))   # SPI3_SCK
    _net(d, "WBA_HCI_MISO").connect(mpu.pin("PB10"))  # SPI3_MISO
    _net(d, "WBA_HCI_MOSI").connect(mpu.pin("PB8"))   # SPI3_MOSI
    _net(d, "WBA_HCI_NSS") .connect(mpu.pin("PE13"))
    _net(d, "WBA_HCI_IRQ") .connect(mpu.pin("PB9"))   # host-wake EXTI
    _net(d, "WBA_UART_TX").connect(mpu.pin("PA10"))   # USART2_RX ← WBA55 TX
    _net(d, "WBA_UART_RX").connect(mpu.pin("PA4"))    # USART2_TX → WBA55 RX
    # WBA reset via Q_WBA_RST gate (HIGH = reset) — rule-sweep F1: PB3
    # is a TT pin on VDDIO4/COMP_3V3; tied straight onto the 3V3_AON-
    # pulled WBA_NRST it back-fed ~280 µA through the clamp into the
    # dead MP25 all standby (28 µA floor → ~310 µA). A FET gate has no
    # clamp path. With BOOT0 (PI10) this is the post-pot WBA reflash +
    # hung-radio recovery mechanism.
    _net(d, "WBA_RST_CMD").connect(mpu.pin("PB3"))    # HIGH = reset WBA
    _net(d, "WBA_BOOT0").connect(mpu.pin("PI10"))     # boot strap

    # Control + status GPIO
    _net(d, "PWR_HOLD")  .connect(mpu.pin("PD0"))
    # (2026-11-21) RF_SW_CTRL (PD4) removed: it drove the long-gone BGS12 LoRa
    # diversity switch (WLE5 era); today's BGS12s are steered by the WBA55 /
    # LR2021. PD4 is a spare GPIO.
    _net(d, "GPIO_EXT_0").connect(mpu.pin("PB7"))
    _net(d, "GPIO_EXT_1").connect(mpu.pin("PD3"))
    _net(d, "GPIO_EXT_2").connect(mpu.pin("PB1"))
    _net(d, "GPIO_EXT_3").connect(mpu.pin("PD8"))
    # (nose status LEDs dropped — they crossed the companion↔flight sensor
    # joint, which is the land-budget bottleneck; status goes over CAN/BLE.)

    # Power supervision — orphans now reach the M33 (battery/eFuse/thermal);
    # the STPMIC25 is the MP25's own PMIC (PMIC control wired in the power tree).
    _net(d, "BAT_ISO_DRIVE").connect(mpu.pin("PE6"))  # ideal-diode low-drop enable (out; series R on power_board lets the USB interlock win)
    # PG10 / PF15 freed: eFuse BAT_PGOOD / BAT_IMON removed with the eFuse
    _net(d, "TMP1_ALERT") .connect(mpu.pin("PD1"))    # thermal trip EXTI
    _net(d, "PMIC_PWR_OK").connect(mpu.pin("PI4"))

    # ── EXT_CAN client-extension gateway — FDCAN1 controller side ──────────
    # The MP25 FDCAN1 drives EXT_CAN_TX/RX; the TCAN1042 transceiver itself
    # now lives on flight_board (moved off companion_compute to free top-face
    # room for the un-rotated DDR4 + SPI-NAND). EXT_CAN_TX/RX cross to the
    # transceiver over the flight↔companion LGA backbone. A standard CAN bus
    # is exposed at the activation + nose connectors so third-party CAN
    # payloads can join; the M33 bridges EXT_CAN ↔ SYS_SPI/I2C.
    _net(d, "EXT_CAN_TX").connect(mpu.pin("PD15"))   # FDCAN1_TX
    _net(d, "EXT_CAN_RX").connect(mpu.pin("PD14"))   # FDCAN1_RX

    # ── Depot USB (USB3DR dual-role, Full-speed gadget) ─────────────────
    # The post-potting depot interface: exposed at the NOSE (the only access in
    # that phase), it presents a USB-Ethernet gadget for SSH into A35 Linux +
    # diagnostics, and USB-DFU for signed firmware pushes. FULL-SPEED on purpose
    # — HS (480 Mbps) can't survive the ~4 LGA joints from companion to nose;
    # FS (12 Mbps) is robust over that and ample for SSH + a depot rootfs push.
    # Depot power DOES come in over USB VBUS (USB_VBUS → Q_USB_OR ideal diode on the
    # USB nose since 2026-11-20 + Q_USB_WAKE/Q_USB_WAKE2 wake; Q_ISO's reverse-block keeps the
    # cells at zero load during the session) — the old "power on the nose BAT_PROT
    # pad" note predated the USB-C wake work.
    _net(d, "USB_D_P").connect(mpu.pin("USB3DR_DP"))
    _net(d, "USB_D_N").connect(mpu.pin("USB3DR_DM"))
    _net(d, "USB_VBUS_DET").connect(mpu.pin("PC10"))   # USB3DR_VBUSEN (host-attached sense)
    _net(d, "COMP_3V3")    .connect(mpu.pin("VDD33USB"))
    _net(d, "COMP_1V8").connect(mpu.pin("VDDA18USB"))
    cap_to_gnd(d, "COMP_3V3", "1uF", ref="C_USB_33", board_tag=BTAG, pin=mpu.pin("VDD33USB"))
    cap_to_gnd(d, "COMP_1V8", "100nF", ref="C_USB_18",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=mpu.pin("VDDA18USB"))
    # PC10 = USB3DR_VBUSEN ("VBUS valid" sense for the device stack),
    # strapped permanently high (rule-sweep F4): the depot session powers
    # the whole round from VBUS, so whenever the MP25 runs with a cable
    # in, VBUS is by construction present — a real divider off USB_VBUS
    # would spend a crossing land for no information. (Ref name is a
    # fossil: this is a pull-UP.)
    res_between(d, "COMP_3V3", "USB_VBUS_DET", "100k",
                ref="R_USB_VBUS_PD", board_tag=BTAG)

    # ── Stage-1 factory debug (JTAG/SWD + reset + BOOT0) ────────────────
    # Reached via the aft activation array (the once-only, pre-pot interface).
    # This is the MP25's own debug port (the H562↔MP25 SWD link is gone); it
    # goes electrically inert after the RDP/OTP lockdown at the end of stage 1.
    _net(d, "COMP_SWDCLK").connect(mpu.pin("JTCK-SWCLK"))   # SWCLK
    _net(d, "COMP_SWDIO") .connect(mpu.pin("JTMS-SWDIO"))   # SWDIO
    _net(d, "SWO")        .connect(mpu.pin("JTDO-TRACESWO"))
    _net(d, "NRST")       .connect(mpu.pin("NRST"))
    _net(d, "BOOT0")      .connect(mpu.pin("BOOT0"))        # force serial boot
    # (2026-11-21, user: dev board must flash + diagnose the tower) DEBUG
    # CONSOLE on USART6 — PF5 TX / PF4 RX, one of the MP25 ROM-bootloader
    # UARTs (DS boot-interface table), so the aft fixture also serial-boots it.
    _net(d, "MP25_CONSOLE_TX").connect(mpu.pin("PF5"))  # USART6_TX → aft TP_CONS_TX
    _net(d, "MP25_CONSOLE_RX").connect(mpu.pin("PF4"))  # USART6_RX ← aft TP_CONS_RX
    _net(d, "GND").connect(mpu.pin("BOOT1"))   # boot-mode straps — defined low;
    _net(d, "GND").connect(mpu.pin("BOOT2"))   # the OTP overrides boot device
    _net(d, "GND").connect(mpu.pin("BOOT3"))   # after provisioning.
    res_between(d, "COMP_3V3", "NRST", "10k", ref="R_MPU_NRST", board_tag=BTAG)
    cap_to_gnd(d, "NRST", "100nF", ref="C_MPU_NRST", board_tag=BTAG, pin=mpu.pin("NRST"))
    res_between(d, "GND", "BOOT0", "10k", ref="R_MPU_BOOT0", board_tag=BTAG)

    # Bulk decoupling on supply rails
    cap_to_gnd(d, "COMP_5V",  "10uF",  ref="C_MPU_5V",   board_tag=BTAG)
    cap_to_gnd(d, "COMP_5V",  "100nF", ref="C_MPU_5V2",
               embedded_cap_absorbs=True, board_tag=BTAG)
    cap_to_gnd(d, "COMP_3V3", "10uF",  ref="C_MPU_33",   board_tag=BTAG)
    cap_to_gnd(d, "COMP_3V3", "100nF", ref="C_MPU_33b",
               embedded_cap_absorbs=True, board_tag=BTAG)

    # ── DDR3L (Micron MT41K256M16TW-107 IT:P, VFBGA-96 8×14; 1.35 V) ──
    # (2026-11-22, user) the DDR4 (SMARTsemi KTDM4G4B626BGIEAT) went OBSOLETE
    # and no orderable DDR4/LPDDR4 x16 had stock at two suppliers; the
    # MT41K256M16TW-107 IT:P is stocked at Mouser/Farnell/Digi-Key (38k), with
    # SMARTsemi KTDM4G3C618BGIEAT and ISSI IS43TR16256BL as same-land
    # alternates (availability/bom_alternates.csv). DDR3L-1866 on a 16-bit bus
    # (MP25: DDR3L up to 1066 MHz) — ~20 % less bandwidth than the DDR4-2400.
    # A/C + data mapping = ST's AL (10×10) DDR3L template VERBATIM
    # (Research/STM32MP25xxAx/STM32MP25xxAL/1DDR3L_Memory_length_equalization_
    # in_mm_for_STM32MP25xxAL (10x10)_Template.xlsx, BALL NAME → NET NAME).
    # UNROUTED (user): the DDR4 pre-route (smash.layout.ddr_route, mined from
    # ST's routed DDR4 reference) does not carry over — the layout EE routes
    # the DDR3L with ST's length template (CLK ±3.55 mm A/C window, DQS ±1.42).
    ddr = add_mt41k256m16tw_107_ptr(d, ref="U_DDR", board_tag=BTAG,
                                    manf_pn="MT41K256M16TW-107 IT:P",
                                    name="MT41K256M16TW-107 IT:P", value="MT41K256M16TW-107 IT:P",
                                    height_mm=1.2)   # Micron TW VFBGA-96: 1.2 max (factory left it unset)

    # Data: byte 0 = L*, byte 1 = U* (1:1 per the ST template)
    for i in range(8):
        _net(d, f"DDR3L_DQ{i}").connect(ddr.pin(f"DQ{i}"))
        _net(d, f"DDR3L_DQ{i + 8}").connect(ddr.pin(f"DQ{i + 8}"))
    _net(d, "DDR3L_DQS0_P").connect(ddr.pin("LDQS")); _net(d, "DDR3L_DQS0_N").connect(ddr.pin("LDQS#"))
    _net(d, "DDR3L_DQS1_P").connect(ddr.pin("UDQS")); _net(d, "DDR3L_DQS1_N").connect(ddr.pin("UDQS#"))
    _net(d, "DDR3L_DM0").connect(ddr.pin("LDM")); _net(d, "DDR3L_DM1").connect(ddr.pin("UDM"))
    # Address A0..A14 (4 Gb x16: 32K rows; A15 not used), bank, command
    for i in range(15):
        pin = {10: "A10/AP", 12: "A12/BC#"}.get(i, f"A{i}")
        _net(d, f"DDR3L_A{i}").connect(ddr.pin(pin))
    for k in range(3):
        _net(d, f"DDR3L_BA{k}").connect(ddr.pin(f"BA{k}"))
    for net, pin in (("DDR3L_RAS_N", "RAS#"), ("DDR3L_CAS_N", "CAS#"), ("DDR3L_WE_N", "WE#"),
                     ("DDR3L_CK_P", "CK"), ("DDR3L_CK_N", "CK#"), ("DDR3L_CKE", "CKE"),
                     ("DDR3L_CS_N", "CS#"), ("DDR3L_ODT", "ODT"), ("DDR3L_RESET_N", "RESET#")):
        _net(d, net).connect(ddr.pin(pin))
    res_between(d, "DDR3L_RESET_N", "GND", "10k", ref="R_DDR_RESETN_PD", board_tag=BTAG)

    # References: VREFCA + VREFDQ = VDD/2 (0.675 V) from one 1k/1k divider,
    # each pin with its own 100 nF; ZQ 240 Ω 1 % to GND.
    _net(d, "DDR3L_VREF").connect(ddr.pin("VREFCA")); _net(d, "DDR3L_VREF").connect(ddr.pin("VREFDQ"))
    _net(d, "DDR3L_ZQ").connect(ddr.pin("ZQ"))
    # Power: VDD/VDDQ = 1.35 V (COMP_1V35, PMIC BUCK6)
    for p in ddr.pins:
        if re.fullmatch(r"VDDQ?_\d+", p.name):
            _net(d, "COMP_1V35").connect(p)
        elif re.fullmatch(r"VSSQ?_\d+", p.name):
            _net(d, "GND").connect(p)

    # ── MPU-side DDR3L wiring (ST AL template, BALL NAME → NET NAME) ──
    for i in range(16):
        _net(d, f"DDR3L_DQ{i}").connect(mpu.pin(f"DDR_DQ{i}"))
    _net(d, "DDR3L_DQS0_P").connect(mpu.pin("DDR_DQS0P")); _net(d, "DDR3L_DQS0_N").connect(mpu.pin("DDR_DQS0N"))
    _net(d, "DDR3L_DQS1_P").connect(mpu.pin("DDR_DQS1P")); _net(d, "DDR3L_DQS1_N").connect(mpu.pin("DDR_DQS1N"))
    _net(d, "DDR3L_DM0").connect(mpu.pin("DDR_DQM0")); _net(d, "DDR3L_DM1").connect(mpu.pin("DDR_DQM1"))
    _DDR3L_AC = {   # MPU ball DDR_A<n> → DDR3L net (template rows; DDR_A1/A6/A7 = NA)
        0: "CKE", 2: "CS_N", 3: "ODT", 4: "CK_P", 5: "CK_N", 8: "A0", 9: "A7", 10: "A2", 11: "A9",
        12: "A8", 13: "WE_N", 14: "RAS_N", 15: "A12", 16: "A10", 17: "A14", 18: "A4", 20: "A13",
        21: "A5", 22: "A3", 23: "BA0", 25: "BA2", 26: "CAS_N", 28: "A1", 29: "A11", 30: "BA1", 31: "A6"}
    # (DDR_A27 → DDR3L A15 in the template: unused on a 4 Gb x16, left open)
    for ball, sig in _DDR3L_AC.items():
        _net(d, f"DDR3L_{sig}").connect(mpu.pin(f"DDR_A{ball}"))
    _net(d, "DDR3L_RESET_N").connect(mpu.pin("DDR_RESETN"))
    _net(d, "DDR3L_VREF").connect(mpu.pin("DDR_VREF"))
    try:
        _net(d, "MPU_DDR_ZQ").connect(mpu.pin("DDR_ZQ"))
        cap_to_gnd(d, "MPU_DDR_ZQ", "0.1uF", ref="C_MPU_DDR_ZQ",
                   board_tag=BTAG, pin=mpu.pin("DDR_ZQ"))
    except KeyError:
        pass

    # Calibration + reference generation
    res_between(d, "DDR3L_ZQ", "GND", "240", ref="R_DDR_ZQ", board_tag=BTAG)
    # (2026-11-22, user) VREF = STPMIC25 VREFDDR (pin 45, sink-source LDO fed
    # internally from VOUT6 = COMP_1V35 → tracks VDDQ/2, ±1 %, 5 mA rms); was a
    # 1k/1k divider (0.7 mA standing). FIRMWARE: enable REFDDR (REFDDR_MAIN_CR
    # 0x64 EN) together with BUCK6. Local 100 nF at each VREF ball stays.
    cap_to_gnd(d, "DDR3L_VREF", "100nF", ref="C_DDR_VREFCA", board_tag=BTAG, pin=ddr.pin("VREFCA"))
    cap_to_gnd(d, "DDR3L_VREF", "100nF", ref="C_DDR_VREFDQ", board_tag=BTAG, pin=ddr.pin("VREFDQ"))

    # 1.35 V decoupling: 6× per-ball 100 nF (ECM) + 2× 10 µF bulk
    for n in range(1, 7):
        cap_to_gnd(d, "COMP_1V35", "100nF", ref=f"C_DDR_VDD{n}",
                   embedded_cap_absorbs=True, board_tag=BTAG, pin=(ddr.ref, None))
    cap_to_gnd(d, "COMP_1V35", "10uF", ref="C_DDR_BULK1", board_tag=BTAG, pin=(ddr.ref, None))
    cap_to_gnd(d, "COMP_1V35", "10uF", ref="C_DDR_BULK2", board_tag=BTAG, pin=(ddr.ref, None))


def build_radar_module(d: Design) -> None:
    """AWR2944 77 GHz FMCW radar SoC + 1.0V buck (LMR10510) + 1.8V LDO
    (LDL112PV18R). Host link is SPI to the MP25 Cortex-M33 (also its host-SPI
    boot path — the radar has no local flash, RAM-loaded every power-up). The
    image is streamed ENCRYPTED: the AWR HSM secure-boot (TI HS-SE, AES-256
    with the customer MEK + MPK signature, keys in the AWR eFuses) decrypts +
    verifies it in-radar, so plaintext never crosses the SPI wire — see
    firmware_lifecycle.md. The buck + LDO tap always-on BAT_PROT directly and
    self-gate via their EN pins (RADAR_EN, M33 PE10) — no discrete load switch;
    a 100k pull-down keeps the radar OFF when the M33 is unpowered."""
    BTAG = "radar_module"

    # ── 1.0V buck (LMR10510XMFE/NOPB, SOT-23-5) ─────────────────────
    buck = add_lmr10510ysde_nopb(d, ref="U_AWR_BUCK", board_tag=BTAG)   # (2026-11-22) WSON-6 0.8 mm (was SOT-23-5 1.45)
    _net(d, "BAT_PROT")  .connect(buck.pin("VIN"))   # always-on tap (no load switch)
    _net(d, "BAT_PROT")  .connect(buck.pin("VINA"))
    _net(d, "GND")       .connect(buck.pin("GND"))
    _net(d, "GND")       .connect(buck.pin("DAP"))
    _net(d, "AWR_1V0_SW").connect(buck.pin("SW"))
    _net(d, "RADAR_EN")  .connect(buck.pin("EN"))    # M33-gated via the reg EN
    _net(d, "AWR_1V0_FB").connect(buck.pin("FB"))
    # Radar power: the buck + LDO tap always-on BAT_PROT and self-gate via their
    # EN pins tied to RADAR_EN (M33 PE10) — no upstream FET. The 100k pull-down
    # keeps both regulators OFF (radar unpowered) whenever the M33 is unpowered
    # (shelf/standby); RADAR_EN's 3V3 logic-high clears the EN thresholds
    # (≥1.4 V), which is what the old BSS138 level-shifter existed for.
    res_between(d, "RADAR_EN", "GND", "100k", ref="R_RADAR_EN_PD", board_tag=BTAG)

    # system.py uses L_0402 for the AWR buck inductor (Wurth WE-KI
    # family goes up to 22 µH in 0402 even though smash's auto-
    # dispatch is conservative — force the family explicitly).
    ind_between(d, "AWR_1V0_SW", "AWR_1V0", "4.7uH",
                ref="L_AWR_BUCK", family="we-ki", board_tag=BTAG)
    res_between(d, "AWR_1V0",    "AWR_1V0_FB", "30k",
                ref="R_AWR_FB1", board_tag=BTAG)
    res_between(d, "AWR_1V0_FB", "GND",        "100k",
                ref="R_AWR_FB2", board_tag=BTAG)

    cap_to_gnd(d, "BAT_PROT", "10uF",  ref="C_AWR_BUCK_IN1", board_tag=BTAG, pin=buck.pin("VIN"))
    cap_to_gnd(d, "BAT_PROT", "100nF", ref="C_AWR_BUCK_IN2", board_tag=BTAG, pin=buck.pin("VIN"))
    cap_to_gnd(d, "AWR_1V0",   "22uF",  ref="C_AWR_1V0_1",    board_tag=BTAG, pin=(buck.ref, None))
    cap_to_gnd(d, "AWR_1V0",   "100nF", ref="C_AWR_1V0_2",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=(buck.ref, None))

    # ── 1.8V LDO ────────────────────────────────────────────────────
    ldo18 = add_xc6220b181mr_g(d, ref="U_AWR_LDO18", board_tag=BTAG)
    _net(d, "BAT_PROT").connect(ldo18.pin("VIN"))
    _net(d, "GND")     .connect(ldo18.pin("GND"))
    _net(d, "RADAR_EN").connect(ldo18.pin("EN"))
    _net(d, "AWR_1V8")  .connect(ldo18.pin("VOUT"))
    # (2026-11-22) XC6220 SOT-25 has no exposed pad (LDL112 EP tie removed)

    cap_to_gnd(d, "AWR_1V8", "10uF",  ref="C_AWR_1V8_1", board_tag=BTAG, pin=ldo18.pin("VOUT"))
    cap_to_gnd(d, "AWR_1V8", "100nF", ref="C_AWR_1V8_2",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=ldo18.pin("VOUT"))

    # ── AWR2944 ─────────────────────────────────────────────────────
    awr = add_awr2944abgaltrq1(d, ref="U_AWR", board_tag=BTAG)

    # 1.0V digital + RF analog
    for n in range(1, 18):  _net(d, "AWR_1V0").connect(awr.pin(f"VDD_{n}"))
    _net(d, "AWR_1V0").connect(awr.pin("VDD_SRAM"))
    _net(d, "AWR_1V0").connect(awr.pin("VDDA_10RF2_1"))
    _net(d, "AWR_1V0").connect(awr.pin("VDDA_10RF2_2"))
    _net(d, "AWR_1V0").connect(awr.pin("VIDDA__10RF1"))

    # 1.8V analog + I/O
    for nm in ("VDDA_18BB", "VDDA_18CLK", "VDDA_18PM", "VDDA_18VCO",
               "VIOIN__18CSI", "VIOIN__18LVDS"):
        _net(d, "AWR_1V8").connect(awr.pin(nm))
    for n in range(1, 4):  _net(d, "AWR_1V8").connect(awr.pin(f"VIOIN_18_{n}"))
    for n in range(1, 6):  _net(d, "AWR_1V8").connect(awr.pin(f"VIOIN_{n}"))

    # Internal-regulator decoupling
    _net(d, "VBGAP")        .connect(awr.pin("VBGAP"))
    _net(d, "VOUT__14APLL") .connect(awr.pin("VOUT__14APLL"))
    _net(d, "VOUT__14SYNTH").connect(awr.pin("VOUT__14SYNTH"))
    cap_to_gnd(d, "VBGAP",         "100nF", ref="C_AWR_VBGAP",   board_tag=BTAG, pin=awr.pin("VBGAP"))
    cap_to_gnd(d, "VOUT__14APLL",  "100nF", ref="C_AWR_14APLL",  board_tag=BTAG, pin=awr.pin("VOUT__14APLL"))
    cap_to_gnd(d, "VOUT__14SYNTH", "100nF", ref="C_AWR_14SYNTH", board_tag=BTAG, pin=awr.pin("VOUT__14SYNTH"))

    # Substrate + VPP to GND
    _net(d, "GND").connect(awr.pin("VNWA"))
    _net(d, "GND").connect(awr.pin("VPP"))

    # All grounds — iterate VSS_1..69 + VSSA_1..52, skip any not present
    for n in range(1, 70):
        try:
            _net(d, "GND").connect(awr.pin(f"VSS_{n}"))
        except KeyError:
            break
    for n in range(1, 53):
        try:
            _net(d, "GND").connect(awr.pin(f"VSSA_{n}"))
        except KeyError:
            break

    # Signal pins
    _net(d, "AWR_NRESET")  .connect(awr.pin("NRESET"))
    _net(d, "AWR_FAULT")   .connect(awr.pin("NERROR_OUT"))
    _net(d, "AWR_SPI_CS")  .connect(awr.pin("MSS_MIBSPIA__~{CS0}"))
    _net(d, "AWR_SPI_CLK") .connect(awr.pin("MSS_MIBSPIA__CLK"))
    _net(d, "AWR_SPI_MOSI").connect(awr.pin("MSS_MIBSPIA__MOSI"))
    _net(d, "AWR_SPI_MISO").connect(awr.pin("MSS_MIBSPIA__MISO"))

    # Gigabit Ethernet (CPSW RGMII) → MP25 GMAC, MAC-to-MAC (no PHY/magnetics).
    # The AWR's TX pairs to the MP25's RX and vice-versa (crossed). MDIO unused
    # (fixed-link). This is the radar data path (range-Doppler frames to the NPU).
    for net, pin in (
        # MP25 TX → AWR RX
        ("RAD_ETH_TXD0", "MSS_RGMII__RD0"),   ("RAD_ETH_TXD1", "MSS_RGMII__RD1"),
        ("RAD_ETH_TXD2", "MSS_RGMII__RD2"),   ("RAD_ETH_TXD3", "MSS_RGMII__RD3"),
        ("RAD_ETH_TX_CTL", "MSS_RGMII__RCTL"),("RAD_ETH_TXC", "MSS_RGMII__RCLK"),
        # AWR TX → MP25 RX
        ("RAD_ETH_RXD0", "MSS_RGMII__TD0"),   ("RAD_ETH_RXD1", "MSS_RGMII__TD1"),
        ("RAD_ETH_RXD2", "MSS_RGMII__TD2"),   ("RAD_ETH_RXD3", "MSS_RGMII__TD3"),
        ("RAD_ETH_RX_CTL", "MSS_RGMII__TCTL"),("RAD_ETH_RXC", "MSS_RGMII__TCLK"),
    ):
        _net(d, net).connect(awr.pin(pin))
    # MCAN unused — the radar's host link is SPI (MSS_MIBSPIA, above), which is
    # also its host-SPI boot interface (SOP=1). CAN-FD removed system-wide.
    _net(d, "AWR_TX0").connect(awr.pin("TX1"))
    _net(d, "AWR_TX1").connect(awr.pin("TX2"))
    _net(d, "AWR_TX2").connect(awr.pin("TX3"))
    _net(d, "AWR_RX0").connect(awr.pin("RX1"))
    _net(d, "AWR_RX1").connect(awr.pin("RX2"))
    _net(d, "AWR_RX2").connect(awr.pin("RX3"))
    _net(d, "AWR_RX3").connect(awr.pin("RX4"))

    # SOP boot-mode (5 pins, mapped to SamacSys post-boot signal names)
    _net(d, "AWR_SOP0").connect(awr.pin("TDO"))
    _net(d, "AWR_SOP1").connect(awr.pin("MSS_MIBSPIB__CS2"))
    _net(d, "AWR_SOP2").connect(awr.pin("PMIC_CLKOUT"))
    _net(d, "AWR_SOP3").connect(awr.pin("MSS_UARTB__TX"))
    _net(d, "AWR_SOP4").connect(awr.pin("MSS_UARTA__TX"))

    # Reset pull-up + filter; fault pull-up; SOP bias resistors
    res_between(d, "AWR_1V8", "AWR_NRESET", "10k",
                ref="R_AWR_NRST",     board_tag=BTAG)
    cap_to_gnd(d, "AWR_NRESET", "100nF", ref="C_AWR_NRST", board_tag=BTAG, pin=awr.pin("NRESET"))
    res_between(d, "3V3",     "AWR_FAULT",  "100k",
                ref="R_AWR_FAULT_PU", board_tag=BTAG)
    res_between(d, "AWR_1V8", "AWR_SOP0", "10k", ref="R_AWR_SOP0", board_tag=BTAG)
    res_between(d, "AWR_SOP1","GND",      "10k", ref="R_AWR_SOP1", board_tag=BTAG)
    res_between(d, "AWR_SOP2","GND",      "10k", ref="R_AWR_SOP2", board_tag=BTAG)
    res_between(d, "AWR_SOP3","GND",      "10k", ref="R_AWR_SOP3", board_tag=BTAG)
    res_between(d, "AWR_SOP4","GND",      "10k", ref="R_AWR_SOP4", board_tag=BTAG)

    # CAN-FD transceiver removed — the radar talks to the MP25 M33 over SPI
    # (MSS_MIBSPIA), which doubles as its host-SPI boot/flash path.


def build_radar_module_awr2e44p(d: Design) -> None:
    """Forward-end variant of build_radar_module using the **AWR2E44P** instead
    of the AWR2944. Same power tree (1.0 V buck + 1.8 V LDO off BAT_PROT, M33-
    gated via RADAR_EN), same SPI host link + RGMII data path to the MP25 — but
    three things change with the rearchitecture:

      1. NO discrete TX/RX antenna pins. The AWR2E44P couples 77 GHz into the
         machined aluminium waveguide/horn block via on-package SIW launches
         (`VDDA_10RF*` rails), so the AWR2944's TX1-3/RX1-4 balls simply don't
         exist — there is nothing to wire to the laminate. (This is also why
         the radar board dropped Rogers for plain FR4: the PCB never sees RF.)
      2. The SoC is 13.5×12 mm FCCSP, 278-ball — a different footprint, wired
         here from the EVM-lifted ballmap (see add_awr2e44pbgamxrq1).
      3. The pin naming follows the EVM ballmap (single-underscore, ball-unique)
         rather than the AWR2944 SamacSys symbol, so rails are gathered with
         `pins_by_name()` (e.g. 127× VSSA) and signals resolved by name.

    NOT wired into the live netlist yet — build_radar_module (AWR2944) is still
    the active radar. Swap the call in build_design() to switch the forward end
    to the AWR2E44P once the castellated USB/LED block + FR4 stack land.

    DATASHEET CAVEATS (cross-ref awr2944p_family.pdf before fab):
      • VIO domain: the EVM runs the bare `VIOIN` rail at 3.3 V (net 3V3_VIO).
        We tie it to AWR_1V8 to match the AWR2944 baseline + the MP25 host bank;
        confirm the MP25 GMAC/SPI bank voltage and flip to 3V3 if needed.
      • SOP boot straps: SOP0=TDO, SOP2=PMIC_CLKOUT, SOP4=MSS_UARTA_TX are
        EVM-confirmed (FUNC/host-SPI = SOP[2:0]=001, 40 MHz xtal = SOP[4:3]=00).
        SOP1/SOP3 ride muxed functions (MSS_SPIB_CS2 / MSS_UARTB_TX) that the
        lifted ballmap doesn't break out — set those balls + the exact bias
        resistor values per the datasheet boot table.
      • 40 MHz reference (CLKP/CLKM xtal or driven XREF_CLK0) is left open here,
        exactly as build_radar_module leaves the AWR2944 clock — add it system-
        wide when the clocking is finalized."""
    BTAG = "radar_module"

    # ── Power tree (identical to the AWR2944 build: 1.0 V buck + 1.8 V LDO,
    #    both tapping always-on BAT_PROT and self-gating via RADAR_EN) ──────
    buck = add_lmr10510ysde_nopb(d, ref="U_AWR_BUCK", board_tag=BTAG)   # (2026-11-22) WSON-6 0.8 mm (was SOT-23-5 1.45)
    _net(d, "BAT_PROT")  .connect(buck.pin("VIN"))
    _net(d, "BAT_PROT")  .connect(buck.pin("VINA"))
    _net(d, "GND")       .connect(buck.pin("GND"))
    _net(d, "GND")       .connect(buck.pin("DAP"))
    _net(d, "AWR_1V0_SW").connect(buck.pin("SW"))
    _net(d, "RADAR_EN")  .connect(buck.pin("EN"))
    _net(d, "AWR_1V0_FB").connect(buck.pin("FB"))
    res_between(d, "RADAR_EN", "GND", "100k", ref="R_RADAR_EN_PD", board_tag=BTAG)
    ind_between(d, "AWR_1V0_SW", "AWR_1V0", "4.7uH",
                ref="L_AWR_BUCK", family="we-ki", board_tag=BTAG)
    res_between(d, "AWR_1V0",    "AWR_1V0_FB", "30k",
                ref="R_AWR_FB1", board_tag=BTAG)
    res_between(d, "AWR_1V0_FB", "GND",        "100k",
                ref="R_AWR_FB2", board_tag=BTAG)
    cap_to_gnd(d, "BAT_PROT", "10uF",  ref="C_AWR_BUCK_IN1", board_tag=BTAG, pin=buck.pin("VIN"))
    cap_to_gnd(d, "BAT_PROT", "100nF", ref="C_AWR_BUCK_IN2", board_tag=BTAG, pin=buck.pin("VIN"))
    cap_to_gnd(d, "AWR_1V0",   "22uF",  ref="C_AWR_1V0_1",    board_tag=BTAG, pin=(buck.ref, None))
    cap_to_gnd(d, "AWR_1V0",   "100nF", ref="C_AWR_1V0_2",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=(buck.ref, None))

    ldo18 = add_xc6220b181mr_g(d, ref="U_AWR_LDO18", board_tag=BTAG)
    _net(d, "BAT_PROT").connect(ldo18.pin("VIN"))
    _net(d, "GND")     .connect(ldo18.pin("GND"))
    _net(d, "RADAR_EN").connect(ldo18.pin("EN"))
    _net(d, "AWR_1V8")  .connect(ldo18.pin("VOUT"))
    # (2026-11-22) XC6220 SOT-25 has no exposed pad (LDL112 EP tie removed)
    cap_to_gnd(d, "AWR_1V8", "10uF",  ref="C_AWR_1V8_1", board_tag=BTAG, pin=ldo18.pin("VOUT"))
    cap_to_gnd(d, "AWR_1V8", "100nF", ref="C_AWR_1V8_2",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=ldo18.pin("VOUT"))

    # ── AWR2E44P ────────────────────────────────────────────────────────────
    awr = add_awr2e44pbgamxrq1(d, ref="U_AWR", board_tag=BTAG)

    def _rail(net, *names):
        """Tie every ball carrying any of `names` to `net` (handles the
        many-balls-per-rail case, e.g. 16× VDD / 127× VSSA)."""
        for nm in names:
            balls = awr.pins_by_name(nm)
            if not balls:
                raise KeyError(f"AWR2E44P: no ball named {nm!r}")
            for p in balls:
                _net(d, net).connect(p)

    # 1.0 V — digital core + SRAM + RF analog (the SIW-launch supplies)
    _rail("AWR_1V0", "VDD", "VDD_SRAM", "VDDA_10RF1", "VDDA_10RF2")
    # 1.8 V — analog (baseband/VCO), PM input, LVDS/CSI + clock I/O
    _rail("AWR_1V8", "VDDA_18BB", "VDDA_18VCO", "VIN_18PM",
          "VIOIN_18", "VIOIN_18LVDS", "VIOIN_18CLK")
    # VIO domain — run at 1.8 V to match the AWR2944 baseline + MP25 host bank
    # (the EVM runs this 3V3_VIO; see the docstring caveat).
    _rail("AWR_1V8", "VIOIN")

    # Internal-regulator outputs — decouple to GND, never driven
    for net, ball in (("VBGAP", "VBGAP"),
                      ("VOUT_14APLL", "VOUT_14APLL"),
                      ("VOUT_14SYNTH", "VOUT_14SYNTH")):
        _net(d, net).connect(awr.pin(ball))
    cap_to_gnd(d, "VBGAP",        "100nF", ref="C_AWR_VBGAP",   board_tag=BTAG, pin=(awr.ref, "VBGAP"))
    cap_to_gnd(d, "VOUT_14APLL",  "100nF", ref="C_AWR_14APLL",  board_tag=BTAG, pin=(awr.ref, "VOUT_14APLL"))
    cap_to_gnd(d, "VOUT_14SYNTH", "100nF", ref="C_AWR_14SYNTH", board_tag=BTAG, pin=(awr.ref, "VOUT_14SYNTH"))

    # Grounds (VSSA ×127 + VSS ×22) + substrate (VNWA) + VPP (tie GND when not
    # one-time-programming, per the AWR2944 build)
    _rail("GND", "VSSA", "VSS", "VNWA", "VPP")

    # Reset / fault — active-low balls carry KiCad overbar escaping in the
    # lifted ballmap (R\E\S\E\T\, E\R\R\O\R\_\O\U\T\), so resolve them by ball.
    _net(d, "AWR_NRESET").connect(awr.pin("C19"))   # R\E\S\E\T\
    _net(d, "AWR_FAULT") .connect(awr.pin("B6"))    # E\R\R\O\R\_\O\U\T\
    res_between(d, "AWR_1V8", "AWR_NRESET", "10k", ref="R_AWR_NRST", board_tag=BTAG)
    cap_to_gnd(d, "AWR_NRESET", "100nF", ref="C_AWR_NRST", board_tag=BTAG, pin=awr.pin("C19"))
    res_between(d, "3V3", "AWR_FAULT", "100k", ref="R_AWR_FAULT_PU", board_tag=BTAG)

    # Host link — MSS_MIBSPIA to the MP25 M33 (also the host-SPI boot path)
    _net(d, "AWR_SPI_CS")  .connect(awr.pin("MSS_MIBSPIA_CS0"))
    _net(d, "AWR_SPI_CLK") .connect(awr.pin("MSS_MIBSPIA_CLK"))
    _net(d, "AWR_SPI_MOSI").connect(awr.pin("MSS_MIBSPIA_MOSI"))
    _net(d, "AWR_SPI_MISO").connect(awr.pin("MSS_MIBSPIA_MISO"))

    # Gigabit Ethernet (CPSW RGMII) → MP25 GMAC, MAC-to-MAC, crossed (TX↔RX),
    # same data path as the AWR2944 build (range-Doppler frames to the NPU).
    for net, pin in (
        ("RAD_ETH_TXD0", "MSS_RGMII_RD0"),   ("RAD_ETH_TXD1", "MSS_RGMII_RD1"),
        ("RAD_ETH_TXD2", "MSS_RGMII_RD2"),   ("RAD_ETH_TXD3", "MSS_RGMII_RD3"),
        ("RAD_ETH_TX_CTL", "MSS_RGMII_RCTL"),("RAD_ETH_TXC", "MSS_RGMII_RCLK"),
        ("RAD_ETH_RXD0", "MSS_RGMII_TD0"),   ("RAD_ETH_RXD1", "MSS_RGMII_TD1"),
        ("RAD_ETH_RXD2", "MSS_RGMII_TD2"),   ("RAD_ETH_RXD3", "MSS_RGMII_TD3"),
        ("RAD_ETH_RX_CTL", "MSS_RGMII_TCTL"),("RAD_ETH_RXC", "MSS_RGMII_TCLK"),
    ):
        _net(d, net).connect(awr.pin(pin))

    # SOP boot straps — FUNC / host-SPI boot (SOP[2:0]=001), 40 MHz (SOP[4:3]=00).
    # Only the EVM-confirmed straps are wired; SOP1/SOP3 ride muxed functions the
    # lifted ballmap doesn't expose (see docstring). Bias values per datasheet.
    _net(d, "AWR_SOP0").connect(awr.pin("TDO"))          # SOP0
    _net(d, "AWR_SOP2").connect(awr.pin("PMIC_CLKOUT"))  # SOP2 (EVM SOP2_PMIC_CLK)
    _net(d, "AWR_SOP4").connect(awr.pin("MSS_UARTA_TX")) # SOP4 (EVM SOP4_MSS_UARTA_TX)
    res_between(d, "AWR_1V8", "AWR_SOP0", "10k", ref="R_AWR_SOP0", board_tag=BTAG)
    res_between(d, "AWR_SOP2", "GND",     "10k", ref="R_AWR_SOP2", board_tag=BTAG)
    res_between(d, "AWR_SOP4", "GND",     "10k", ref="R_AWR_SOP4", board_tag=BTAG)

    # Spare/debug/clock balls (CLKP/CLKM, XREF_CLK0, GPIO, I2C, MCAN, QSPI,
    # MDIO, CSI2, LVDS_TX, ADC, MIBSPIB, UART RX, RS232, WARM_RESET) are left
    # unconnected — not used in the radar role, matching the AWR2944 build.


def build_radar_module_awr1843aop(d: Design) -> None:
    """Forward-end variant using the **AWR1843AOP** (Antennas-On-Package).

    Third radar option after build_radar_module (AWR2944 — discrete TX/RX
    balls → external antenna) and build_radar_module_awr2e44p (waveguide
    launches → horn block). Here the 3 TX + 4 RX patches are ON the package,
    so — like the AWR2E44P — there are NO antenna balls and NO RF on the
    laminate; the nose is an RF-transparent **radome** (the PEEK-LDS cup's
    closed end — smash.export.nose_radome). See add_awr1843aop.

    Architecture (radar does its own detection): the AWR1843's C674x DSP +
    Radar HWA + Cortex-R4F run the detection chain ON-CHIP (range/Doppler
    FFT, CFAR, AoA) and emit a point cloud / object list to the MP25 over
    **SPIA**, with a data-ready interrupt (SPI_HOST_INTR). The radar
    communicates *detections*, not raw frames — so the AWR2944/2E44P gigabit
    RGMII data path is dropped.

    Boot DIFFERS from the AWR2944: the AWR1843AOP has no host-SPI-to-RAM boot —
    it boots its application from a local **QSPI flash** (datasheet §6.10.12;
    "autonomous mode"). So this build adds an S25HL512T QSPI NOR. The image is
    encrypted + signed and decrypted in-chip by the AoP HSM (secure boot), so
    plaintext firmware never persists at rest — the firmware_lifecycle.md rule
    holds; only the mechanism changes (local encrypted flash the MP25
    provisions, vs the AWR2944's MP25-streams-over-SPI). A 40 MHz reference
    (DSC1001CI5-040 oscillator → CLKP) is required for boot and is wired here.

    Power tree differs from the AWR2944/2E44P: the 1843's core is **1.2 V**
    (SWRS236 VDDIN/VIN_SRAM/VNWA — the 2944's was 1.0 V) and it adds
    **1.3 V** for the RF front-end (VIN_13RF). So: a 1.2 V buck + a 1.3 V
    buck (each LMR10510 + catch diode — the part is non-synchronous) + a
    1.8 V LDO, all off always-on BAT_PROT and self-gated via RADAR_EN. The
    EVM (AWR1843AOPEVM / SPRR449) uses one **LP87524-Q1** quad-buck PMIC for
    these rails — a future area-saving swap for the Ø34 sonde; kept discrete
    here to reuse the catalogue and match the other radar builds.

    DATASHEET STATUS (audited vs SWRS236C, 2026-06-10):
      • Rails set per ROC: 1.2 V core (100k/100k, VFB=0.6) incl. VNWA back
        bias; 1.3 V RF (118k/100k); VIOIN on COMP_3V3 (the TI EVM config —
        matches the MP25 host pins, which live in 3.3 V banks). The boot
        flash followed: SST26WF080B (1.8 V) → SST26VF080A (2.7-3.6 V),
        pin-compatible. Control/strap pull-ups all ride the VIOIN rail.
      • SOP straps wired 001 = functional/QSPI-flash boot; exact decode
        still to be confirmed against the TRM + EVM jumper defaults.
      • 40 MHz reference: DSC1001 square DC-coupled through 330/390 to
        ≈1.0 V per Table 6-6 (AC coupling is the sine-mode option).
      • VPP grounded = no in-system fuse programming (keys factory-fused)."""
    BTAG = "radar_module"

    # ── 1.2 V buck (LMR10510) — VDDIN core + SRAM + VNWA back-bias ──────────
    # SWRS236 rail: 1.2 V (1.14–1.32) — the previous 1.0 V target was an
    # AWR2944 leftover, and its 30k/100k divider actually made 0.78 V (the
    # LMR10510 reference is 0.600 V, not 0.8). 100k/100k → 1.200 V.
    buck12 = add_lmr10510ysde_nopb(d, ref="U_AWR_BUCK12", feature="bottom", board_tag=BTAG)   # (2026-11-22) WSON-6 0.8 mm (was SOT-23-5 1.45)
    _net(d, "BAT_PROT")  .connect(buck12.pin("VIN"))
    _net(d, "BAT_PROT")  .connect(buck12.pin("VINA"))
    _net(d, "GND")       .connect(buck12.pin("GND"))
    _net(d, "GND")       .connect(buck12.pin("DAP"))
    _net(d, "AWR_1V2_SW").connect(buck12.pin("SW"))
    _net(d, "RADAR_EN")  .connect(buck12.pin("EN"))
    _net(d, "AWR_1V2_FB").connect(buck12.pin("FB"))
    res_between(d, "RADAR_EN", "GND", "100k", ref="R_RADAR_EN_PD", board_tag=BTAG)
    # 2.2 µH TMS: ΔiL ≈ 0.32 A p-p @1.6 MHz → peak ≈ 0.6 A, inside the
    # LMR10510's 1.2 A limit and the TMS-2R2's Isat (the old binding was
    # a nonexistent "WE-KI 0402 4.7 µH" — an RF family capped ~120 nH).
    # The WHOLE buck cluster (U+L+D+caps) rides the BOTTOM
    # (companion-facing) face with the locked J_USB_C + its usb_zone
    # column owning the top NE: packer-placed L/D/C on the top face
    # ended up hugging the USB area (L13 at board (7.7,7.7)) and
    # dragging the nose-side cutout into it — and the SMC catch
    # diodes found no top slot at all (parked = the radar overflow).
    # Bottom south is open, and one face keeps the switch loop tight.
    ind_between(d, "AWR_1V2_SW", "AWR_1V2", "2.2uH",
                ref="L_AWR_BUCK12", feature="bottom", board_tag=BTAG)
    # Catch diode — the LMR10510 is NON-synchronous (DS pin table: SW
    # "connect to the inductor and catch diode"); without it the inductor
    # has no off-time path and the rail can't regulate.
    d_b12 = add_rb160vam_60(d, ref="D_AWR_BUCK12", feature="bottom",   # (2026-11-20) 1.1 mm, 1 A ≫ 0.35 A avg; was 2.61 mm SMC MBRS340
                           board_tag=BTAG)
    _net(d, "AWR_1V2_SW").connect(d_b12.pin("K"))
    _net(d, "GND")       .connect(d_b12.pin("A"))
    res_between(d, "AWR_1V2", "AWR_1V2_FB", "100k", ref="R_AWR12_FB1", board_tag=BTAG)
    res_between(d, "AWR_1V2_FB", "GND", "100k", ref="R_AWR12_FB2", board_tag=BTAG)
    cap_to_gnd(d, "AWR_1V2", "22uF/LV",  ref="C_AWR_1V2_1",
               feature="bottom", board_tag=BTAG, pin=(buck12.ref, None))
    cap_to_gnd(d, "AWR_1V2", "100nF", ref="C_AWR_1V2_2",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=(buck12.ref, None))

    # ── 1.3 V buck (LMR10510) — VIN_13RF RF supply ──────────────────────────
    # 118k/100k → 0.6×2.18 = 1.308 V (the old 68k/100k made 1.008 V).
    buck13 = add_lmr10510ysde_nopb(d, ref="U_AWR_BUCK13", feature="bottom", board_tag=BTAG)   # (2026-11-22) WSON-6 0.8 mm (was SOT-23-5 1.45)
    _net(d, "BAT_PROT")  .connect(buck13.pin("VIN"))
    _net(d, "BAT_PROT")  .connect(buck13.pin("VINA"))
    _net(d, "GND")       .connect(buck13.pin("GND"))
    _net(d, "GND")       .connect(buck13.pin("DAP"))
    _net(d, "AWR_1V3_SW").connect(buck13.pin("SW"))
    _net(d, "RADAR_EN")  .connect(buck13.pin("EN"))
    _net(d, "AWR_1V3_FB").connect(buck13.pin("FB"))
    ind_between(d, "AWR_1V3_SW", "AWR_1V3", "2.2uH",
                ref="L_AWR_BUCK13", feature="bottom",
                board_tag=BTAG)   # see L_AWR_BUCK12 note
    d_b13 = add_rb160vam_60(d, ref="D_AWR_BUCK13", feature="bottom",   # (2026-11-20) 1.1 mm, 1 A ≫ 0.35 A avg; was 2.61 mm SMC MBRS340
                           board_tag=BTAG)   # catch diode (see BUCK12)
    _net(d, "AWR_1V3_SW").connect(d_b13.pin("K"))
    _net(d, "GND")       .connect(d_b13.pin("A"))
    res_between(d, "AWR_1V3", "AWR_1V3_FB", "118k", ref="R_AWR13_FB1", board_tag=BTAG)
    res_between(d, "AWR_1V3_FB", "GND", "100k", ref="R_AWR13_FB2", board_tag=BTAG)
    cap_to_gnd(d, "AWR_1V3", "22uF/LV",  ref="C_AWR_1V3_1",
               feature="bottom", board_tag=BTAG, pin=(buck13.ref, None))
    cap_to_gnd(d, "AWR_1V3", "100nF", ref="C_AWR_1V3_2",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=(buck13.ref, None))

    # Shared buck input decoupling on always-on BAT_PROT (bottom, at
    # the bucks' VIN — the 10 µF was landing on F.Cu dead-centre,
    # inside the U_AWR courtyard)
    cap_to_gnd(d, "BAT_PROT", "10uF",  ref="C_AWR_BUCK_IN1",
               feature="bottom", board_tag=BTAG, pin=[buck12.pin("VIN"), buck13.pin("VIN")])
    cap_to_gnd(d, "BAT_PROT", "100nF", ref="C_AWR_BUCK_IN2",
               feature="bottom", board_tag=BTAG, pin=[buck12.pin("VIN"), buck13.pin("VIN")])

    # ── 1.8 V LDO (LDL112PV18R) — analog (BB/VCO/CLK) + I/O ──────────────────
    ldo18 = add_xc6220b181mr_g(d, ref="U_AWR_LDO18", board_tag=BTAG)
    _net(d, "BAT_PROT").connect(ldo18.pin("VIN"))
    _net(d, "GND")     .connect(ldo18.pin("GND"))
    _net(d, "RADAR_EN").connect(ldo18.pin("EN"))
    _net(d, "AWR_1V8") .connect(ldo18.pin("VOUT"))
    # (2026-11-22) XC6220 SOT-25 has no exposed pad (LDL112 EP tie removed)
    cap_to_gnd(d, "AWR_1V8", "10uF",  ref="C_AWR_1V8_1", board_tag=BTAG, pin=ldo18.pin("VOUT"))
    cap_to_gnd(d, "AWR_1V8", "100nF", ref="C_AWR_1V8_2",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=ldo18.pin("VOUT"))

    # ── AWR1843AOP ──────────────────────────────────────────────────────────
    # feature="rf": the AoP is the radiator → stays on the nose-facing TOP
    # face. Only small/legged support opts to the bottom (the clock via
    # feature="clock", the SOT-23 bucks + boot flash via feature="bottom"); the
    # LDO + bulk caps stay on top, under the cup's radome pocket. (Bulk caps
    # kept top: too tall/heavy for the bottom envelope.)
    awr = add_awr1843aop(d, ref="U_AWR", secure=_RADAR_SECURE, board_tag=BTAG)

    def _tie(net, *bases):
        """Connect every ball named `base` or `base_<n>` (n=1..) to `net` —
        handles unnumbered (VPP, VBGAP) and numbered (VDDIN_1..5) rails alike.
        Raises if a base matches nothing (catches symbol drift)."""
        for base in bases:
            matched = False
            try:
                _net(d, net).connect(awr.pin(base)); matched = True
            except KeyError:
                pass
            n = 1
            while True:
                try:
                    _net(d, net).connect(awr.pin(f"{base}_{n}"))
                    matched = True; n += 1
                except KeyError:
                    break
            if not matched:
                raise KeyError(f"AWR1843AOP: no ball for rail base {base!r}")

    # 1.2 V — digital core + SRAM + SRAM array back bias (SWRS236: VNWA is a
    # 1.2 V POWER rail, 1.14–1.32 V recommended — NOT a ground tie)
    _tie("AWR_1V2", "VDDIN", "VIN_SRAM", "VNWA")
    # 1.3 V — RF front-end (TX PAs + RX)
    _tie("AWR_1V3", "VIN_13RF1", "VIN_13RF2")
    # 1.8 V — baseband / VCO / CLK analog + diff + 1.8 V I/O bank
    _tie("AWR_1V8", "VIN_18BB", "VIN_18VCO", "VIN_18CLK", "VIOIN_18", "VIOIN_18DIFF")
    # VIOIN general I/O domain — 3.3 V (the TI EVM configuration): the MP25
    # host pins for SPIA/IRQ/reset live in 3.3 V banks (VDDIO1/3 + VDD), so
    # the AWR's dual-voltage I/O domain matches them. COMP_3V3 extends one
    # gap (companion→radar) over the LGA lands. The VIOIN_18* balls above
    # stay on AWR_1V8 — that domain is fixed-1.8 V by the chip.
    _tie("COMP_3V3", "VIOIN")

    # Internal-regulator outputs — decouple to GND, never driven
    for net, base in (("VBGAP", "VBGAP"),
                      ("AWR_VOUT_14APLL", "VOUT_14APLL"),
                      ("AWR_VOUT_14SYNTH", "VOUT_14SYNTH"),
                      ("AWR_VOUT_PA", "VOUT_PA")):
        _tie(net, base)
    cap_to_gnd(d, "VBGAP",            "100nF", ref="C_AWR_VBGAP",   board_tag=BTAG, pin=(awr.ref, "VBGAP"))
    cap_to_gnd(d, "AWR_VOUT_14APLL",  "100nF", ref="C_AWR_14APLL",  board_tag=BTAG, pin=(awr.ref, "VOUT_14APLL"))
    cap_to_gnd(d, "AWR_VOUT_14SYNTH", "100nF", ref="C_AWR_14SYNTH", board_tag=BTAG, pin=(awr.ref, "VOUT_14SYNTH"))
    cap_to_gnd(d, "AWR_VOUT_PA",      "100nF", ref="C_AWR_VOUT_PA", board_tag=BTAG, pin=(awr.ref, None))  # 3 VOUT_PA balls

    # Grounds (VSS ×22 + VSSA ×53) + VPP (GND = no in-system OTP/fuse
    # programming — secure-boot keys must come factory-fused; provisioning-
    # flow decision, confirm vs TRM). VNWA moved to the 1.2 V tie above.
    _tie("GND", "VSS", "VSSA", "VPP")

    # ── Reset / fault ───────────────────────────────────────────────────────
    _net(d, "AWR_NRESET").connect(awr.pin("NRESET"))
    _net(d, "AWR_FAULT") .connect(awr.pin("NERROR_OUT"))
    # All control pull-ups ride the VIOIN-domain rail (COMP_3V3 — SWRS236
    # §5.3: the I/Os are non-failsafe, never pull above/without VIO; with
    # VIOIN at 3.3 V the straps must pull to 3.3 V to clear VIH = 0.7·VIO).
    res_between(d, "COMP_3V3", "AWR_NRESET", "10k", ref="R_AWR_NRST", board_tag=BTAG)
    cap_to_gnd(d, "AWR_NRESET", "100nF", ref="C_AWR_NRST", board_tag=BTAG, pin=awr.pin("NRESET"))
    res_between(d, "COMP_3V3", "AWR_FAULT", "100k", ref="R_AWR_FAULT_PU", board_tag=BTAG)
    # error-in + warm-reset held inactive (pulled up to the VIOIN domain)
    _net(d, "AWR_NERR_IN") .connect(awr.pin("NERROR_IN"))
    _net(d, "AWR_WARM_RST").connect(awr.pin("WARM_RESET"))
    res_between(d, "COMP_3V3", "AWR_NERR_IN",  "10k", ref="R_AWR_NERRIN_PU",  board_tag=BTAG)
    res_between(d, "COMP_3V3", "AWR_WARM_RST", "10k", ref="R_AWR_WARMRST_PU", board_tag=BTAG)

    # ── Host link — SPIA to the MP25 M33 (detections out + host-SPI boot in) ──
    _net(d, "AWR_SPI_CS")  .connect(awr.pin("SPIA_CS_N"))
    _net(d, "AWR_SPI_CLK") .connect(awr.pin("SPIA_CLK"))
    _net(d, "AWR_SPI_MOSI").connect(awr.pin("SPIA_MOSI"))
    _net(d, "AWR_SPI_MISO").connect(awr.pin("SPIA_MISO"))
    _net(d, "AWR_DRDY")    .connect(awr.pin("SPI_HOST_INTR"))  # detections-ready IRQ → MP25 GPIO
    res_between(d, "COMP_3V3", "AWR_DRDY", "10k", ref="R_AWR_DRDY_PU", board_tag=BTAG)

    # ── 40 MHz reference clock (DSC1001CI5-040 MEMS oscillator) ──────────────
    # The AWR1843AOP requires an external 40 MHz reference for boot (datasheet
    # §6: "requires external clock source ... for initial boot"). External-clock
    # mode: drive CLKP single-ended, AC-coupled; CLKM AC-grounded (Table 6-6).
    # The oscillator runs off AWR_1V8 (RADAR_EN-gated) so the clock is stable
    # with the rails before reset releases. All-silicon MEMS (robust to launch
    # shock). Kept on the TOP face — NO feature="clock" (which would sweep it to
    # the bottom): the AoP's CLKP is on the top, so the clock sits beside it for
    # the shortest reference route; and as a leadless DFN it's better off the
    # internal bottom face anyway. (The MP25 HSE differs — its OSC balls are on
    # its bottom, so that one keeps feature="clock".)
    osc = add_sit1602bi_12_xxe_40(d, ref="Y_AWR_HSE", board_tag=BTAG, vdd="18")
    _net(d, "AWR_1V8")    .connect(osc.pin("1"))   # STANDBY# tied high → run
    _net(d, "GND")        .connect(osc.pin("2"))   # GND
    _net(d, "AWR_OSC_OUT").connect(osc.pin("3"))   # OUT (40 MHz)
    _net(d, "AWR_1V8")    .connect(osc.pin("4"))   # VDD
    cap_to_gnd(d, "AWR_1V8", "100nF", ref="C_AWR_OSC_VDD",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=osc.pin("4"))
    _net(d, "AWR_CLKREF").connect(awr.pin("CLKP"))
    _net(d, "AWR_CLKM")  .connect(awr.pin("CLKM"))
    # External-clock mode per SWRS236 Table 6-6: AC-coupled SINE or
    # DC-COUPLED SQUARE, amplitude 0.7–1.2 V. The DSC1001 is a 1.8 Vpp CMOS
    # square → DC-coupled through a 330/390 divider: 1.8 × 390/720 ≈ 0.98 V
    # square at CLKP (≈2.5 mA oscillator load; ~1.7 ns edge RC against the
    # pin capacitance). The old 100 pF AC-block was the sine-mode coupling
    # at full CMOS swing — wrong on both counts.
    res_between(d, "AWR_OSC_OUT", "AWR_CLKREF", "330",
                ref="R_AWR_CLK_SER", board_tag=BTAG)
    res_between(d, "AWR_CLKREF", "GND", "390",
                ref="R_AWR_CLK_SH", board_tag=BTAG)
    cap_to_gnd(d, "AWR_CLKM", "100pF", ref="C_AWR_CLKM", board_tag=BTAG, pin=awr.pin("CLKM"))  # CLKM AC-gnd (confirm vs TI mmWave HW guide)

    # ── SPI boot flash (SST26WF080B, 8 Mbit/1 MB, SINGLE-bit SPI) ────────────
    # The AWR1843AOP boots its application from this NOR during GROUND staging
    # (depot-BIST sessions re-boot from it; since the Chambered→Ready merge the
    # radar is DARK in Ready and cold-boots on rapid deceleration) —
    # historically NOT after launch, which was a resume from RAM (power_states.md). So boot
    # latency is ground-side and a plain 4-wire single-SPI bus (CLK/CS/SI/SO) is
    # plenty — no need for the SST26's x2/x4 modes or a 6-wire quad bus. 1 MB >
    # the ~832 KB program-RAM ceiling, so it holds a full image. The image is
    # ENCRYPTED + signed, decrypted in-chip by the AoP HSM (secure boot on the
    # production AWR1843ARBSALPQ1); the MP25 owns/provisions the blob.
    # SST26VF080A (2.7-3.6 V) — the 3.3 V sibling of the original 1.8 V
    # SST26WF080B, swapped when VIOIN moved to 3.3 V: the AWR QSPI bus is
    # VIOIN-domain, so the flash levels must follow. Pin map is 1:1 (pin 7
    # gains a RESET# alternate; tied high = inactive either way).
    # feature="bottom": the saturated top face left no slot for the 6×5 WDFN
    # (packer parked it off-board = the radar overflow). A leadless, low-mass
    # package with its EP soldered down rides the internal bottom face fine,
    fl = add_mx25v8035fzni(d, ref="U_AWR_FLASH", feature="bottom", board_tag=BTAG)
    _net(d, "COMP_3V3").connect(fl.pin("VDD"))
    _net(d, "GND")     .connect(fl.pin("VSS"))
    _net(d, "GND")     .connect(fl.pin("EP"))             # exposed pad
    cap_to_gnd(d, "COMP_3V3", "100nF", ref="C_AWR_FLASH_VCC",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=fl.pin("VDD"))
    _net(d, "AWR_QSPI_CLK").connect(awr.pin("QSPI_CLK"))
    _net(d, "AWR_QSPI_CLK").connect(fl.pin("SCK"))
    _net(d, "AWR_QSPI_CS") .connect(awr.pin("QSPI_CS_N"))
    _net(d, "AWR_QSPI_CS") .connect(fl.pin("CE#"))
    _net(d, "AWR_QSPI_SI") .connect(awr.pin("QSPI[0]"))    # AWR DQ0 → flash SI
    _net(d, "AWR_QSPI_SI") .connect(fl.pin("SI/SIO0"))
    _net(d, "AWR_QSPI_SO") .connect(awr.pin("QSPI[1]"))    # flash SO → AWR DQ1
    _net(d, "AWR_QSPI_SO") .connect(fl.pin("SO/SIO1"))
    # Single-SPI: tie the quad data lines (SIO2/SIO3) inactive (high).
    _net(d, "COMP_3V3").connect(fl.pin("WP#/SIO2"))               # WP# inactive
    _net(d, "COMP_3V3").connect(fl.pin("RESET#/HOLD#/SIO3"))      # RESET#/HOLD# inactive
    # AWR QSPI[2]/QSPI[3] (quad data) unused in single-SPI mode — left open.

    # ── SOP boot straps → functional / QSPI-flash boot ───────────────────────
    # SOP[2:0] are muxed onto functional balls (datasheet pin table): SOP0=TDO
    # (U10), SOP1=SYNC_OUT (M3), SOP2=PMIC_CLKOUT (V10) — sensed only at power-up.
    # Strapped for QSPI-flash boot; the exact SOP[2:0] decode is TRM-level, so
    # VERIFY against the AWR1843 TRM + the AWR1843AOPEVM jumper defaults.
    _net(d, "AWR_SOP0").connect(awr.pin("TDO"))          # U10
    _net(d, "AWR_SOP1").connect(awr.pin("SYNC_OUT"))     # M3
    _net(d, "AWR_SOP2").connect(awr.pin("PMIC_CLKOUT"))  # V10
    res_between(d, "COMP_3V3", "AWR_SOP0", "10k", ref="R_AWR_SOP0", board_tag=BTAG)  # SOP0=1 (VIOIN domain)
    res_between(d, "AWR_SOP1", "GND",     "10k", ref="R_AWR_SOP1", board_tag=BTAG)  # SOP1=0
    res_between(d, "AWR_SOP2", "GND",     "10k", ref="R_AWR_SOP2", board_tag=BTAG)  # SOP2=0

    # No discrete TX/RX antenna balls (antenna-on-package) and no RGMII path —
    # the radar emits detections over SPIA above.


# Fin-stepper driver count on the fins_module. Each fin gets one DRV8428E
# (HTSSOP-16, integrated FETs), so the four drivers + the G0B1 node MCU +
# the small 5 V boost fit on one Ø34 tile — the retired DRV8711 pre-driver
# (HTSSOP-38 + 8 external FETs each) plus a CAN node once forced a second.
_N_FIN_DRIVERS = 4


def _fin_mcu_node(d: Design, *, board_tag: str) -> Chip:
    """(2026-11-22) Fin-node MCU = STM32U545REI6Q (replaces the STM32G0B1REI6N:
    Mouser 39 pcs / 52 wk; availability/decisions.csv) on the SYS_SPI bus (MP25
    M33 is master), with its SMPS, decoupling and reset network. Returns the
    Chip so the caller can wire its application GPIO.

    Flashed + commanded over SYS_SPI = the U5 ROM bootloader's SPI1 slave
    (AN2606 §98, STM32U535xx/545xx: PA4 NSS, PA5 SCK, PA6 MISO, PA7 MOSI —
    SPI2 is unusable here, PB12 is not bonded on UFBGA-64). Entry: BOOT0
    (PH3) pulled LOW = run from flash; the application jumps to system memory
    on an update command (or an empty part boots the bootloader). SWD stays
    the recovery path. Ball map = SamacSys symbol, checked 64/64 against
    CubeMX STM32U545REIxQ.xml."""
    g = add_stm32u545rei6q(d, ref="U_FIN_MCU", board_tag=board_tag, feature="bottom")
    for p in g.pins:
        if p.name.startswith(("VDD_", "VDDA", "VDDSMPS", "VBAT", "VDDUSB")):
            _net(d, "3V3").connect(p)
        elif p.name.startswith(("VSS", "VSSA", "VSSSMPS")):
            _net(d, "GND").connect(p)
    # SMPS: VLXSMPS → 2.2 µH → VDD11 (both balls), 2.2 µF per VDD11 ball
    ind_between(d, "FIN_MCU_VLX", "FIN_MCU_VDD11", "2.2uH", ref="L_FIN_MCU_SMPS",
                board_tag=board_tag)
    _net(d, "FIN_MCU_VLX").connect(g.pin("VLXSMPS"))
    for k in (1, 2):
        _net(d, "FIN_MCU_VDD11").connect(g.pin(f"VDD11_{k}"))
        cap_to_gnd(d, "FIN_MCU_VDD11", "2.2uF", ref=f"C_FIN_MCU_VDD11_{k}",
                   board_tag=board_tag, pin=g.pin(f"VDD11_{k}"))
    cap_to_gnd(d, "3V3", "4.7uF", ref="C_FIN_MCU_SMPS_IN", board_tag=board_tag,
               pin=g.pin("VDDSMPS"))
    for k in (1, 2):
        cap_to_gnd(d, "3V3", "100nF", ref=f"C_FIN_MCU_VDD{k}", embedded_cap_absorbs=True,
                   board_tag=board_tag, pin=g.pin(f"VDD_{k}"))
    cap_to_gnd(d, "3V3", "100nF", ref="C_FIN_MCU_VDDA", board_tag=board_tag, pin=g.pin("VDDA"))
    cap_to_gnd(d, "3V3", "1uF", ref="C_FIN_MCU_BULK", board_tag=board_tag, pin=(g.ref, None))
    # reset + boot
    _net(d, "FIN_MCU_NRST").connect(g.pin("NRST"))
    res_between(d, "3V3", "FIN_MCU_NRST", "10k", ref="R_FIN_MCU_NRST", board_tag=board_tag)
    cap_to_gnd(d, "FIN_MCU_NRST", "100nF", ref="C_FIN_MCU_NRST", board_tag=board_tag,
               pin=g.pin("NRST"))
    _net(d, "FIN_MCU_BOOT0").connect(g.pin("PH3-BOOT0"))
    res_between(d, "FIN_MCU_BOOT0", "GND", "10k", ref="R_FIN_MCU_BOOT0", board_tag=board_tag)
    # SWD to the aft interface (recovery)
    _net(d, "FIN_MCU_SWDIO").connect(g.pin("PA13"))
    _net(d, "FIN_MCU_SWCLK").connect(g.pin("PA14"))
    # SYS_SPI slave = bootloader SPI1
    _net(d, "SYS_SPI_SCLK").connect(g.pin("PA5"))
    _net(d, "SYS_SPI_MISO").connect(g.pin("PA6"))
    _net(d, "SYS_SPI_MOSI").connect(g.pin("PA7"))
    _net(d, "SYS_SPI_CS_FIN").connect(g.pin("PA4"))
    return g


def _hall_switch(d: Design, *, ref: str, board_tag: str, out_net: str,
                 gpio_chip: Chip, gpio_pin: str) -> None:
    """DRV5023 Hall switch — an OFF-board sensor (it mounts by the moving
    magnet it senses, not on the PCB). The board only lands its three
    wires (VCC / GND / OUT — open-drain digital, no bus) plus the
    required OUT pull-up and local decoupling; the MCU reads OUT as a
    GPIO level."""
    for sig, net in (("VCC", "3V3"), ("GND", "GND"), ("OUT", out_net)):
        pad = add_pogo_pad(d, ref=f"{ref}_{sig}", board_tag=board_tag,
                           manf_pn=None)
        _net(d, net).connect(pad.pin("1"))
    res_between(d, "3V3", out_net, "10k", ref=f"R_{ref}_PU",
                board_tag=board_tag)                    # required pull-up
    cap_to_gnd(d, "3V3", "100nF", ref=f"C_{ref}_VCC", board_tag=board_tag, pin=(f"{ref}_VCC", "1"))
    _net(d, out_net).connect(gpio_chip.pin(gpio_pin))


def _build_lr_radio(d: Design, BTAG: str, *, face: str = "bottom") -> None:
    """Long-range radio, built on `BTAG` next to its host MCU (2026-11-16:
    wakeup_board, top face beside the WBA's RF π-match — the whole radio is
    board-local, no host or RF line crosses a joint).

    Semtech LR2021, HF path ONLY (2026-11-17: sub-GHz dropped — no room for
    a radiator on the tower, external-antenna pad removed). The LR2021 stays
    (an SX1280 was considered) because its HF section tunes 1.5-2.5 GHz and
    the only efficient sleeve slot, S1, resonates at ~2.15 GHz (openEMS C2:
    57 % total efficiency, ~80 MHz -10 dB BW) — outside the SX1280's
    2.400-2.500 GHz. The link HOPS inside S1's band.
    Host = the WBA55 (same board) over SPI1 (host side wired in
    build_wakeup_board):
      LR_SPI_SCK  WBA PB4  (SPI1_SCK,  AF5)   → SCK
      LR_SPI_MOSI WBA PA15 (SPI1_MOSI, AF5)   → MOSI
      LR_SPI_MISO WBA PB3  (SPI1_MISO, AF5)   ← MISO
      LR_NSS      WBA PA4  (GPIO, software NSS) → NSS
      LR_BUSY     WBA PB0  (GPIO in)          ← BUSY
      LR_IRQ      WBA PB13 (EXTI13)           ← DIO7 (IRQ, firmware-mapped)
      LR_NRESET   WBA PA3  (GPIO out)         → NRESET
    Series R on the host lines as in the Semtech reference design (Fig 23-1):
    220 Ω on SCK / MOSI / NSS, 470 Ω on BUSY / IRQ / NRESET (MISO direct).

    TX/RX switch U_LR_SW_HF (BGS12: CTRL 1 = RF2 = TX, 0 = RF1 = RX) on
    LR2021 DIO8 (net LR_RFSW_TX), DIO_FUNCTION_RF_SWITCH with mask TX_HF;
    100 k pull-down → RX after reset. NOT DIO5/DIO6: those come up PULLED
    HIGH after POR/reset (DS v2.2 §5.1.1) and would park the switch on TX;
    firmware forces DIO5/6 to DIO_FUNCTION_NONE on cold start (§6.8.1).

    RF (2026-11-17: DEDICATED antennas, no band / owner switching):
      • HF: RFO_HF (choke from VR_PA, Fig 1-4) → series-L / shunt-C match +
        low-pass, DC block → U_LR_SW_HF RF2; RFI_HF → L-match, DC block →
        RF1; switch common → DC block → tunable π (2 × PE64906 DTC, 3.9 nH) →
        owner switch U_ANTSW_S1 RF2 → DC block → ANT_HF_S1 (sleeve slot S1,
        activation↔fin_ble gap; 2.4 GHz ISM default, ~2.1-2.4 GHz authorised).
      • BLE (WBA RF π-match in build_wakeup_board) → BLE_RF → DC block →
        owner switch RF1 (default, 3V3_AON) → the SAME slot S1 (S3 merged
        2026-11-17; LR2021 DIO9 selects the LR path).
      • LF pins RFO_LF1/LF2 + RFI_LF left UNCONNECTED (DS v2.2 §23.5
        "Unused RF pins: leave unconnected"). FIRMWARE: pa_lf_duty_cycle = 6,
        pa_lf_slices = 7 (LF PA unused, §7).
      • ⚠ No dummy load any more (the PE42442's RF4 reset default is gone):
        firmware must NOT transmit before the LR2021 is configured.
      • 32 MHz TCXO (Y_LR_TCXO, placeholder part) powered from VTCXO,
        AC-coupled into XTA; XTB NC. NTC NC.
    Power — LDO mode (DS v2.2 Fig 1-14, user 2026-11-16; no SIMO coil,
    LXA/LXB NC): VBAT on 3V3 (100 nF + 4.7 µF); VDCC1→VDCC2 on LR_VDCC;
    VPAX1→VPAX2 on their OWN net LR_VPAX (2.2 µF each — never on VBAT/3V3,
    VPAX1 is the internal regulator's output); VR_PA 1 nF (ref C28) feeding
    the HF PA choke. VBAT through ferrite bead FB_LR_VBAT (Murata
    BLM18PG221SN1D, ref design FB14) from 3V3 onto LR_VBAT.

    ⚠ OPEN: pins and supply wiring follow the FINAL DS (LR20xx Rev 2.2), but
    the reference schematic carries no RF L/C values — every match / filter
    value here is a PLACEHOLDER until the Semtech ref BOM / AN1200.66 is
    transcribed and the slot impedances come from the antenna sim. FIRMWARE:
    the WBA is on 3V3_AON and the LR2021 on 3V3 — hold the host lines
    low/Hi-Z while 3V3 is off (no back-power through the LR2021's IO
    clamps)."""
    F = face
    lr = add_lr2021imltrt(d, ref="U_LR", board_tag=BTAG, feature=F)
    tcxo = add_tcxo_32m_2016(d, ref="Y_LR_TCXO", board_tag=BTAG, feature=F)
    swhf = add_bgs12p2l6e6327xtsa1(d, ref="U_LR_SW_HF", board_tag=BTAG, feature=F)

    def C0G(net, val, ref, pin=None):
        cap_to_gnd(d, net, val, ref=ref, board_tag=BTAG, feature=F,
                   **_as_built_0402(val, "C0G/NP0"), pin=pin)

    def series_cap(n1, n2, val, ref):
        c = add_capacitor_c0g_0603_avx_sqcs(
            d, ref=ref, value=val, board_tag=BTAG, feature=F,
            **_as_built_0402(val, "C0G/NP0"))
        _net(d, n1).connect(c.pin("1")); _net(d, n2).connect(c.pin("2"))

    def L(n1, n2, val, ref):
        ind_between(d, n1, n2, val, ref=ref, board_tag=BTAG, feature=F)

    # ── LR2021 supplies (LDO mode, DS v2.2 Fig 1-14) ─────────────────
    for pn in ("GND", "GND_DCC", "EP"):
        _net(d, "GND").connect(lr.pin(pn))
    fb = add_blm18pg221sn1d(d, ref="FB_LR_VBAT", board_tag=BTAG, feature=F)
    _net(d, "3V3").connect(fb.pin("1")); _net(d, "LR_VBAT").connect(fb.pin("2"))
    _net(d, "LR_VBAT").connect(lr.pin("VBAT"))
    cap_to_gnd(d, "LR_VBAT", "100nF", ref="C_LR_VBAT", board_tag=BTAG, pin=lr.pin("VBAT"))
    cap_to_gnd(d, "LR_VBAT", "4.7uF", ref="C_LR_BULK", board_tag=BTAG, pin=lr.pin("VBAT"))
    # VPAX1 (regulator OUTPUT for the PAs) → VPAX2 (PA-regulator input).
    _net(d, "LR_VPAX").connect(lr.pin("VPAX1")); _net(d, "LR_VPAX").connect(lr.pin("VPAX2"))
    cap_to_gnd(d, "LR_VPAX", "2.2uF", ref="C_LR_VPAX1", board_tag=BTAG, pin=lr.pin("VPAX1"))
    cap_to_gnd(d, "LR_VPAX", "2.2uF", ref="C_LR_VPAX2", board_tag=BTAG, pin=lr.pin("VPAX2"))
    _net(d, "LR_VDCC").connect(lr.pin("VDCC1")); _net(d, "LR_VDCC").connect(lr.pin("VDCC2"))
    cap_to_gnd(d, "LR_VDCC", "1uF", ref="C_LR_VDCC1", board_tag=BTAG, pin=lr.pin("VDCC1"))
    cap_to_gnd(d, "LR_VDCC", "1uF", ref="C_LR_VDCC2", board_tag=BTAG, pin=lr.pin("VDCC2"))
    _net(d, "LR_VR_PA").connect(lr.pin("VR_PA"))
    cap_to_gnd(d, "LR_VR_PA", "1nF", ref="C_LR_VRPA", board_tag=BTAG, pin=lr.pin("VR_PA"))

    # ── 32 MHz reference → AC-coupled into XTA (and the ADF4351 REFIN) ─
    # (2026-11-22, user) DUAL FOOTPRINT: the SiTime SiT5356 MEMS TCXO is FITTED
    # (shock-robust; 3.3 V, so it cannot run off the LR2021 VTCXO pin: a P-FET
    # load switch from 3V3, its gate pulled low by an N-FET driven by VTCXO, so
    # the radio still powers the reference on/off itself). The Epson TG2016
    # quartz TCXO stays on VTCXO as the UNFITTED alternate. One 0 Ω select
    # link per source onto LR_TCXO_OUT (fit exactly one). FIRMWARE: set the
    # LR2021 TCXO start-up delay to the SiT5356's (datasheet) value.
    _net(d, "LR_VTCXO").connect(lr.pin("VTCXO")); _net(d, "LR_VTCXO").connect(tcxo.pin("VDD"))
    cap_to_gnd(d, "LR_VTCXO", "100nF", ref="C_LR_VTCXO", board_tag=BTAG, pin=tcxo.pin("VDD"))
    _net(d, "GND").connect(tcxo.pin("GND"))
    _net(d, "LR_TCXO_OUT_QZ").connect(tcxo.pin("OUT"))
    tcxo.dnp = True
    r_qz = res_between(d, "LR_TCXO_OUT_QZ", "LR_TCXO_OUT", "0", ref="R_LR_TCXO_SEL_QZ", board_tag=BTAG)
    r_qz.dnp = True
    mems = add_sit5356aecfq_33n0_32(d, ref="Y_LR_TCXO_MEMS", board_tag=BTAG, feature=F)
    q_sw = add_ssm3j372r_lf(d, ref="Q_LR_TCXO_SW", board_tag=BTAG)
    _net(d, "3V3").connect(q_sw.pin("S"))
    _net(d, "LR_TCXO_3V3").connect(q_sw.pin("D"))
    _net(d, "LR_TCXO_SW_G").connect(q_sw.pin("G"))
    res_between(d, "3V3", "LR_TCXO_SW_G", "100k", ref="R_LR_TCXO_SW_PU", board_tag=BTAG)
    q_en = add_ssm3k35ctc_l3f(d, ref="Q_LR_TCXO_EN", board_tag=BTAG)
    _net(d, "LR_TCXO_SW_G").connect(q_en.pin("D"))
    _net(d, "GND").connect(q_en.pin("S"))
    _net(d, "LR_VTCXO").connect(q_en.pin("G"))       # VTCXO high → reference on
    _net(d, "LR_TCXO_3V3").connect(mems.pin("VDD"))
    _net(d, "GND").connect(mems.pin("GND"))
    cap_to_gnd(d, "LR_TCXO_3V3", "100nF", ref="C_LR_TCXO_MEMS1", board_tag=BTAG, pin=mems.pin("VDD"))
    cap_to_gnd(d, "LR_TCXO_3V3", "1uF", ref="C_LR_TCXO_MEMS2", board_tag=BTAG, pin=mems.pin("VDD"))
    _net(d, "LR_TCXO_OUT_MEMS").connect(mems.pin("CLK"))
    res_between(d, "LR_TCXO_OUT_MEMS", "LR_TCXO_OUT", "0", ref="R_LR_TCXO_SEL_MEMS", board_tag=BTAG)
    series_cap("LR_TCXO_OUT", "LR_XTA", "10pF", "C_LR_TCXO_AC")
    _net(d, "LR_XTA").connect(lr.pin("XTA"))

    # ── Host link (WBA side wired in build_wakeup_board) ─────────────
    # Series R at the radio, values from the ref design (Fig 23-1); MISO
    # direct (ref 0 Ω). The host-side nets keep their names.
    for net, lpin, r_val in (("LR_SPI_SCK", "SCK", "220"), ("LR_SPI_MOSI", "MOSI", "220"),
                             ("LR_NSS", "NSS", "220"), ("LR_BUSY", "BUSY", "470"),
                             ("LR_IRQ", "DIO7", "470"), ("LR_NRESET", "NRESET", "470")):
        pin_net = f"{net}_L"
        res_between(d, net, pin_net, r_val, ref=f"R_{net}", board_tag=BTAG, feature=F)
        _net(d, pin_net).connect(lr.pin(lpin))
    _net(d, "LR_SPI_MISO").connect(lr.pin("MISO"))
    res_between(d, "3V3", "LR_NSS", "100k", ref="R_LR_NSS_PU", board_tag=BTAG)

    # ── HF TX/RX switch (BGS12: CTRL 0 → RF1 = RX, 1 → RF2 = TX) ─────
    # RF-switch DIO8 (mask TX_HF). DIO5/DIO6 stay unconnected.
    _net(d, "LR_RFSW_TX").connect(lr.pin("DIO8"))
    res_between(d, "LR_RFSW_TX", "GND", "100k", ref="R_LR_RFSW_PD", board_tag=BTAG)
    _net(d, "GND").connect(swhf.pin("GND"))
    _net(d, "3V3").connect(swhf.pin("VDD"))
    cap_to_gnd(d, "3V3", "100nF", ref="C_LR_SW_HF_VDD", board_tag=BTAG, pin=swhf.pin("VDD"))
    _net(d, "LR_RFSW_TX").connect(swhf.pin("CTRL"))

    # ── HF 1.5-2.5 GHz — ⚠ values PLACEHOLDERS ───────────────────────
    _net(d, "LR_HF_RFO").connect(lr.pin("RFO_HF"))
    L("LR_VR_PA", "LR_HF_RFO", "10nH", "L_LR_HF_CHOKE")    # PA_HF bias (Fig 1-4, ref L7)
    L("LR_HF_RFO", "LR_HF_TX_M", "2.7nH", "L_LR_HF_TX1")
    C0G("LR_HF_TX_M", "1.2pF", "C_LR_HF_TX1")
    L("LR_HF_TX_M", "LR_HF_TX_F", "2.2nH", "L_LR_HF_TX2")
    C0G("LR_HF_TX_F", "1.0pF", "C_LR_HF_TX2")
    series_cap("LR_HF_TX_F", "LR_HF_TX", "100pF", "C_LR_HF_TXBLK")
    _net(d, "LR_HF_TX").connect(swhf.pin("RF2"))
    _net(d, "LR_HF_RFI").connect(lr.pin("RFI_HF"))
    L("LR_HF_RFI", "LR_HF_RX_M", "3.3nH", "L_LR_HF_RX")
    C0G("LR_HF_RX_M", "0.8pF", "C_LR_HF_RX")
    series_cap("LR_HF_RX_M", "LR_HF_RX", "100pF", "C_LR_HF_RXBLK")
    _net(d, "LR_HF_RX").connect(swhf.pin("RF1"))
    _net(d, "LR_HF_TRX").connect(swhf.pin("RFIN"))
    # Switch common → DC block → TUNABLE π (LR branch only, 2026-11-17):
    # shunt DTC U_LR_DTC1 – series 3.9 nH – shunt DTC U_LR_DTC2 → antenna
    # owner switch. pSemi PE64906B-Z (0.9-4.6 pF, 32 states, Q 40→13 at
    # 2 GHz), fitted to the openEMS S1 impedances; states set per unit at end
    # of line (open loop, WBA flash) and optionally per hop (≤ 12 µs).
    # Control from the WBA: shared SCL/SDA, one SEN per DTC (DS Fig 10).
    # ── IF tap for the S4 transverter (2026-11-18) ─────────────────────
    # U_LR_IFSW (BGS12P2L6, CTRL 0 → RF1 = S1 path, 1 → RF2 = transverter
    # IF) between the T/R switch common and the S1 π. CTRL on LR2021 DIO10
    # (net LR_XV_SEL, DIO_FUNCTION_RF_SWITCH asserted in BOTH TX_HF and
    # RX_HF while a transverter channel is active) with a 100 k pull-down →
    # S1 by default and whenever the LR2021 is unpowered. +0.3-0.4 dB on
    # the S1 path at 2.1-2.5 GHz (DS IL). No DC on either side (both ends
    # are DC-blocked).
    ifsw = add_bgs12p2l6e6327xtsa1(d, ref="U_LR_IFSW", board_tag=BTAG, feature=F)
    _net(d, "GND").connect(ifsw.pin("GND"))
    _net(d, "3V3").connect(ifsw.pin("VDD"))
    cap_to_gnd(d, "3V3", "100nF", ref="C_LR_IFSW_VDD", board_tag=BTAG, pin=ifsw.pin("VDD"))
    _net(d, "LR_XV_SEL").connect(lr.pin("DIO10"))
    _net(d, "LR_XV_SEL").connect(ifsw.pin("CTRL"))
    res_between(d, "LR_XV_SEL", "GND", "100k", ref="R_LR_XV_SEL_PD", board_tag=BTAG)
    _net(d, "LR_HF_TRX").connect(ifsw.pin("RFIN"))
    _net(d, "LR_HF_S1").connect(ifsw.pin("RF1"))
    _net(d, "XV_IF_SW").connect(ifsw.pin("RF2"))
    series_cap("LR_HF_S1", "LR_HF_ANT_IN", "100pF", "C_LR_HF_ANTBLK")
    L("LR_HF_ANT_IN", "LR_HF_ANT_OUT", "3.9nH", "L_LR_HF_ANT_LPF")
    for ref, rf_net, sen in (("U_LR_DTC1", "LR_HF_ANT_IN", "LR_DTC_SEN1"),
                             ("U_LR_DTC2", "LR_HF_ANT_OUT", "LR_DTC_SEN2")):
        dtc = add_pe64904d_z(d, ref=ref, board_tag=BTAG, feature=F)   # (2026-11-22) PE64906B-Z 0 stock
        for pn in ("RF+_1", "RF+_2"):
            _net(d, rf_net).connect(dtc.pin(pn))
        for pn in ("RF-_1", "RF-_2", "GND_1", "GND_2"):            # PE64904: no EP
            _net(d, "GND").connect(dtc.pin(pn))
        _net(d, "3V3").connect(dtc.pin("VDD"))
        cap_to_gnd(d, "3V3", "100nF", ref=f"C_{ref[2:]}_VDD", board_tag=BTAG, pin=dtc.pin("VDD"))
        _net(d, "LR_DTC_SCL_LV").connect(dtc.pin("SCL"))
        _net(d, "LR_DTC_SDA_LV").connect(dtc.pin("SDA"))
        _net(d, f"{sen}_LV").connect(dtc.pin("SEN"))
    # (2026-11-21) PE64906 logic HIGH max 3.1 V (DS p.3 Table 2, no I/O abs
    # max) but the WBA drives 3.3 V → a 220 Ω / 1 kΩ divider per line
    # (2.70 V, 2.84 V at +5 %); ~180 Ω source keeps edges ≈ 2 ns (≤ 6.5 ns,
    # DS Table 5). SCL/SDA dividers sit AFTER the ADF4351 branch (it keeps
    # 3.3 V). Firmware: idle the lines LOW (≈ 2.7 mA per line while high).
    for line in ("LR_DTC_SCL", "LR_DTC_SDA", "LR_DTC_SEN1", "LR_DTC_SEN2"):
        res_between(d, line, f"{line}_LV", "220", ref=f"R_{line[3:]}_TOP", board_tag=BTAG)
        res_between(d, f"{line}_LV", "GND", "1k", ref=f"R_{line[3:]}_BOT", board_tag=BTAG)

    # ── ONE 2.4 GHz slot (S1) shared by the LR2021 and BLE (2026-11-17,
    # user: S3 merged into S1 — with PEEK gap rings S1 peaks at 2.44-2.48 GHz;
    # the radios never use it at the same time). Owner switch U_ANTSW_S1
    # (BGS12: CTRL 0 → RF1 = BLE, 1 → RF2 = LR2021) on 3V3_AON so BLE works
    # with 3V3 off; CTRL from LR2021 DIO9 (DIO_FUNCTION_GPIO_OUTPUT_HIGH while
    # the LR owns the antenna) with a 100 k pull-down → BLE by default and
    # whenever the LR2021 is unpowered / in reset. FIRMWARE: drive DIO9 high
    # before any LR RX/TX, low after. DC blocks: BGS12 ports carry no DC and
    # the slot feed is a DC short.
    swa = add_bgs12p2l6e6327xtsa1(d, ref="U_ANTSW_S1", board_tag=BTAG, feature=F)
    _net(d, "GND").connect(swa.pin("GND"))
    _net(d, "3V3_AON").connect(swa.pin("VDD"))
    cap_to_gnd(d, "3V3_AON", "100nF", ref="C_ANTSW_S1_VDD", board_tag=BTAG, pin=swa.pin("VDD"))
    _net(d, "ANTSW_S1_LR").connect(lr.pin("DIO9"))
    _net(d, "ANTSW_S1_LR").connect(swa.pin("CTRL"))
    res_between(d, "ANTSW_S1_LR", "GND", "100k", ref="R_ANTSW_S1_PD", board_tag=BTAG)
    _net(d, "LR_HF_ANT_OUT").connect(swa.pin("RF2"))
    series_cap("BLE_RF", "BLE_ANT", "100pF", "C_BLE_DCBLK")
    _net(d, "BLE_ANT").connect(swa.pin("RF1"))
    _net(d, "ANT_S1_COM").connect(swa.pin("RFIN"))
    series_cap("ANT_S1_COM", "ANT_HF_S1", "100pF", "C_ANT_S1_DCBLK")

    # ── Antenna feeds: ANT_HF_S1 leaves the board through its dedicated
    # castellation in the sleeve's ANTENNA sector
    # (castellations.ANTENNA_FEED_ANGLES_DEG) → sleeve via → CPW → slot S1.
    # ANT_HF_S4 (4.4-5.0 GHz transverter, _build_transverter) likewise.


def _build_transverter(d: Design, BTAG: str, *, face: str = "rf") -> None:
    """S4 transverter, 4.4-5.0 GHz (user-approved plan 2026-11-18).

    The LR2021 HF port is the IF (≈1.8-2.2 GHz — NOT 2.4: that would put the
    LO at 2.4 GHz and the LR2021's 2nd harmonic on the channel), switched in
    by U_LR_IFSW (_build_lr_radio). Low-side LO: RF = LO + IF.

      XV_IF_SW → DC block → LTC5549 IF   ← LO: ADF4351 RFOUTA+ (2.2-3.2 GHz,
      LTC5549 RF → DC block → U_XV_TR1     fundamental VCO, no divider; ref =
                                            the LR2021 32 MHz TCXO)
        TX (CTRL 1): 10 dB π pad → GRF5126 PA (4400-5000 MHz Guerrilla custom
                     tune, XV_5V 110 mA, VGAIN high) → U_XV_TR2 RF2
        RX (CTRL 0): U_XV_TR2 RF1 → GRF2073W LNA (3V3) → U_XV_TR1 RF1
      U_XV_TR2 common → 4.4-5.0 GHz BPF → series 0.5 pF match → ANT_HF_S4
      (sleeve slot S4, fin_ble↔wakeup gap; feed castellation emitted
      automatically because the net exists).

    Control (all parts default OFF / RX):
      • LR2021 DIO11 → XV_TX (both T/R switches; RF-switch function, TX_HF
        mask, 100 k pull-down → RX). DIO10 → LR_XV_SEL (IF switch).
      • WBA55 GPIO (spare UFBGA59 balls): XV_LO_LE PB14, XV_LO_CE PA10,
        XV_LO_MUX PB11 (MUXOUT = digital lock detect / readback),
        XV_MIX_EN PA11, XV_LNA_EN PB6, XV_PA_EN PB7 (boost EN). LO SPI
        CLK/DATA share the bit-banged DTC bus (LR_DTC_SCL / LR_DTC_SDA).
      • XV_5V = MCP1640D boost (true output disconnect) → PA fully off
        (VBIAS < 0.2 V) whenever XV_PA_EN is low. FIRMWARE: raise XV_PA_EN
        ≥ ~1 ms before TX (boost start-up), drop it after.

    Power while active: LO ~0.41 W + mixer 0.38 W; TX + PA 0.55 W (5 V,
    110 mA) / boost efficiency, drawn from REG_IN_MAIN, not 3V3 (see the
    U_BOOST load budget); RX + LNA ~0.2 W. ⚠ PLACEHOLDERS: loop
    filter (ADIsimPLL), LO pad, BPF,
    GRF2073W 4.4-5.0 GHz match + VENABLE resistor (only 2.3 / 3.4-3.8 GHz
    BOMs published — re-tune from the vendored S-parameters), GRF5126 VDD1
    inductor. The GRF5126 tune topology is read off Guerrilla's annotated
    eval-board photo (GRF5126_tune_4400-5000MHz.pdf p2) — confirm with
    applications@guerrilla-rf.com before layout. TCXO → ADF4351 REFIN needs
    ≥ 0.7 Vpp (DS) — check against the chosen TCXO's clipped-sine level."""
    F = face

    def C0G(net, val, ref, pin=None):
        cap_to_gnd(d, net, val, ref=ref, board_tag=BTAG, feature=F,
                   **_as_built_0402(val, "C0G/NP0"), pin=pin)

    def series_cap(n1, n2, val, ref):
        c = add_capacitor_c0g_0603_avx_sqcs(
            d, ref=ref, value=val, board_tag=BTAG, feature=F,
            **_as_built_0402(val, "C0G/NP0"))
        _net(d, n1).connect(c.pin("1")); _net(d, n2).connect(c.pin("2"))

    def L(n1, n2, val, ref):
        ind_between(d, n1, n2, val, ref=ref, board_tag=BTAG, feature=F)

    def R(n1, n2, val, ref):
        res_between(d, n1, n2, val, ref=ref, board_tag=BTAG, feature=F)

    def gnd(chip, *pins):
        for p in pins:
            _net(d, "GND").connect(chip.pin(p))

    def bgs12(ref, rfin, rf1, rf2, ctrl):
        sw = add_bgs12p2l6e6327xtsa1(d, ref=ref, board_tag=BTAG, feature=F)
        gnd(sw, "GND")
        _net(d, "3V3").connect(sw.pin("VDD"))
        cap_to_gnd(d, "3V3", "100nF", ref=f"C_{ref[2:]}_VDD", board_tag=BTAG, pin=sw.pin("VDD"))
        for pn, net in (("RFIN", rfin), ("RF1", rf1), ("RF2", rf2), ("CTRL", ctrl)):
            _net(d, net).connect(sw.pin(pn))
        return sw

    # ── LO: ADF4351 on its own ferrite-isolated 3.3 V ─────────────────
    lo = add_adf4351bcpz_rl7(d, ref="U_XV_LO", board_tag=BTAG, feature=F)
    fb = add_blm18pg221sn1d(d, ref="FB_XV_LO", board_tag=BTAG, feature=F)
    _net(d, "3V3").connect(fb.pin("1")); _net(d, "XV_LO_3V3").connect(fb.pin("2"))
    cap_to_gnd(d, "XV_LO_3V3", "10uF", ref="C_XV_LO_BULK", board_tag=BTAG)
    for pn in ("AVDD", "DVDD", "SDVDD", "VP", "VVCO", "VVCO_2"):
        _net(d, "XV_LO_3V3").connect(lo.pin(pn))
        cap_to_gnd(d, "XV_LO_3V3", "100nF", ref=f"C_XV_LO_{pn}", board_tag=BTAG, pin=lo.pin(pn))
    gnd(lo, "CPGND", "AGND", "AGNDVCO", "AGNDVCO_2", "AGNDVCO_3", "DGND", "SDGND", "EP")
    _net(d, "XV_LO_RSET").connect(lo.pin("RSET"))
    R("XV_LO_RSET", "GND", "5.1k", "R_XV_LO_RSET")                # ICP = 25.5/RSET = 5 mA (DS)
    for pn in ("VCOM", "VREF", "TEMP"):                             # DS: decouple at the pin
        _net(d, f"XV_LO_{pn}").connect(lo.pin(pn))
        cap_to_gnd(d, f"XV_LO_{pn}", "100nF", ref=f"C_XV_LO_{pn}", board_tag=BTAG, pin=lo.pin(pn))
    # Reference: the LR2021's 32 MHz TCXO, AC-coupled (REFIN self-biases
    # at AVDD/2, 100 kΩ) — one reference for the whole link.
    series_cap("LR_TCXO_OUT", "XV_LO_REF", "100pF", "C_XV_LO_REF")
    _net(d, "XV_LO_REF").connect(lo.pin("REFIN"))
    # Control: SPI shared with the DTC bus; LE / CE / MUXOUT on WBA GPIO.
    _net(d, "LR_DTC_SCL").connect(lo.pin("CLK"))
    _net(d, "LR_DTC_SDA").connect(lo.pin("DATA"))
    _net(d, "XV_LO_LE").connect(lo.pin("LE"))
    _net(d, "XV_LO_CE").connect(lo.pin("CE"))
    R("XV_LO_CE", "GND", "100k", "R_XV_LO_CE_PD")                  # powered down by default
    _net(d, "XV_LO_MUX").connect(lo.pin("MUXOUT"))
    R("XV_LO_3V3", "XV_LO_PDBRF", "10k", "R_XV_LO_PDBRF")          # RF on; mute via R4
    _net(d, "XV_LO_PDBRF").connect(lo.pin("PDBRF"))
    # 3rd-order passive loop filter — ⚠ PLACEHOLDER values (ADIsimPLL).
    _net(d, "XV_LO_CP").connect(lo.pin("CPOUT"))
    C0G("XV_LO_CP", "1nF", "C_XV_LO_LF1")
    R("XV_LO_CP", "XV_LO_LF2", "470", "R_XV_LO_LF1")
    cap_to_gnd(d, "XV_LO_LF2", "22nF", ref="C_XV_LO_LF2", board_tag=BTAG)
    R("XV_LO_CP", "XV_LO_VTUNE", "1k", "R_XV_LO_LF2")
    C0G("XV_LO_VTUNE", "220pF", "C_XV_LO_LF3")
    _net(d, "XV_LO_VTUNE").connect(lo.pin("VTUNE"))
    # RFOUTA±: 50 Ω pull-ups to VVCO + 100 pF (DS "Output Matching");
    # A+ drives the mixer through a ~3 dB π pad, A− is terminated in 50 Ω.
    # RFOUTB± unused (R4 DB9 = 0), left open.
    _net(d, "XV_LO_OUTP").connect(lo.pin("RFOUTA+"))
    _net(d, "XV_LO_OUTN").connect(lo.pin("RFOUTA-"))
    R("XV_LO_3V3", "XV_LO_OUTP", "51", "R_XV_LO_PUP")
    R("XV_LO_3V3", "XV_LO_OUTN", "51", "R_XV_LO_PUN")
    series_cap("XV_LO_OUTP", "XV_LO_PAD_I", "100pF", "C_XV_LO_OUTP")
    series_cap("XV_LO_OUTN", "XV_LO_TERM", "100pF", "C_XV_LO_OUTN")
    R("XV_LO_TERM", "GND", "51", "R_XV_LO_TERM")
    R("XV_LO_PAD_I", "GND", "300", "R_XV_LO_PAD1")                 # ⚠ PLACEHOLDER 3 dB π
    R("XV_LO_PAD_I", "XV_LO_PAD_O", "18", "R_XV_LO_PAD2")
    R("XV_LO_PAD_O", "GND", "300", "R_XV_LO_PAD3")
    series_cap("XV_LO_PAD_O", "XV_MIX_LO", "18pF", "C_XV_MIX_LO")   # LTC5552 DS Fig. 1: C1 = 18 pF

    # ── Mixer: LTC5552, used both ways (TDD) ──────────────────────────
    # (2026-11-22, mixer round 18) LTC5549 restricted → LTC5552 (same UDB
    # land; pin 3 = IF−, pin 8 = GND; 0 dBm LO; 132 mA). Its IF is
    # differential → 1:1 balun T_XV_IF (NCS1-292+, 1.65-2.85 GHz).
    mix = add_ltc5552iudb(d, ref="U_XV_MIX", board_tag=BTAG, feature=F)
    gnd(mix, "GND_1", "GND_3", "GND_4", "GND_5", "GND_6", "GND_7", "EP")
    _net(d, "3V3").connect(mix.pin("VCC"))
    cap_to_gnd(d, "3V3", "1uF", ref="C_XV_MIX_VCC1", board_tag=BTAG, pin=mix.pin("VCC"))
    C0G("3V3", "1nF", "C_XV_MIX_VCC2", pin=mix.pin("VCC"))
    _net(d, "XV_MIX_EN").connect(mix.pin("EN"))                    # internal 376 k pull-down
    _net(d, "XV_MIX_LO").connect(mix.pin("LO"))
    series_cap("XV_IF_SW", "XV_MIX_IF", "100pF", "C_XV_MIX_IF")
    bal = add_ncs1_292p(d, ref="T_XV_IF", board_tag=BTAG, feature=F)
    _net(d, "XV_MIX_IF").connect(bal.pin("UNBAL"))
    _net(d, "XV_MIX_IFP").connect(bal.pin("BAL_P")); _net(d, "XV_MIX_IFP").connect(mix.pin("IF+"))
    _net(d, "XV_MIX_IFN").connect(bal.pin("BAL_N")); _net(d, "XV_MIX_IFN").connect(mix.pin("IF-"))
    _net(d, "GND").connect(bal.pin("GND_DC")); _net(d, "GND").connect(bal.pin("NU_GND"))
    _net(d, "XV_MIX_RF").connect(mix.pin("RF"))
    series_cap("XV_MIX_RF", "XV_RF", "10pF", "C_XV_MIX_RF")

    # ── T/R switches (CTRL 0 → RF1 = RX default, 1 → RF2 = TX) ────────
    _net(d, "XV_TX").connect(next(c for c in d.chips if c.ref == "U_LR").pin("DIO11"))
    R("XV_TX", "GND", "100k", "R_XV_TX_PD")
    bgs12("U_XV_TR1", "XV_RF", "XV_RX_OUT", "XV_TX_IN", "XV_TX")
    bgs12("U_XV_TR2", "XV_ANT_SW", "XV_RX_IN", "XV_TX_OUT", "XV_TX")

    # ── TX: 10 dB π pad → GRF5126 (Guerrilla 4400-5000 MHz tune) ──────
    # Mixer ≈ +4 dBm out; GRF5126 IP1dB ≈ -8…-9 dBm at high gain.
    R("XV_TX_IN", "GND", "100", "R_XV_TX_PAD1")                     # 10 dB π, 50 Ω (E12)
    R("XV_TX_IN", "XV_PA_PADO", "68", "R_XV_TX_PAD2")
    R("XV_PA_PADO", "GND", "100", "R_XV_TX_PAD3")
    pa = add_grf5126(d, ref="U_XV_PA", board_tag=BTAG, feature=F)
    gnd(pa, "GND", "EP", *[f"NC_{n}" for n in (3, 5, 6, 7, 8, 9, 11, 12, 16)])
    L("XV_PA_PADO", "GND", "1.3nH", "L_XV_PA_IN")                    # tune: 1.3 nH "TN"
    series_cap("XV_PA_PADO", "XV_PA_IN", "1.5pF", "C_XV_PA_IN")      # tune: 1.5 pF (DC block)
    _net(d, "XV_PA_IN").connect(pa.pin("RF_IN"))
    L("XV_5V", "XV_PA_VDD1", "22nH", "L_XV_PA_VDD1")                  # ⚠ PLACEHOLDER (DS: "through inductor")
    _net(d, "XV_PA_VDD1").connect(pa.pin("VDD1"))
    cap_to_gnd(d, "XV_PA_VDD1", "100nF", ref="C_XV_PA_VDD1", board_tag=BTAG, pin=pa.pin("VDD1"))  # tune M13
    _net(d, "XV_PA_OUT").connect(pa.pin("RF_OUT"))
    L("XV_5V", "XV_PA_OUT", "6.2nH", "L_XV_PA_CHOKE")                 # tune: 6.2 nH
    C0G("XV_PA_OUT", "0.8pF", "C_XV_PA_OUTSH")                       # tune M27: 0.8 pF
    series_cap("XV_PA_OUT", "XV_TX_OUT", "10pF", "C_XV_PA_OUT")      # tune: 10 pF
    R("XV_5V", "XV_PA_VB1", "2.74k", "R_XV_PA_VB1")                  # tune: 2740 Ω
    R("XV_5V", "XV_PA_VB2", "2.32k", "R_XV_PA_VB2")                  # tune: 2320 Ω
    _net(d, "XV_PA_VB1").connect(pa.pin("VBIAS1"))
    _net(d, "XV_PA_VB2").connect(pa.pin("VBIAS2"))
    cap_to_gnd(d, "XV_PA_VB1", "100nF", ref="C_XV_PA_VB1", board_tag=BTAG, pin=pa.pin("VBIAS1"))
    cap_to_gnd(d, "XV_PA_VB2", "100nF", ref="C_XV_PA_VB2", board_tag=BTAG, pin=pa.pin("VBIAS2"))
    # VGAIN high (≥ 1.0 V, ≤ 2.5 V): 2.03 V from XV_5V so it drops with the rail.
    R("XV_5V", "XV_PA_VGAIN", "22k", "R_XV_PA_VG1")
    R("XV_PA_VGAIN", "GND", "15k", "R_XV_PA_VG2")
    _net(d, "XV_PA_VGAIN").connect(pa.pin("VGAIN"))
    cap_to_gnd(d, "XV_5V", "10uF", ref="C_XV_PA_BULK1", board_tag=BTAG)
    cap_to_gnd(d, "XV_5V", "100nF", ref="C_XV_PA_CHOKE", board_tag=BTAG)

    # ── XV_5V: MCP1640D boost (output disconnect when EN low) ─────────
    # (2026-11-20, user) DFN-8 (1.0 mm) instead of SOT-23-6; D = true output disconnect
    # (2026-11-21, user) the PA-supply boost is DC, not RF: it rides wakeup's
    # BOTTOM (frees ~28 mm² of the radio-crowded top; same board, no lanes).
    _XVB = "bottom"
    bst = add_mcp1640_dfn(d, ref="U_XV_BOOST", board_tag=BTAG, feature=_XVB, variant="D",
                          manf_pn="MCP1640D-I/MC", name="MCP1640D-I/MC", value="MCP1640D-I/MC")   # (2026-11-22) sourcing swap, availability/decisions.csv: tube code (reel had 0 stock)
    # (2026-11-22) VIN on REG_IN_MAIN (QMAIN drain, born on this board — no new
    # lanes), NOT 3V3: TX through 3V3 was ~0.5 A (LO 125 + mixer 132 + this
    # boost's 110 mA @ 5 V ≈ 190 mA at 3.3 V + LR/MCU/sensors ~50) against the
    # U_BOOST MCP1640's ~350 mA here (400 mA abs max in pass-through on a fresh
    # pack ≥ 3.87 V). Off REG_IN_MAIN the 3V3 TX load drops to ~0.31 A, and
    # the PA still dies with QMAIN in shelf. 3.0-4.2 V in → 4.95 V out stays a
    # true boost (MCP1640 VIN ≤ 5.5 V); ~165 mA in at 4 V, ~215 mA at 3.0 V.
    _net(d, "REG_IN_MAIN").connect(bst.pin("VIN"))
    gnd(bst, "SGND", "PGND", "EP")
    _net(d, "XV_PA_EN").connect(bst.pin("EN"))
    R("XV_PA_EN", "GND", "100k", "R_XV_PA_EN_PD")
    _net(d, "XV_BST_SW").connect(bst.pin("SW"))
    ind_between(d, "REG_IN_MAIN", "XV_BST_SW", "2.2uH", ref="L_XV_BOOST", board_tag=BTAG, feature=_XVB)
    _net(d, "XV_5V").connect(bst.pin("VOUTP"))
    _net(d, "XV_5V").connect(bst.pin("VOUTS"))
    _net(d, "XV_BST_FB").connect(bst.pin("VFB"))
    res_between(d, "XV_5V", "XV_BST_FB", "309k", ref="R_XV_BST_FB1", board_tag=BTAG, feature=_XVB)                  # 1.21 V × (1 + 309/100) = 4.95 V
    res_between(d, "XV_BST_FB", "GND", "100k", ref="R_XV_BST_FB2", board_tag=BTAG, feature=_XVB)
    cap_to_gnd(d, "REG_IN_MAIN", "10uF", ref="C_XV_BST_IN", board_tag=BTAG, feature=_XVB, pin=bst.pin("VIN"))
    cap_to_gnd(d, "XV_5V", "22uF", ref="C_XV_BST_OUT", board_tag=BTAG, feature=_XVB, pin=bst.pin("VOUTP"))

    # ── RX: GRF2073W LNA on 3V3 (⚠ match = DS 3.4-3.8 GHz BOM, PLACEHOLDER) ─
    lna = add_grf2073w(d, ref="U_XV_LNA", board_tag=BTAG, feature=F)
    gnd(lna, "EP", *[f"NC_{n}" for n in (3, 4, 5, 6, 8)])
    series_cap("XV_RX_IN", "XV_LNA_IN", "1.2pF", "C_XV_LNA_IN")      # DS M1
    _net(d, "XV_LNA_IN").connect(lna.pin("RF_IN"))
    _net(d, "XV_LNA_OUT").connect(lna.pin("RF_OUT"))
    L("XV_LNA_VDD", "XV_LNA_OUT", "1.8nH", "L_XV_LNA_BIAS")           # DS M8
    R("3V3", "XV_LNA_VDD", "0", "R_XV_LNA_VDD")
    cap_to_gnd(d, "XV_LNA_VDD", "100nF", ref="C_XV_LNA_VDD1", board_tag=BTAG)  # DS M9
    C0G("XV_LNA_VDD", "100pF", "C_XV_LNA_VDD2")                      # DS M10
    series_cap("XV_LNA_OUT", "XV_RX_OUT", "5.1pF", "C_XV_LNA_OUT")   # DS M11
    R("XV_LNA_EN", "XV_LNA_VEN", "1k", "R_XV_LNA_VEN")               # ⚠ PLACEHOLDER (sets IDDQ)
    _net(d, "XV_LNA_VEN").connect(lna.pin("VENABLE"))
    R("XV_LNA_EN", "GND", "100k", "R_XV_LNA_EN_PD")

    # ── 4.4-5.0 GHz BPF + S4 L-match (⚠ PLACEHOLDERS, both resonators at 4.8 GHz) ─
    L("XV_ANT_SW", "XV_BPF_M", "2.2nH", "L_XV_BPF_SER")
    series_cap("XV_BPF_M", "XV_BPF_O", "0.5pF", "C_XV_BPF_SER")
    L("XV_BPF_O", "GND", "1nH", "L_XV_BPF_SH")
    C0G("XV_BPF_O", "1.1pF", "C_XV_BPF_SH")
    # S4 match: the retuned slot (antenna_slots S4, sim C2_P_S4_p17_sc90_f20_w2)
    # sits at R 41-69 Ω with +54…+95 Ω inductive reactance over 4.6-5.0 GHz —
    # one series 0.5 pF cancels it (S11 ≈ -12…-25 dB, calc) and DC-blocks.
    series_cap("XV_BPF_O", "ANT_HF_S4", "0.5pF", "C_ANT_S4_MATCH")


def build_fins_module(d: Design) -> None:
    """Fin actuators — on fin_ble_board (2026-07-30 split: the wakeup tile got
    too crowded, so the fin actuation moved to its own tile; parts carry
    board_tag="fin_ble_board". The WBA55 BLE cluster briefly rode along and
    moved BACK to wakeup_board 2026-07-31 — the wake/activation_unlock ladder rides a
    tile every config carries). The same day's stack reorder (activation
    dropped down between aft_end and cell_floor) made this tile the BATTERY
    COMPARTMENT CEILING — the cells' + contact lands P_CELL_CONTACTS ride
    its bottom face (built in build_power_board) with its embeddable
    passives tucked into the compartment's free trefoil space — and the
    host of the piezo launch cluster (disc + comparator column, top face;
    emitted in build_activation_interface). Both are CORE functions, so
    fin_ble_board is in EVERY config, core_radar included — that config
    still flies RF-dark, shedding only the Yagi leaves. A SYS_SPI
    node (STM32G0B1, MP25 M33 is master) driving the four fin steppers via
    integrated DRV8428E drivers.

    The spin-brake tile was retired (its DRV8833 brake driver dropped as
    redundant); only its FINBOOST boost moved here (now 5 V) — there's room
    because the DRV8428E is tiny (HTSSOP-16, integrated FETs) next to the
    DRV8711 pre-driver it replaces (HTSSOP-38 + 8 external FETs per fin).

    BOM:
      - STM32G0B1REI6N — node MCU (SYS_SPI slave; flashed over SPI ROM
        bootloader by the MP25 M33 root — no CAN transceiver)
      - TPS61175PWPR   — shared 5 V boost on power_board (VMOT taps COMP_5V_RAW)
      - 4× DRV8428EPWPR — integrated bipolar-stepper drivers (one per fin)
      - DRV5023AJQLPG  — Hall position sensor (deploy), OFF-board: 3 wire pads

    DRV8428E is fully integrated: PH/EN control (APH/AEN + BPH/BEN), an
    internal current regulator referenced to VREF (no external sense
    shunts), no SPI and no external FETs. Only the four motor-coil outputs
    leave the tile edge to each fin's stepper.
    """
    # (2026-11-21, user) fin_ble_board MERGED into activation_interface: with
    # the low-profile swaps both tiles' parts fit on activation's top face
    # (~440 of 644 mm²), which drops one board + one gap (~3.5 mm).
    BTAG = "activation_interface"
    g = _fin_mcu_node(d, board_tag=BTAG)
    # (2026-11-22) U545 pin map (CubeMX STM32U545REIxQ.xml; PA4-7 = SYS_SPI):
    # parachute-matrix SELECT lines → rows PC0..PC3, columns PA8..PA11
    for k, pin in enumerate(("PC0", "PC1", "PC2", "PC3")):
        _net(d, f"ACT_ROW_SEL_{k}").connect(g.pin(pin))
    for k, pin in enumerate(("PA8", "PA9", "PA10", "PA11")):
        _net(d, f"ACT_COL_SEL_{k}").connect(g.pin(pin))
    # Shared standby + per-bridge ENB (PWM, timer channels) / PHA (GPIO)
    _net(d, "FIN_NSLEEP").connect(g.pin("PB7"))
    _fin_aen = {1: "PA0", 2: "PA2", 3: "PC6", 4: "PC8"}   # TIM2_CH1/CH3, TIM3_CH1/CH3
    _fin_ben = {1: "PA1", 2: "PA3", 3: "PC7", 4: "PC9"}   # TIM2_CH2/CH4, TIM3_CH2/CH4
    _fin_aph = {1: "PB0", 2: "PB1", 3: "PB2", 4: "PB3"}
    _fin_bph = {1: "PB4", 2: "PB5", 3: "PB6", 4: "PB8"}
    for i in range(1, _N_FIN_DRIVERS + 1):
        _net(d, f"FIN{i}_AEN").connect(g.pin(_fin_aen[i]))
        _net(d, f"FIN{i}_APH").connect(g.pin(_fin_aph[i]))
        _net(d, f"FIN{i}_BEN").connect(g.pin(_fin_ben[i]))
        _net(d, f"FIN{i}_BPH").connect(g.pin(_fin_bph[i]))
    # ── 4× TC78H653FTG dual H-bridges (2026-11-22; were DRV8428E) ─────
    # PHASE input mode (MODE = H), two independent bridges (LARGE = L),
    # STBY = FIN_NSLEEP. No current regulator / VREF any more: the coil
    # current is VM / R_winding, firmware PWMs ENB (TIM2/TIM3) to limit it.
    # VM = COMP_5V_RAW (5 V; part max 7.5 V operating, 8.0 V abs).
    for i in range(1, _N_FIN_DRIVERS + 1):
        drv = add_tc78h653ftg(d, ref=f"U_FIN{i}", board_tag=BTAG)
        _net(d, "COMP_5V_RAW").connect(drv.pin("VM"))
        for gpin in ("GND_1", "GND_2", "EP"):
            _net(d, "GND").connect(drv.pin(gpin))
        _net(d, "3V3").connect(drv.pin("MODE"))      # phase/enable inputs
        _net(d, "GND").connect(drv.pin("LARGE"))     # two bridges (stepper)
        cap_to_gnd(d, "COMP_5V_RAW", "100nF", ref=f"C_FIN{i}_VM", board_tag=BTAG, pin=drv.pin("VM"))
        _net(d, f"FIN{i}_AEN").connect(drv.pin("IN1/ENB_A"))
        _net(d, f"FIN{i}_APH").connect(drv.pin("IN2/PHA_A"))
        _net(d, f"FIN{i}_BEN").connect(drv.pin("IN3/ENB_B"))
        _net(d, f"FIN{i}_BPH").connect(drv.pin("IN4/PHA_B"))
        _net(d, "FIN_NSLEEP").connect(drv.pin("STBY"))
        # Motor-coil outputs → off-tile to each fin stepper (bridge A = OUT1/2,
        # bridge B = OUT3/4; net names kept from the DRV8428 AOUTx/BOUTx)
        for net_pin, drv_pin in (("AOUT1", "OUT1"), ("AOUT2", "OUT2"), ("BOUT1", "OUT3"), ("BOUT2", "OUT4")):
            _net(d, f"FIN{i}_{net_pin}").connect(drv.pin(drv_pin))
    # Local VM bulk (coil current pulses stay off the LGA lands).
    cap_to_gnd(d, "COMP_5V_RAW", "10uF", ref="C_FIN_VM_BULK", board_tag=BTAG)

    # Hall position sensor (fin-deploy reference)
    _hall_switch(d, ref="J_HALL_FIN", board_tag=BTAG, out_net="FIN_HALL",
                 gpio_chip=g, gpio_pin="PC13")

    # (2026-11-16) The long-range radio moved to wakeup_board, next to its
    # WBA55 host (build_wakeup_board → _build_lr_radio).

    # ── Fin VM rail: merged onto COMP_5V ──────────────────────────────
    # The standalone U_FINBOOST (BAT_PROT->5V) is GONE — the DRV8428E VM now
    # taps COMP_5V_RAW (the shared 5V boost on power_board, 1 gap away). The
    # drivers are gated by FIN_NSLEEP, so the always-on VM is fine. (VMOT_EN /
    # node-MCU PB14 freed.)


def build_aft_end_board(d: Design) -> None:
    """Aft-most service tile (snake start) — the parachute-cutter board
    for the emergency sensor drop (sonar, infrared, or a radio) onto an
    illuminated point
    (2026-07-31: the sector select + cutter chain came here from
    activation_interface; the piezo cluster left for fin_ble_board's top face in the
    same-day stack reorder that also brought activation_interface down to
    be this tile's direct neighbour — see the piezo block). Top face: the
    COMPLETE sector-select chain — the CD74HC4514 4-to-16 decoder, the 16
    DMN6075 select NFETs, the DMP6110 parachute_cutter_activate high-side + level shift, HV
    monitor + bleed (see _build_activation_array) — and the EXT_CAN
    gateway (TCAN1042 + terminator) at its TP_CAN pads; all 16
    Y*_ACTIVATE_SEL gate nets are tile-local. Bottom (outer) face: the
    bench-test pogo array + the 16 outbound parachute-restraint pads + the
    PARACHUTE_CUTTER_ACTIVATE common — so every cutter net is a top↔bottom via through THIS tile and
    none cross the battery compartment. All emitted by the existing
    builders tagged ``board_tag="aft_end_board"``. In the 3-cell default
    the cells do NOT sit here (they stand on cell_floor_board, past
    activation since the reorder — see build_cell_floor_board); only
    single-cell mode lays its one horizontal cell on this tile (tab lands
    P_CELL_TAB_POS/NEG — the activate bank then shares the top face with the
    cell swath). The boost power stage (ACTIVATE_HV) sits on
    activation_interface — its 2.8 mm inductor doesn't fit this thin
    gap, but since the reorder that is ONE thin gap away, so ACTIVATE_HV no
    longer crosses the battery column. This is the named builder hook
    for the tile; it adds nothing on its own."""
    return


def build_cell_floor_board(d: Design) -> None:
    """The THIN battery-floor tile (between activation_interface and the
    battery spacers since the 2026-07-31 stack reorder) — REINSTATED
    2026-07-30 (same-day revert of a brief deletion: with the cells
    standing on aft_end, the piezo hole + comparator pockets + tab
    chimneys starved the aft LGA joint, 59→20 lands, and moving the
    comparator to the bottom face gave PIEZO_P an unwanted via stub). Now
    6L / ~0.85 mm, NO Cu coin (the potted monolith carries the ~27 g pack's
    rapid-deceleration load — full-stack FEA): it carries the cells' side solder-tab −
    lands (`P_CELL_TAB_NEG1..3`, inside the cell bore circles, GND; built in
    build_power_board), the backbone LGA/filled-via pass-through, and TWO
    potting pass-through holes so the thin aft gaps below it
    (activation↔cell_floor, and via activation's own holes
    aft_end↔activation) fill from the compartment channels. The
    compartment sits nose-ward of this tile, up to the fin_ble_board
    ceiling. Dropped in single-cell mode. This is the named builder hook
    for the tile; it adds nothing on its own."""
    return


def build_activation_interface(d: Design) -> None:
    """Aft electronics: the 46-pad grouped bench-bringup pogo array + (since
    2026-07-31) the sector select + activate chain and the EXT-CAN gateway
    — all tagged ``board_tag="aft_end_board"`` and physically mounting on
    the aft_end_board tile; the piezo launch detector is emitted here too
    but rides fin_ble_board's top face (see the piezo block).
    activation_interface itself moved DOWN in the 2026-07-31 stack
    reorder — it now sits between aft_end_board and cell_floor_board, so
    its ACTIVATE_HV boost power stage (top face, 2.8 mm inductor) feeds the
    aft_end activate bank across ONE thin gap instead of the battery column.
    Its battery-connector role went with the compartment: the cell +
    contact pads (P_CELL_CONTACTS, built in build_power_board) now ride
    fin_ble_board's bottom face, the compartment ceiling. This tile's
    bottom face stays chip-free (lands only — a bottom-face part sees
    rapid deceleration as joint TENSION, see the piezo block). The H3LIS331
    high-g accel and the CAN PHY that used to share its top moved to
    fin_ble_board on 2026-11-17 (the top was too busy). The AON
    latch moved to wakeup_board and the activate chain + CAN gateway to
    aft_end_board in the 2026-07-31 redistribution/swap. The function
    name is kept (many sims/tools enumerate it). Each pogo pad is a
    single-net landing for an external fixture (oscilloscope, current
    shunt, BOOT0 jumper, ISP programmer, etc.).

    The array exposes each MCU's purpose pins plus the system serial buses:
    programming (SWD + BOOT0/NRST to the MP25 M33), the SYS_SPI ISP bus and
    SYS_I2C control/sensor bus (the CAN replacement), the live fin-driver
    lines, spare GPIO, and power. The retired CAN + spin-brake pads are gone."""
    # Bottom-face bench pad map (2026-09-10 re-layout). Grouped by function
    # in rows around the centred PARACHUTE_CUTTER_ACTIVATE common, at the array's 2.101 mm
    # pitch; positions are pinned in locked_placements.json so the silkscreen
    # groups and the bench fixture stay in step. The four TP_ACT_MOTOR*
    # single-phase probes are GONE — every fin now surfaces its FULL bipolar
    # pair set (A1/A2 + B1/B2), so a stepper can actually be driven from this
    # face rather than only probed.
    POGOS = {
        # ── SPI ── SYS_SPI ISP root (MP25 SPI2 -> G0B1 SPI3 slaves)
        "TP_SPI_MOSI":    "SYS_SPI_MOSI",
        "TP_SPI_CS_FIN":  "SYS_SPI_CS_FIN",
        "TP_SPI_MISO":    "SYS_SPI_MISO",
        "TP_SPI_SCLK":    "SYS_SPI_SCLK",
        # ── FIN 1..4 ── full bipolar coil pairs, one row per fin pair.
        # Each coil's two lands are ADJACENT so the go/return currents
        # cancel: these are PWM-switched phases crossing 22 LGA lands to
        # reach the drivers on fin_ble_board, and pair adjacency is what
        # keeps the loop area (and the stack-length radiator) small.
        "TP_FIN1_A1":     "FIN1_AOUT1",
        "TP_FIN1_A2":     "FIN1_AOUT2",
        "TP_FIN1_B1":     "FIN1_BOUT1",
        "TP_FIN1_B2":     "FIN1_BOUT2",
        "TP_FIN2_A1":     "FIN2_AOUT1",
        "TP_FIN2_A2":     "FIN2_AOUT2",
        "TP_FIN2_B1":     "FIN2_BOUT1",
        "TP_FIN2_B2":     "FIN2_BOUT2",
        "TP_FIN3_A1":     "FIN3_AOUT1",
        "TP_FIN3_A2":     "FIN3_AOUT2",
        "TP_FIN3_B1":     "FIN3_BOUT1",
        "TP_FIN3_B2":     "FIN3_BOUT2",
        "TP_FIN4_A1":     "FIN4_AOUT1",
        "TP_FIN4_A2":     "FIN4_AOUT2",
        "TP_FIN4_B1":     "FIN4_BOUT1",
        "TP_FIN4_B2":     "FIN4_BOUT2",
        # NOTE: no TP_FIN_VREF. The shared DRV8428E current-set reference is
        # NOT surfaced on this face (omitted from the final pad map) — there
        # is no bench access to the fin current setpoint. FIN_VREF still
        # crosses the joints; only the aft pad is gone.
        # ── CAN ── client-extension gateway (MP25 FDCAN1 -> TCAN1042)
        "TP_CAN_N":       "EXT_CAN_N",
        "TP_CAN_P":       "EXT_CAN_P",
        # ── BAT ── power monitor / shunt insertion
        "TP_BAT_RAW":     "BAT_RAW",
        "TP_BAT_PROT":    "BAT_PROT",
        # ── parachute cutter ── PARACHUTE_CUTTER_SET arms the high side;
        # ACTIVATE_CONFIRM is the 33 V rail monitor. Driving the set pad
        # on the bench connects ACTIVATE_HV to the restraint wires.
        "TP_ACT_CONFIRM": "ACTIVATE_CONFIRM",
        "TP_PARACHUTE_CUTTER_SET":     "PARACHUTE_CUTTER_SET",
        # ── GROUND ── the single bench ground
        "TP_GND_ACT":     "FLEX_GND",
        # ── HALL ── fin-deploy DRV5023 (OFF-board). HALL_VIN exposes the
        # sensor's own 3V3 rail -- NOT the 3V3_AON that TP_VDD carries --
        # so the open-drain OUT reads meaningfully only when 3V3 is up.
        "TP_FIN_HALL":    "FIN_HALL",
        "TP_HALL_VIN":    "3V3",
        # ── I2C ── SYS_I2C control / sensor / payload bus
        "TP_I2C_SDA":     "SYS_I2C_SDA",
        "TP_I2C_SCL":     "SYS_I2C_SCL",
        # ── PROGRAM_MP25 ── Tag-Connect TC2030-CTX signal ORDER so a stock
        # 6-pad Cortex fixture maps straight onto it, then the straps.
        # BOOT0 sits LAST and adjacent to GND, never next to VDD: it has a
        # 10 k pull-down, so a bridge to ground is a no-op while a bridge to
        # the rail would silently drop the MP25 into the ROM bootloader.
        "TP_VDD":         "3V3_AON",
        "TP_SWDIO":       "COMP_SWDIO",
        "TP_NRST":        "NRST",
        "TP_SWCLK":       "COMP_SWDCLK",
        "TP_MP25_GND1":   "FLEX_GND",
        "TP_SWO":         "SWO",
        "TP_MP25_GND2":   "FLEX_GND",
        "TP_BOOT0":       "BOOT0",
        # ── GPIO ── 4-to-16 sector-decoder address lines (NOT spares while
        # the parachute-cutter rail is armed -- they select which restraint cuts)
        "TP_GPIO_0":      "GPIO_EXT_0",
        "TP_GPIO_1":      "GPIO_EXT_1",
        "TP_GPIO_2":      "GPIO_EXT_2",
        "TP_GPIO_3":      "GPIO_EXT_3",
        # ── (2026-11-21, user) dev-board programming + diagnostics ──
        # MP25 debug console (USART6 = a ROM-bootloader UART)
        "TP_CONS_TX":     "MP25_CONSOLE_TX",
        "TP_CONS_RX":     "MP25_CONSOLE_RX",
        # WBA55 SWD — direct debug / recovery even when the MP25 is down
        # (normally the MP25 reflashes it: it drives the WBA's BOOT0 / reset /
        # LPUART into the ROM bootloader)
        "TP_WBA_SWDIO":   "WBA_SWDIO",
        "TP_WBA_SWCLK":   "WBA_SWCLK",
        "TP_WBA_NRST":    "WBA_NRST",
        # fin MCU (STM32U545) SWD — its recovery path
        "TP_FIN_SWDIO":   "FIN_MCU_SWDIO",
        "TP_FIN_SWCLK":   "FIN_MCU_SWCLK",
        "TP_FIN_NRST":    "FIN_MCU_NRST",
    }
    # Pin-1 convention: the FIRST pad of each silkscreen group is SQUARE,
    # the rest round. Same 2.0 mm size and pitch either way — the silhouette
    # alone tells a bench user where a group starts, with no legend to read.
    # Single-pad groups (parachute wires, GROUND) get no marker: there is no run to start.
    SQUARE_STARTS = {
        "TP_SPI_MOSI",                                     # SPI
        "TP_FIN1_A1", "TP_FIN2_A1", "TP_FIN3_A1", "TP_FIN4_A1",   # FIN 1..4
        "TP_CAN_N",                                        # CAN
        "TP_BAT_RAW",                                      # BAT
        "TP_ACT_CONFIRM",                                  # parachute cutter
        "TP_FIN_HALL",                                     # HALL
        "TP_I2C_SDA",                                      # I2C
        "TP_JUMP_WAKE",                                    # JUMPSTART
        "TP_VDD",                                          # PROGRAM_MP25
        "TP_GPIO_0",                                       # GPIO
        "TP_CONS_TX", "TP_WBA_SWDIO", "TP_FIN_SWDIO",     # (2026-11-21) dev board
    }
    for ref, net in POGOS.items():
        # Pogo pads have no MFG PN; system.py treats them as bare PCB
        # geometry. Smash factory defaults to manf_pn="Pogo_Pad_D2.0mm"
        # (the part's internal designation) — override to match.
        # (2026-11-19, user) the bench pads become CONTACTS of the aft_end_cap's
        # crown (the public interface; no PCB — board_tag AFT_CAP is virtual);
        # only the two parachute-cutter pads stay, centred on aft_end's bottom.
        btag = "aft_end_board" if ref in _AFT_CUTTER_PADS else AFT_CAP
        pad = add_pogo_pad(d, ref=ref, board_tag=btag,
                           manf_pn=None, square=ref in SQUARE_STARTS)
        _net(d, net).connect(pad.pin("1"))

    # ── piezo launch/impact sensor — fin_ble top, compression-loaded ──
    # Steminc SMD10T04R111 bare PZT disc (Ø10 × 0.4 mm, SM111 hard PZT,
    # wrap-around electrode) reflowed flat onto fin_ble_board's TOP face on
    # the spin axis (2026-07-31 stack reorder, user call: the disc + column
    # swapped off the saturated aft_end top; fin_ble — now the battery
    # compartment ceiling — has the room). The TOP (nose-facing) face is
    # the hard rule (user-confirmed over the compartment-side bottom):
    #   • MECHANICAL — rapid deceleration throws every part AFT, so a nose-facing
    #     (top) face loads the disc in COMPRESSION against rigid FR4
    #     (far below the >500 MPa PZT compressive strength; this is also the
    #     bonded-compression sensing mode). An aft-facing mount inverts
    #     that: the disc's inertia under rapid deceleration is carried by the
    #     In52 joints in TENSION, or by the
    #     potting pillar behind it — where any fill void becomes a bending
    #     span, and PZT in bending (~80-100 MPa, less at solder stress
    #     risers) cracks. Never mount the ceramic on an aft-facing face.
    #   • THERMAL — PZT depoles above ~Curie/2 ≈ 160 °C, so the disc can
    #     only be attached in the final In52/Sn48 118 °C step. ⚠ OPEN
    #     ASSEMBLY ITEM: the disc's face now sits in the fin_ble↔wakeup
    #     gap, so the fold/pot sequence must keep that gap open (attach the
    #     disc, close the fold, pot) — verify against the assembly order.
    # It replaced the CEB-21018-L100 brass diaphragm (−20…+60 °C — the
    # narrowest-rated part in the round; SM111's ~320 °C Curie clears the
    # full envelope) and with it the milled pocket: a rigid bonded disc
    # needs no recess or flex gap. Bonded-compression sensing scales with
    # thickness² (diameter-independent), compared with the 0.30 V
    # threshold under rapid deceleration. Two pads: MAIN electrode → sense node, WRAP (top electrode
    # brought around) → GND.
    #
    # A LOCAL TLV3691 thresholds PIEZO_P → COMP_OUT (= piezo_over_threshold),
    # which crosses to the M33 PD5 EXTI as the drop-shock witness for the
    # sensor deployment, before PARACHUTE_CUTTER_SET is allowed to cut.
    # The comparator + its resistors ride the SAME top face right beside the
    # disc (the EE's hand-placed x≈8.5 column) so the high-impedance PIEZO_P
    # charge node stays microscopically short — only the digital edge
    # crosses off-tile (and the hub is now 2 gaps away, not 5). The packer
    # fits the fins cluster (G0B1 + 4× DRV8428E) around these locks.
    # PARACHUTE_CUTTER_SET / ACTIVATE_CONFIRM are firmware GPIOs now — the old hardware
    # confirm AND-gate is gone. The comparator runs off the always-on bootstrap
    # 3V3 (exposed on the aft_end TP_VDD pogo) so the detector is alive while
    # the unit waits for launch. Complements the H3LIS331 high-G accel (on
    # fin_ble_board's top since 2026-11-17): the H3LIS gives the quantitative ±400 g over
    # I²C, the piezo the fast edge.
    piezo = add_piezo_disc_smd10t04r111(d, ref="P_PIEZO",
                                        board_tag="aft_end_board")
    _net(d, "PIEZO_P").connect(piezo.pin("1"))   # MAIN (bottom electrode)
    _net(d, "GND")    .connect(piezo.pin("2"))   # WRAP (top electrode, wrapped)
    res_between(d, "PIEZO_P", "GND", "1M", ref="R_PIEZO_BLEED",
                board_tag="aft_end_board")   # DC return + charge bleed
    res_between(d, "PIEZO_P",  "COMP_INP", "100k", ref="R_COMP_SER",
                board_tag="aft_end_board")
    res_between(d, "3V3_AON",  "COMP_INM", "1M",   ref="R_THR1",
                board_tag="aft_end_board")
    res_between(d, "COMP_INM", "GND",      "100k", ref="R_THR2",
                board_tag="aft_end_board")
    # TLV3691 nanopower comparator (~0.15 µA Iq) — replaces the LMV331 so the
    # launch detector can stay on the always-on 3V3 without being an ~80 µA shelf
    # load. Push-pull output → NO pull-up (the LMV331's R_COMP_PU is gone, which
    # would otherwise sink ~33 µA whenever COMP_OUT is low ≈ always). V+ is pin 6
    # (pin 5 is NC). COMP_OUT drives the M33 PD5 EXTI directly.
    # (2026-11-22) TLV3691 lots are China. The MCP6541 (SOT-23-5, 1.45 mm) does
    # NOT fit: this column sits in the battery-holder floor's 0.6 mm piezo
    # pocket, the floor is 1.2 mm and the slot lies under a cell (no
    # through-cut). Needs a ≤ 0.6 mm comparator (TLV7031 X2SON: Digi-Key US lot).
    # (2026-11-22) → TLV7031DPWR (X2SON-5 0.4 mm, 335 nA, push-pull; Digi-Key US lot)
    comp = add_tlv7031dpwr(d, ref="U_COMP_PZ", board_tag="aft_end_board")
    _net(d, "COMP_INP").connect(comp.pin("IN+"))
    _net(d, "GND")     .connect(comp.pin("V-"))
    _net(d, "COMP_INM").connect(comp.pin("IN-"))
    _net(d, "COMP_OUT").connect(comp.pin("OUT"))  # push-pull → M33 PD5 EXTI
    _net(d, "3V3_AON") .connect(comp.pin("V+"))   # launch detector active from Standby on
    cap_to_gnd(d, "3V3_AON", "100nF", ref="C_COMP_PZ",
               board_tag="aft_end_board", pin=comp.pin("V+"))   # local comparator decoupling

    # ── "Healthy and running" beacons (2026-11-18, user: signal a fully
    # active system to a reader clamped on / at the barrel; redundant to IR).
    # Both are keyed by the MP25 (PG7 / PG8, freed by the retired nose LEDs),
    # so they only ever run when the main system is up.
    #
    # VIBRATION: the launch disc doubles as the emitter. PIEZO_TX (MP25 PG8,
    # a 3.3 V square wave — e.g. a coded ~kHz–tens-of-kHz burst) couples onto
    # PIEZO_P through 1 k + 10 nF (≈ 2.7 V across the 2.1 nF disc). Idle, the
    # pin holds low, so the 10 nF loads the disc and the launch comparator's
    # sensitivity drops ~6× — accepted (user: launch sensing is not subtle).
    # Firmware masks COMP_OUT while it transmits.
    res_between(d, "PIEZO_TX", "PIEZO_TX_C", "1k", ref="R_PZ_TX",
                board_tag="aft_end_board")
    cap_to_gnd(d, "PIEZO_TX_C", "10nF", gnd_net="PIEZO_P", ref="C_PZ_TX",
               board_tag="aft_end_board")
    # MAGNETIC: an 8-turn rim spiral embedded in aft_end_board (In2.Cu,
    # r 13–15.5 mm, 0.2 mm trace (2026-11-21), In3.Cu return — away from the antennas), pulsed at
    # 3–30 Hz from BAT_PROT through a 4 × 47 Ω bank (≈ 0.19 A ≈ 1.5 A·turns)
    # by a low-side BSS138 (top face — the battery ceiling's bottom stays empty,
    # 2026-11-20) + passives on activation_interface
    # (aft_end's top is the battery-holder seat). smash.sim.inductive: ≥ ~45 dB at a ring
    # clamp through 1–10 mm of barrel steel. HEALTH_COIL_TX = MP25 PG7.
    # The coil itself is copper only — added AFTER placement by
    # _place_health_coil (like the castellations) so the packer never sees a
    # Ø31 obstacle; its two nets are wired there.
    for k in range(1, 5):
        res_between(d, "HEALTH_COIL_RET", "HEALTH_COIL_D", "47", ref=f"R_COIL_{k}",
                    board_tag="activation_interface")
    q_coil = add_ssm3k7002kfu_lf(d, ref="Q_HEALTH_COIL", board_tag="activation_interface")
    _net(d, "HEALTH_COIL_D").connect(q_coil.pin("3"))   # Drain
    _net(d, "GND")          .connect(q_coil.pin("2"))   # Source
    _net(d, "HEALTH_COIL_G").connect(q_coil.pin("1"))   # Gate
    res_between(d, "HEALTH_COIL_TX", "HEALTH_COIL_G", "100", ref="R_COIL_G",
                board_tag="activation_interface")
    res_between(d, "HEALTH_COIL_G", "GND", "100k", ref="R_COIL_PD",
                board_tag="activation_interface")
    # decouples the coil's FEED (pin 1, on BAT_PROT) — not the FET drain,
    # which sits on HEALTH_COIL_D. The coil is added post-place
    # (_place_health_coil), so it is referenced by (ref, pin).
    cap_to_gnd(d, "BAT_PROT", "10uF", ref="C_HEALTH_COIL",
               board_tag="activation_interface", pin=("L_HEALTH_COIL", "1"))

    _build_activation_array(d)


# ── aft parachute-cutter array — 16 nichrome restraint sectors ──
def _build_activation_array(d: Design) -> None:
    """Sixteen nichrome parachute restraints for an emergency sensor drop.

    The payload is a sonar, an infrared sensor, or a radio, put down on
    an illuminated point so missing people can be found while the window
    is still open. Fins steer the fall; the 1064 nm quadrant detector
    and camera see the mark. At release, PARACHUTE_CUTTER_SET turns on the high-side
    PFET and connects ACTIVATE_HV to PARACHUTE_CUTTER_ACTIVATE, the
    common that feeds whichever restraint the sector decoder has
    selected. That wire fuses and lets its sector of the canopy go.

    A TPS61175 boost makes ACTIVATE_HV = 33 V (off COMP_5V) and sources the
    cutter current DIRECTLY — no reservoir cap. At this operating point one
    sector is ~30 mm of 25 µm / fine outbound at current density
    ~1000 A/mm²: V = J·ρ·L = 33 V, the wire draws ~20-120 mA depending on
    gauge (0.65-4 W), and self-fuses adiabatically in ~5 ms. That power is
    well within the boost's ~280 mA @ 33 V output, so the old cutter cap
    (and the cell-pulse problem it solved) is GONE — the wire is the load.

    Selection (2026-11-20): a 4 × 4 DIODE MATRIX driven straight by the fin
                MCU (G0B1 PA0..3 = rows, PA5..8 = columns). Row = DMP6110
                high side (BSS138 level shift), column = BSS138 low side; each
                wire has its own BAS40-02L steering diode (aft_end top) — no
                sneak paths, 8 nets to aft_end instead of 17. Replaces the
                CD74HC4514 decoder + 16 DMN6075 select NFETs.
    Set/activate: PARACHUTE_CUTTER_SET (MP25) → DMP6110 master high side
                (ACTIVATE_HV → PARACHUTE_CUTTER_ACTIVATE → the 4 row PFETs).
                Without it ACTIVATE_HV reaches no wire even if a row and a
                column switch both short. The
                PFET gate is a resistor divider (R1=R2=100k off
                ACTIVATE_HV) → V_GS ≈ -16.5 V at 33 V, inside the ±20 V
                limit (no zener).
    Monitor:    ACTIVATE_HV → 100k/11k divider → ACTIVATE_CONFIRM (MP25 ADC) so
                firmware verifies the 33 V rail before the cut; R_ACTIVATE_BLEED
                discharges the small output cap when PARACHUTE_CUTTER_SET is released.

    Both 33 V (vs the cap's 25 V) and 60 V FETs are comfortable; only the
    boost's mandatory output ceramic remains on ACTIVATE_HV (50 V, loop
    stability — NOT a cutter reservoir). All on aft_end_board. SAFETY
    (eFuse-gated decoder + PARACHUTE_CUTTER_SET interlock): no restraint
    cuts unless the package is in MAIN (BAT_PROT live) AND
    PARACHUTE_CUTTER_SET drives the high side."""
    # SECTOR SELECT + ACTIVATE CHAIN on aft_end_board's TOP face (moved here
    # from activation 2026-07-31; the piezo cluster moved OUT to
    # fin_ble_board's top in the same-day stack reorder, freeing the room
    # that lets the whole chain sit together): the CD74HC4514 4-to-16
    # decoder, 16 select NFETs, parachute_cutter_activate high-side + level shift, HV monitor and
    # bleed all sit ONE via away from the outbound wire-pad ring + common
    # on aft_end's bottom face — the 16 Y*_ACTIVATE_SEL gate nets are
    # tile-local, and ACT_WIRE_0..15 + parachute_cutter_activate never cross the battery
    # compartment. ACTIVATE_HV comes down from the boost on activation, which
    # the reorder made the DIRECT neighbour (one thin gap, not the battery
    # column; the 2.8 mm inductor still doesn't fit this tile's thin gap).
    # The bench pogos + wire pads + common ride aft_end's BOTTOM (aft
    # service) face.
    BT = "aft_end_board"
    # ── activate-rail boost: COMP_5V → ACTIVATE_HV 33 V (TPS61175) ──────────────
    # Fed from COMP_5V (not BAT_PROT): 5→33 V is 85 % duty vs 88 % from a
    # depleted cell — comfortable headroom under the TPS61175 ~89 % DMAX.
    # The boost POWER STAGE lives one tile up on ACTIVATION_INTERFACE
    # (top face): its 2.8 mm WE-PD inductor would force the thin
    # aft_end↔activation spacer to grow by ~1 mm, and in single-cell mode
    # aft_end's top also hosts the horizontal cell swath (|x| < 7.55 mm),
    # which the boost's three big bodies don't fit around. Since the
    # 2026-07-31 stack reorder activation is aft_end's DIRECT neighbour,
    # so ACTIVATE_HV (unswitched) crosses only that one thin gap — no longer
    # the battery column (its feed COMP_5V now rides the column lands down
    # from power_board instead; 33 V across 0.37 mm potted land gaps was
    # fine per IPC-2221, and the 5 V rail is more comfortable still); the
    # parachute_cutter_activate high-side, decoder, NFETs, monitor and bleed sit on aft_end with
    # the wires — safety topology unchanged.
    # (2026-11-20, user) the fire boost moved to power_board's TOP, next to the
    # COMP 5 V boost that feeds it: both tall boost stages face ONE gap
    # (power↔compute); only ACTIVATE_HV (33 V, ≤ 0.12 A) runs down to the
    # cutter / matrix on activation_interface.
    BT_BOOST = "power_board"
    boost = add_tps61175pwpr(d, ref="U_ACTIVATE_BOOST", board_tag=BT_BOOST)
    _net(d, "COMP_5V")    .connect(boost.pin("VIN"))     # 3
    _net(d, "ACTIVATE_SW")    .connect(boost.pin("SW_1"))    # 1
    _net(d, "ACTIVATE_SW")    .connect(boost.pin("SW_2"))    # 2
    _net(d, "ACTIVATE_FB")    .connect(boost.pin("FB"))      # 9
    for p in ("PGND_1", "PGND_2", "PGND_3", "AGND", "EP", "NC", "SYNC"):
        _net(d, "GND")    .connect(boost.pin(p))
    # EN = COMP_5V: ACTIVATE_HV is live whenever the package is in MAIN. The
    # PARACHUTE_CUTTER_SET interlock + bleed keep the restraints intact until it cuts.
    _net(d, "COMP_5V")    .connect(boost.pin("EN"))      # 4
    _net(d, "ACTIVATE_COMP")  .connect(boost.pin("COMP"))    # 8
    _net(d, "ACTIVATE_FREQ")  .connect(boost.pin("FREQ"))    # 10
    res_between(d, "ACTIVATE_FREQ", "GND", "174k", ref="R_ACTIVATE_FREQ", board_tag=BT_BOOST)  # ≈600 kHz (2026-11-21: 176k is not E96 → 174k, +1 %)
    _net(d, "ACTIVATE_SS")    .connect(boost.pin("SS"))      # 5
    cap_to_gnd(d, "ACTIVATE_SS", "47nF", ref="C_ACTIVATE_SS", board_tag=BT_BOOST, pin=boost.pin("SS"))
    cap_to_gnd(d, "COMP_5V", "10uF", ref="C_ACTIVATE_IN", board_tag=BT_BOOST, pin=boost.pin("VIN"))
    # WE-PD 10 µH (DS 4.7-47 µH window) — reused from the COMP_5V boost.
    # D_ACTIVATE keeps the MBRS540T3G: the 33 V output leaves only 7 V of V_RRM
    # margin, so this rectifier is NOT a candidate for the 40 V flat part
    # until that headroom is revisited (it is now the only MBRS540 user).
    # (2026-11-21) Coilcraft XGL5020-822MEC 8.2 µH (XGL5020 family, same land
    # pattern as L_BOOST_COMP's 4.7 µH). At D ≈ 0.85-0.87 the TPS61175's slope
    # compensation wants L well above its 4.7 µH minimum (DS §7.3.1), so 8.2 µH:
    # ripple ≈ 0.8-0.9 A p-p → steady peak 1.6-1.7 A < the 1.8 A 10 %-drop point.
    # Loop (DS §8.2.2.10 model, 4.7 µF derated to ~1.5 µF at 33 V): fc ≈ 7-8 kHz,
    # PM ≈ 87-89°, fRHPZ ≥ 79 kHz — the 1.6 k / 220 nF network stays. Load from
    # the battery-mission sim (smash-electronics tools/simulate_battery_mission.py,
    # P_SECTOR): ONE burn-wire sector, 5 W × 5 ms → 0.15 A at 33 V ≈ 1.2 A in
    # from COMP_5V; D ≈ 0.85, ripple ≈ 1.5 A p-p at 600 kHz → ~1.9 A peak
    # (Isat 3.6 A at 20 % drop). Switching a wire onto the 4.7 µF rail drives the
    # boost into its 5 A max limit (transient; the cycle-by-cycle limit holds as
    # the composite core soft-saturates). The LPS4018 / 744043100 saturated at
    # ~1-1.2 A.
    l_activate = add_ihlp2020bzer100m01(d, ref="L_ACTIVATE", board_tag=BT_BOOST)   # (2026-11-22) 10 µH IHLP-2020BZ-01 (Mexico lots); was XGL5020-822
    _net(d, "ACTIVATE_SW") .connect(l_activate.pin("1"))   # marked start lead on SW (Coilcraft: lowest EMI)
    _net(d, "COMP_5V").connect(l_activate.pin("2"))
    # (2026-11-20, user) flat 60 V / 1 A SOD-123Flat (1.1 mm) instead of the
    # 2.56 mm MBRS540T3G SMC — out of the tall-part group, more V_RRM margin
    d_activate = add_rb160vam_60(d, ref="D_ACTIVATE", board_tag=BT_BOOST)   # (2026-11-21) SOD323F 0.8 mm, same 60 V / 1 A
    _net(d, "ACTIVATE_SW").connect(d_activate.pin("A"))
    _net(d, "ACTIVATE_HV").connect(d_activate.pin("K"))
    # FB: VOUT = 1.229 × (1 + 261/10) = 33.3 V
    res_between(d, "ACTIVATE_HV", "ACTIVATE_FB", "261k", ref="R_ACTIVATE_FB1", board_tag=BT_BOOST)
    res_between(d, "ACTIVATE_FB", "GND",     "10k",  ref="R_ACTIVATE_FB2", board_tag=BT_BOOST)
    # COMP RC — light load (the wire), loop non-critical; reuse known values.
    res_between(d, "ACTIVATE_COMP", "ACTIVATE_COMP_C", "1.6k", ref="R_ACTIVATE_COMP", board_tag=BT_BOOST)
    cap_to_gnd(d, "ACTIVATE_COMP_C", "220nF", ref="C_ACTIVATE_COMP", board_tag=BT_BOOST, pin=(boost.ref, None))
    # Boost output ceramic — loop stability only (DS wants ≥4.7 µF out), NOT
    # an activate reservoir. cap_to_gnd dispatches 4.7 µF → 50 V KEMET 0603.
    # (2026-11-21, user) on the 33 V rail: 2 × 2.2 µF 0805 X7R 50 V (KEMET
    # C0805C225K5RACTU) — no 0603 2.2 µF X7R is made above 10 V.
    for _k in (1, 2):
        # (2026-11-22, smaller-parts round 17) 1.45 → 1.25 mm: TDK C2012X7R1H225K125AC
        from smash.parts.passives import add_capacitor_tdk_c2012x7r1h225k125ac
        _c = add_capacitor_tdk_c2012x7r1h225k125ac(d, ref=f"C_ACTIVATE_OUT_{_k}", board_tag=BT_BOOST)
        _net(d, "ACTIVATE_HV").connect(_c.pin("1")); _net(d, "GND").connect(_c.pin("2"))

    # ── bleed + HV monitor ─────────────────────────────────────────────
    res_between(d, "ACTIVATE_HV", "GND", "100k", ref="R_ACTIVATE_BLEED", board_tag=BT)
    # HV monitor: 33 V × 11/(100+11) = 3.27 V into the MP25 ADC.
    res_between(d, "ACTIVATE_HV", "ACTIVATE_CONFIRM", "100k",
                ref="R_ACTIVATE_MON1", board_tag=BT)
    res_between(d, "ACTIVATE_CONFIRM", "GND", "11k",
                ref="R_ACTIVATE_MON2", board_tag=BT)

    # ── high-side parachute_cutter_activate (DMP6110) + level-shift + gate-clamp divider ─────
    # (2026-11-21) BUK6D120-60PX DFN2020MD-6 0.65 mm (was DMP6110 TSOT-26 1.0 mm)
    unlock = add_buk6d120_60px(d, ref="Q_PARACHUTE_CUTTER_ACTIVATE", board_tag=BT)
    for dp in ("D_1", "D_2", "D_3", "D_4", "D_5"):
        _net(d, "PARACHUTE_CUTTER_ACTIVATE").connect(unlock.pin(dp))   # drains → sector common
    for sp in ("S_1", "S_2"):
        _net(d, "ACTIVATE_HV").connect(unlock.pin(sp))      # source = the 33 V rail
    _net(d, "PARACHUTE_CUTTER_ACTIVATE_G").connect(unlock.pin("G"))
    # gate divider: ACTIVATE_HV ─100k─ G ─100k─ (BSS138 drain). parachute_cutter_activate → G≈16.5 V
    # → V_GS≈-16.5 V (PFET on, inside ±20 V); without parachute_cutter_activate → G=ACTIVATE_HV (off).
    res_between(d, "ACTIVATE_HV", "PARACHUTE_CUTTER_ACTIVATE_G", "100k", ref="R_PARACHUTE_CUTTER_ACTIVATE_H", board_tag=BT)
    res_between(d, "PARACHUTE_CUTTER_ACTIVATE_G", "PARACHUTE_CUTTER_ACTIVATE_GD", "100k", ref="R_PARACHUTE_CUTTER_ACTIVATE_L", board_tag=BT)
    q_unlock = add_ssm3k7002kfu_lf(d, ref="Q_PARACHUTE_CUTTER_ACTIVATE_LS", board_tag=BT)
    _net(d, "PARACHUTE_CUTTER_ACTIVATE_GD").connect(q_unlock.pin("3"))   # drain
    _net(d, "GND")        .connect(q_unlock.pin("2"))   # source
    _net(d, "PARACHUTE_CUTTER_SET").connect(q_unlock.pin("1"))  # gate ← MP25 PARACHUTE_CUTTER_SET

    # ── (2026-11-20, user) 4 × 4 DIODE MATRIX, driven straight by the fin MCU ──
    # Wire k = (row k // 4, column k % 4): row PFET (high side, behind the
    # master PARACHUTE_CUTTER_ACTIVATE PFET) → D_ACT_WIRE_k (BAS40-02L, on
    # aft_end's TOP in the holder floor's annular pocket) → ACT_WIRE_k clamp
    # tab → nichrome → its column tab ACT_COL_j → column NFET → GND. Only 8
    # nets (ACT_ROW_0..3, ACT_COL_0..3) cross to aft_end (was 16 wires + the
    # common); the series diodes leave NO sneak path. Selection comes from the
    # fin MCU (G0B1, PA0..3 rows / PA5..8 columns: logic-level BSS138s, 100 k
    # pull-downs → all off while it is unpowered), the release from the MP25
    # (PARACHUTE_CUTTER_SET → master PFET): TWO processors must agree.
    # Firmware rule: at most ONE row and ONE column at a time.
    for r in range(4):
        row = f"ACT_ROW_{r}"
        q = add_buk6d120_60px(d, ref=f"Q_ACT_ROW{r}", board_tag=BT)   # (2026-11-21) was DMP6110
        for dp in ("D_1", "D_2", "D_3", "D_4", "D_5"):
            _net(d, row).connect(q.pin(dp))
        for sp in ("S_1", "S_2"):
            _net(d, "PARACHUTE_CUTTER_ACTIVATE").connect(q.pin(sp))
        _net(d, f"{row}_G").connect(q.pin("G"))
        # gate divider off the PFET's own source: V_GS ≈ −16.5 V on, 0 V off
        res_between(d, "PARACHUTE_CUTTER_ACTIVATE", f"{row}_G", "100k",
                    ref=f"R_ACT_ROW{r}_H", board_tag=BT)
        res_between(d, f"{row}_G", f"{row}_GD", "100k", ref=f"R_ACT_ROW{r}_L", board_tag=BT)
        ls = add_ssm3k7002kfu_lf(d, ref=f"Q_ACT_ROW{r}_LS", board_tag=BT)
        _net(d, f"{row}_GD").connect(ls.pin("3"))
        _net(d, "GND").connect(ls.pin("2"))
        _net(d, f"ACT_ROW_SEL_{r}").connect(ls.pin("1"))
        res_between(d, f"ACT_ROW_SEL_{r}", "GND", "100k", ref=f"R_ACT_ROW{r}_PD", board_tag=BT)
    for c in range(4):
        q = add_ssm3k7002kfu_lf(d, ref=f"Q_ACT_COL{c}", board_tag=BT)
        _net(d, f"ACT_COL_{c}").connect(q.pin("3"))
        _net(d, "GND").connect(q.pin("2"))
        _net(d, f"ACT_COL_SEL_{c}").connect(q.pin("1"))
        res_between(d, f"ACT_COL_SEL_{c}", "GND", "100k", ref=f"R_ACT_COL{c}_PD", board_tag=BT)
        # column clamp tab: the return ends of its 4 wires
        ct = add_clamp_tab(d, ref=f"P_ACT_COL_{c}", board_tag="aft_end_board", feature="bottom")
        _net(d, f"ACT_COL_{c}").connect(ct.pin("1"))
    # Restraint-wire clamp tabs (aft_end BOTTOM, r 6.4 ring) + their series
    # steering diodes right above them (aft_end TOP, holder-floor pocket).
    for i in range(16):
        dk = add_bas40_02l(d, ref=f"D_ACT_WIRE_{i}", board_tag="aft_end_board")
        _net(d, f"ACT_ROW_{i // 4}").connect(dk.pin("A"))
        _net(d, f"ACT_WIRE_{i}").connect(dk.pin("K"))
        pad = add_clamp_tab(d, ref=f"P_ACT_WIRE_{i}", board_tag="aft_end_board",
                            feature="bottom")
        _net(d, f"ACT_WIRE_{i}").connect(pad.pin("1"))


def build_camera_module(d: Design) -> None:
    """AR0234CS 2.3-MP monochrome global-shutter image sensor (83-ball
    ODCSP) + power-rail decoupling caps + RSVD pulldown. 2-lane MIPI
    CSI-2 + I²C + EXTCLK + RESET_BAR control. On a Ø34 tile (was Ø15,
    grown 2026-11-18 to carry the IR service-link pair and seat on the cup's
    stop bosses) behind the nose lens. It steers the drop onto the
    illuminated aim point and, once down, looks for people."""
    cam = add_ar0234cssm00suka0_cp(d, ref="U_CAM", board_tag="camera_module")
    _add_ir_service_link(d, "camera_module", "_C")

    # ── Power rails (per datasheet Table 3) ─────────────────────────
    # (2026-11-20, user) LOCAL camera rails, each with two sources: a FITTED
    # 0 Ω from the PMIC rail (COMP_1V2 / COMP_2V8) or a DNP LP5907 low-noise
    # LDO from BAT_PROT (already on the crown) — fit the LDO + lift the 0 Ω
    # if the PMIC rails prove too noisy for the sensor; never both.
    # 1.2V (VDD, VDD_PHY, VDD_DATA)
    for ball in ["A4", "A8", "A12", "B10", "D7", "E1", "G8"]:
        _net(d, "CAM_VDD_1V2", kind="power", voltage_v=1.2).connect(cam.pin(ball))
    _net(d, "CAM_VDD_1V2").connect(cam.pin("C8"))       # VDD_PHY
    _net(d, "CAM_VDD_1V2").connect(cam.pin("F11"))      # VDD_DATA

    # 1.8V (VDD_IO, VDDIO_PHY): logic level for MP25 SDIO/CSI
    for ball in ["A7", "B4", "B5", "B11", "D3", "D6", "F1", "G12"]:
        _net(d, "COMP_1V8", kind="power", voltage_v=1.8).connect(cam.pin(ball))
    _net(d, "COMP_1V8").connect(cam.pin("D10"))      # VDDIO_PHY

    # 2.8V (VAA, VAA_PIX, VAA_PHY): analog supply for image sensor
    for ball in ["A10", "B1", "G2", "G7"]:
        _net(d, "CAM_VAA_2V8", kind="power", voltage_v=2.8).connect(cam.pin(ball))  # VAA
    for ball in ["B8", "C2", "G1", "G9"]:
        _net(d, "CAM_VAA_2V8").connect(cam.pin(ball))   # VAA_PIX
    _net(d, "CAM_VAA_2V8").connect(cam.pin("F8"))       # VAA_PHY
    CT = "camera_module"
    # (2026-11-22) DDR3L moved the PMIC DDR rail to 1.35 V, so the camera's
    # 1.2 V core can no longer share it: U_CAM_LDO_VDD (LP5907 1.2 V from
    # BAT_PROT) is now FITTED, enabled by the camera IO rail COMP_1V8 (camera
    # off whenever the compute is off). The 2.8 V keeps its 0 Ω + DNP LDO pair.
    res_between(d, "COMP_2V8", "CAM_VAA_2V8", "0", ref="R_CAM_VAA_SRC", board_tag=CT)
    for ref, factory, out, cin, cout, en, fitted in (
            ("U_CAM_LDO_VDD", add_lp5907mfx_1_2_nopb, "CAM_VDD_1V2", "1uF", "2.2uF", "COMP_1V8", True),
            ("U_CAM_LDO_VAA", add_lp5907mfx_2_8_nopb, "CAM_VAA_2V8", "1uF", "4.7uF", "BAT_PROT", False)):
        ldo = factory(d, ref=ref, board_tag=CT)
        _net(d, "BAT_PROT").connect(ldo.pin("1"))   # IN
        _net(d, "GND")     .connect(ldo.pin("2"))
        _net(d, en)        .connect(ldo.pin("3"))   # EN
        _net(d, out)       .connect(ldo.pin("5"))   # OUT
        ldo.dnp = not fitted
        for c in (cap_to_gnd(d, "BAT_PROT", cin, ref=f"C_{ref[2:]}_IN", board_tag=CT, pin=ldo.pin("1"))
                  + cap_to_gnd(d, out, cout, ref=f"C_{ref[2:]}_OUT", board_tag=CT, pin=ldo.pin("5"))):
            c.dnp = not fitted

    # ── Grounds ─────────────────────────────────────────────────────
    for ball in ["A2", "A3", "A6", "B2", "C1", "C5", "D8", "D9",
                 "E2", "E8", "F2", "F9", "G10"]:
        _net(d, "GND", kind="ground").connect(cam.pin(ball))    # DGND
    for ball in ["A9", "C3", "G3", "G6"]:
        _net(d, "GND").connect(cam.pin(ball))                   # AGND
    for ball in ["B12", "E7"]:
        _net(d, "GND").connect(cam.pin(ball))                   # GNDIO_PHY

    # ── MIPI CSI-2 (2-lane: D0+D1 used; D2+D3 NC) ──────────────────
    _net(d, "CAM_CSI_D0_P") .connect(cam.pin("C9"))
    _net(d, "CAM_CSI_D0_N") .connect(cam.pin("C10"))
    _net(d, "CAM_CSI_D1_P") .connect(cam.pin("C12"))
    _net(d, "CAM_CSI_D1_N") .connect(cam.pin("C11"))
    _net(d, "CAM_CSI_CLK_P").connect(cam.pin("D11"))
    _net(d, "CAM_CSI_CLK_N").connect(cam.pin("D12"))

    # ── I²C + control ───────────────────────────────────────────────
    _net(d, "CAM_SCL")   .connect(cam.pin("F6"))     # SCLK
    _net(d, "CAM_SDA")   .connect(cam.pin("E6"))     # SDATA
    _net(d, "CAM_NRST")  .connect(cam.pin("F7"))     # RESET_BAR
    _net(d, "CAM_EXTCLK").connect(cam.pin("G11"))    # 27 MHz, local oscillator
    # (2026-11-21) local 27 MHz DSC1001 at the sensor's 1.8 V IO rail: the MP25
    # PA8 clock was 3.3 V into EXTCLK (abs max VDD_IO + 0.3 = 2.1 V); also
    # frees a sleeve lane and keeps a 27 MHz clock off the LDS.
    ycam = add_dsc1001ci1_027_0000(d, ref="Y_CAM_EXTCLK", board_tag="camera_module")
    _net(d, "COMP_1V8")  .connect(ycam.pin("1"))     # STANDBY# tied high
    _net(d, "GND")       .connect(ycam.pin("2"))
    _net(d, "CAM_EXTCLK").connect(ycam.pin("3"))
    _net(d, "COMP_1V8")  .connect(ycam.pin("4"))
    cap_to_gnd(d, "COMP_1V8", "100nF", ref="C_CAM_EXTCLK_VDD", board_tag="camera_module",
               pin=ycam.pin("4"))

    # (2026-11-21) CONTROL WAS UNCONNECTED (CAM_SCL / CAM_SDA / CAM_NRST were
    # one-pin nets — ERC). The sensor's I/O is 1.8 V (COMP_1V8); SYS_I2C (I2C1,
    # nothing else on it, AR0234 at 0x10) is 3.3 V → a two-MOSFET bidirectional
    # shifter per line (NXP AN10441: gate on the low rail, source low side,
    # drain bus side; pull-ups both sides — the bus side's are RPU_*_EXT on
    # wakeup). BSS138AKM: already in the library, 0.37 mm tall.
    for line in ("SCL", "SDA"):
        q = add_ssm3k35ctc_l3f(d, ref=f"Q_CAM_{line}", board_tag="camera_module")
        _net(d, "COMP_1V8")         .connect(q.pin("1"))   # gate
        _net(d, f"CAM_{line}")      .connect(q.pin("2"))   # source (1.8 V side)
        _net(d, f"SYS_I2C_{line}")  .connect(q.pin("3"))   # drain (3.3 V bus)
        res_between(d, "COMP_1V8", f"CAM_{line}", "4.7k", ref=f"R_CAM_{line}_PU",
                    board_tag="camera_module")
    # RESET_BAR: MP25 PA9 as OPEN-DRAIN (only ever pulls low) + pull-up to the
    # sensor's own 1.8 V, so no 3.3 V reaches it
    res_between(d, "COMP_1V8", "CAM_NRST", "10k", ref="R_CAM_NRST_PU",
                board_tag="camera_module")

    # ── Strap pins to GND (defaults per datasheet) ──────────────────
    _net(d, "GND").connect(cam.pin("A5"))   # SADDR — I²C addr 0x20/0x21
    _net(d, "GND").connect(cam.pin("B6"))   # OE_BAR — MIPI mode
    _net(d, "GND").connect(cam.pin("F5"))   # TEST — normal operation
    _net(d, "GND").connect(cam.pin("D5"))   # TRIGGER — not used

    # ── Required passives per datasheet ─────────────────────────────
    # RSVD (F10): 1.5kΩ to DGND. res_between needs net names — use
    # an explicit named net (system.py emits the anon N$XX, but the
    # alias mechanism will resolve the merge if we add an explicit
    # name on either side).
    _net(d, "CAM_RSVD").connect(cam.pin("F10"))
    res_between(d, "CAM_RSVD", "GND", "1.5k", ref="R_CAM_RSVD",
                board_tag="camera_module")

    # CAP_1UF_PHY (F12): 1 µF decoupling for MIPI regulator
    _net(d, "CAM_PHY_REG").connect(cam.pin("F12"))
    cap_to_gnd(d, "CAM_PHY_REG", "1uF", ref="C_CAM_PHY_REG",
               board_tag="camera_module", pin=cam.pin("F12"))

    # ── Power-rail decoupling ───────────────────────────────────────
    # 100 nF HF caps absorbed by the ECM laminate; 1 µF bulk stays
    # discrete for frame-rate current swings.
    cap_to_gnd(d, "CAM_VDD_1V2", "100nF", ref="C_CAM_VDD_1",
               embedded_cap_absorbs=True, board_tag="camera_module", pin=(cam.ref, None))
    cap_to_gnd(d, "CAM_VDD_1V2", "1uF",   ref="C_CAM_VDD_BULK",
               board_tag="camera_module", pin=(cam.ref, None))
    cap_to_gnd(d, "COMP_1V8", "100nF", ref="C_CAM_VDDIO_1",
               embedded_cap_absorbs=True, board_tag="camera_module", pin=(cam.ref, None))
    cap_to_gnd(d, "COMP_1V8", "1uF",   ref="C_CAM_VDDIO_BULK",
               board_tag="camera_module", pin=(cam.ref, None))
    cap_to_gnd(d, "CAM_VAA_2V8", "100nF", ref="C_CAM_VAA_1",
               embedded_cap_absorbs=True, board_tag="camera_module", pin=(cam.ref, None))
    cap_to_gnd(d, "CAM_VAA_2V8", "1uF",   ref="C_CAM_VAA_BULK",
               board_tag="camera_module", pin=(cam.ref, None))


def _add_ir_service_link(d: Design, board_tag: str, sfx: str = "",
                         dnp: bool = False) -> None:
    """IR service-link pair on `board_tag`'s nose-facing TOP face: D_IR_TX
    (VSMB1940X01 940 nm emitter + its tile-local drive loop off BAT_PROT) and
    D_IR_WAKE (VBPW34FAS photodiode, cathode on the shared IR_WAKE wake net).

    (2026-11-18, user: "IR in every config") One copy per nose payload —
    radar_module (sfx ""), qpd_module ("_Q"), camera_module ("_C"; both
    payload boards grew to Ø34). (`core` has none yet — no compute-rim spot
    fits the photodiode.) Only IR_TX / IR_WAKE / BAT_PROT / GND are
    shared; the drive-loop nets carry the suffix so copies never short. Each
    diode looks out through a light pipe moulded into the cup nose (kept out
    of the black, IR-opaque potting — smash.export.cup_noses)."""
    first = len(d.chips)
    # D_IR_TX — VSMB1940X01 940 nm emitter, the TX half of the service link
    # (15 ns die → kbps–MHz OOK; the wand's receiver sets the rate). The
    # drive loop is TILE-LOCAL off BAT_PROT (alive in every state):
    # BAT_PROT → LED → 2× 27 Ω → BSS138 → GND ≈ 44 mA @ 4 V driven rail /
    # ≈ 31 mA @ 3.3 V shelf-diode rail (I_FM abs-max 200 mA; the split
    # current R keeps each 0402 at ~26 mW @ 50 % modulation duty —
    # firmware must cap continuous-ON dwell). Only the logic-level gate
    # net IR_TX crosses the backbone (→ WBA PA6, 3 joints): the WBA keys
    # the emitter from Standby with the MP25 dark, so a wand session — or
    # the bore-side optical downlink, the one channel that escapes a
    # chambered round (Ø30 steel bore is below cutoff at 2.4 GHz) — needs
    # no rail-up. 100 k gate pull-down holds it dark whenever the WBA is
    # unpowered (shelf); C_IR_TX is the local burst reservoir (real part,
    # never ECM-absorbed — it feeds 44 mA edges at the end of the rail).
    tx = add_vsmb1940x01(d, ref=f"D_IR_TX{sfx}", board_tag=board_tag)
    _net(d, "BAT_PROT").connect(tx.pin("A"))
    _net(d, f"IR_TX_K{sfx}") .connect(tx.pin("K"))
    res_between(d, f"IR_TX_K{sfx}", f"IR_TX_M{sfx}", "27",
                ref=f"R_IR_TX_A{sfx}", board_tag=board_tag)
    res_between(d, f"IR_TX_M{sfx}", f"IR_TX_D{sfx}", "27",
                ref=f"R_IR_TX_B{sfx}", board_tag=board_tag)
    q_irtx = add_ssm3k35ctc_l3f(d, ref=f"Q_IR_TX{sfx}", board_tag=board_tag)
    _net(d, f"IR_TX_D{sfx}").connect(q_irtx.pin("3"))   # Drain
    _net(d, "GND")    .connect(q_irtx.pin("2"))   # Source
    _net(d, f"IR_TX_G{sfx}").connect(q_irtx.pin("1"))   # Gate
    res_between(d, "IR_TX",   f"IR_TX_G{sfx}", "100",
                ref=f"R_IR_TX_G{sfx}",  board_tag=board_tag)
    res_between(d, f"IR_TX_G{sfx}", "GND",     "100k",
                ref=f"R_IR_TX_PD{sfx}", board_tag=board_tag)
    cap_to_gnd(d, "BAT_PROT", "1uF", ref=f"C_IR_TX{sfx}", board_tag=board_tag, pin=tx.pin("A"))

    # ── IR activation_unlock wake — VBPW34FAS daylight-filtered PIN photodiode ─────────
    # The optical on-switch (Standby → Ready, the merged staged state):
    # deliberate ~950 nm IR
    # illumination at the nose wakes the WBA55 from Stop1 via EXTI12.
    # Photoconductive mode against RPU_IR_WAKE (470 k → 3V3_AON, lives on
    # wakeup_board beside the WBA — the high-value bias stays OFF this
    # tile so the only long net is the photodiode's own cathode node).
    # Wake needs the node below V_IL ≈ 1 V: (3.3 − 1) / 470 k ≈ 5 µA of
    # photocurrent; the part delivers 45–55 µA at 1 mW/cm² (950 nm,
    # DS 81127) — a close-range IR wand saturates the margin. Sunlight
    # rejection is layered: the package daylight filter (λ < 780 nm
    # blocked), the recessed cup-nose IR hole's narrow acceptance cone, and
    # a WBA firmware persistence/pattern check (a false wake costs µJ —
    # sample, disqualify, back to Stop1). Zero Standby power adder: the
    # pull-up conducts only when illuminated (dark current 2–30 nA).
    # Light path: an IR through-hole in the cup nose over the part
    # (a light pipe moulded into the cup — smash.export.cup_noses). This REPLACES the
    # H3LIS motion-detect as the Standby→Ready entry; the H3LIS
    # (now on main 3V3) keeps its launch-witness + flight-recorder
    # roles from Ready on. ⚠ CONOPS: activation_unlock is now a deliberate
    # operator/launcher action — revises the "no launcher cooperation"
    # ground rule in the power_states.md preamble. A round never given IR activation_unlock stays in
    # Standby through launch (no motion fallback any more).
    pd_wake = add_vemd5110x01(d, ref=f"D_IR_WAKE{sfx}", board_tag=board_tag)   # (2026-11-22) sourcing swap, availability/decisions.csv: VBPW34FAS → VEMD5110X01
    _net(d, "IR_WAKE").connect(pd_wake.pin("K"))   # reverse-biased by the pull-up
    _net(d, "IR_WAKE").connect(pd_wake.pin("K2"))  # second cathode pad
    _net(d, "GND")    .connect(pd_wake.pin("A"))
    if dnp:
        for c in d.chips[first:]:
            c.dnp = True


def build_radar_nose_io(d: Design) -> None:
    """Radar nose I/O: the IR service-link pair on radar_module's nose-facing
    top face. (2026-11-18) The depot USB-C moved to its own USB NOSE
    (build_usb_nose) — every nose plugs into the same crown interface, so
    USB is fitted by swapping the nose, not tied to the radar."""
    _add_ir_service_link(d, "radar_module")


def build_usb_nose(d: Design) -> None:
    """USB NOSE (2026-11-18, user): a nose module carrying the depot **USB-C**
    (UJ20, power-in + USB2 data) + its CC Rds + an IR service-link pair. It
    is the default nose on `core` (doubles as the protective cap) and is
    swapped onto any config for programming: unscrew the payload nose, screw
    the USB nose onto the same crown interface (smash.export.nose_interface).

    USB-C is the depot service port — **power-in** (VBUS → BAT_PROT via the
    OR switch on power_board, so the TPS25940 eFuse's reverse-blocking keeps
    the primary cells isolated while USB runs the whole unit) **+ USB2 data**
    (D± → MP25 USB-FS for SSH / USB-DFU). UJ20 16-pin USB2-only IP67
    receptacle SMT on the nose board's top at the north chord, mouth radially
    out through the cone's window (SBU contacts unconnected).

    (2026-11-18, user) VERTICAL USB-C at the nose tip: the receptacle stands at
    the board centre and the plug goes in axially through the flat face —
    (2026-11-19) Same Sky UJ20-C-V-G-SMT-23B-P16-TR-X5 (6.3 mm tall).
    ⚠ Check its country of origin."""
    _net(d, "GND", kind="ground")

    # ── Depot USB-C (vertical UJ20, SMT at the USB nose board's centre) ───────
    # On the radar's nose-facing top face at the (0,12) north-rim spot, mouth
    # out through the 17 mm N chord notch (kicad_pcb._tile_cuts); the cup has a
    # matching window (smash.export.nose_radome). board_tag=radar_module.
    # 16-contact USB2 receptacle; the pads combine the A/B sides (A4_B9 = VBUS,
    # A1_B12 = GND, …) so we wire by pad NUMBER — the symbol's repeated functional
    # names arrive de-duped (VBUS__1, GND__1, SHIELD__1…), so number is the key.
    # (2026-11-19) VERTICAL USB-C: Same Sky UJ20-C-V-G-SMT-23B-P16-TR-X5 —
    # separate A/B pads (no combined A4_B9 etc.), MP1–4 shell tabs.
    usb = add_uj20_c_v_g_smt_23b_p16_tr_x5(d, ref="J_USB_C", board_tag="usb_nose")
    for nm in ("A4", "A9", "B4", "B9"):                           # VBUS
        _net(d, "USB_VBUS").connect(usb.pin(nm))
    for nm in ("A1", "A12", "B1", "B12", "MP1", "MP2", "MP3", "MP4"):   # GND + shell
        _net(d, "GND").connect(usb.pin(nm))
    # CC1/CC2: 5.1 kΩ Rd to GND each → UFP sink presentation (source enables 5 V).
    # CC is a static DC presentation — no SI need to sit by the connector, so the
    # two Rds live on the RADAR (like the IR service-link pair + the OR diode on power_board),
    # all on the radar.
    CC_BTAG = "usb_nose"
    _net(d, "USB_CC1").connect(usb.pin("A5"))
    res_between(d, "USB_CC1", "GND", "5.1k", ref="R_USB_CC1", board_tag=CC_BTAG)
    _net(d, "USB_CC2").connect(usb.pin("B5"))
    res_between(d, "USB_CC2", "GND", "5.1k", ref="R_USB_CC2", board_tag=CC_BTAG)
    # USB2 D± — tied across both plug orientations → the MP25 USB-FS pair
    _net(d, "USB_D_P").connect(usb.pin("A6")); _net(d, "USB_D_P").connect(usb.pin("B6"))
    _net(d, "USB_D_N").connect(usb.pin("A7")); _net(d, "USB_D_N").connect(usb.pin("B7"))
    # SBU1/2 (A8/B8) left unconnected — power + USB2 only.

    # Depot single-cable power: USB 5 V VBUS ORed into BAT_PROT — the protected
    # battery rail that feeds EVERYTHING (PMIC → COMP_5V/COMP_3V3/MP25-core, plus
    # the radar buck + LDO tap BAT_PROT directly), so the depot USB-C runs the
    # FULL unit (NPU + radar), not just a service rail. Q_USB_OR (DMP6110 P-FET
    # ideal diode, 6.5 A) carries it; the binding limit is the ~3 A a non-PD
    # USB-C source can deliver, not the switch. When USB is live it drives
    # BAT_PROT to ≈4.94 V (5 V − 130 mΩ·I, was 5 V − V_F of a Schottky);
    # BAT_PROT > BAT_RAW reverse-biases Q_ISO's body diode (and Q_ISO is force-OFF
    # via the USB interlock), isolating the primary cells (no backfeed, no
    # charging — a Li primary must never be charged). Q_USB_OR's own body diode
    # blocks BAT_PROT from draining into a dead USB line on cell power, with its
    # gate drive unpowered. The OR switch + its VBUS bulk cap
    # live on POWER_BOARD (where BAT_PROT exists), so only USB_VBUS crosses
    # the snake. The CC Rds (above) and the IR service-link pair (below) live
    # on the radar beside the connector.
    # The OR switch + VBUS bulk cap + the USB-wake interlock all carry
    # board_tag="power_board" and are authored in build_power_board (the
    # shared power tile must fab identically in EVERY config, USB depot
    # present or not — economies of scale); only USB_VBUS crosses the
    # snake to reach them.

    # ── Nose optical service port — status LEDs RETIRED (2026-07-27) ────────
    # The green/red muzzle LEDs + their MP25 PG7/PG8 sinks are GONE: state
    # and the batt<1h warning are now QUERIED over the IR link (wand asks,
    # round answers) instead of read by eye at the muzzle — power_states §4a.
    # Their slots became the IR pair: D_IR_WAKE (receiver, below) + D_IR_TX.
    #
    _add_ir_service_link(d, "usb_nose", "_U")

    # The AoP radiates through the cup's λ/2 radome window; the air pocket
    # over it is kept free of black Stycast (a 77 GHz absorber) by the cup's
    # inner dam rib (smash.export.nose_radome).


# build_nfc_antenna_flex REMOVED 2026-07-30 (NFC subsystem deleted).
# Yagi A/B flex tiles + _add_yagi_meander_2g4 REMOVED 2026-11-14: BLE is
# ground-only and shares the conformal 2.4 GHz antenna in the PEEK battery
# compartment (see _build_lr_radio).


def build_spacers(d: Design, boards: dict | None = None) -> None:
    """One mechanical spacer disc per accordion-fold gap. Each is a Ø34 mm
    rigid PCB disc with chip-clearance cavities milled on both faces.
    Pin 1 ties to GND just to give the netlist a connection (no real
    electrical function).

    Panel-driven: the snake order (and therefore which board pairs are
    adjacent) comes from the fold solver, so we create a spacer chip for
    every spacer Board the panel produced rather than a hard-coded pair
    list. `boards` defaults to a fresh `build_panel()` (deterministic, so
    the spacer board_tags match). Mirrors system.py:add_spacer_boards."""
    if boards is None:
        _panel, boards = build_panel()
    spacer_boards = [b for b in boards.values()
                     if getattr(b, "kind", None) == "spacer"]
    for sp_board in spacer_boards:
        # Ref derives from the spacer NAME, not creation order — a config
        # with fewer spacers must still emit the identical scaffold chip
        # per shared spacer (economies of scale; was SP1..SPn positional).
        sp = add_mechanical_spacer_34mm(
            d, ref="SP_" + sp_board.name.removeprefix("spacer_"),
            board_tag=sp_board.name,
            value=sp_board.name.upper(), manf_pn=None,
            description=(
                f"Mechanical spacer {sp_board.name} — Ø34 mm rigid "
                "interposer, cavities milled for chips on both adjacent "
                "tile faces. No signals."))
        _net(d, "GND").connect(sp.pin("1"))


# (2026-11-21, user) all magnetometers (IIS2MDC, TMR shelf-wake + its LDO,
# DRV5032 activation-unlock Hall) live on fin_ble_board: they only run while
# the fin motors are idle, so motor noise is moot; frees wakeup's top.
_MAG_TAG = "activation_interface"   # (2026-11-21) was fin_ble_board (merged)


def build_flight_board(d: Design, board_tag: str = "flight_board",
                       imu_tag: str | None = None) -> None:
    """IMU / magnetometer sensor cluster. As of the wakeup+flight consolidation
    this FOLDS INTO wakeup_board: build_wakeup_board calls it with
    board_tag="wakeup_board". The two aft tiles merged because each was left with
    only a handful of chips once flight control moved onto the MP25 Cortex-M33.
    The default board_tag="flight_board" keeps the standalone Ø34 tile available
    as a test fixture (and for any config that still folds it separately).

    Builds on `board_tag`: BMM350 magnetometer + 3x ISM330DLC IMU on I2C2/3,
    their pull-ups + the SYS_I2C pull-ups, and the flex-bus alias merges. Two
    blocks created here are tagged to their OWN tiles (placement follows the tag,
    not `board_tag`): the EXT_CAN TCAN1042 (aft_end_board, by the TP_CAN pads)
    and the 4 QPD transimpedance amps (qpd_module, behind the photodiode). The
    launch-detect comparator itself lives on aft_end_board (by the piezo).

    `imu_tag` (2026-11-16): the 3x ISM330DHCX + their passives / test points
    go on that tile instead (fin_ble_board), freeing wakeup for the radio;
    the magnetometer and the I2C2/3 + SYS_I2C pull-ups stay on `board_tag`."""
    BTAG = board_tag
    ITAG = imu_tag or board_tag

    # ── System control bus pull-ups (SYS_I2C; the M33 is master) ─────
    # (boot-transient pre-charge through the MP25 TT clamps — see the
    # rule-sweep F5 note at the I2C2/3 pull-ups)
    res_between(d, "3V3", "SYS_I2C_SCL", "4.7k", ref="RPU_SCL_EXT", board_tag=BTAG)
    res_between(d, "3V3", "SYS_I2C_SDA", "4.7k", ref="RPU_SDA_EXT", board_tag=BTAG)

    # ── EXT_CAN transceiver (TCAN1042) — re-homed here from companion_compute ──
    # The MP25 FDCAN1 controller (EXT_CAN_TX/RX) drives this PHY across the
    # LGA backbone; CANH/CANL are exposed at the TP_CAN_P/N pogo pads on
    # aft_end's service face. Moved off companion_compute to free top-face
    # area for the un-rotated DDR4 + the two SPI-NAND dies; moved again
    # activation→aft_end 2026-07-31 (activation chip redistribution): the PHY
    # + its 120 Ω terminator now sit directly at the CAN pads (CANH/CANL are
    # local vias), and only the digital TXD/RXD cross up to the MP25 FDCAN1.
    # (2026-11-17, user) moved again → fin_ble_board: after the aft reorder
    # _empty_aft_end_top had parked it on activation_interface, whose top is
    # too busy. Lane-neutral: CANH/CANL now cross activation↔fin_ble instead
    # of TXD/RXD (the PHY sits ~6 mm further from the TP_CAN pads — fine for
    # CAN FD). (Code lives here in build_flight_board for now; placement
    # follows board_tag.)
    # BOTTOM face: the SOIC-8 is 1.75 mm tall; on fin_ble's top it faced
    # wakeup's bottom and grew that ~3.0 mm gap to 3.5 mm (2026-11-17 build).
    # The activation↔fin_ble gap below is already 4.4 mm.
    # (2026-11-20, user) tall parts grouped: the 1.75 mm SOIC-8 joins the
    # boost stages on power_board's TOP (that gap is set by the 2.8 mm
    # inductors anyway); CANH/CANL ride two lanes down to the aft interface.
    _CAN_TAG = "power_board"
    # (2026-11-20, user) VSON-8 (1.0 mm) instead of the 1.75 mm SOIC-8
    can_gw = add_tja1462btk_0z(d, ref="U_CAN_GW", board_tag=_CAN_TAG)
    _net(d, "EXT_CAN_TX").connect(can_gw.pin("TXD"))
    _net(d, "EXT_CAN_RX").connect(can_gw.pin("RXD"))
    _net(d, "GND").connect(can_gw.pin("GND"))
    _net(d, "GND").connect(can_gw.pin("EP"))       # exposed pad
    # VCC needs 4.5-5.5 V (SLLSES9D §7.4 — the GV variant UVLOs below
    # that, so a 3V3-fed PHY sits in protected mode = bus dead). COMP_5V
    # extends aft down the whole column (wakeup → activation → the battery
    # spacers → aft_end) to feed it; VIO
    # stays on 3V3 (3-5.5 V) level-shifting TXD/RXD to the MP25's 3.3 V
    # FDCAN logic — exactly the split the V variant exists for. CAN is
    # alive only while the COMP boost runs, which is fine: the MP25 (the
    # only FDCAN controller) is only alive then too.
    # Rail-audit disposition (2026-06-11): COMP_5V spanning power→wakeup→
    # activation is DELIBERATE — retraction via a 3.3 V CAN PHY was
    # considered and dropped; a high-power line through the whole stack
    # is worth the 4 lands (future loads tap it without re-plumbing).
    _net(d, "COMP_5V").connect(can_gw.pin("VCC"))
    _net(d, "3V3").connect(can_gw.pin("VIO"))
    _net(d, "GND").connect(can_gw.pin("STB"))        # high-speed mode
    _net(d, "EXT_CAN_P").connect(can_gw.pin("CANH"))
    _net(d, "EXT_CAN_N").connect(can_gw.pin("CANL"))
    cap_to_gnd(d, "COMP_5V", "100nF", ref="C_CAN_GW",
               embedded_cap_absorbs=True, board_tag=_CAN_TAG, pin=can_gw.pin("VCC"))
    res_between(d, "EXT_CAN_P", "EXT_CAN_N", "120",
                ref="R_EXT_CAN_TERM", board_tag=_CAN_TAG)

    # ── BMM350 magnetometer on I2C2 (INT/DRDY -> M33 EXTI) ────────────
    # (2026-11-22) replaces the IIS2MDC (0 stock at all 3 suppliers;
    # availability/decisions.csv). I²C address 0x14 (ADSEL = GND).
    # FIRMWARE: new driver; ⚠ re-run the magnetic-link sim with BMM350 noise.
    mag = add_bmm350(d, ref="U_MAG", board_tag=_MAG_TAG, feature="bottom")
    _net(d, "3V3")     .connect(mag.pin("VDD"))
    _net(d, "3V3")     .connect(mag.pin("VDDIO"))
    _net(d, "GND")     .connect(mag.pin("GND"))
    _net(d, "GND")     .connect(mag.pin("BYPASS"))
    _net(d, "GND")     .connect(mag.pin("ADSEL"))     # → 0x14
    _net(d, "I2C2_SCL").connect(mag.pin("SCK"))
    _net(d, "I2C2_SDA").connect(mag.pin("SDA"))
    _net(d, "MAG_DRDY").connect(mag.pin("INT"))
    _net(d, "MAG_CRST").connect(mag.pin("CRST"))
    # CRST reservoir: 2.2 µF low-ESL, tight to C2 — a real discrete, never
    # ECM-absorbed (private node, not a rail).
    cap_to_gnd(d, "MAG_CRST", "2.2uF", ref="C_MAG_C1", board_tag=_MAG_TAG, pin=mag.pin("CRST"))
    cap_to_gnd(d, "3V3", "100nF", ref="C_MAG1", embedded_cap_absorbs=True, board_tag=_MAG_TAG, pin=(mag.ref, None))
    cap_to_gnd(d, "3V3", "1uF",   ref="C_MAG2", board_tag=_MAG_TAG, pin=(mag.ref, None))
    tp_drdy = _add_testpoint(d, ref="TP_MAG_DRDY", board_tag=_MAG_TAG)
    _net(d, "MAG_DRDY").connect(tp_drdy.pin("1"))

    # ── I2C2/3 pull-ups ──────────────────────────────────────────────
    # Two sensor I2C buses (was three) — frees 2 LGA lands on the tight
    # companion↔flight joint for the depot USB pair, keeping all 3 IMUs.
    # ⚠ rule-sweep F5 (boot transient, ACCEPTED): 3V3 rises at QMAIN
    # while the MP25's VDDIO (COMP_3V3 = PMIC BUCK2, rank 1) is still
    # down, so for the few PMIC-boot ms every 3V3 pull that reaches an
    # MP25 TT pin (I2C2/3, SYS_I2C, PMIC INTN) pre-charges COMP_3V3
    # through the TT clamp (~0.6 mA/line, ~4 mA total). Within the TT
    # injection limits and the STPMIC25 bucks are pre-bias safe.
    # BRING-UP: scope COMP_3V3 pre-bias at main-switch turn-on.
    for bus in ("I2C2", "I2C3"):
        res_between(d, "3V3", f"{bus}_SCL", "4.7k", ref=f"RPU_{bus}_SCL", board_tag=BTAG)
        res_between(d, "3V3", f"{bus}_SDA", "4.7k", ref=f"RPU_{bus}_SDA", board_tag=BTAG)

    # ── 3x ISM330DHCX IMU (INT1 -> M33 EXTI) ────────────────────────
    # I2C2: mag (BMM350 0x14) + IMU1 (SA0=0). I2C3: IMU2 (SA0=0) + IMU3 (SA0=1) —
    # distinct addresses per bus; two independent buses still isolate a fault.
    for idx, scl, sda, sa0 in [(1, "I2C2_SCL", "I2C2_SDA", "GND"),
                               (2, "I2C3_SCL", "I2C3_SDA", "GND"),
                               (3, "I2C3_SCL", "I2C3_SDA", "3V3")]:
        imu = add_ism330dlctr(d, ref=f"U_IMU{idx}", board_tag=ITAG)
        _net(d, "3V3").connect(imu.pin("VDD"))
        _net(d, "3V3").connect(imu.pin("VDDIO"))
        _net(d, "GND").connect(imu.pin("GND_1"))
        _net(d, "GND").connect(imu.pin("GND_2"))
        _net(d, scl).connect(imu.pin("SCL"))
        _net(d, sda).connect(imu.pin("SDA"))
        _net(d, "3V3").connect(imu.pin("CS"))
        _net(d, f"IMU{idx}_INT") .connect(imu.pin("INT1"))
        _net(d, f"IMU{idx}_INT2").connect(imu.pin("INT2"))
        _net(d, sa0).connect(imu.pin("SA0"))
        _net(d, f"IMU{idx}_SCX").connect(imu.pin("SCX"))
        _net(d, f"IMU{idx}_SDX").connect(imu.pin("SDX"))
        res_between(d, "3V3", f"IMU{idx}_SCX", "10k", ref=f"R_IMU{idx}_SCX_PU", board_tag=ITAG)
        res_between(d, "3V3", f"IMU{idx}_SDX", "10k", ref=f"R_IMU{idx}_SDX_PU", board_tag=ITAG)
        # Aux-SPI unused — DS13012 pin table: OCS_Aux "leave unconnected"
        # (it's the aux-interface enable; the old GND tie was an
        # unsanctioned strap), SDO_Aux "connect to Vdd_IO or leave
        # unconnected" (GND not allowed). Both left floating.
        cap_to_gnd(d, "3V3", "100nF", ref=f"C_IMU{idx}_1", embedded_cap_absorbs=True, board_tag=ITAG, pin=(imu.ref, None))
        cap_to_gnd(d, "3V3", "2.2uF", ref=f"C_IMU{idx}_2", board_tag=ITAG, pin=(imu.ref, None))
        cap_to_gnd(d, "3V3", "10nF",  ref=f"C_IMU{idx}_3", embedded_cap_absorbs=True, board_tag=ITAG, pin=(imu.ref, None))
        tp_int = _add_testpoint(d, ref=f"TP_IMU{idx}_INT", board_tag=ITAG)
        _net(d, f"IMU{idx}_INT").connect(tp_int.pin("1"))

    # ── flex bus alias merges (FLEX_* -> rigid rails; bench I2C -> SYS_I2C) ─
    d.merge_nets("FLEX_GND", "GND")
    d.merge_nets("3V3", "FLEX_3V3")
    d.merge_nets("SYS_I2C_SCL", "FLEX_I2C_SCL")
    d.merge_nets("SYS_I2C_SDA", "FLEX_I2C_SDA")
    # (2026-11-20) C_CAM_VDD removed: a stray COMP_1V8 cap, the rail's only
    # user on this board (the camera has its own VDDIO decoupling).

    # Launch detect (piezo comparator) lives on fin_ble_board — it sits by
    # the piezo disk (the battery-compartment ceiling's top face since the
    # 2026-07-31 stack reorder) so the high-Z analog stays local; only the
    # digital COMP_OUT crosses to the M33 PD5 EXTI. The hardware confirm
    # AND-gate is retired: PARACHUTE_CUTTER_SET / ACTIVATE_CONFIRM are firmware GPIOs.

    # ── 4x AD8603 QPD transimpedance amps (board_tag=qpd_module, bottom face — directly behind the photodiode so
    # the high-Z anode->TIA node is microscopic; TIA outputs ride the branch to ADC) ────────
    # QPD_VREF (mid-rail 1.65 V) is BOTH the TIAs' +IN reference AND the
    # photodiode common-cathode return (build_qpd_module), so every quadrant
    # sits at true zero bias (photovoltaic). Outputs idle at 1.65 V and swing
    # DOWN with light: Vout = VREF − Ip·Rf, 1.65 µA full scale per quadrant.
    # The divider's 50 kΩ Thevenin carries the summed photocurrents — pulsed
    # content rides the 1 µF; stiffen/buffer if DC accuracy ever matters.
    res_between(d, "3V3",      "QPD_VREF", "100k", ref="R_QPD_VREF_H", board_tag="qpd_module")
    res_between(d, "QPD_VREF", "GND",      "100k", ref="R_QPD_VREF_L", board_tag="qpd_module")
    cap_to_gnd(d, "QPD_VREF", "1uF",   ref="C_QPD_VREF1", board_tag="qpd_module")
    cap_to_gnd(d, "QPD_VREF", "100nF", ref="C_QPD_VREF2", board_tag="qpd_module")
    for ch, qpd_in_net, tia_out_net in [("A", "QPD_A", "QPD_TIA_A"),
                                        ("B", "QPD_B", "QPD_TIA_B"),
                                        ("C", "QPD_C", "QPD_TIA_C"),
                                        ("D", "QPD_D", "QPD_TIA_D")]:
        res_between(d, qpd_in_net, tia_out_net, "1M", ref=f"R_TIA_{ch}", board_tag="qpd_module")
        # Cf = 8.2 pF for TIA stability: at zero bias the MT03-092 quadrant is
        # ~140 pF (DS, VR=0), and Cf_opt ≈ sqrt(Cin/(2π·Rf·GBP)) =
        # sqrt(140p/(2π·1M·400k)) ≈ 7.5 pF — the old 1 pF left the noise-gain
        # crossing badly underdamped (ringing). BW = 1/(2π·1M·8.2p) ≈ 19 kHz:
        # a charge-integrating pulse detector, consistent with the AD8603's
        # 400 kHz GBP
        cap_fb = add_capacitor_c0g_0603_avx_sqcs(d, ref=f"C_TIA_{ch}", value="8.2pF", board_tag="qpd_module")
        _net(d, qpd_in_net) .connect(cap_fb.pin("1"))
        _net(d, tia_out_net).connect(cap_fb.pin("2"))
        opa = add_ad8603aujz_r2_single_supply(d, ref=f"U_TIA_{ch}", board_tag="qpd_module")
        _net(d, qpd_in_net) .connect(opa.pin("-IN"))
        _net(d, "GND")      .connect(opa.pin("V-"))
        _net(d, "QPD_VREF") .connect(opa.pin("+IN"))
        _net(d, tia_out_net).connect(opa.pin("OUT"))
        _net(d, "3V3")      .connect(opa.pin("V+"))
        cap_to_gnd(d, "3V3", "100nF", ref=f"C_TIA_{ch}_PWR", embedded_cap_absorbs=True, board_tag="qpd_module", pin=opa.pin("V+"))

    # (Radar power switch deleted — the AWR's buck + LDO now tap always-on
    # BAT_PROT directly and self-gate via their EN pins tied to RADAR_EN; the
    # gating + the RADAR_EN pull-down live on radar_module. flight is pure sensors.)


def build_power_board(d: Design) -> None:
    """Power tile — concentrates the power conversion stack between
    activation_interface (cells) and wakeup_board:
      - 3× TLM-1520HPM/S cells via CellAttach pads + 200 mΩ iso resistors
      - Q_ISO nanopower ideal-diode reverse-block (BAT_RAW → BAT_PROT;
        replaces the TPS25940 eFuse — kills the ~10 µA shelf floor)
      - TPS61175 boost reg (REG_IN_MAIN → COMP_5V ≈ 5.03 V, feeds PMIC + fins)
      - STPMIC25APQR PMIC (COMP_5V → 0V9 / 1V8 / 1V2 / 2V8 / VPP 2.5 rails)
      (the separate companion-3V3 LDO is gone — the single 3V3 rail from
       wakeup_board now feeds the companion's 3.3 V loads too)
      - Optional dedicated camera LDOs (DNP; LP5907 ×2 for VAA / VDD)
      - TMP117 precision temp sensor on I2C2 (hottest tile)

    Mirrors system.py boards 4627–4642 (between `_BOARD_TAG=power_board`
    and the wakeup_board transition).
    """
    BTAG = "power_board"

    # ── battery cells + contacts (mode = module global _BATTERY_MODE) ─
    # The cells use factory-welded SIDE solder tabs (no end pins — the old
    # pinned-contact scheme is gone, 2026-07-30). Triple: cells stand in the
    # compartment between the THIN cell_floor_board and fin_ble_board (the
    # ceiling since the 2026-07-31 stack reorder — activation_interface
    # moved down between aft_end and cell_floor). Only the tab-landing pads
    # live on the tiles.
    # DEFAULT: 3× TLM-1520HPM/S stood VERTICAL, triangle around the spin
    # axis, bases flat on cell_floor_board. + tab lands on
    # fin_ble_board's bottom face (one per cell, at the cell centres —
    # the compartment ceiling), − side tabs bend down to three discrete
    # lands on cell_floor_board inside the cell bore circles (locked —
    # battery-facing faces keep everything inside the 3 bores so the
    # compartment spacers give up no extra cutout), each
    # + → 200 mΩ iso resistor → BAT_RAW.
    # (The cells themselves are not board-tagged parts, just the pads +
    # iso resistors.)
    # (2026-11-14) + side: the cells' existing TAB EXTENSIONS bend up across
    # the 2 mm headroom to three DISCRETE lands (one per cell centre) on
    # fin_ble's bottom face — was one 3-pad P_CELL_CONTACTS footprint whose
    # ~21 × 19 mm bounding box blanked the board centre for the packer.
    # (2026-11-15 aft reorder) BOTH tab sets land on activation_interface's
    # BOTTOM face — the compartment ceiling; aft_end's top (the floor) is
    # bare for the glued + screwed Al compartment.
    # (2026-11-20, user) NO TABS: Tadiran /P cells (axial pins). Both leads
    # land on aft_end_board, soldered from below before the aft cap goes on:
    # − pins straight through the holder floor (P_CELL_PIN_NEG*, at the cell
    # axes); + pins via AWG 28 wires down the holder's potting channel
    # (P_CELL_WIRE_POS*, round the channel exit). activation_interface's
    # bottom face is EMPTY (it mates flat over the 1 mm headroom).
    for _k in (1, 2, 3):
        pw = add_cell_lead_pth(d, ref=f"P_CELL_WIRE_POS{_k}", role="wire",
                               board_tag="aft_end_board")
        _net(d, f"BAT_CELL{_k}_POS").connect(pw.pin("1"))
    for _k in (1, 2, 3):
        pn = add_cell_lead_pth(d, ref=f"P_CELL_PIN_NEG{_k}", role="pin",
                               board_tag="aft_end_board")
        _net(d, "GND").connect(pn.pin("1"))

    # The 3× 200 mΩ iso resistors are UNCONDITIONAL: power_board is a
    # shared part across every config (economies of scale), so its copper
    # must not depend on the battery mode. In single mode the BAT_CELLx_POS
    # nets are stubs (the cell + ties to BAT_RAW at the aft_end tab) — the
    # resistors fab anyway, DNP at assembly.
    res_between(d, "BAT_CELL1_POS", "BAT_RAW", "200m",
                ref="R_BAT1_ISO", board_tag=BTAG)
    res_between(d, "BAT_CELL2_POS", "BAT_RAW", "200m",
                ref="R_BAT2_ISO", board_tag=BTAG)
    res_between(d, "BAT_CELL3_POS", "BAT_RAW", "200m",
                ref="R_BAT3_ISO", board_tag=BTAG)

    # ── BAT_RAW bulk caps + nanopower ideal-diode reverse-block ──────
    # The TPS25940 eFuse was REMOVED (2026-06). Its IQ(OFF) ≈ 9-15 µA sat
    # on the always-live cell rail and WAS the entire ~10 µA shelf floor,
    # dragging the 200 mAh cell's shelf life to ~2 y when the chemistry
    # alone supports ~20 y (datasheet self-discharge ~3 %/yr). The eFuse
    # earned its place by three jobs: (1) reverse-block depot-USB out of
    # the Li primary (a primary must NEVER be back-fed), (2) 5 A
    # overcurrent trip, (3) IMON/PGOOD/FLT telemetry. (2) and (3) are
    # dropped — the TLM-1530M/S passes Tadiran's external-short safety
    # test, so an unprotected short does not vent — and (1), the safety-
    # critical one, is kept as a nanopower P-FET ideal diode (Q_ISO).
    # (2026-11-22, user) CERAMIC bank instead of 2 × 470 µF polymer. The 940 µF
    # dated from the DRV8711 era (fins straight on the cell rail, ~33 A for four
    # fins) — and its own sum was off ×1000 (24 A × 10 ms = 240 mC, not µC;
    # 940 µF could hold that for ~40 µs). Now every heavy load sits behind a
    # boost/regulator with its own storage (fins + PMIC on COMP_5V_RAW, cutter
    # on the 33 V boost, PA on XV_5V); BAT_RAW only needs low impedance for
    # sub-100 µs edges. A ~4 A coincident step settles at ~0.5 V droop set by
    # the cells' source R (3 × (R_cell + 200 mΩ)) whatever the capacitance; the
    # bank just sets the edge time constant (~6 µs). 6 × 22 µF 10 V 0805,
    # 1.25 mm (no 470 µF ≤ 1.5 mm part was orderable outside China lots).
    from smash.parts.passives import add_capacitor_grm21br61a226me44l
    for _k in range(1, 7):
        _c = add_capacitor_grm21br61a226me44l(d, ref=f"C_BAT_BULK{_k}", board_tag=BTAG, feature="bottom")
        _net(d, "BAT_RAW").connect(_c.pin("1")); _net(d, "GND").connect(_c.pin("2"))

    # Q_ISO — ideal-diode reverse-block, BAT_RAW (cell) → BAT_PROT (load /
    # USB-OR point). Body diode (drain=BAT_RAW → source=BAT_PROT) passes
    # the cell FORWARD and BLOCKS BAT_PROT→cell, so depot USB (≈4.94 V on
    # BAT_PROT via the Q_USB_OR ideal diode) cannot charge the primary.
    # Default OFF (gate≈source via R_ISO_H, V_GS≈0) → body-diode-only,
    # ~nA reverse leakage → NANOPOWER shelf, no IQ on the cell. Firmware
    # pulls it fully ON in flight (BAT_ISO_EN) for a low-drop forward
    # path; depot-USB force-OFF is a HARDWARE interlock (Q_ISO_USB),
    # independent of firmware. DMP6110: -60 V, 6.5 A cont — carries the
    # whole pack (the radar taps BAT_PROT downstream of this, ahead of
    # QMAIN). Same high-side P-FET + NFET gate-pull idiom as Q_PARACHUTE_CUTTER_ACTIVATE.
    # NOTE: forward-drop, gate-drive timing and the USB interlock want
    # bench/sim confirmation before fab (analog behaviour, not modelled
    # by the connectivity build).
    q_iso = add_buk6d120_60px(d, ref="Q_ISO", board_tag=BTAG)   # (2026-11-22) sourcing swap, availability/decisions.csv: DMP6110 → BUK6D120
    for dp in ("D_1", "D_2", "D_3", "D_4", "D_5"):
        _net(d, "BAT_RAW").connect(q_iso.pin(dp))      # drains → cell side
    for sp in ("S_1", "S_2"):
        _net(d, "BAT_PROT").connect(q_iso.pin(sp))       # source → load / USB side
    _net(d, "BAT_ISO_G").connect(q_iso.pin("G"))
    # Gate divider: BAT_PROT ─100k─ G ─10k─ Q_ISO_DRV drain. DRV off →
    # G≈BAT_PROT (V_GS≈0, OFF, nanopower). DRV on → G≈BAT_PROT·10/110
    # ≈0.4 V → V_GS≈-3.6 V (fully on, within ±20 V V_GSS).
    res_between(d, "BAT_PROT",  "BAT_ISO_G",  "100k", ref="R_ISO_H", board_tag=BTAG)
    res_between(d, "BAT_ISO_G", "BAT_ISO_GD", "10k",  ref="R_ISO_L", board_tag=BTAG)
    q_iso_drv = add_ssm3k35ctc_l3f(d, ref="Q_ISO_DRV", board_tag=BTAG)
    _net(d, "BAT_ISO_GD").connect(q_iso_drv.pin("3"))   # drain → gate divider
    _net(d, "GND")       .connect(q_iso_drv.pin("2"))   # source
    _net(d, "BAT_ISO_EN").connect(q_iso_drv.pin("1"))   # gate (driven via R_ISO_EN_S)
    res_between(d, "BAT_ISO_EN", "GND", "100k", ref="R_ISO_EN_PD", board_tag=BTAG)
    # SAFETY: BAT_ISO_EN is driven from the MP25 GPIO through a 10k SERIES R so
    # the hardware USB interlock below ALWAYS wins — Q_ISO_USB (RDS ~Ω) sinks
    # BAT_ISO_EN to GND even against a push-pull GPIO driving high through 10k
    # (contention bounded to ~0.33 mA). A primary cell must never be back-fed,
    # so firmware MUST NOT be able to override the interlock.
    res_between(d, "BAT_ISO_DRIVE", "BAT_ISO_EN", "10k", ref="R_ISO_EN_S", board_tag=BTAG)
    # Depot-USB hardware interlock: VBUS present → Q_ISO_USB pulls BAT_ISO_EN
    # low → Q_ISO OFF → body diode reverse-blocks → cell isolated, regardless
    # of (and overriding) firmware. The body diode is the unconditional backstop;
    # this interlock only matters in the one window where firmware has turned the
    # channel ON (low-drop forward) and USB is then plugged.
    q_iso_usb = add_ssm3k35ctc_l3f(d, ref="Q_ISO_USB", board_tag=BTAG)
    _net(d, "BAT_ISO_EN")  .connect(q_iso_usb.pin("3"))   # drain → force EN low
    _net(d, "GND")         .connect(q_iso_usb.pin("2"))   # source
    _net(d, "BAT_ISO_USBG").connect(q_iso_usb.pin("1"))   # gate
    res_between(d, "USB_VBUS",      "BAT_ISO_USBG", "100k", ref="R_ISO_USB_H", board_tag=BTAG)
    res_between(d, "BAT_ISO_USBG",  "GND",          "100k", ref="R_ISO_USB_L", board_tag=BTAG)

    cap_to_gnd(d, "BAT_PROT", "100uF", ref="CBAT1", board_tag=BTAG, feature="bottom")
    cap_to_gnd(d, "BAT_PROT", "100uF", ref="CBAT2", board_tag=BTAG, feature="bottom")
    cap_to_gnd(d, "BAT_PROT", "1uF",   ref="CBAT3", board_tag=BTAG)

    # ── add_companion_power — ONE shared 5 V boost (PMIC + fins) ─────
    # Merged: this boost replaces the separate fins U_FINBOOST — it now feeds the
    # PMIC (MP25) AND the 4 DRV8428E fin drivers (which tap COMP_5V_RAW one gap
    # away). TPS61175 (3 A min switch limit, SLVS892F) — upsized 2026-06-11
    # from the 2 A TPS61085 (rail-audit item; combined load ~2–2.5 A pk @ 5 V).
    # Continuous capability IOUT(max) = VIN·ILIM·(1−ΔI/2)·η/VOUT ≈ 1.55 A at
    # VIN=3.0 V → ~2.2 A at 4.2 V (DS Eq.8); fin VM pulses above that ride the
    # ~70 µF output bank (C_BOOST_OUT* + C_FIN_VM_BULK + LC-side caps).
    # The fins sit on COMP_5V_RAW (boost output, noisy side); an LC filter
    # (L_PMIC_FILT) isolates the PMIC's COMP_5V so motor switching doesn't
    # reach the MP25 core rails.
    # feature="bottom": the HTSSOP-14 body (4.4×5.0 vs the old TSSOP-8's
    # 3.0×4.4) overflows the saturated power↔companion joint by 5 lands in
    # core_radar — bottom face also co-locates it with L_BOOST_COMP (tight
    # SW loop on one face).
    # (2026-11-20) TOP face with the fire boost (tall parts grouped on one face)
    boost = add_tps61175pwpr(d, ref="U_COMP_BOOST", board_tag=BTAG)
    _net(d, "REG_IN_MAIN") .connect(boost.pin("VIN"))     # 3
    _net(d, "COMP_5V_SW")  .connect(boost.pin("SW_1"))    # 1 ┐ switch node
    _net(d, "COMP_5V_SW")  .connect(boost.pin("SW_2"))    # 2 ┘
    _net(d, "COMP_5V_FB")  .connect(boost.pin("FB"))      # 9
    _net(d, "GND")         .connect(boost.pin("PGND_1"))  # 12
    _net(d, "GND")         .connect(boost.pin("PGND_2"))  # 13
    _net(d, "GND")         .connect(boost.pin("PGND_3"))  # 14
    _net(d, "GND")         .connect(boost.pin("AGND"))    # 7
    _net(d, "GND")         .connect(boost.pin("EP"))      # 15 thermal pad → GND plane vias
    _net(d, "GND")         .connect(boost.pin("NC"))      # 11 DS: "Reserved. Must connect to ground."
    _net(d, "GND")         .connect(boost.pin("SYNC"))    # 6 internal osc — DS: tie to AGND when unused
    _net(d, "REG_IN_MAIN") .connect(boost.pin("EN"))      # 4 (always-on, follows the main switch)
    _net(d, "COMP_5V_COMP").connect(boost.pin("COMP"))    # 8
    # fSW = 600 kHz via R_FREQ = 176 k (DS Table 2) — matched to the 10 µH
    # inductor: ΔI_L ≈ 0.2 A (~12 % ripple) keeps a usable current-sense
    # ramp; at 1.2 MHz the same L leaves ~6 % and the DS warns internal-osc
    # pulse-skipping above 1.2 MHz anyway. FREQ must never be left open.
    _net(d, "COMP_5V_FREQ").connect(boost.pin("FREQ"))    # 10
    res_between(d, "COMP_5V_FREQ", "GND", "174k",          # (2026-11-21) 176k not E96
                ref="R_BOOST_FREQ", board_tag=BTAG)
    # Soft-start 47 nF (DS §7.3.2: "eliminates the output overshoot ... for
    # most applications") — closes the rail-audit inrush item: the PMIC +
    # 47 µF + fin bulk downstream of QMAIN were unmanaged with the 61085's
    # open SS pin.
    _net(d, "COMP_5V_SS")  .connect(boost.pin("SS"))      # 5
    cap_to_gnd(d, "COMP_5V_SS", "47nF", ref="C_BOOST_SS", board_tag=BTAG, pin=boost.pin("SS"))

    # Boost topology per DS §Typical Application (non-synchronous):
    # inductor IN → SW, Schottky rectifier SW → VOUT.
    # (2026-11-21) Coilcraft XGL5020-472MEC 4.7 µH: Isat 5.3 A at 30 % drop
    # covers the TPS61175's 5 A MAX switch limit (3.0/3.8/5.0 A), which the
    # fin pulses drive it into; DCR 36 mΩ, 2.1 mm. The earlier WE-PD
    # 744043100 (10 µH, mislabelled "Isat 6 A" here) and LPS4018 saturated at
    # ~1-1.2 A. 4.7 µH = bottom of the DS 4.7–47 µH window; ripple ≈ 0.43 A
    # at 600 kHz. COMP network re-derived for 4.7 µH below.
    # Pin 1 (marked start lead) on the SW node, per Coilcraft (lowest EMI).
    l_boost = add_inductor_we_mapi_74438356047(d, ref="L_BOOST_COMP", board_tag=BTAG)   # (2026-11-22) XGL5020-472 → WE-MAPI 4020, same 2.1 mm
    _net(d, "COMP_5V_SW") .connect(l_boost.pin("1"))
    _net(d, "REG_IN_MAIN").connect(l_boost.pin("2"))
    # PMEG040V050EPE-QZ 5 A/40 V low-V_F Schottky (was an MBRS540T3G in SMC
    # until 2026-09-02): diode average current = IOUT (≤ ~2.2 A) but fin-pulse
    # peaks track the 3.8 A typ switch limit, so the 5 A envelope stays.
    # A non-synchronous boost NEEDS a rectifier diode — the TPS61175 carries
    # only the low-side switch — so unlike the depot-USB OR this cannot become
    # an ideal-diode FET. The swap is about HEIGHT: CFP15B is 1.1 mm against
    # the SMC's 2.56 mm, and the SMC was the single part on this face driving
    # the power↔companion spacer past what the rest of the gap needs (see
    # spacer_sizing). Same 40 V/5 A, same drop (520 vs 500 mV max at 5 A),
    # lower leakage, 175 °C T_j, AEC-Q101. Pins 1+2 are both anode (tie both
    # — the clip-bond package splits the anode across two leads), 3 = cathode.
    d_boost = add_pmeg040v050epe_qz(d, ref="D_BOOST_COMP", board_tag=BTAG)
    _net(d, "COMP_5V_SW") .connect(d_boost.pin("A_1"))
    _net(d, "COMP_5V_SW") .connect(d_boost.pin("A_2"))
    _net(d, "COMP_5V_RAW").connect(d_boost.pin("K"))
    # (2026-11-22, height round 16) 47 µF polymer → 2 × 22 µF 25 V 0805 (1.25 mm)
    from smash.parts.passives import add_capacitor_grm21br61e226me44l
    for _k in (1, 2):
        _c = add_capacitor_grm21br61e226me44l(d, ref=f"C_BOOST_OUT1_{_k}", board_tag=BTAG, feature="bottom")
        _c.decouples = [(boost.ref, None)]
        _net(d, "COMP_5V_RAW").connect(_c.pin("1")); _net(d, "GND").connect(_c.pin("2"))
    cap_to_gnd(d, "COMP_5V_RAW", "10uF",  ref="C_BOOST_OUT2", board_tag=BTAG, pin=(boost.ref, None))
    cap_to_gnd(d, "COMP_5V_RAW", "100nF", ref="C_BOOST_OUT3",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=(boost.ref, None))
    # VOUT = 1.229 × (1 + 309/100) = 5.03 V (TPS61175 V_REF, DS §6.5)
    res_between(d, "COMP_5V_RAW", "COMP_5V_FB", "309k",
                ref="R_BOOST_R1", board_tag=BTAG)
    res_between(d, "COMP_5V_FB", "GND",        "100k",
                ref="R_BOOST_R2", board_tag=BTAG)
    # Loop compensation (DS §8.2.2.10; Gea 340 µS, Rsense 40 mΩ). (2026-11-21)
    # re-derived for L = 4.7 µH: fRHPZ = RO/(2πL)·(VIN/VOUT)² rises to ≈ 30 kHz
    # at VIN 3.0 V / 2 A (was 14 kHz at 10 µH), so fC may go to ≈ 10 kHz
    # (fRHPZ/3). R3 2.7 k / C4 120 nF (fZ ≈ 490 Hz) → fC 7-10 kHz, PM 93-96°
    # over VIN 3.0-4.2 V, 0.3-2.2 A (COUT_eff ≈ 70 µF) — ~2× faster recovery
    # from fin-pulse load steps than the 1.6 k / 220 nF set for 10 µH, and
    # ≥ 30 % below the limit for the ±30 % Gea spread. (The 51 k/1.1 nF pair
    # was the 61085's gm/sense design.)
    res_between(d, "COMP_5V_COMP", "COMP_5V_COMP_C", "2.7k",
                ref="R_BOOST_COMP", board_tag=BTAG)
    cap_to_gnd(d, "COMP_5V_COMP_C", "120nF",
               ref="C_BOOST_COMP", board_tag=BTAG, pin=(boost.ref, None))
    # LC filter: COMP_5V_RAW (fins, noisy) → COMP_5V (PMIC, clean).
    ind_between(d, "COMP_5V_RAW", "COMP_5V", "1uH",
                ref="L_PMIC_FILT", board_tag=BTAG)   # TMS-1R0, Isat 2.7 A (was bogus WE-KI 0402)
    cap_to_gnd(d, "COMP_5V", "10uF", ref="C_PMIC_5V_FILT", board_tag=BTAG)

    # Companion-3V3 LDO (U_COMP_33) REMOVED — the two 3.3 V rails are unified.
    # The companion's 3.3 V loads (MP25 VDD-IO + SPI-NAND) now draw from the
    # single 3V3 rail generated on wakeup_board (MCP1640 boost → LDL112 LDO).
    # Both 3.3 V domains already shared the same system-on enable (off in
    # shelf), so this drops a duplicate boost-tap + LDO without changing
    # sequencing or hold-up. COMP_5V is still produced (TPS61175) for the PMIC.

    # ── add_stpmic2 — STPMIC25APQR multi-rail PMIC ───────────────────
    pmic = add_stpmic25apqr(d, ref="U_PMIC", board_tag=BTAG)

    # Power input — all BUCKnIN + LDOnnIN tied to COMP_5V
    _net(d, "COMP_5V").connect(pmic.pin("VIN"))
    for n in (1, 2, 3, 4, 5, 6, 7):
        _net(d, "COMP_5V").connect(pmic.pin(f"BUCK{n}IN"))
    _net(d, "COMP_5V").connect(pmic.pin("LDO12IN"))
    _net(d, "COMP_5V").connect(pmic.pin("LDO3IN"))
    _net(d, "COMP_5V").connect(pmic.pin("LDO56IN"))
    _net(d, "COMP_5V").connect(pmic.pin("LDO78IN"))

    # Grounds — the buck power returns + analog/LDO grounds (DS14278
    # Table 3: PGND1-7 / AGND / GNDLDO tie to GND even when the rail is
    # unused; only the EP was wired before this pass).
    for n in (1, 2, 3, 4, 5, 6, 7):
        _net(d, "GND").connect(pmic.pin(f"PGND{n}"))
    _net(d, "GND").connect(pmic.pin("AGND"))
    _net(d, "GND").connect(pmic.pin("GNDLDO"))

    # VIO — IO-ring reference for SCL/SDA/RSTn/INTn/PWRCTRLx (DS spec
    # 1.7-3.6 V). Tied to the always-on 3V3 bootstrap rail: it matches
    # the I2C2 bus pull-ups (RPU_I2C2_*) and keeps WAKEUPn/RSTn (whose
    # internal pull-ups reference VIO) alive while the PMIC's own COMP
    # rails are down — a PMIC-generated VIO could never be woken.
    _net(d, "3V3").connect(pmic.pin("VIO"))
    # VBUS stays floating per DS Table 3 "not used" column (USB power-source
    # detect unused). (2026-11-22) VREFDDR (pin 45) now drives DDR3L_VREF
    # (VOUT6/2 = 0.675 V) on the compute board, through the sleeve.
    _net(d, "DDR3L_VREF").connect(pmic.pin("VREFDDR"))

    # Active BUCKs — (2026-11-21) RE-MAPPED to the STPMIC25A's FACTORY NVM
    # (DS14278 Table 1) and to each buck's output RANGE (Table "BUCKx output
    # voltage", 0.5–1.5 V on BUCK1/2/3/6, 1.5–4.2 V on BUCK4/5/7). The old
    # map put 3.3 V on BUCK2 and 2.5 V on BUCK3 (0.5–1.5 V bucks; VOUT2 abs
    # max 3 V), 0.82 V on BUCK5 (≥ 1.5 V) and BUCK4 (default 3.3 V) on the
    # 1.8 V rail — no NVM retune can fix a range. Now every rail powers up at
    # its factory default in ST's MP25 order:
    #   rank 1  BUCK4 3.30 V → COMP_3V3  (MP25 VDD/VDDIO first; ~0.3 A of 0.5)
    #   rank 2  BUCK2 0.82 V → COMP_0V82 (VDDCORE, 2 A)
    #   rank 3  BUCK1 0.80 V → COMP_0V9  (VDDCPU; firmware raises to 0.9 V)
    #   rank 3  BUCK5 1.80 V → COMP_1V8  (VDDA18*, camera IO; 0.5 A)
    #   off     BUCK6 → COMP_1V35 (DDR3L VDD/VDDQ, 2026-11-22; was 1.2 V DDR4):
    #           boot firmware sets 1.35 V + enables it before DDR init.
    # BUCK3 / BUCK7 unused. ⚠ NVM: BUCK7 (3.3 V rank 4) and LDO1/2/4 default
    # ON with no load — set their rank to 0 in the provisioning pass.
    _net(d, "PMIC_SW1") .connect(pmic.pin("VLX1"))
    _net(d, "COMP_0V9") .connect(pmic.pin("VOUT1"))
    _net(d, "PMIC_SW2") .connect(pmic.pin("VLX2"))
    _net(d, "COMP_0V82").connect(pmic.pin("VOUT2"))
    _net(d, "PMIC_SW4") .connect(pmic.pin("VLX4"))
    _net(d, "COMP_3V3") .connect(pmic.pin("VOUT4"))
    _net(d, "PMIC_SW5") .connect(pmic.pin("VLX5"))
    _net(d, "COMP_1V8") .connect(pmic.pin("VOUT5"))
    _net(d, "PMIC_SW6") .connect(pmic.pin("VLX6"))
    _net(d, "COMP_1V35").connect(pmic.pin("VOUT6"))
    # feature="bottom" on the VDDCORE inductor: the 4×4 mm part's spacer
    # cavity on the top face ate the power↔companion joint (kept from BUCK5).
    ind_between(d, "PMIC_SW2", "COMP_0V82", "1uH",
                ref="L_PMIC_BUCK2", board_tag=BTAG, feature="bottom")
    cap_to_gnd(d, "COMP_0V82", "22uF/LV",  ref="C_PMIC_0V82_1", board_tag=BTAG,
               feature="bottom", pin=pmic.pin("VOUT2"))
    cap_to_gnd(d, "COMP_0V82", "100nF", ref="C_PMIC_0V82_2",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=pmic.pin("VOUT2"))
    cap_to_gnd(d, "COMP_3V3", "22uF/LV",  ref="C_PMIC_3V3_1", board_tag=BTAG, pin=pmic.pin("VOUT4"))
    cap_to_gnd(d, "COMP_3V3", "100nF", ref="C_PMIC_3V3_2",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=pmic.pin("VOUT4"))

    # Unused BUCK 3 / 7 — VLX + VOUT decoupling caps on auto-named nets
    for n in (3, 7):
        vlx_net  = f"PMIC_VLX{n}_TERM"
        vout_net = f"PMIC_VOUT{n}_TERM"
        _net(d, vlx_net) .connect(pmic.pin(f"VLX{n}"))
        _net(d, vout_net).connect(pmic.pin(f"VOUT{n}"))
        cap_to_gnd(d, vlx_net,  "100nF", ref=f"C_PMIC_VLX{n}",  board_tag=BTAG, pin=pmic.pin(f"VLX{n}"))
        cap_to_gnd(d, vout_net, "100nF", ref=f"C_PMIC_VOUT{n}", board_tag=BTAG, pin=pmic.pin(f"VOUT{n}"))

    # (2026-11-22) LDO6 was the DDR4 VPP 2.5 V — DDR3L has no VPP: unused now,
    # handled with the other spare LDOs below.

    # LDO5 → COMP_2V8 (camera analog rail)
    _net(d, "COMP_2V8").connect(pmic.pin("LDO5OUT"))

    # Remaining LDOs (1-2, 4, 7-8) — decoupling caps on auto-named nets
    for n in (1, 2, 4, 6, 7, 8):
        ldo_net = f"PMIC_LDO{n}_TERM"
        _net(d, ldo_net).connect(pmic.pin(f"LDO{n}OUT"))
        cap_to_gnd(d, ldo_net, "100nF", ref=f"C_PMIC_LDO{n}",
                   embedded_cap_absorbs=True, board_tag=BTAG, pin=pmic.pin(f"LDO{n}OUT"))
    # LDO3 (the DDR sink-source terminator) is unused — DS Table 3 says
    # tie BOTH LDO3IN and LDO3OUT to VIN when not used (no output cap).
    _net(d, "COMP_5V").connect(pmic.pin("LDO3OUT"))

    # Control — I²C on the system I2C2 bus (MP25 PB5/PB4; the TMP117 on
    # this tile already rides it, pull-ups RPU_I2C2_* to 3V3 live on
    # wakeup_board). (2026-11-21) The buck map now MATCHES the STPMIC25A
    # factory NVM (see "Active BUCKs"), so the core rails come up right with
    # no programming; I²C turns on BUCK6 (DDR VDD/VDDQ), LDO6 (VPP 2.5 V) and
    # LDO5 (camera 2.8 V), raises BUCK1 to 0.9 V, and the provisioning pass
    # sets the unused BUCK7 / LDO1/2/4 to rank 0.
    _net(d, "I2C2_SCL")    .connect(pmic.pin("SCL"))
    _net(d, "I2C2_SDA")    .connect(pmic.pin("SDA"))
    _net(d, "PMIC_NRST")   .connect(pmic.pin("RSTN"))
    _net(d, "PMIC_PWR_OK") .connect(pmic.pin("INTN"))

    # PONKEY/WAKEUP pull-ups — to the always-on 3V3 (= VIO rail), NOT
    # COMP_5V: WAKEUPn/RSTn/INTn are rated -0.5..+4.2 V abs max (DS14278
    # Table 4), so a 5 V pull-up violates the rating. (They also carry
    # internal pull-ups referenced to VIO/VINTLDO — the externals are
    # belt-and-braces only.)
    _net(d, "PMIC_PONKEY") .connect(pmic.pin("PONKEYN"))
    res_between(d, "3V3", "PMIC_PONKEY", "10k",
                ref="R_PMIC_PONKEY", board_tag=BTAG)
    _net(d, "PMIC_WAKEUP") .connect(pmic.pin("WAKEUPN"))
    res_between(d, "3V3", "PMIC_WAKEUP", "10k",
                ref="R_PMIC_WAKEUP", board_tag=BTAG)

    # PWRCTRL pull-downs (safe-default off)
    _net(d, "PMIC_PWRCTRL1").connect(pmic.pin("PWRCTRL1"))
    _net(d, "PMIC_PWRCTRL2").connect(pmic.pin("PWRCTRL2"))
    _net(d, "PMIC_PWRCTRL3").connect(pmic.pin("PWRCTRL3"))
    res_between(d, "PMIC_PWRCTRL1", "GND", "10k",
                ref="R_PMIC_PWRCTRL1_PD", board_tag=BTAG)
    res_between(d, "PMIC_PWRCTRL2", "GND", "10k",
                ref="R_PMIC_PWRCTRL2_PD", board_tag=BTAG)
    res_between(d, "PMIC_PWRCTRL3", "GND", "10k",
                ref="R_PMIC_PWRCTRL3_PD", board_tag=BTAG)

    # INTLDO bypass — 4.7 µF per DS14278 Table 3 (pin 8) / Table 2 CINTLDO
    _net(d, "PMIC_INTLDO").connect(pmic.pin("INTLDO"))
    cap_to_gnd(d, "PMIC_INTLDO", "4.7uF",
               ref="C_PMIC_INTLDO", board_tag=BTAG, pin=pmic.pin("INTLDO"))

    # Exposed pad
    _net(d, "GND").connect(pmic.pin("EP"))

    # Buck inductors (1µH, 3A shielded — STPMIC2 reference design)
    # Low-V rails (BUCK1/5/6): ST Table 2 says 0.68 µH; the TMS family has
    # no 0.68 — 1.0 µH is the nearest value on the lower-ripple side
    # (Isat 2.7 A), benign for the adaptive-COT loop (internal ramp).
    ind_between(d, "PMIC_SW1", "COMP_0V9",  "1uH",
                ref="L_PMIC_BUCK1", board_tag=BTAG)
    ind_between(d, "PMIC_SW4", "COMP_3V3",  "2.2uH",
                ref="L_PMIC_BUCK4", board_tag=BTAG)   # ST Table 2 (≥ 1.8 V rail)
    ind_between(d, "PMIC_SW5", "COMP_1V8",  "2.2uH",
                ref="L_PMIC_BUCK5", board_tag=BTAG)   # ST Table 2 (≥ 1.8 V rail)
    ind_between(d, "PMIC_SW6", "COMP_1V35", "1uH",
                ref="L_PMIC_BUCK6", board_tag=BTAG)

    # Per-rail output decoupling
    # Output capacitance: ST Table 2 runs 3-4×22 µF X5R per rail at EVB
    # currents. Here each rail keeps 1×22 µF + the ECM 100 nF: DELIBERATE
    # deviation, justified by (a) rail loads far below the EVB's (no
    # display, NPU at the 0.82 V point), (b) the load-side bulk already
    # on companion (C_MPU_*, C_DDR_BULK*), and (c) the power↔companion
    # LGA joint being SATURATED — adding four more tantalum bodies on
    # this tile threw 21 nets off the lands when tried (2026-06-10).
    cap_to_gnd(d, "COMP_0V9",  "22uF/LV",  ref="C_PMIC_0V9_1", board_tag=BTAG, pin=pmic.pin("VOUT1"))
    cap_to_gnd(d, "COMP_0V9",  "100nF", ref="C_PMIC_0V9_2",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=pmic.pin("VOUT1"))
    cap_to_gnd(d, "COMP_1V8",  "22uF/LV",  ref="C_PMIC_1V8_1", board_tag=BTAG, pin=pmic.pin("VOUT5"))
    cap_to_gnd(d, "COMP_1V8",  "100nF", ref="C_PMIC_1V8_2",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=pmic.pin("VOUT5"))
    cap_to_gnd(d, "COMP_1V35", "10uF",  ref="C_PMIC_1V35_1", board_tag=BTAG, pin=pmic.pin("VOUT6"))
    cap_to_gnd(d, "COMP_1V35", "100nF", ref="C_PMIC_1V35_2",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=pmic.pin("VOUT6"))
    cap_to_gnd(d, "COMP_2V8",  "4.7uF", ref="C_PMIC_2V8_1", board_tag=BTAG, pin=pmic.pin("LDO5OUT"))
    cap_to_gnd(d, "COMP_2V8",  "100nF", ref="C_PMIC_2V8_2",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=pmic.pin("LDO5OUT"))

    # COMP_5V VIN bulk + distributed per-input locals (ST Table 2 wants
    # 10 µF ceramic per BUCKxIN; 4×2.2 µF 0603 spread along the input pins
    # + the shared bulk approximates it at our lower input ripple)
    cap_to_gnd(d, "COMP_5V", "22uF",  ref="C_PMIC_VIN1", board_tag=BTAG, pin=(pmic.ref, None))
    for _i in range(3, 7):
        cap_to_gnd(d, "COMP_5V", "2.2uF", ref=f"C_PMIC_VIN{_i}", board_tag=BTAG, pin=(pmic.ref, None))
    cap_to_gnd(d, "COMP_5V", "100nF", ref="C_PMIC_VIN2",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=(pmic.ref, None))

    # Reset + PWR_OK open-drain pull-ups — to 3V3 (= VIO rail), not
    # COMP_5V: RSTn/INTn abs max is +4.2 V (DS14278 Table 4).
    # Rule-sweep: 3V3 (not COMP_3V3) is LOAD-BEARING for RSTn/PONKEY/
    # WAKEUP — COMP_3V3 is BUCK2's own output, pulling reset to it is a
    # chicken-and-egg lockup. INTN's MP25 reader sees the F5 boot
    # transient (note at the I2C2/3 pull-ups).
    res_between(d, "3V3", "PMIC_NRST",   "10k",
                ref="R_PMIC_NRST",   board_tag=BTAG)
    res_between(d, "3V3", "PMIC_PWR_OK", "10k",
                ref="R_PMIC_PWR_OK", board_tag=BTAG)

    # (2026-11-20, user) the optional DNP camera LDOs moved to camera_module
    # (local rails, 0 Ω-selectable) — see build_camera_module.

    # ── add_tmp117(1, I2C2_SCL, I2C2_SDA) ────────────────────────────
    # (2026-11-22) TMP117 → MCP9808T-E/MC (availability/decisions.csv).
    # Address 0x1A (A2=0, A1=1, A0=0): clear of the
    # magnetometer (BMM350 0x14) on I2C2. FIRMWARE: new driver + address.
    tmp = add_mcp9808t_e_mc(d, ref="U_TMP1", board_tag=BTAG)
    _net(d, "I2C2_SCL")  .connect(tmp.pin("SCL"))
    _net(d, "I2C2_SDA")  .connect(tmp.pin("SDA"))
    _net(d, "3V3")       .connect(tmp.pin("VDD"))
    _net(d, "GND")       .connect(tmp.pin("GND"))
    _net(d, "GND")       .connect(tmp.pin("A2"))
    _net(d, "3V3")       .connect(tmp.pin("A1"))
    _net(d, "GND")       .connect(tmp.pin("A0"))
    _net(d, "TMP1_ALERT").connect(tmp.pin("ALERT"))
    # TMP117 DS pin table: ALERT is open-drain and "requires a pullup
    # resistor". COMP_3V3 = the reading MP25's IO domain (same rationale
    # as the eFuse PGOOD/FLT pull-ups); the pin is 5.5 V-tolerant.
    res_between(d, "COMP_3V3", "TMP1_ALERT", "10k",
                ref="R_TMP1_ALERT_PU", board_tag=BTAG)
    _net(d, "GND")       .connect(tmp.pin("EP"))    # DFN-8 exposed pad → GND
    cap_to_gnd(d, "3V3", "100nF", ref="C_TMP1",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=tmp.pin("V+"))
    # NB: system.py's TMP117 placeholder doesn't expose EP. The smash
    # factory does — leave unconnected to match.

    # ── Depot-USB power OR + wake interlock (moved here from
    # the nose_cap builder 2026-08-28: these are power_board parts — "the OR
    # diode + its VBUS bulk cap live on POWER_BOARD (where BAT_PROT
    # exists)" — and the shared power tile must fab identically in every
    # config, USB depot present or not). USB 5 V VBUS ORed into BAT_PROT —
    # the protected battery rail that feeds EVERYTHING, so the depot USB-C
    # runs the FULL unit. In configs without the nose USB connector
    # USB_VBUS is a stub net — the parts still fab (shared bare board).
    #
    # Q_USB_OR — IDEAL-DIODE OR (replaced the MBRS540T3G Schottky
    # D_USB_PWR 2026-09-02). The Schottky was a SHELF-LEAKAGE fault, not
    # merely an oversized package: BAT_PROT sits at cell − 0.7 V through
    # Q_ISO's body diode in shelf (power_states.md), so the OR device is
    # reverse-biased across ~3 V for the whole storage life with its anode
    # tied to ground by the wake divider. MBRS540T3G Fig 3 (typical)
    # reads ~3 µA at 3 V / 25 °C, doubling every ~9 °C — against a ~1 µA
    # TOTAL shelf budget, i.e. >the whole pack over the 15 y claim, and
    # enough return current through R_USBWK_G/R_USBWK_PD to walk
    # USBWK_GATE up to a BSS138 threshold and self-wake a warm round.
    # Schottky low-V_F and high I_R are the same physics; a silicon PN
    # diode fixes the leak but its ~0.8 V drop puts BAT_PROT BELOW the
    # cells at the low end of USB tolerance, which breaks the isolation.
    #
    # So: the same P-FET ideal-diode idiom as Q_ISO, one net away, with
    # BAT_PROT as the shared source — Q_ISO's drains face the cell,
    # Q_USB_OR's face VBUS, a textbook 2-input ideal-diode OR. Body diode
    # (drain=USB_VBUS → source=BAT_PROT) passes VBUS FORWARD and blocks
    # BAT_PROT→VBUS, so the dead-USB backfeed the Schottky blocked is
    # still blocked with the gate drive unpowered. OFF-state leak is
    # DMP6110 I_DSS (~nA, −1 µA max) instead of Schottky junction leak.
    # Drop at a ~0.5 A depot load is 130 mΩ ≈ 65 mV (was ~400 mV), so
    # BAT_PROT ≈ 4.94 V against ~4 V cells — the reverse-bias margin that
    # keeps Q_ISO's body diode off GROWS from ~0.35 V to ~0.94 V.
    # Purely hardware: firmware is not in this path at all.
    #
    # (2026-11-20, user) ON THE USB NOSE, next to the USB-C: the OR + its
    # VBUS-presence driver + VBUS bulk only exist where the connector does
    # (`core`), not in every config. The 3 A now comes up the crown as
    # BAT_PROT (3 teeth); VBUS crosses only as a presence signal (1 tooth)
    # for Q_ISO_USB / the USB wake / the MP25 VBUS detect, which stay put.
    # NOTE: like Q_ISO, the forward drop and the gate-drive timing want
    # bench confirmation before fab (analog behaviour, not modelled by
    # the connectivity build).
    UT = "usb_nose"
    q_usb_or = add_buk6d120_60px(d, ref="Q_USB_OR", board_tag=UT)   # (2026-11-22) sourcing swap, availability/decisions.csv: DMP6110 → BUK6D120
    for dp in ("D_1", "D_2", "D_3", "D_4", "D_5"):
        _net(d, "USB_VBUS").connect(q_usb_or.pin(dp))   # drains → VBUS side
    for sp in ("S_1", "S_2"):
        _net(d, "BAT_PROT").connect(q_usb_or.pin(sp))   # source → load side
    _net(d, "USB_OR_G")   .connect(q_usb_or.pin("G"))
    # Gate divider, mirroring Q_ISO: BAT_PROT ─100k─ G ─10k─ DRV drain.
    # DRV off → G≈BAT_PROT (V_GS≈0, OFF, nanopower, body-diode-only).
    # DRV on → G≈BAT_PROT·10/110 ≈ 0.45 V → V_GS≈-4.5 V (fully enhanced,
    # R_DS(on) 130 mΩ, inside the ±20 V V_GSS). The 110k chain draws
    # ~45 µA ONLY while USB is live — i.e. off the depot supply, never
    # off the cells.
    res_between(d, "BAT_PROT",  "USB_OR_G",  "100k", ref="R_USBOR_H", board_tag=UT)
    res_between(d, "USB_OR_G",  "USB_OR_GD", "10k",  ref="R_USBOR_L", board_tag=UT)
    q_usbor_drv = add_ssm3k35ctc_l3f(d, ref="Q_USBOR_DRV", board_tag=UT)
    _net(d, "USB_OR_GD").connect(q_usbor_drv.pin("3"))   # drain → gate divider
    _net(d, "GND")      .connect(q_usbor_drv.pin("2"))   # source
    _net(d, "USB_OR_EN").connect(q_usbor_drv.pin("1"))   # gate ← VBUS presence
    # VBUS-presence divider (same idiom as R_ISO_USB_H/L on the interlock):
    # VBUS 5 V → USB_OR_EN 2.5 V, well above the BSS138 V_GS(th) 0.8-1.5 V;
    # VBUS absent → 0 V through R_USBOR_USB_L, so the P-FET defaults OFF.
    res_between(d, "USB_VBUS",   "USB_OR_EN", "100k", ref="R_USBOR_USB_H", board_tag=UT)
    res_between(d, "USB_OR_EN",  "GND",       "100k", ref="R_USBOR_USB_L", board_tag=UT)
    cap_to_gnd(d, "USB_VBUS", "10uF", ref="C_USB_VBUS", board_tag=UT)

    # ── Depot-USB WAKE: VBUS presence joins the MAIN_SW_GATE open-drain
    # OR (4th member after the NFC GPO diode, QHOLD/MP25, QHOLD2/WBA) —
    # plugging the depot cable powers the round up DELIBERATELY (not via
    # the marginal V_GS the diode-OR would otherwise produce). The load
    # then runs ENTIRELY from USB: VBUS−0.4 ≈ 4.7 V on BAT_PROT sits
    # above the 4 V cells, so Q_ISO (force-OFF by the USB interlock, body
    # diode reverse-biased) keeps the pack at zero load-current — only the
    # 3V3_AON trinkets draw from the cells during a depot session (no eFuse
    # IQ any more). Unplug: VBUS falls → Q_USB_WAKE and the Q_ISO interlock
    # release; if no firmware hold is up the round drops cleanly back to
    # shelf, else Q_ISO's body diode hands the load back to the cells.
    q_usbwk = add_ssm3k35ctc_l3f(d, ref="Q_USB_WAKE", board_tag=BTAG,
                          feature="bottom")  # keep the saturated companion joint face clear
    _net(d, "MAIN_SW_GATE").connect(q_usbwk.pin("3"))   # Drain → the latch OR
    _net(d, "GND")         .connect(q_usbwk.pin("2"))   # Source
    _net(d, "USBWK_GATE")  .connect(q_usbwk.pin("1"))   # Gate ← VBUS divider
    res_between(d, "USB_VBUS",   "USBWK_GATE", "10k",
                ref="R_USBWK_G",  board_tag=BTAG)
    res_between(d, "USBWK_GATE", "GND",        "100k",
                ref="R_USBWK_PD", board_tag=BTAG)

    # P_AFT_LGA removed: activation_interface is now flex-connected to
    # power_board (snake), so the rigid-mate LGA harness no longer
    # exists.


def _as_built_0402(value: str, dielectric: str) -> dict:
    """Factory overrides that put a cap in the 0402 package Francesco placed
    on the routed wakeup_board (WIP/Finalized from Francesco/wakeup_board 2),
    where the value-based dispatch would pick 0603. Footprint, body and mass
    follow the board as built; the MPN is left for the EE to confirm — the
    0603 family the dispatch picks (MIL X7R / AVX SQCS) has no 0402 part at
    this value."""
    from smash.parts.passives import _stock_smd_2pad, weight_g_for_passive
    return dict(
        footprint=_stock_smd_2pad(
            name="Capacitor_SMD:C_0402_1005Metric",
            size_mm=(1.0, 0.5), height_mm=0.50,
            pad_size=(0.55, 0.6), pad_pitch_mm=0.95,
            package_class="0402"),
        package="0402", size_mm=(1.0, 0.5), height_mm=0.50,
        weight_g=weight_g_for_passive("0402"),
        name=f"C_0402_{value}", dielectric=dielectric,
        manf_pn=f"TBD 0402 {dielectric} {value} (as placed; confirm MPN)",
        description=(f"0402 {dielectric} ceramic, {value} — package per the "
                     f"routed wakeup_board; MPN to confirm"))


def build_wakeup_board(d: Design) -> None:
    """Always-on wakeup tile (post-WLE5 architecture. The 2026-07-30
    crowding split moved the FIN ACTUATION one tile aft onto
    fin_ble_board; the WBA55 cluster briefly went with it and came BACK
    2026-07-31 — the power_states.md ladder is WBA-orchestrated end to
    end, and at the time core_radar dropped fin_ble_board (it no longer
    does — the tile is the battery ceiling + piezo host now), so
    everything wake/activation_unlock-critical was consolidated here and stays):

      • QMAIN/QHOLD/QHOLD2 load-switch + hold latches + MCP1640 boost +
        LDL112PV33R LDO power chain (3V3 always-on rail)
      • STM32WBA55HGF6TR (WLCSP41) — wake orchestrator + BLE 2.4 GHz
        radio, with its DSC1001 MEMS HSE, reset/BOOT0 network, π-match
        + Wilkinson/90°-hybrid RF chain (the Yagi A/B leaves branch off
        THIS tile's N/S edges), the IR_WAKE bias/filter pair and
        RHOLD_AON beside it. In core_radar the Yagi leaves are dropped
        (RF-dark: no BLE session) but the wake/activation_unlock ladder is intact —
        the IR link runs off the radar tile's optics.
      • Wake listeners: RR123 TMR shelf ear + its TPS7A02 nano-LDO,
        DRV5032FC magnetic activation_unlock Hall (MAG_WAKE_N → WBA PC14,
        tile-local), jumpstart wake OR legs (pads on aft_end_board)
      • H3LIS331DL ±400g accelerometer — on the MAIN 3V3 rail +
        M33 I2C3/PD10 (launch witness only; board_tag=activation)
      • 3× test points
      • BMM350 magnetometer + 3× ISM330DLC IMU on I2C2/3 — the flight sensor
        cluster, folded in from the merged-away flight_board (each aft tile had
        only a handful of chips left after flight control moved onto the MP25
        M33). Built via build_flight_board(board_tag="wakeup_board"); their
        INT/DRDY/I2C nets are now local to this tile instead of crossing a gap.

    Removed:
      G0B1 + TCAN1042 CAN-FD bridge — WBA55 (no FDCAN) needed a whole bridge
      MCU + transceiver to reach the CAN bus; with CAN gone it talks to the
      MP25 M33 root directly over LPUART1, so the bridge and the AON_GATED switch
      that gated it are both deleted. Prior WLE5-era: WLE5 + its nano-LDO /
      LSE / RF-match / recovery straps, MT29F NAND, BGS12 LoRa diversity
      switch. NFC subsystem deleted 2026-07-30 (tag + coil + GPO legs)."""
    BTAG = "wakeup_board"

    # ── add_power_input_with_rf_wake — QMAIN load switch + QHOLD latch ──
    qmain = add_ssm3j372r_lf(d, ref="QMAIN", board_tag=BTAG)
    _net(d, "BAT_PROT")     .connect(qmain.pin("2"))   # Source
    _net(d, "REG_IN_MAIN")  .connect(qmain.pin("3"))   # Drain
    _net(d, "MAIN_SW_GATE") .connect(qmain.pin("1"))   # Gate

    # Gate pull-up on BAT_RAW (the always-live cell rail): holds QMAIN
    # off in shelf. With the eFuse gone, BAT_PROT is now ALIVE in shelf
    # through Q_ISO's body diode (≈ cell − 0.7 V), so the NFC GPO pull-up
    # to BAT_PROT still works and QMAIN gates REG_IN_MAIN directly — no
    # eFuse-enable step. Depot-USB plug-in wakes the round EXPLICITLY via
    # Q_USB_WAKE (power_board), which joins this gate's open-drain OR.
    res_between(d, "BAT_RAW", "MAIN_SW_GATE", "1M",
                ref="RMAIN_PU",     board_tag=BTAG)
    cap_to_gnd(d, "MAIN_SW_GATE", "100nF", ref="CMAIN_HOLD", board_tag=BTAG, pin=qmain.pin("1"))

    # (Q_EFEN removed with the eFuse — there is no longer an eFuse EN to
    # gate. The wake now self-sequences through Q_ISO's body diode:
    # MAIN_SW_GATE low → QMAIN conducts → REG_IN_MAIN rises off the
    # already-live BAT_PROT. Every hold — NFC GPO diode, QHOLD/MP25,
    # QHOLD2/WBA — gates QMAIN alone now.)

    qhold = add_ssm3k35ctc_l3f(d, ref="QHOLD", board_tag=BTAG)
    _net(d, "MAIN_SW_GATE") .connect(qhold.pin("3"))   # Drain
    _net(d, "GND")          .connect(qhold.pin("2"))   # Source
    _net(d, "QHOLD_GATE")   .connect(qhold.pin("1"))   # Gate

    # PWR_HOLD ← the MP25 M33 (inter-board)
    res_between(d, "PWR_HOLD",   "QHOLD_GATE", "100",
                ref="RHOLD_G",      board_tag=BTAG)
    res_between(d, "QHOLD_GATE", "GND",        "100k",
                ref="RHOLD_PD",     board_tag=BTAG)

    # ── GENUINE always-on wake path: NFC tap → QMAIN, no MCU alive ───
    # In TRUE shelf (QMAIN off) every rail aft of REG_IN_MAIN is dead —
    # including the WBA the old design expected to hear the NFC GPO.
    # The ST25DV is the one listener needing NO supply: RF-POWERED, it
    # pulses its open-drain GPO against the existing 330 k pull-up to
    # BAT_PROT (DS13519 Fig. 8: "power-up by RF, no VCC, pull-up on
    # GPO"). One Schottky ORs that pulse onto QMAIN's gate:
    #   tap → GPO low → gate ≈ V_OL + V_f + I·R ≈ 0.7 V → V_GS ≈ −3.3 V
    #   → QMAIN ON → 3V3 rises → WBA boots (ms) and takes the hold over
    # via WBA_WAKE/PB4 long before the wand leaves the field (the
    # CMAIN_HOLD 100 nF × 1 MΩ bridges ~100 ms of handover regardless).
    # Releasing the hold drops back to shelf — Standby→Shelf without activation_unlock
    # still works; with the gate held low the diode just blocks while
    # GPO floats back to BAT_PROT for clean WBA PA8 edges (reverse
    # ≤ ~5 V « 40 V V_R). The 3.3 k series R caps the CMAIN_HOLD
    # discharge at ~1.0 mA — under the GPO's 1.5 mA DC sink abs-max.
    # ⚠ Provisioning: the ST25DV GPO_CTRL NVM bits must enable an RF
    # event (FIELD_CHANGE / RF_USER) so GPO activates with VCC absent; and
    # verify GPO V_OL at 1 mA in RF-only mode at bring-up.
    # ── MAGNETIC activation_unlock listener (repositioned 2026-07-30, same day as
    # the NFC removal): U_MAG_WAKE — a DRV5032FC nanopower Hall (1.6 µA
    # typ, omnipolar so orientation doesn't matter, open-drain) — now on
    # **3V3_AON**, NOT the always-live rail: it hears nothing in TRUE
    # shelf and costs the shelf budget NOTHING (Shelf back to ~1 µA
    # electronic ≈ 15 y). From STANDBY it is the second activation_unlock trigger
    # beside the IR wand: a coded ~2 Hz ≥4.8 mT field (coil or wand
    # magnet — reaches through container/bore walls that block IR;
    # aluminium near-lossless, steel ~30-100× shunted) lands on WBA PC14
    # as an EXTI (≥9.5 mT since the DRV5032AJ swap); the WBA verifies the pattern in a persistence window
    # (mirror of the IR activation_unlock) and then runs the SAME deliberate activation_unlock
    # sequence. NO power-OR legs: activation_unlock is WBA-orchestrated, never a
    # hardware power-pull, and fails CLOSED (no pattern → no activation_unlock). Shelf
    # wake is jumpstart/USB only.
    # (2026-11-21) DRV5032AJ X2SON 0.4 mm (was DRV5032FC SOT-23 1.12 mm):
    # ⚠ B_OP 9.5 mT max (FC: 4.8) — the coded wake field must double.
    hall = add_drv5032ajdmrr(d, ref="U_MAG_WAKE", board_tag=_MAG_TAG)
    _net(d, "3V3_AON")   .connect(hall.pin("VCC"))   # activation_unlock listener: alive from Standby, silent+free in Shelf
    _net(d, "GND")       .connect(hall.pin("GND"))
    _net(d, "GND")       .connect(hall.pin("EP"))
    _net(d, "MAG_WAKE_N").connect(hall.pin("OUT"))
    cap_to_gnd(d, "3V3_AON", "100nF", ref="C_MAG_WAKE", board_tag=_MAG_TAG, pin=hall.pin("VCC"))
    # Open-drain node bias: 1 M to 3V3_AON keeps the WBA pin ≤3.3 V (no
    # BAT_RAW level issue). In TRUE shelf AON is down and the node floats
    # — harmless: the shelf wake path needs only the Hall's active sink
    # through the diode, and the WBA is unpowered anyway.
    res_between(d, "3V3_AON", "MAG_WAKE_N", "1M",
                ref="RPU_MAG_WAKE", board_tag=_MAG_TAG)

    # ── MAGNETIC SHELF-WAKE ear (2026-07-30, completing the split roles):
    # U_MAG_SHELF — Coto RR123-1H02-612 TMR (20 nA avg, omnipolar,
    # ACTIVE-LOW push-pull, B_OP 0.7 mT — 7× more sensitive than the
    # activation_unlock Hall, so the through-container coil shrinks 7× and
    # through-steel becomes plausible). Its VDD abs-max is 3.6 V so it
    # CANNOT hang on BAT_RAW: a dedicated always-on TPS7A02 (25 nA IQ,
    # EN tied to IN) feeds TMR_VDD → listener total ≈ 45 nA — Shelf stays
    # ~1 µA-class (~15 y). The active-low output drives the SPARE K_2
    # legs of BOTH wake diodes (twin main+AON ORs — the mandatory
    # two-legs rule) through the usual 3.3 k; idle-HIGH at TMR_VDD keeps
    # the diodes blocked, and no MCU pin is involved (no back-power
    # path). f_SW is 1 Hz typ (±50 % over temp) → the coded shelf-wake
    # sequence is SLOW: bits ≥ ~3 s, full wake ~10-15 s — a depot
    # bulk-wake, not a tap. The WBA (once booted) IDs the wake source by
    # elimination and demands the pattern continue before holding.
    tmr_ldo = add_s1318d33_a4t2u4(d, ref="U_TMR_LDO", board_tag=_MAG_TAG)   # (2026-11-22) HSNT-4 0.4 mm   # (2026-11-22) sourcing swap, availability/decisions.csv   # (2026-11-20) X2SON 0.4 mm
    _net(d, "BAT_RAW").connect(tmr_ldo.pin("IN"))
    _net(d, "BAT_RAW").connect(tmr_ldo.pin("EN"))     # always on
    _net(d, "GND")    .connect(tmr_ldo.pin("GND"))
    _net(d, "GND")    .connect(tmr_ldo.pin("EP"))       # heat sink → GND (DS)
    _net(d, "TMR_VDD").connect(tmr_ldo.pin("OUT"))
    cap_to_gnd(d, "TMR_VDD", "1uF", ref="C_TMR_LDO", board_tag=_MAG_TAG, pin=tmr_ldo.pin("OUT"))
    tmr = add_rr123_1h02_612(d, ref="U_MAG_SHELF", board_tag=_MAG_TAG)
    _net(d, "TMR_VDD")    .connect(tmr.pin("VDD"))
    _net(d, "GND")        .connect(tmr.pin("GND"))
    _net(d, "MAG_SHELF_N").connect(tmr.pin("DIGITAL_OUT"))
    _net(d, "GND")        .connect(tmr.pin("LATCH_CONTROL"))   # latch inactive (VERIFY polarity)
    cap_to_gnd(d, "TMR_VDD", "100nF", ref="C_MAG_SHELF", board_tag=_MAG_TAG, pin=tmr.pin("VDD"))
    res_between(d, "MAG_SHELF_K", "MAG_SHELF_N", "3.3k",
                ref="R_MAG_SHELF", board_tag=_MAG_TAG)

    # ── JUMPSTART contacts (2026-07-30): two exposed 1.5 mm pads on the
    # AFT face — bridge them with anything metallic and the round boots.
    # Zero-equipment activation: production first-power-on, depot/EOD
    # probe, field fallback when wand/coil/NFC gear is absent. Same latch
    # pattern as every wake source: the bridge pulls a diode leg of the
    # QMAIN gate OR, QHOLD2 latches within ms, the bridge can lift.
    # Moisture immunity by a STIFF divider: 22 k pull-up + 10 k pad
    # series set the wake threshold at bridge ≤ ~35 kΩ — a coin, clip or
    # probe wakes it; a wet/salt film (≥ ~50-100 kΩ) leaves the node high
    # and the diode reverse-biased. Unbridged the leg draws ZERO (node
    # rests at BAT_RAW → 0 V across pull-up AND diode). The 10 k at the
    # pad is also the ESD barrier; the Schottky isolates the gate node.
    # NOT routed to a WBA pin (node rests above 3.3 V): firmware
    # disambiguates the wake source by elimination — no NFC GPO edge, no
    # PC14 pattern, no VBUS ⇒ jumpstart.
    # Ø2.0 pogo pads, not the Ø1.5 _add_testpoint default: these two are the
    # only pads on this face a user BRIDGES rather than probes, so they match
    # the rest of the bench array's 2.0 mm size (uniform field, one fixture
    # pitch) and give a coin or clip more copper to land on. JUMP_WAKE carries
    # the square group-start silhouette.
    # (2026-11-19) contacts of the aft_end_cap crown (the public interface)
    tp_jw = add_pogo_pad(d, ref="TP_JUMP_WAKE", board_tag=AFT_CAP,
                         manf_pn=None, square=True)
    tp_jg = add_pogo_pad(d, ref="TP_JUMP_GND", board_tag=AFT_CAP,
                         manf_pn=None)
    _net(d, "JUMP_PAD").connect(tp_jw.pin("1"))
    _net(d, "GND")     .connect(tp_jg.pin("1"))
    res_between(d, "JUMP_PAD", "JUMP_WAKE", "10k",
                ref="R_JUMP_PAD", board_tag="aft_end_board")
    res_between(d, "BAT_RAW", "JUMP_WAKE", "22k",
                ref="R_JUMP_PU", board_tag=BTAG)
    # (2026-11-22, user) the dual common-anode BAT64-06 (shallow stock,
    # China-origin lots) became two single Infineon BAS40-02L (TSLP-2-1,
    # 1.0 × 0.6 mm, made in Austria; already in the BOM for the parachute
    # matrix). Same OR: anodes on the gate, one cathode per wake source.
    d_jump1 = add_bas40_02l(d, ref="D_JUMP_WAKE", board_tag=BTAG)
    _net(d, "MAIN_SW_GATE").connect(d_jump1.pin("A"))
    _net(d, "JUMP_WAKE_K") .connect(d_jump1.pin("K"))
    res_between(d, "JUMP_WAKE_K", "JUMP_WAKE", "3.3k",
                ref="R_JUMP_WAKE", board_tag=BTAG)
    d_jump2 = add_bas40_02l(d, ref="D_JUMP_WAKE2", board_tag=BTAG)
    _net(d, "MAIN_SW_GATE").connect(d_jump2.pin("A"))
    _net(d, "MAG_SHELF_K") .connect(d_jump2.pin("K"))   # TMR shelf-wake leg

    # (2026-11-20, user) the whole 3V3 chain (MCP1640 boost + LDL112 LDO +
    # their caps, ~86 mm²) moved wakeup → power_board BOTTOM: wakeup's top
    # was over the ~500 mm²-per-face packing ceiling (544 mm²), power's
    # bottom had ~158 mm² spare (its top only ~73). Power next to power;
    # REG_IN_MAIN + 3V3 now cross the wakeup↔power gap (one gap).
    _PWR_TAG, _PWR_FACE = "power_board", "bottom"
    # ── MCP1640 boost regulator (REG_IN_MAIN → BOOST_OUT ≈ 3.87 V) ──
    # (2026-11-20, user) DFN-8 (1.0 mm) instead of SOT-23-6
    boost = add_mcp1640_dfn(d, ref="U_BOOST", board_tag=_PWR_TAG, feature=_PWR_FACE, variant="C")
    _net(d, "REG_IN_MAIN") .connect(boost.pin("VIN"))
    _net(d, "REG_IN_MAIN") .connect(boost.pin("EN"))      # EN tied VIN
    for _g in ("SGND", "PGND", "EP"):
        _net(d, "GND")     .connect(boost.pin(_g))
    _net(d, "BOOST_SW")    .connect(boost.pin("SW"))
    _net(d, "BOOST_OUT")   .connect(boost.pin("VOUTP"))
    _net(d, "BOOST_OUT")   .connect(boost.pin("VOUTS"))
    _net(d, "BOOST_FB")    .connect(boost.pin("VFB"))

    # 2.2 µH TMS (real 0806 power part, Isat 1.2 A; MCP1640 DS inductor
    # range 2.2–10 µH). (2026-11-22) LOAD BUDGET — the old "~0.2 A boost
    # peaks" predates the 11-18 transverter. 3V3 peak = S4 TX: LO ~125 mA +
    # mixer (LTC5552) ~132 mA + LR2021/WBA/sensors ~50 mA ≈ 0.31 A (the PA
    # boost U_XV_BOOST moved to REG_IN_MAIN; on 3V3 it was ~0.5 A). Limit:
    # MCP1640 ~350 mA at this VIN/VOUT, and on a fresh pack (≥ 3.87 V) it
    # passes VIN through — 400 mA ABS MAX. ~0.31 A fits with thin margin;
    # next steps if loads grow: LO + mixer → COMP_3V3, or a ≥ 1 A buck-boost. The old binding was a
    # nonexistent "WE-KI 0402 4.7 µH" RF part (family capped ~120 nH) —
    # same bogus binding fixed on L_BOOST_COMP + both AWR bucks.
    ind_between(d, "REG_IN_MAIN", "BOOST_SW", "2.2uH",
                ref="L_PWR", board_tag=_PWR_TAG, feature=_PWR_FACE)
    res_between(d, "BOOST_OUT", "BOOST_FB", "220k",
                ref="R_BOOST_FB1", board_tag=_PWR_TAG, feature=_PWR_FACE)
    res_between(d, "BOOST_FB",  "GND",      "100k",
                ref="R_BOOST_FB2", board_tag=_PWR_TAG, feature=_PWR_FACE)
    cap_to_gnd(d, "REG_IN_MAIN", "10uF",  ref="CBOOST_IN1",  board_tag=_PWR_TAG, feature=_PWR_FACE, pin=boost.pin("VIN"))
    cap_to_gnd(d, "REG_IN_MAIN", "100nF", ref="CBOOST_IN2",  board_tag=_PWR_TAG, feature=_PWR_FACE, pin=boost.pin("VIN"))
    cap_to_gnd(d, "BOOST_OUT",   "22uF",  ref="CBOOST_OUT1", board_tag=_PWR_TAG, feature=_PWR_FACE, pin=boost.pin("VOUTP"))
    cap_to_gnd(d, "BOOST_OUT",   "100nF", ref="CBOOST_OUT2",
               embedded_cap_absorbs=True, board_tag=_PWR_TAG, feature=_PWR_FACE, pin=boost.pin("VOUTP"))

    # ── LDL112PV33R: BOOST_OUT (3.87 V) → 3V3 ──
    # ST DS10321 Table 1: pin 1=EN, pin 2=GND, pin 3=ADJ (NC on fixed),
    # pin 4=VOUT, pin 5=NC, pin 6=VIN, pin 7=EP-to-GND.
    ldo_pwr = add_ldl112pv33r(d, ref="U_PWR", board_tag=_PWR_TAG, feature=_PWR_FACE)
    _net(d, "BOOST_OUT") .connect(ldo_pwr.pin("VIN"))
    _net(d, "GND")       .connect(ldo_pwr.pin("GND"))
    _net(d, "BOOST_OUT") .connect(ldo_pwr.pin("EN"))   # tied VIN → always-on
    _net(d, "3V3")       .connect(ldo_pwr.pin("VOUT"))
    _net(d, "GND")       .connect(ldo_pwr.pin("EP"))   # thermal pad → GND
    cap_to_gnd(d, "3V3", "22uF",  ref="COUT1", board_tag=_PWR_TAG, feature=_PWR_FACE, pin=ldo_pwr.pin("VOUT"))
    cap_to_gnd(d, "3V3", "22uF",  ref="COUT2", board_tag=_PWR_TAG, feature=_PWR_FACE, pin=ldo_pwr.pin("VOUT"))
    cap_to_gnd(d, "3V3", "100nF", ref="COUT3",
               embedded_cap_absorbs=True, board_tag=_PWR_TAG, feature=_PWR_FACE, pin=ldo_pwr.pin("VOUT"))

    # ── add_st25dv_tssop8_rf_wake — NFC dual-port tag ──
    # AON latch host tile. Was activation_interface ("beside the ST25DV/H3LIS")
    # — moved to wakeup_board 2026-07-31 in the activation chip redistribution:
    # the ST25DV is deleted, and every other member of the wake pattern (WBA
    # hold, TMR shelf ear, Hall listener, D_JUMP_WAKE, the QHOLD/QMAIN
    # latches) already lives on wakeup_board, so AON_EN / MAG_SHELF_K become
    # tile-local there. (NOT fin_ble_board: core_radar dropped that tile at
    # the time — it no longer does — and the wake pattern is wakeup-local
    # anyway.)
    _ACT_TAG = "wakeup_board"

    # ── NFC subsystem REMOVED 2026-07-30 (user decision): the ST25DV tag,
    # its Ø22 antenna flex, GPO wake legs, session-gated VCC (WBA PA7) and
    # GPO EXTI (WBA PA8) are all deleted. Wake channels are now MAGNETIC
    # (coded field → U_MAG_WAKE Hall), JUMPSTART (aft contact pads) and
    # depot USB; per-round identity/telemetry rides the IR/BLE session
    # post-wake; activation_unlock release = IR wand. Consequence accepted: there is no
    # zero-power Shelf interrogation any more — a shelf round must be
    # woken (magnet/jumpstart, µJ) to be queried.

    # ── 3V3_AON — the nanopower STANDBY domain (TPS7A02, 25 nA IQ) ────
    # Hangs directly on BAT_RAW, UPSTREAM of the wake-gated eFuse: in
    # Standby the eFuse + QMAIN are both OFF and only this domain lives
    # (WBA55 + H3LIS + ST25DV VCC + TLV3691 ≈ 17 µA), so Standby
    # drops from ~320 µA (26 d) to ~28 µA (~10 months on the 1-cell
    # pack). The LDO's own current limit is the protection for this
    # µA-class domain (it bypasses the eFuse by design). Sited on
    # wakeup_board beside the WBA + Hall (two of its loads) and the rest
    # of the wake-latch pattern; BAT_RAW reaches it over the backbone.
    aon = add_s1318d33_a4t2u4(d, ref="U_AON_LDO", board_tag=_ACT_TAG)   # (2026-11-22) HSNT-4 0.4 mm   # (2026-11-22) sourcing swap, availability/decisions.csv   # (2026-11-20) X2SON 0.4 mm
    _net(d, "BAT_RAW").connect(aon.pin("IN"))
    _net(d, "GND")    .connect(aon.pin("GND"))
    _net(d, "GND")    .connect(aon.pin("EP"))     # heat sink → GND (DS)
    _net(d, "AON_EN") .connect(aon.pin("EN"))
    # S-1318 D type has no ON/OFF pull-down (the XC6504's "floats = OFF"
    # was internal) → 10 MΩ external (0.33 µA, only while AON is on).
    res_between(d, "AON_EN", "GND", "10M", ref="R_AON_EN_PD", board_tag=_ACT_TAG)
    _net(d, "3V3_AON").connect(aon.pin("OUT"))
    cap_to_gnd(d, "BAT_RAW", "1uF", ref="C_AON_IN",  board_tag=_ACT_TAG, pin=aon.pin("IN"))
    cap_to_gnd(d, "3V3_AON", "1uF", ref="C_AON_OUT", board_tag=_ACT_TAG, pin=aon.pin("OUT"))

    # AON-EN latch — third instance of the wake pattern: Q_AON_EN raises
    # EN to BAT_RAW when a wake source (magnetic / jumpstart via
    # D_AON_WAKE's shared cathode nets, since the 2026-07-30 NFC removal)
    # or the depot-USB presence (Q_USB_WAKE2, gate on the shared USBWK divider) pulls
    # its gate low. The WBA then HOLDS AON via PB15 → 1 k → EN (a 3V3-
    # push-pull high; safe vs the FET's 4 V drive through the 1 k, and a
    # DEAD PB15 leaks nothing because EN idles at 0 V in shelf). States:
    #   shelf   = no holds, EN=0     → AON + main both off (~10 µA)
    #   standby = WBA holds EN only  → AON on, eFuse+QMAIN off (~28 µA)
    #   on      = + PB4/PWR_HOLD     → everything up
    q_aon = add_ssm3j372r_lf(d, ref="Q_AON_EN", board_tag=_ACT_TAG)
    _net(d, "BAT_RAW")    .connect(q_aon.pin("2"))   # Source
    _net(d, "AON_EN")     .connect(q_aon.pin("3"))   # Drain → LDO EN
    _net(d, "AON_EN_GATE").connect(q_aon.pin("1"))   # Gate
    res_between(d, "BAT_RAW", "AON_EN_GATE", "1M",
                ref="RAON_PU", board_tag=_ACT_TAG)
    # D_AON_WAKE (was D_NFC_WAKE2): the AON-side wake OR. Shares each
    # source's cathode net with the main-OR diode (the proven two-diode
    # topology NFC used) so a magnetic or jumpstart wake raises BOTH the
    # main rail AND 3V3_AON — without this the WBA (which lives on AON)
    # never boots and the round falls back asleep after the ~100 ms gate
    # hold. (Latent bug in the first mag/jumpstart wiring, found and
    # fixed during the NFC removal 2026-07-30.)
    # (2026-11-22, user) two single BAS40-02L instead of the dual BAT64-06.
    d_aon1 = add_bas40_02l(d, ref="D_AON_WAKE", board_tag=_ACT_TAG)
    _net(d, "AON_EN_GATE").connect(d_aon1.pin("A"))
    _net(d, "JUMP_WAKE_K").connect(d_aon1.pin("K"))    # shared 3.3 k → JUMP_WAKE
    d_aon2 = add_bas40_02l(d, ref="D_AON_WAKE2", board_tag=_ACT_TAG)
    _net(d, "AON_EN_GATE").connect(d_aon2.pin("A"))
    _net(d, "MAG_SHELF_K").connect(d_aon2.pin("K"))    # TMR shelf-wake leg (twin-OR rule)
    q_usbwk2 = add_ssm3k35ctc_l3f(d, ref="Q_USB_WAKE2", board_tag=_ACT_TAG)
    _net(d, "AON_EN_GATE").connect(q_usbwk2.pin("3"))  # Drain
    _net(d, "GND")        .connect(q_usbwk2.pin("2"))  # Source
    _net(d, "USBWK_GATE") .connect(q_usbwk2.pin("1"))  # Gate ← shared VBUS divider

    # WLE5 + dedicated nano-LDO + 12-ball bypass network removed.
    # WBA55 replaces the wake orchestrator + 2.4 GHz radio role (added
    # below by task #7); it runs directly from the 3V3 rail (no dedicated
    # LDO needed). MP25 M33 recovery via BLE OTA — no more WLE5↔H562 strap
    # resistors. The wake nets MAG_WAKE_N + IR_WAKE terminate at the WBA55
    # additions below (H3LIS_* moved to the M33 with the IR-wake change);
    # its LPUART1 now goes to the
    # MP25 M33 root (WBA_UART_*) instead of the removed CAN bridge.

    # AON load-switch REMOVED (QAON / QAON_EN PMOS+NMOS + R_AON_PU /
    # R_AON_EN_PD / C_AON1 / C_AON2). It gated the G0B1+TCAN CAN bridge (now
    # deleted) and the H3LIS accel off in shelf; with the bridge gone the only
    # consumer was the µA-class accel, which simply runs from 3V3 now. The
    # AON_EN GPIO on the WBA55 is freed.

    # ── STM32WBA55UGI7 wake orchestrator + BLE 2.4 GHz radio ───────────
    # UFBGA59 (was WLCSP41 HGF6TR; pin comments below still carry some
    # WLCSP41 ball names). DS14127. Consolidated roles:
    #   - Wake orchestrator (RTC + EXTI from MAG_WAKE_N and IR_WAKE)
    #   - Optical service link (2026-07-27): IR_WAKE RX (PA12) + IR_TX
    #     keying (PA6). Standby is
    #     RF-SILENT — no standing BLE advertising; an IR/NFC
    #     interrogation wakes the WBA, which brings BLE up for a
    #     bounded session (IR-initiated BLE), then goes dark again.
    #   - BLE, GROUND-ONLY (programming / activation_unlock) on its own
    #     sleeve slot S3 (2026-11-17; the Yagi pair is long gone)
    #   - Host of the LR2021 long-range radio on this board (SPI1)
    #   - MAIN_SW_GATE driver (flight-rail PMOS gate)
    #   - SPI3 HCI link to the MP25 application processor (SPI1 is the
    #     LR2021's)
    #   - LPUART1 → MP25 M33 root (firmware bootloader + console — replaces the
    #     old G0B1/CAN bridge; WBA55 has no FDCAN, but UART to the root needs
    #     no transceiver)
    #   - I²C1 on the shared I2C2_* bus (mag / PMIC / TMP117; the MP25
    #     is the other master — the ST25DV left with the NFC removal)
    #   - S1 antenna tuner (2 × PE64906 DTC, 2026-11-17): PA7 SCL, PA8 SDA,
    #     PA9 SEN1, PC15 SEN2 (bit-banged 3-wire)
    #   - S4 transverter control (2026-11-18): PB14/PA10/PB11 ADF4351
    #     LE/CE/MUXOUT, PA11 mixer EN, PB6 LNA EN, PB7 PA boost EN.
    #     Spare after that: PC13 only
    # Lives directly on the always-on 3V3 rail (no dedicated nano-LDO).
    # 32 MHz HSE via MEMS resonator (survives rapid deceleration); LSE = internal LSI
    # which frees PC14/PC15 as plain spare GPIOs.
    # Mandatory: die-area underfill (Hysol FP4549) — captured on the
    # Chip record; an assembly-process validator enforces it.
    wba = add_stm32wba55ugi7(d, ref="U_WBA", board_tag=BTAG)

    # Power pins — all VDD variants → 3V3_AON (the nanopower standby
    # domain: the WBA must run in Standby with the eFuse + main path
    # OFF), VSS → GND.
    _net(d, "3V3_AON").connect(wba.pin("VDDA"))      # E12 — analog
    _net(d, "3V3_AON").connect(wba.pin("VDD_ANA"))   # B5  — analog (VDDANA)
    _net(d, "3V3_AON").connect(wba.pin("VDD_1"))     # A10 — digital
    _net(d, "3V3_AON").connect(wba.pin("VDD_2"))     # G4
    _net(d, "3V3_AON").connect(wba.pin("VDDRF"))     # A6  — radio digital
    _net(d, "3V3_AON").connect(wba.pin("VDD_RFPA"))  #  — radio PA (needs ≥2.5 V for +9.5 dBm)
    # (2026-11-21) VDDHPA is NOT a supply input: "provided to connect an
    # external decoupling capacitor" (typ 470 nF) — DS p.28. Was on 3V3_AON.
    _net(d, "WBA_VDDHPA").connect(wba.pin("VDD_HPA"))  # B4
    cap_to_gnd(d, "WBA_VDDHPA", "470nF", ref="C_WBA_VDDHPA", board_tag=BTAG,
               pin=wba.pin("VDD_HPA"))
    _net(d, "GND").connect(wba.pin("VSS_1"))     # B9
    _net(d, "GND").connect(wba.pin("VSS_2"))     # G6
    _net(d, "GND").connect(wba.pin("VSSA"))      # D13
    _net(d, "GND").connect(wba.pin("VSSRF_1"))   # D1
    _net(d, "GND").connect(wba.pin("VSSRF_2"))   # D3
    # UFBGA59 extras: VDD_3/4, VSS_3/4 (no VSSRF_3 on this package).
    _net(d, "3V3_AON").connect(wba.pin("VDD_3"))
    _net(d, "3V3_AON").connect(wba.pin("VDD_4"))
    _net(d, "GND").connect(wba.pin("VSS_3"))
    _net(d, "GND").connect(wba.pin("VSS_4"))

    # SMPS step-down for digital core (cuts Run current by ~30 % vs LDO
    # mode). Reference network from RM0497 §6.10: VDDSMPS = 3V3 input,
    # VLXSMPS through 2.2 µH inductor + 2.2 µF cap → VDD11 (regulated
    # ~1.1 V core supply). VSSSMPS is the low-noise SMPS ground return.
    _net(d, "3V3_AON")        .connect(wba.pin("VDD_SMPS"))   # B13
    _net(d, "GND")        .connect(wba.pin("VSS_SMPS"))   # A12
    _net(d, "WBA_VLX")    .connect(wba.pin("VLX_SMPS"))   # C12
    _net(d, "WBA_VDD11")  .connect(wba.pin("VDD11"))      # B11
    ind_between(d, "WBA_VLX", "WBA_VDD11", "2.2uH",
                ref="L_WBA_SMPS", board_tag=BTAG)
    cap_to_gnd(d, "WBA_VDD11", "2.2uF",
               ref="C_WBA_VDD11", board_tag=BTAG,
               **_as_built_0402("2.2uF", "X5R"), pin=wba.pin("VDD11"))

    # VDD decoupling — one 100 nF per pin + bulk. The embedded plane
    # absorbs the per-pin caps; the bulk stays discrete for ESR.
    for tag, vdd_pin in (("VDDA", "VDDA"), ("VDDANA", "VDD_ANA"),
                         ("VDD1", "VDD_1"), ("VDD2", "VDD_2"),
                         ("VDD3", "VDD_3"), ("VDD4", "VDD_4"),
                         ("VDDRF", "VDDRF"), ("VDDRFPA", "VDD_RFPA"),
                         ("VDDSMPS", "VDD_SMPS")):
        cap_to_gnd(d, "3V3_AON", "100nF", ref=f"C_WBA_{tag}",
                   embedded_cap_absorbs=True, board_tag=BTAG,
                   pin=wba.pin(vdd_pin))
    cap_to_gnd(d, "3V3_AON", "4.7uF", ref="C_WBA_BULK", board_tag=BTAG, pin=(wba.ref, None))

    # NRST network — 10 kΩ pull-up + 100 nF to GND (RM0497 §6.3.5).
    _net(d, "WBA_NRST").connect(wba.pin("NRST"))   # E2
    res_between(d, "3V3_AON", "WBA_NRST", "10k",
                ref="R_WBA_NRST", board_tag=BTAG)
    cap_to_gnd(d, "WBA_NRST", "100nF",
               ref="C_WBA_NRST", board_tag=BTAG, pin=wba.pin("NRST"))
    # MP25 → WBA reset, open-drain via NFET (rule-sweep F1 fix): PB3 is
    # a TT pin clamped to VDDIO4/COMP_3V3, so a direct tie onto this
    # 3V3_AON-pulled net back-fed ~280 µA through the dead MP25 every
    # standby second. Gate has no clamp; the 100 k pull-down keeps the
    # FET off while PB3 floats (standby, MP25 POR). FIRMWARE: PB3 HIGH
    # = reset WBA (inverted vs the old direct tie); with WBA_BOOT0
    # (PI10) high first this enters the ROM bootloader for the post-pot
    # reflash over the UART/HCI link (initial load stays SWD-on-pogos).
    # feature="bottom": on the top (power-facing) face the SOT-23 threw
    # WBA_UART_*/WBA_RST_CMD off the tight wakeup↔power lands.
    q_wbarst = add_ssm3k35ctc_l3f(d, ref="Q_WBA_RST", board_tag=BTAG,
                              feature="bottom")
    _net(d, "WBA_NRST")   .connect(q_wbarst.pin("3"))   # Drain
    _net(d, "GND")        .connect(q_wbarst.pin("2"))   # Source
    _net(d, "WBA_RST_CMD").connect(q_wbarst.pin("1"))   # Gate ← MP25 PB3
    res_between(d, "WBA_RST_CMD", "GND", "100k",
                ref="R_WBARST_PD", board_tag=BTAG)

    # BOOT0 — pull-down for normal flash boot. (Recovery uses BLE OTA.)
    _net(d, "WBA_BOOT0").connect(wba.pin("PH3__BOOT0"))
    res_between(d, "WBA_BOOT0", "GND", "10k",
                ref="R_WBA_BOOT0", board_tag=BTAG)

    # 32 MHz HSE — MEMS clipped-sine clock into OSC_IN. OSC_OUT NC
    # (HSEBYP=1 in RCC_CR; no crystal feedback path).
    hse_osc = add_dsc1001ci5_032_0000(d, ref="Y_WBA_HSE", board_tag=BTAG)
    _net(d, "3V3_AON")    .connect(hse_osc.pin("1"))  # STANDBY# tied VDD
    _net(d, "GND")        .connect(hse_osc.pin("2"))
    _net(d, "WBA_HSE_OSC").connect(hse_osc.pin("3"))  # OUT (3.3 V CMOS)
    _net(d, "3V3_AON")    .connect(hse_osc.pin("4"))  # VDD
    # (2026-11-21) HSE32 bypass input wants 0–0.9 V, 200–900 mVpp, AC coupling
    # 470 pF–100 nF (DS Table 61); the DSC1001 wants a load R > 10 kΩ, C ≤ 15 pF.
    # → COMPENSATED divider (R_top·C_top = R_bot·C_bot: flat attenuation)
    # 10 k ∥ 3.3 pF over 2.2 k ∥ 10 pF ≈ 0.6 Vpp, load ≈ 12 kΩ / 2.7 pF,
    # then 470 pF into OSC_IN.
    def _c0g_between(n1, n2, val, ref):
        c = add_capacitor_c0g_0603_avx_sqcs(d, ref=ref, value=val, board_tag=BTAG,
                                            **_as_built_0402(val, "C0G/NP0"))
        _net(d, n1).connect(c.pin("1")); _net(d, n2).connect(c.pin("2"))
    res_between(d, "WBA_HSE_OSC", "WBA_HSE_DIV", "10k", ref="R_WBA_HSE_TOP", board_tag=BTAG)
    _c0g_between("WBA_HSE_OSC", "WBA_HSE_DIV", "3.3pF", "C_WBA_HSE_TOP")
    res_between(d, "WBA_HSE_DIV", "GND", "2.2k", ref="R_WBA_HSE_BOT", board_tag=BTAG)
    cap_to_gnd(d, "WBA_HSE_DIV", "10pF", ref="C_WBA_HSE_BOT", board_tag=BTAG, force_c0g=True)
    _c0g_between("WBA_HSE_DIV", "WBA_HSE_IN", "470pF", "C_WBA_HSE_CPL")
    _net(d, "WBA_HSE_IN") .connect(wba.pin("OSC_IN"))   # A8
    cap_to_gnd(d, "3V3_AON", "100nF", ref="C_WBA_HSE_VDD",
               embedded_cap_absorbs=True, board_tag=BTAG, pin=hse_osc.pin("4"))
    # LSE = internal LSI (±5 %); PC14/PC15 reused as GPIOs.

    # SWD debug
    _net(d, "WBA_SWDIO").connect(wba.pin("PA13"))  # E8 — JTMS/SWDIO
    _net(d, "WBA_SWCLK").connect(wba.pin("PA14"))  # F1 — JTCK/SWCLK

    # LPUART1 ↔ MP25 M33 UART (firmware bootloader host + console). Was the
    # G0B1/CAN bridge link; now a direct UART to the MP25 M33 root — the
    # bridge MCU + transceiver are gone (WBA55 has no FDCAN, so CAN required a
    # whole bridge; UART to the root needs none). PA2=TX, PA1=RX (Table 24).
    _net(d, "WBA_UART_TX") .connect(wba.pin("PA2"))   # F11 — LPUART1_TX → MP25 M33 RX
    _net(d, "WBA_UART_RX") .connect(wba.pin("PA1"))   # E10 — LPUART1_RX ← MP25 M33 TX

    # I²C1 → ST25DV. PA15=I2C1_SCL, PB3=I2C1_SDA (only SDA option in
    # WLCSP41). The ST25DV block above keeps the legacy I2C2_SCL/SDA
    # net names — wiring stable across the chip swap.
    # 2026-11-15: moved PA15/PB3 → PB2/PB1 (I2C1 AF4 on UFBGA59) to free
    # SPI1 (PB4/PB3/PA15) for the LR2021 on fin_ble.
    _net(d, "I2C2_SCL").connect(wba.pin("PB2"))   # I2C1_SCL (AF4)
    _net(d, "I2C2_SDA").connect(wba.pin("PB1"))   # I2C1_SDA (AF4)

    # SPI1 + control → LR2021 on this board (local since 2026-11-16). AFs per
    # DS14127 Table 25 (SPI1 exists only on PB4/PB3/PA15/PA12; NSS is a
    # software GPIO so PA12 stays IR_WAKE).
    _net(d, "LR_SPI_SCK") .connect(wba.pin("PB4"))   # SPI1_SCK  (AF5)
    _net(d, "LR_SPI_MISO").connect(wba.pin("PB3"))   # SPI1_MISO (AF5)
    _net(d, "LR_SPI_MOSI").connect(wba.pin("PA15"))  # SPI1_MOSI (AF5)
    _net(d, "LR_NSS")     .connect(wba.pin("PA4"))   # GPIO (software NSS)
    _net(d, "LR_BUSY")    .connect(wba.pin("PB0"))   # GPIO in
    _net(d, "LR_IRQ")     .connect(wba.pin("PB13"))  # EXTI13 ← LR2021 DIO7
    _net(d, "LR_NRESET")  .connect(wba.pin("PA3"))   # GPIO out
    # S1 tuner DTCs (U_LR_DTC1/2, on 3V3 like the LR2021 — hold these low
    # while 3V3 is off). Bit-banged, ≥ 38.4 ns SCL period.
    _net(d, "LR_DTC_SCL") .connect(wba.pin("PA7"))
    _net(d, "LR_DTC_SDA") .connect(wba.pin("PA8"))
    _net(d, "LR_DTC_SEN1").connect(wba.pin("PA9"))
    _net(d, "LR_DTC_SEN2").connect(wba.pin("PC15__OSC32__OUT"))  # low-drive pin: fine for a latch line
    # S4 transverter (2026-11-18, _build_transverter) on spare UFBGA59 GPIO —
    # all on 3V3 parts: hold LOW / Hi-Z while 3V3 is off. LO SPI CLK/DATA
    # share LR_DTC_SCL/SDA above; the T/R and IF switches run off LR2021 DIOs.
    _net(d, "XV_LO_LE")   .connect(wba.pin("PB14"))   # ADF4351 LE
    _net(d, "XV_LO_CE")   .connect(wba.pin("PA10"))   # ADF4351 CE (100 k pull-down)
    _net(d, "XV_LO_MUX")  .connect(wba.pin("PB11"))   # ADF4351 MUXOUT (lock detect / readback) in
    _net(d, "XV_MIX_EN")  .connect(wba.pin("PA11"))   # LTC5549 EN
    _net(d, "XV_LNA_EN")  .connect(wba.pin("PB6"))    # GRF2073W VENABLE
    _net(d, "XV_PA_EN")   .connect(wba.pin("PB7"))    # MCP1640D EN → XV_5V → GRF5126

    # PA6/PA7 (freed by the H3LIS→M33 move) re-tasked for the optical
    # service link (2026-07-27):
    # IR_TX → the D_IR_TX gate on radar_module (3 joints; drive loop is
    # tile-local at the nose — see the radar builder). Bit-banged OOK
    # from Run, or hardware-timer subcarrier if PA6 has a TIM AF on
    # WLCSP41 (check DS14403 at bring-up — not blocking, kbps needs none).
    _net(d, "IR_TX").connect(wba.pin("PA6"))        # D9
    # (ST25DV session-power role deleted with the NFC removal 2026-07-30.)
    # (PA7 freed 2026-07-30 — ST25DV session-VCC gate left with the NFC removal.)

    # SPI3 HCI link to MP25 (SPI1 unusable — see header comment).
    _net(d, "WBA_HCI_SCK") .connect(wba.pin("PA0"))   # G12 — SPI3_SCK
    _net(d, "WBA_HCI_MISO").connect(wba.pin("PB9"))   # F9  — SPI3_MISO
    _net(d, "WBA_HCI_MOSI").connect(wba.pin("PB8"))   # G10 — SPI3_MOSI
    _net(d, "WBA_HCI_NSS") .connect(wba.pin("PA5"))   # F13 — SPI3_NSS
    _net(d, "WBA_HCI_IRQ") .connect(wba.pin("PB12"))  # C10 — host-wake GPIO

    # EXTI wake inputs
    # (PA8/EXTI8 freed 2026-07-30 — the NFC GPO left with the NFC removal.)
    # MAG_WAKE_N ← U_MAG_WAKE DRV5032FC Hall (open-drain, 1 M to 3V3_AON;
    # see the magnetic-wake block). Standby listener for the coded magnetic
    # pattern — any EXTI-capable GPIO wakes the WBA from Stop1, same
    # mechanism as the IR photodiode on EXTI12. PC14 was the freed
    # OSC32 spare (LSE = internal LSI); PC15 is the tuner's SEN2.
    _net(d, "MAG_WAKE_N").connect(wba.pin("PC14__OSC32__IN"))  # EXTI wake

    # IR_WAKE ← D_IR_WAKE photodiode cathode on radar_module (see the
    # radar builder for the full rationale). Bias + filter live HERE, next
    # to the WBA: 470 k pull-up to 3V3_AON (the wake threshold), 10 nF to
    # GND (τ ≈ 4.7 ms with the pull-up — EMI/debounce for the 3-joint
    # backbone run past the DDR/radar switching). The cap is a REAL
    # discrete on a private high-Z node — never ECM-absorbed (same rule
    # as the mag's C1 reservoir). EXTI12 is free: PB12 (shared line
    # number) is an output (HCI IRQ to the MP25).
    res_between(d, "3V3_AON", "IR_WAKE", "470k",
                ref="RPU_IR_WAKE", board_tag=BTAG)
    cap_to_gnd(d, "IR_WAKE", "10nF", ref="C_IR_WAKE", board_tag=BTAG, pin=wba.pin("PA12"))
    _net(d, "IR_WAKE").connect(wba.pin("PA12"))   # E6 — EXTI12, falling edge

    _net(d, "WBA_WAKE").connect(wba.pin("PB5"))   # GPIO, push high to hold (was PB4 → SPI1_SCK)
    # AON hold — PB15 (poetically, the old AON_GATED enable pin) pushes
    # HIGH into the TPS7A02's EN through 1 k: holds the 3V3_AON domain
    # (= the WBA's own life support) after the NFC tap ends. Releasing
    # it (with PB4 already low) drops the round to TRUE shelf.
    _net(d, "WBA_AON_HOLD").connect(wba.pin("PB15"))   # E4 — push high to hold AON
    res_between(d, "WBA_AON_HOLD", "AON_EN", "1k",
                ref="RHOLD_AON", board_tag=BTAG)

    # Antenna pin → π-match → BLE_RF → DC block → owner switch → slot S1 (_build_lr_radio).
    _net(d, "WBA_RF").connect(wba.pin("RF"))  # C2

    # ── WBA55 RF chain — π-match → BLE_RF → shared slot S1 (owner switch) ──
    # (2026-11-17) BLE is GROUND-ONLY (programming / activation_unlock) and
    # has its own sleeve slot S3 (2.40-2.48 GHz); no owner switch, no FEM.
    # BLE_RF → C_BLE_DCBLK → U_ANTSW_S1 → ANT_HF_S1 is built in _build_lr_radio.
    #
    # π-match L + 2 shunt C. Values are placeholders; topology is locked.
    # `feature="rf"` keeps these on the top face (face_split's ECM-embedding
    # rule normally sweeps 0402/0603 passives to the bottom).
    ind_between(d, "WBA_RF", "BLE_RF", "2.7nH",
                ref="L_WBA_PI", board_tag=BTAG, feature="rf")
    cap_to_gnd(d, "WBA_RF",   "0.5pF", ref="C_WBA_PI1",
               board_tag=BTAG, feature="rf",
               **_as_built_0402("0.5pF", "C0G/NP0"), pin=wba.pin("RF"))
    cap_to_gnd(d, "BLE_RF", "0.5pF", ref="C_WBA_PI2",
               board_tag=BTAG, feature="rf",
               **_as_built_0402("0.5pF", "C0G/NP0"))   # (2026-11-22) obsolete SQCS 0603 → GJM1555 0402

    # ── LR2021 long-range radio — on THIS board, top face beside the WBA RF
    # (2026-11-16): host lines and BLE_RF are local; only the two antenna
    # feeds (S1, S3) leave (castellations in the antenna sector).
    # The magnetometer sits on the opposite (bottom) face, away from the PA bursts.
    _build_lr_radio(d, BTAG, face="rf")
    # S4 transverter, 4.4-5.0 GHz (2026-11-18): IF from U_LR_IFSW.
    _build_transverter(d, BTAG, face="rf")

    # WLE5 LSE oscillator removed — WBA55 uses internal LSI (±5 %); LSE
    # crystal not needed for periodic BLE-scan timing accuracy.

    # WLE5 reset / BOOT0 / RF pi-network / test point all removed.

    # MT29F NAND removed (higher comms speeds eliminate OTA buffering).

    # G0B1 + TCAN1042 CAN bridge REMOVED. It existed only to put the WBA55
    # (which has no FDCAN peripheral) onto the CAN bus — an entire bridge MCU
    # + transceiver. With CAN gone, the WBA55 talks to the MP25 M33 root directly
    # over LPUART1 (firmware + console, wired above) and rides SYS_I2C for
    # runtime telemetry. This deletes U_G0B1 + U_TCAN + their decoupling /
    # reset network, and frees the AON_GATED rail (now only the accel — see
    # the power-simplification pass).

    # BGS12 SP2T LoRa diversity switch removed. Its BGS12 successor (the
    # nose-chip-antenna vs Yagi-pair SPDT off the WBA55 antenna pin) is
    # gone too — see the RF-chain comment above.

    # Flight-rail HOLD — via a dedicated low-side FET (QHOLD2), the same
    # pattern as the MP25's PWR_HOLD/QHOLD. The old bare 10 k from PB4 to
    # MAIN_SW_GATE defeated TRUE shelf: with the WBA unpowered, the gate
    # node (at BAT_PROT through the 1 MΩ pull-up) leaked into the dead
    # PB4 — sub-µA of unpowered-pin leakage × 1 MΩ sags the gate ~1 V,
    # enough to half-enhance QMAIN (V_th(max) −0.95 V). A FET hold has no
    # path when its driver is dead (the 100 k gate pull-down keeps it
    # off). ⚠ FIRMWARE: hold polarity INVERTED vs the old wiring — the
    # WBA now drives PB4 HIGH to hold power (was: low/open-drain-low).
    qhold2 = add_ssm3k35ctc_l3f(d, ref="QHOLD2", board_tag=BTAG)
    _net(d, "MAIN_SW_GATE").connect(qhold2.pin("3"))   # Drain
    _net(d, "GND")         .connect(qhold2.pin("2"))   # Source
    _net(d, "QHOLD2_GATE") .connect(qhold2.pin("1"))   # Gate
    res_between(d, "WBA_WAKE",    "QHOLD2_GATE", "100",
                ref="RHOLD2_G",  board_tag=BTAG)
    res_between(d, "QHOLD2_GATE", "GND",         "100k",
                ref="RHOLD2_PD", board_tag=BTAG)

    # ── add_h3lis_accel — H3LIS331DL ±400g, back on the MAIN 3V3 rail ──
    # Wired per ST datasheet DocID13335 LGA-16 pinout. IR-wake change
    # (2026-07): the accel left the 3V3_AON domain — its Standby
    # motion-detect role (10 µA, the old Standby→staged trigger) is
    # replaced by the D_IR_WAKE photodiode on the radar tile, so it now
    # powers up with the main rail at Ready (the merged staged state) and keeps only its
    # launch-witness + flight-recorder roles (quantitative ±400 g beside
    # the piezo's fast edge; the ±16 g ISM330s saturate under rapid deceleration).
    # I²C moved WBA→M33 with the rail: it joins the M33's I2C3 bus
    # (addr 0x18 — no clash with IMU2/IMU3 at 0x6A/0x6B; bus pull-ups
    # RPU_I2C3_* to 3V3 already exist on wakeup_board, so the dedicated
    # RPU_HACC_* pair is gone). Unpowered-on-dead-bus is the same
    # pattern as every 3V3 sensor in Standby. INT1 → M33 PD10 EXTI.
    # board_tag=fin_ble_board (2026-11-17, user: activation_interface's top
    # was too busy; was activation_interface): the H3LIS331 ±400g high-G
    # accel keeps its locked 1.41 mm spin-axis offset, now on fin_ble's TOP
    # face (its bottom centre is U_G0B1_FIN). Every one of its signals goes
    # UP (I2C3 → fin_ble/wakeup/compute, INT1 → the M33), so the move takes
    # 3 lanes out of the activation↔fin_ble gap.
    _HACC_TAG = "activation_interface"   # (2026-11-21) was fin_ble_board (merged)
    acc = add_h3lis331dltr(d, ref="U_HACC", board_tag=_HACC_TAG)
    _net(d, "3V3")       .connect(acc.pin("VDD_IO"))   # 1
    # 2, 3 = NC_1, NC_2 → leave floating per datasheet
    _net(d, "I2C3_SCL")  .connect(acc.pin("SCL"))      # 4
    _net(d, "GND")       .connect(acc.pin("GND_1"))    # 5
    _net(d, "I2C3_SDA")  .connect(acc.pin("SDA"))      # 6
    _net(d, "GND")       .connect(acc.pin("SDO"))      # 7 SDO/SA0 → addr 0x18
    _net(d, "3V3")       .connect(acc.pin("CS"))       # 8 CS high → I2C mode
    # INT2 (pin 9) is a logic OUTPUT — leave floating per datasheet.
    # Tying to GND would short the driver when firmware enables it.
    # Firmware masks INT2 via INT_CFG register (CTRL_REG3 = 0).
    _net(d, "GND")       .connect(acc.pin("RESERVED_1"))  # 10 — DS9012 Tab 1: connect to GND
    _net(d, "H3LIS_INT1").connect(acc.pin("INT1"))     # 11
    _net(d, "GND")       .connect(acc.pin("GND_2"))    # 12
    _net(d, "GND")       .connect(acc.pin("GND_3"))    # 13
    _net(d, "3V3")       .connect(acc.pin("VDD"))      # 14
    _net(d, "3V3")       .connect(acc.pin("RESERVED_2"))  # 15 — DS9012 Tab 1: connect to Vdd (NOT GND — the two reserved straps differ)
    _net(d, "GND")       .connect(acc.pin("GND_4"))    # 16
    # DS9012 §"Application hints": 100 nF ceramic + 10 µF bulk at pin 14
    cap_to_gnd(d, "3V3", "100nF", ref="C_HACC1",
               embedded_cap_absorbs=True, board_tag=_HACC_TAG, pin=acc.pin("VDD"))
    cap_to_gnd(d, "3V3", "10uF",  ref="C_HACC2", board_tag=_HACC_TAG, pin=acc.pin("VDD"))

    # ── 3 test points post-build (per system.py wakeup_board block end) ──
    tp_bat = _add_testpoint(d, ref="TP_BAT", board_tag=BTAG)
    tp_3v3 = _add_testpoint(d, ref="TP_3V3", board_tag=BTAG)
    tp_gnd = _add_testpoint(d, ref="TP_GND", board_tag=BTAG)
    _net(d, "BAT_PROT").connect(tp_bat.pin("1"))
    _net(d, "3V3")     .connect(tp_3v3.pin("1"))
    _net(d, "GND")     .connect(tp_gnd.pin("1"))


# ── main ──────────────────────────────────────────────────────────────────

def _prime_power_rails(d: Design) -> None:
    """Pre-create every known power + ground net + clock net up-front
    so the smash-side wiring helpers (cap_to_gnd / res_between /
    ind_between in `smash.netlist`) find them via
    `design.net_by_name(...)` and don't accidentally re-create them as
    `kind="signal"` later via `design.connect(name)`. Mirrors the
    `_AUTO_POWER_RAILS` map but eager — guarantees pin/net-kind
    validators see consistent kinds for every connection."""
    for name, v in _AUTO_POWER_RAILS.items():
        _net(d, name, kind="power", voltage_v=v)
    # ── absorbed flight sensors (wakeup+flight consolidation) ────────
    # The IMU/mag cluster folds onto this tile — each aft tile had only a few
    # chips left after flight control moved onto the MP25 M33. build_flight_board
    # tags the sensors board_tag="wakeup_board"; its TCAN (activation_interface)
    # and QPD TIAs (qpd_module) keep their own tags. Sensor INT/I2C nets that used
    # to cross the wakeup↔flight gap are now local to this tile.
    build_flight_board(d, board_tag="wakeup_board", imu_tag="activation_interface")

    for name in _AUTO_GROUND_NETS:
        _net(d, name, kind="ground")
    # Clock nets — frequencies sourced from the oscillator datasheets
    # and cross-validated against MCU clock-input ranges by the
    # `_v_clock_pin_frequency` validator.
    d.add_clock_net("HSE_IN",       frequency_hz=8_000_000)   # legacy / unused (orphaned — H562 retired)
    d.add_clock_net("LSE_IN",       frequency_hz=32_768)      # legacy / unused (orphaned — H562 retired)
    d.add_clock_net("WBA_HSE_IN",   frequency_hz=32_000_000)  # DSC1001 32 MHz → WBA55 OSC_IN
    d.add_clock_net("COMP_HSE_IN",  frequency_hz=40_000_000)  # DSC1001 40 MHz → MP25 OSC_IN (HSE)
    d.add_clock_net("COMP_LSE_IN",  frequency_hz=32_768)      # SiT1630 32.768 kHz → MP25 OSC32_IN (LSE)


# ── board configurations ───────────────────────────────────────────────
# Each named configuration is a subset of the snake, listed in fold order.
# `build_config_panel` folds just those boards (+ inline spacers) and we
# export one <config>.kicad_pcb per entry. To add a config, list its
# board tags here; the builder for each must exist in _BOARD_BUILDERS.
_BOARD_BUILDERS = {
    "power_board":          lambda d: build_power_board(d),
    "wakeup_board":         lambda d: build_wakeup_board(d),  # IMU/mag sensors folded in
    "radar_module":         lambda d: (build_radar_module_awr1843aop(d),
                                       build_radar_nose_io(d)),
    "usb_nose":             lambda d: build_usb_nose(d),
    "companion_compute":    lambda d: build_companion_compute(d),
    "aft_end_board":        lambda d: build_aft_end_board(d),
    "cell_floor_board":     lambda d: build_cell_floor_board(d),
    "activation_interface": lambda d: (build_activation_interface(d),
                                       build_fins_module(d)),   # fin_ble merged in (2026-11-21)
    "camera_module":        lambda d: build_camera_module(d),
    "qpd_module":           lambda d: build_qpd_module(d),
}

# Snake fold order (rigid boards). A config's snake is this list filtered
# to the boards it contains; the fold solver compacts whatever remains.
# Post-consolidation the MP25 (companion_compute) is the single hub. wakeup_board
# carries the flight IMU/mag sensors (the two thin aft tiles merged) AND the
# WBA55 (back 2026-07-31 — wake/activation_unlock consolidation; core_radar dropped
# fin_ble_board at the time), so wakeup→hub carries the WBA (~9 nets) + sensor
# I2C/ADC/INT (~17) traffic; the fin actuators + the piezo launch cluster
# sit one tile aft on fin_ble_board (2026-07-30 crowding split; the piezo
# came in the 2026-07-31 stack reorder that made the tile the battery
# ceiling) whose →hub run is the fin SYS_SPI (~5) + COMP_OUT, and whose
# AFT side feeds the battery column (BAT_CELL*_POS from the + contact
# lands). compute sits adjacent to its two heaviest peers — power_board
# (the STPMIC25 COMP_* rails) and radar_module (the RGMII bus); the adaptive
# land densify widens the aft→hub runs across the intervening gaps as needed.
_MASTER_SNAKE = [
    "aft_end_board", "activation_interface",
    "wakeup_board", "power_board", "companion_compute",
    "radar_module",
]
# Branch tiles → (parent board, flex length mm, branch_side, s_fold).
# branch_side is "N" / "S" / "W" / "E" / None (None = inherit the panel-default).
# E/W are only free on the snake's END tiles (the root's west edge, the tail's
# east edge — mid-tiles use E/W for the snake), so they give an end-tile branch
# its own meridian. s_fold=False (Yagi tiles) means the leaf sits DIRECTLY
# perpendicular to the snake; s_fold=True tucks it alongside the snake flex.
_BRANCH_PARENT = {
    # qpd N / camera S in EVERY build (matching the maximalist panel,
    # where both coexist): the companion's flex-launch strips must sit
    # at the SAME spot in every config so the board routes ONCE — a
    # per-config side flip would move the strip and fork the layout.
    "qpd_module":       ("companion_compute", 70.0, "N", False),
    "camera_module":    ("companion_compute", 70.0, "S", False),  # mutually excl.
    # (2026-11-18) USB nose: a nose module like qpd / camera. In a config its
    # parent compute is the snake's tail, so its EAST edge is free.
    "usb_nose":         ("companion_compute", 70.0, "E", False),
}

# Branch-flex launch CONTRACT — the fixed companion-side interface
# (strip side + alphabetical net order = pad order) carried by
# companion_compute in EVERY config, leaf present or not (an
# unpopulated "connector" at the flex mouth — the whole point is that
# the companion layout never changes between configs). Sides must
# match _BRANCH_PARENT + the maximalist build_panel declarations; the
# net list is validated against the live census whenever the leaf IS
# in the build, so a leaf-builder net change breaks generation loudly
# instead of silently moving pads.
# (2026-11-15) The QPD / camera flex leaves are replaced by LDS traces on a
# custom nose cone; the sensors stay PCBs. Their links leave the parent via
# castellations — same net lists as the old launch contract.
def _cone_exits():
    return [(p, leaf, nets) for p, leaf, _side, nets in _FLEX_LAUNCH_CATALOG]


_FLEX_LAUNCH_CATALOG = [
    ("companion_compute", "qpd_module", "N",
     ["3V3", "FLEX_GND", "QPD_TIA_A", "QPD_TIA_B", "QPD_TIA_C",
      "QPD_TIA_D", "BAT_PROT", "IR_TX", "IR_WAKE"]),
    ("companion_compute", "camera_module", "S",
     ["CAM_CSI_CLK_N", "CAM_CSI_CLK_P", "CAM_CSI_D0_N", "CAM_CSI_D0_P",
      "CAM_CSI_D1_N", "CAM_CSI_D1_P", "CAM_EXTCLK",
      "COMP_1V8", "COMP_2V8", "FLEX_GND", "BAT_PROT", "IR_TX", "IR_WAKE"]),
    ("companion_compute", "usb_nose", "E",
     ["USB_VBUS", "USB_D_P", "USB_D_N", "BAT_PROT", "IR_TX", "IR_WAKE"]),
]

_CONE_EXITS = _cone_exits()

# Canonical order configurations, from components.md "Order
# Configurations" + the config matrix. Board names mapped to twin tags;
# power_board is present in every variant (carries the COMP rails). QPD
# Si/InGaAs are the same board, so they share one layout. Each entry is the
# full board set.
# Consolidation: the STM32MP25 is the SINGLE brain (M33 = flight controller,
# A35/NPU = perception), so companion_compute is in EVERY config — there is no
# more "with/without companion" hardware split. The flight IMU/mag sensors fold
# onto wakeup_board (the two thin aft tiles merged), so there is no separate
# flight_board tile. The fin actuators also fold onto wakeup_board (no separate
# fins_module tile — its FINBOOST 12 V boost came along), so they are carried in
# EVERY config: there is no unguided/guided split.
_CORE      = {"aft_end_board", "power_board",
              "activation_interface", "wakeup_board",
              "companion_compute"}
# fin_ble_board is in EVERY config, core_radar included (2026-07-31 user
# decision, reversing the 2026-07-30 drop: since the same-day stack reorder
# the tile is the battery-compartment CEILING — cell + contact lands — and
# hosts the piezo launch cluster, both core functions, so no config may
# lose it). core_radar still flies RF-dark: it sheds only the two Yagi
# leaves (their parent wakeup_board STAYS; no BLE session without antennas).
# The wake/activation_unlock ladder (power_states.md) is unaffected: the WBA orchestrator +
# every wake listener ride wakeup_board, and the IR service-link optics ride
# radar_module — all present in core_radar.
# (_YAGI_LEAVES removed 2026-11-14 with the Yagi tiles: the 2.4 GHz + sub-GHz
# antennas are conformal elements in the PEEK battery compartment, fed from
# fin_ble_board — a core tile — so there are no RF leaves to shed. "RF-dark"
# core_radar is now a firmware / DNP decision, not a board-set one.)
# nfc_antenna_flex REMOVED 2026-07-30 with the whole NFC subsystem (tag +
# antenna + wake legs) — wake channels are now magnetic / jumpstart / USB.
# The radar forward-end: the AWR1843AOP tile (+ its USB-C / IR nose I/O). The
# nose_cap PCB is RETIRED (2026-11-18): the nose is the closed end of the
# config's one-piece PEEK-LDS cup (smash.export.cup_noses), into which the radar
# board is fixed before the cup goes onto the tower.
_RADAR     = {"radar_module"}

# ── battery variant ──────────────────────────────────────────────────
# DEFAULT FLIPPED 2026-07-28 (battery review): ALL configs now default to the
# 3× TLM-1520HPM/S pack stood VERTICAL (375 mAh). Under the radar-idle Ready
# floor (~110 mA) the single cell cannot carry the 1 h active-operations
# requirement with useful shelf life (tools/simulate_battery_mission.py: 1 h
# to ~5 y shelf on the best single cell vs ~12 y on the pack). The old
# default — 1× TLM-1530M/S laid HORIZONTAL (15.1 mm compartment, ~15 g
# lighter) — was kept as the `core_1cell` opt-in until 2026-11-16, when it was
# DROPPED (user: there will always be 3 cells). ⚠ The TLM-1520HPM's own rapid-deceleration rating is
# NOT datasheet-confirmed (Preliminary 2016) — open Tadiran qualification item.
# BATTERY REWORK 2026-07-30: the cells are ordered with SIDE solder tabs (no
# end pins). Triple mode: the pack stands on the reinstated THIN
# cell_floor_board (6L / ~0.85 mm, NO coin — briefly deleted the same day,
# but cells directly on aft_end starved the aft LGA joint and pushed the
# comparator off the piezo's face); its − tab lands sit inside the cell bore
# circles, the + contacts ride the fin_ble_board ceiling (2026-07-31 stack
# reorder), and the tile passes the potting channels through to the thin
# aft gaps (activate boost / activate bank). The active mode is a module
# global (only "triple" since the single-cell mode was dropped 2026-11-16);
# build_power_board (tab lands), _mark_battery_pockets (cavity), the
# compartment depth, and _config_boards (cell_floor drop) all read it. Any
# code that builds a config's boards/panel (config_costs, config_heights)
# calls _set_battery_mode.
from smash.export.spacer_step import (BATT_FLOOR_MM as _BATT_FLOOR,          # noqa: E402
                                      BATT_CELL_LENGTH_MM as _BATT_CELLS,
                                      BATT_HEADROOM_MM as _BATT_HEAD)
_BATTERY_MODES = {
    # (2026-11-20) derived from the holder: 1.2 mm closed floor + 21 mm cells
    # + 1 mm headroom (Tadiran /P + pin → wire joints; was 2 mm for tabs) = 23.2
    "triple": {"compartment_mm": round(_BATT_FLOOR + _BATT_CELLS + _BATT_HEAD, 3)},
}
_BATTERY_BY_CONFIG: dict = {}   # every config = triple (core_1cell dropped 2026-11-16: always 3 cells)
_BATTERY_MODE = "triple"                          # default = maximalist 3-cell superset


def _set_battery_mode(config_name: str) -> str:
    """Select the battery variant for a config (default 'triple'). Sets the
    module global read by build_power_board + _mark_battery_pockets."""
    global _BATTERY_MODE
    _BATTERY_MODE = _BATTERY_BY_CONFIG.get(config_name, "triple")
    return _BATTERY_MODE


def _config_boards(config_name: str, board_set) -> set:
    """Boards actually built for a config (the board set itself since the
    single-cell mode, which dropped cell_floor_board, went 2026-11-16)."""
    return set(board_set)


def _compartment_mm() -> float:
    """Battery-compartment depth (mm) for the active battery mode."""
    return _BATTERY_MODES[_BATTERY_MODE]["compartment_mm"]


# Every config is "core (guided base) + ONE seeker". The seekers are MUTUALLY
# EXCLUSIVE — 77 GHz radar interferes with the optical seekers (qpd / camera), and
# qpd vs camera share the optics bay — so each config carries at most one seeker;
# there are no radar+seeker combos. fin_ble_board (fins + battery ceiling +
# piezo launch cluster) rides in EVERY config since 2026-07-31; core_radar
# is RF-dark and sheds only the two Yagi leaves (the WBA wake orchestrator
# stays, on wakeup_board, so the full power_states.md ladder works in every
# config).
CONFIGS: dict[str, set[str]] = {
    "core":         _CORE | {"usb_nose"},           # no seeker; USB nose = the cap
    "core_radar":   _CORE | _RADAR,   # RF-dark = firmware/DNP (no RF leaves since 2026-11-14)
    "core_qpd":     _CORE | {"qpd_module"},
    "core_camera":  _CORE | {"camera_module"},
    # (2026-11-16) `core_1cell` (the legacy single horizontal TLM-1530M/S)
    # dropped: every build carries the 3-cell pack.
}




# Spacers are NOT PCBs any more (2026-11-14 spacer-less potted tower with
# castellations + LDS sleeve): no per-spacer .kicad_pcb / gerbers; each gap's
# hardware (Al ring, battery ring, PEEK standoffs) is a generated STEP
# (write_gap_hardware). Flip to True only to resurrect the FR4 interposers.
_SPACERS_ARE_PCBS = False

# ── STEP export of chip-bearing PCBs (via kicad-cli) ────────────────────
# Spacers get true 4 mm bodies from cadquery (write_all_spacer_steps); the
# chip-bearing panels/configs get their 3D bodies from KiCad itself. The
# CLI is resolved once and cached; if it's missing (e.g. CI without KiCad)
# STEP export is skipped and the rest of the generation proceeds. Set
# SMASH_STEP_EXPORT=0 to skip ALL 3D STEP output — the kicad-cli tile STEPs
# AND the cadquery spacer bodies + folded-tower stackup — for fast
# netlist/panel iteration, even when kicad-cli / cadquery are present.
_STEP_ENABLED = os.environ.get("SMASH_STEP_EXPORT", "1") != "0"
# Manufacturing outputs: per-tile Gerbers + Excellon drill + one
# <tile>_gerbers.zip, plotted via kicad-cli next to each tile's
# .kicad_pcb (maximalist + every config). Independent of the STEP gate
# (a netlist-fast SMASH_STEP_EXPORT=0 run can still emit fab data);
# skipped with a note when kicad-cli is absent. SMASH_GERBER_EXPORT=0
# turns it off.
_GERBER_ENABLED = os.environ.get("SMASH_GERBER_EXPORT", "1") != "0"
# Output root is dist/. The EVB panel and the folded-tower stackup sit
# at that root; each CONFIG is a folder of per-board subdirs
# (dist/core_radar/<tile>/ with the tile .kicad_pcb + 3D models inside).
# Maximalist per-tile dumps (the union of every config) live under
# dist/maximalist/<tile>/ so they don't collide with a config's boards.
_DIST = REPO / "dist"
_PCB_OUT = _DIST
_MAXIMALIST_DIR = _DIST / "maximalist"

# The folded-tower stackup STEP (for structural FEA) is ~14 s/cadquery
# build. The full panel always emits it; per-config stackups land at
# <config>/stackup.step too by default (each config is self-contained),
# at a few minutes/regen — set SMASH_STACKUP_ALL=0 to skip them for fast
# iteration.
_STACKUP_ALL = os.environ.get("SMASH_STACKUP_ALL", "1") != "0"
# (2026-11-19, user) Only the COMPONENT stackups are reviewed: the mass-block
# FEA tower (stackup.step + stackup_no_potting.step) and the waveguide stubs
# are opt-in — SMASH_FEA_STEP=1. The tile / gap-hardware / sleeve STEPs the
# component stackups are built from are still written.
_FEA_STEP = os.environ.get("SMASH_FEA_STEP", "0") == "1"
# (2026-11-19, user) 3D-PRINT STLs (per-board split halves, consolidated_stackup.stl,
# housing.stl) are opt-in too — SMASH_PRINT_STL=1.
_PRINT_STL = os.environ.get("SMASH_PRINT_STL", "0") == "1"

# Radar (AWR1843AOP) security tier. Default OFF = the General orderable
# (AWR1843ARBGALPQ1) for prototypes/bring-up — no secure boot, easy sourcing.
# SMASH_RADAR_SECURE=1 selects the pin-identical Secure orderable
# (AWR1843ARBSALPQ1: encrypted+authenticated boot) for fielded/production units,
# REQUIRED because the radar boots from external flash. See add_awr1843aop.
_RADAR_SECURE = os.environ.get("SMASH_RADAR_SECURE", "0") == "1"

# Per-reflow board-to-board stack-assembly .kicad_pcb files (each tile/spacer
# placed as a "chip" onto the one below — for the fab's SMT board-to-board
# assembly). Opt-in via SMASH_GEN_ASSEMBLIES=1; written per config under
# dist/assembly/<config>/.
_GEN_ASSEMBLIES = os.environ.get("SMASH_GEN_ASSEMBLIES", "0") == "1"
_ASSEMBLY_DIR = _DIST / "assembly"

# Lay the snake out as one straight East row (no box-minimising planner);
# deploy branches peel off their parent board's south edge with an
# S-turn instead of claiming a grid cell. Now the default — the
# box-minimising fold solver was folding deploy branches into the wrong
# axial slots and crossing flex links over rigid neighbours; the
# straight-line variant is geometrically what the snake actually wants
# and matches how the prior `evb_2x.py` reference EVB was laid out.
# Set SMASH_STRAIGHT_SNAKE=0 to opt back into the box-minimising planner.
_STRAIGHT_SNAKE = os.environ.get("SMASH_STRAIGHT_SNAKE", "1") == "1"


def _export_stackup(design, boards, snake_chain, out_path, tiles=None,
                    contract=None) -> str:
    """Best-effort folded-tower assembly STEP for FEA. Writes the potted
    tower (`stackup.step`) and a bare-FR4 sibling without the potting
    body (`stackup_no_potting.step`). `tiles` (grid positions) lets the
    assembler apply each tile's accordion fold pose so cavities land under
    their chips. Never raises."""
    out_path = pathlib.Path(out_path)
    nopot_path = out_path.with_name(out_path.stem + "_no_potting.step")
    try:
        r = write_stackup_step(design, boards, snake_chain, out_path,
                               tiles=tiles, sleeve_contract=contract)
        write_stackup_step(design, boards, snake_chain, nopot_path,
                           with_potting=False, tiles=tiles,
                           sleeve_contract=contract)
    except ImportError:
        return "stackup skipped (no cadquery)"
    except Exception as e:                       # keep generation resilient
        return f"stackup FAILED ({type(e).__name__})"
    return (f"stackup {r['n_boards']}+{r['n_spacers']} tiles, "
            f"{r['n_components']} comp, {r['height_mm']} mm "
            f"(+ no-potting variant)")


def _export_components_stackup(boards, snake_chain, tile_step_dir, out_path,
                               tiles=None, nose_key="core_radar"):
    # (2026-11-14) gap hardware + the LDS sleeve (from <tile_step_dir>/sleeve/)
    """Component-render sibling of `_export_stackup` — fold the detailed per-tile
    STEPs (real component bodies, not mass boxes) into the same tower. Needs the
    tile + spacer STEPs already on disk under `tile_step_dir`. Never raises."""
    try:
        # sleeve / crown / nose cone come from the maximalist build (one core
        # sleeve; one nose per config) — dist/maximalist/sleeve/
        r = write_stackup_components_step(
            boards, snake_chain, tile_step_dir, out_path, tiles=tiles,
            sleeve_dir=_MAXIMALIST_DIR / "sleeve", nose_key=nose_key)
    except ImportError:
        return "components stackup skipped (no cadquery)"
    except Exception as e:                       # keep generation resilient
        return f"components stackup FAILED ({type(e).__name__})"
    return (f"components stackup {r['n_tiles']} tiles + {r['n_nose_parts']} sleeve/nose "
            f"parts ({nose_key}), {r['height_mm']} mm -> {pathlib.Path(r['output_path']).name}")


def _export_print_stls(boards, snake_chain, out_dir, tile_step_dir=None):
    """3D-print solids: a SOLID Ø34 cylinder enclosing the system
    (consolidated_stackup.stl — the nose USB-C kept as a real component when the
    per-tile STEPs are on disk under `tile_step_dir`) + the Ø39/Ø34 housing tube
    with a sealed Ø30 floor it drops into (housing.stl). Never raises."""
    out_dir = pathlib.Path(out_dir)
    try:
        cs = write_consolidated_stackup_stl(
            boards, snake_chain, out_dir / "consolidated_stackup.stl",
            tile_step_dir=tile_step_dir)
        hs = write_housing_stl(boards, snake_chain, out_dir / "housing.stl")
    except ImportError:
        return "print STLs skipped (no cadquery)"
    except Exception as e:                       # keep generation resilient
        return f"print STLs FAILED ({type(e).__name__})"
    usb = " +USB" if cs.get("usb_retained") else ""
    return (f"print STLs: consolidated_stackup.stl "
            f"(Ø{cs['diameter_mm']:.0f}x{cs['height_mm']:.1f}mm{usb}) + housing.stl "
            f"(Ø{hs['inner_dia_mm']:.0f}/{hs['outer_dia_mm']:.0f}x{hs['height_mm']:.1f}mm,"
            f" Ø{hs['floor_dia_mm']:.0f} floor)")


def _resolve_awr_placement(boards):
    """The resolved U_AWR placement on radar_module as `((cx,cy), rot_deg)`,
    or None when there is no radar tile / chip (non-radar configs)."""
    radar = boards.get("radar_module")
    if radar is None:
        return None
    for p in radar.chip_placements:
        if getattr(p.item, "ref", None) == "U_AWR":
            return p.position_mm, (getattr(p, "rotation_deg", 0.0) or 0.0)
    return None


def _export_waveguide_stubs(boards, out_path) -> str:
    """Best-effort WR-10 throat-stub STEP for visual alignment over the
    AWR2E44P launches. Reads the resolved U_AWR placement and maps the chip's
    footprint launches into the radar top-face frame (AWR2E44P builds only —
    the nose_cap PCB is retired). The export stacks the AWR footprint context
    (package body + BGA balls + plain verification PCB) DOWN from the launch
    plane so the stubs can be confirmed against the ball grid — no board sits
    between the launches and the stubs. Skips cleanly on non-radar configs /
    no cadquery; never raises. Call AFTER place_design."""
    if not _STEP_ENABLED:
        return "waveguide stubs skipped (STEP off)"
    pl = _resolve_awr_placement(boards)
    if pl is None:
        return "waveguide stubs skipped (no radar tile / U_AWR)"
    # The stubs model the AWR2E44P's on-package waveguide launches. The AoP
    # (antenna-on-package) and AWR2944 (external patches) have no launches, so
    # skip — there is nothing to couple into a horn block; the cup nose is a
    # radome for those parts, not a waveguide block.
    radar = boards.get("radar_module")
    awr_pn = next((getattr(p.item, "manf_pn", "") or "" for p in radar.chip_placements
                   if getattr(p.item, "ref", None) == "U_AWR"), "")
    if "AWR2E44P" not in awr_pn:
        return (f"waveguide stubs skipped (U_AWR={awr_pn or '?'} has no "
                f"launches — AoP/2944 use a radome, not a waveguide block)")
    (cx, cy), rot = pl
    try:
        from smash.export.waveguide_step import write_waveguide_step
        r = write_waveguide_step(
            out_path,
            placement_position_mm=(cx, cy),
            placement_rotation_deg=rot,
        )
    except ImportError:
        return "waveguide stubs skipped (no cadquery)"
    except Exception as e:                       # keep generation resilient
        return f"waveguide stubs FAILED ({type(e).__name__}: {e})"
    return (f"waveguide stubs {r['n_stubs']} @ U_AWR "
            f"({cx:.2f},{cy:.2f},{rot:.0f}deg) -> {pathlib.Path(out_path).name}")


@functools.lru_cache(maxsize=1)
def _step_cli():
    if not _STEP_ENABLED:
        return None
    try:
        return find_kicad_cli()
    except KiCadCliNotFound:
        return None


@functools.lru_cache(maxsize=1)
def _gerber_cli():
    """kicad-cli for fab plots — own gate (SMASH_GERBER_EXPORT), so a
    fast SMASH_STEP_EXPORT=0 run still emits manufacturing data."""
    if not _GERBER_ENABLED:
        return None
    try:
        return find_kicad_cli()
    except KiCadCliNotFound:
        return None


# ── economies-of-scale reference (maximalist → configs) ────────────────
# The maximalist build is the CANONICAL geometry: every board, joint and
# cutout it fabs is the one shared part. main() fills this after the
# maximalist build; _generate_config() injects it so each reduced config
# fabs the identical artifacts — same chip placements, same LGA land
# fields + nets, same milled cavities, same outline chords — instead of
# recomputing them from its own (different) census. Divergence would mean
# a per-config part number and no economies of scale.
_MAX_REF: dict | None = None


def _chain_neighbors(chain: list, bname: str) -> tuple:
    """(prev, next) chain elements around `bname` (None at the ends or when
    the board is off-chain, e.g. a branch leaf)."""
    if bname not in chain:
        return (None, None)
    i = chain.index(bname)
    return (chain[i - 1] if i > 0 else None,
            chain[i + 1] if i + 1 < len(chain) else None)


def _battery_column_conforms(panel, ref) -> bool:
    """True when this config's battery-spacer column sits in the SAME chain
    context as the maximalist reference: identical spacer list AND identical
    end boards. The column is all-or-nothing — its guarantee is ONE shared
    land pattern up the whole run (through-vias stack pad-to-pad), so a
    config whose column moved or shrank must recompute EVERY
    battery joint from its own bore rather than mix replayed and fresh
    patterns mid-column."""
    max_chain = ref.get("chain") or []
    cfg_chain = list(getattr(panel, "snake_chain", []) or [])
    mb = [n for n in max_chain if n.startswith("spacer_battery")]
    cb = [n for n in cfg_chain if n.startswith("spacer_battery")]
    if not cb:
        return True
    if cb != mb:
        return False

    def _ends(chain, bs):
        i0, iN = chain.index(bs[0]), chain.index(bs[-1])
        return (chain[i0 - 1] if i0 > 0 else None,
                chain[iN + 1] if iN + 1 < len(chain) else None)

    return _ends(max_chain, mb) == _ends(cfg_chain, cb)


def _nose_slot_alias(max_chain):
    """(2026-11-21) Fixed noses: whichever payload a config carries sits in the
    NOSE SLOT above compute — the maximalist chain's payload tile (radar). Map
    every payload name (and spacer names containing one) onto that tile so
    conformance / cavity inheritance treat the slot as the same position."""
    from smash.export import nose_interface as NI
    nose = next((n for n in max_chain if n in NI.PAYLOAD_BOARDS), None)
    if NI.MODULAR or nose is None:
        return lambda n: n

    def alias(n):
        for pb in NI.PAYLOAD_BOARDS:
            if pb != nose and (n == pb or n.endswith("_" + pb)):
                return n[: len(n) - len(pb)] + nose
        return n
    return alias


def _reference_conforming(panel, boards, ref) -> tuple[set, list]:
    """Boards whose chain adjacency matches the maximalist reference —
    the ones that may inherit its cavities/outline verbatim. A rigid tile
    conforms when each neighbour is the maximalist one OR absent (chain
    truncation); a spacer must match both neighbours exactly, and battery
    spacers additionally require the whole column to conform (see
    _battery_column_conforms). Returns (conforming, non_conforming_names)."""
    max_chain = ref.get("chain") or []
    alias = _nose_slot_alias(max_chain)
    cfg_chain = [alias(n) for n in (getattr(panel, "snake_chain", []) or [])]
    batt_ok = _battery_column_conforms(panel, ref)
    ok, bad = set(), []
    for bname, b in boards.items():
        rname = alias(bname) if getattr(b, "is_spacer", False) else bname
        if rname not in (ref.get("cavities") or {}):
            bad.append(bname)          # board unknown to maximalist
            continue
        if bname != alias(bname) and not getattr(b, "is_spacer", False):
            ok.add(bname)              # fixed-nose payload in the nose slot: its own part
            continue
        mp, mn = _chain_neighbors(max_chain, rname)
        cp, cn = _chain_neighbors(cfg_chain, alias(bname))
        if getattr(b, "is_spacer", False):
            conforms = (cp == mp and cn == mn)
            if bname.startswith("spacer_battery"):
                conforms = conforms and batt_ok
        else:
            conforms = (cp in (mp, None)) and (cn in (mn, None))
        (ok.add(bname) if conforms else bad.append(bname))
    return ok, sorted(bad)


def _replay_absent_joint_fields(d, panel, boards, ref) -> int:
    """Tile-face land fields for maximalist joints whose SPACER this config
    omits (chain truncation): the shared board still fabs the identical
    copper, so the field is emitted from the reference verbatim (its nets
    become stubs where the mating board is absent). A face already claimed
    by a DIFFERENT joint in this config (novel adjacency, e.g. a
    re-ordered battery column) is skipped with a warning — that board
    cannot stay identical to the maximalist part. Call right after
    place_lga_lands."""
    from smash.parts.connectors import _emit_land_field
    chain = list(getattr(panel, "snake_chain", []) or [])
    idx = {n: i for i, n in enumerate(chain)}
    n = 0
    for jname, J in (ref.get("joints") or {}).items():
        if jname in idx:               # joint present → place_lga_lands
            continue
        for bname, pts, face, step in ((J["before"], J["Qb"], "top", +1),
                                       (J["after"], J["Qa"], "bottom", -1)):
            b = boards.get(bname) if bname else None
            if b is None or getattr(b, "is_spacer", False):
                continue
            i = idx.get(bname)
            nb = (chain[i + step]
                  if i is not None and 0 <= i + step < len(chain) else None)
            if nb is not None:
                print(f"  WARNING: {bname} {face} face mates {nb} in this "
                      f"config, not the maximalist joint {jname} — the "
                      f"board diverges from the shared part", file=sys.stderr)
                continue
            prefix = "J_" if face == "top" else "P_"
            _emit_land_field(d, b, f"{prefix}{bname}_{jname}", pts,
                             J["nets"], face,
                             connect=lambda net, pin: _net(d, net).connect(pin))
            n += 1
    return n


# Board-project labels: the per-board KiCad/Altium projects are named
# <stack letter>_<label> (A = bottom/aft … top); spacers are just "spacer".
_BOARD_LABELS = {
    "aft_end_board":        "bottom",
    "activation_interface": "boost",
    "cell_floor_board":     "cell_floor",
    "wakeup_board":         "wakeup",
    "power_board":          "power",
    "companion_compute":    "compute",
    "radar_module":         "radar",
}


def _write_names_md(path, rows) -> None:
    """NAMES.md beside a config's boards: stack letter → project name →
    the board's design name, and how part references are formed."""
    lines = [
        "# Board and part names",
        "",
        "Generated by `generate_stackup.py` — do not edit; regenerate.",
        "",
        "Boards are lettered up the stack: **A is the bottom (aft end)**, the",
        "last letter the top (nose). Each board's folder and project files",
        "(`.kicad_pcb`, `.kicad_sch`, `.NET`, gerbers) carry `<letter>_<name>`;",
        "spacers are named only by their letter.",
        "",
        "| Letter | Project | Design name (internal) |",
        "|---|---|---|",
        *[f"| {l} | `{p}` | `{n}` |" for l, p, n in rows],
        "",
        "## Part references",
        "",
        "Every part's reference is its board letter + class + number:",
        "`AR1` is resistor 1 on board A, `PC12` capacitor 12 on board P,",
        "`ATP4` test pad 4 on board A. References are unique across the whole",
        "stack. Classes: R, C, L, D, Q, U, J (land fields / connectors),",
        "P (pads), TP (test pads), Y (crystals), SP (spacer body),",
        "MH (mounting holes).",
        "",
        "Each board folder has `<project>_refdes.csv` mapping every reference",
        "to its design name and value (e.g. `ATP4` = `TP_BAT_RAW`). Numbers",
        "follow the design names' order per class, so adding or removing a",
        "part renumbers later parts of that class on that board — check the",
        "CSV after each regeneration.",
        "",
    ]
    path.write_text("\n".join(lines))


def _board_export_bundle(name, b, tile_dir, tile_pcb, gcli, cli, fab) -> dict:
    """Gerbers + kicad-cli STEP + split STLs + layered STEP for one rigid board
    (cached as a unit by smash.export.export_cache). Never raises."""
    from smash.export.layered_step import write_layered_board_step
    r = {"gerber": 0, "failed_gerber": [], "step": 0, "failed_step": [],
         "stl": 0, "failed_stl": [], "layered": 0, "failed_layered": []}
    # Manufacturing set: gerbers/ + <name>_gerbers.zip beside the pcb.
    if gcli is not None:
        try:
            write_gerbers(tile_pcb, b, kicad_cli=gcli)
            r["gerber"] += 1
        except Exception as e:               # keep run resilient
            r["failed_gerber"].append(f"{name}({type(e).__name__})")
    if cli is None:
        return r   # per-board .kicad_pcb written; STEP/STL export off
    step_path = tile_dir / f"{name}.step"
    try:
        write_kicad_step(tile_pcb, step_path, kicad_cli=cli)
        r["step"] += 1
    except Exception as e:                         # keep run resilient
        r["failed_step"].append(f"{name}({type(e).__name__})")
        return r
    # STL — read back the STEP, split at the PCB midplane, stamp a pairing
    # symbol; two halves print flat with no supports (see export.stl).
    # Opt-in (SMASH_PRINT_STL=1).
    if _PRINT_STL:
        try:
            from smash.export.stl import (
                write_split_stls_from_step, unique_symbol,
                TILE_TOLERANCE_MM, TILE_ANGULAR_TOLERANCE,
            )
            for old in (tile_dir / f"{name}.stl",):    # stale single-STL
                if old.exists():
                    old.unlink()
            write_split_stls_from_step(
                step_path, tile_dir / name,
                z_split=b.thickness_mm / 2,
                tolerance=TILE_TOLERANCE_MM,
                angular_tolerance=TILE_ANGULAR_TOLERANCE,
                symbol=unique_symbol(name),
            )
            r["stl"] += 1
        except Exception as e:
            r["failed_stl"].append(f"{name}({type(e).__name__})")
    # Layered STEP — one solid per copper foil / dielectric (+ chip blocks)
    # with a JSON manifest of material properties (FEA / EM-sim ingestion).
    if (b.stackup or []):
        try:
            write_layered_board_step(
                b, tile_dir / f"{name}_layered.step", fab=fab,
                with_components=True, with_al_backing=True,
            )
            r["layered"] += 1
        except Exception as e:
            r["failed_layered"].append(f"{name}({type(e).__name__})")
    return r


def _export_tile_steps(design, panel, boards, out_dir,
                       cutouts_ref: dict | None = None) -> str:
    """Export each rigid board *tile* to its own STEP in `out_dir` —
    write a single-tile .kicad_pcb (with its flex-launch cutouts, which
    depend on the board's neighbours in this panel/config) then
    kicad-cli it. The assembled-panel STEP fuses every tile into one
    body; per-tile STEPs are far easier to inspect. Spacers get their
    fab set here too (.kicad_pcb + gerbers + _cam.md; 3D bodies stay
    with cadquery). A sibling `.stl` is dropped next to each
    `.step` for the 3D-print toolchain (see `documentation/
    3d_printing.md`). Never raises; returns a log fragment."""
    cli = _step_cli()   # None when SMASH_STEP_EXPORT=0 or kicad-cli absent;
                        # the per-board .kicad_pcb still get written either way
    out_dir.mkdir(parents=True, exist_ok=True)
    # Per-link flex widths feed the chord-cutout sizing; compute once.
    from smash.layout.placer.flex_sizing import compute_link_widths
    from smash.export.layered_step import write_layered_board_step
    from smash.export.portable_project import write_portable_project
    from smash import default_fab_profile
    link_widths, _ = compute_link_widths(design, panel)
    fab = default_fab_profile()
    ok, ok_stl, ok_layered, failed, failed_stl, failed_layered = (
        0, 0, 0, [], [], [])
    n_pcb = 0
    written: list[pathlib.Path] = []   # → portable projects, after the exports
    gcli = _gerber_cli()   # None when SMASH_GERBER_EXPORT=0 or kicad-cli absent
    ok_gerber, failed_gerber = 0, []
    # Stack letters: A = the aft end, then up the fold (spacers included).
    # Every part on a board carries its board's letter (AR1, BJ1, …), so
    # refdes are unique across the stack; stack.csv records the letters.
    # A board's project (files, schematic, library) is named
    # <letter>_<label> (A_bottom, B_spacer, …); its folder under out_dir
    # keeps the board name, which the 3D pipeline reads.
    letter = {n: stack_letter(i) for i, n in
              enumerate(getattr(panel, "snake_chain", None) or [])}

    def project_name(n):
        if n not in letter:
            return n
        b = boards.get(n)
        label = "spacer" if getattr(b, "is_spacer", False) else _BOARD_LABELS.get(n, n)
        return f"{letter[n]}_{label}"

    with open(out_dir / "stack.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Letter", "Project", "Board"])
        w.writerows([letter[n], project_name(n), n] for n in letter)
    _write_names_md(out_dir / "NAMES.md", [(letter[n], project_name(n), n) for n in letter])
    # Each board directory also gets <name>.kicad_sch + <name>.NET (Altium):
    # every footprint has
    # a symbol (the .kicad_pcb footprints carry its uuid path), so the EE
    # can open the board as a schematic+PCB project and Update PCB from
    # Schematic. Written before the portable pass, which rewrites the
    # footprint ids the schematic's Footprint fields already point at.
    # kicad-cli (when installed) re-links multi-unit parts to the unit KiCad
    # itself picks, so Update PCB from Schematic finds nothing to change.
    ok_sch, failed_sch = 0, []
    try:
        sch_cli = find_kicad_cli()
    except KiCadCliNotFound:
        sch_cli = None

    def _board_sch(name, b, tile_dir, refs):
        nonlocal ok_sch
        proj = project_name(name)
        try:
            # Short refdes (R1, Q1, TP1 …, unique per board) ↔ design ref:
            # the bench / firmware names live on in this table.
            vals = {c.ref: component_value(c) for c in all_components(design)}
            with open(tile_dir / f"{proj}_refdes.csv", "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["Ref", "Design ref", "Value"])
                for ref, short in sorted(refs.items(), key=lambda kv: (
                        re.match(r"\D*", kv[1])[0], int(re.search(r"\d+$", kv[1])[0]))):
                    w.writerow([short, ref, vals.get(ref, "")])
            write_board_schematic(design, b, tile_dir,
                                  pad_groups=_SCH_PAD_GROUPS.get(name), project=proj)
            # Altium: the same netlist as a Protel .NET, refdes/footprints/
            # nets exactly as on the board.
            write_board_protel_netlist(design, b, tile_dir / f"{proj}.NET")
            if sch_cli is not None:
                relink_multi_unit_footprints(tile_dir / f"{proj}.kicad_pcb",
                                             tile_dir / f"{proj}.kicad_sch", sch_cli)
            ok_sch += 1
        except Exception as e:                   # keep run resilient
            failed_sch.append(f"{name}({type(e).__name__}: {str(e)[:200]})")
    for name, b in boards.items():
        if getattr(b, "is_spacer", False) and not _SPACERS_ARE_PCBS:
            continue              # gap hardware is a STEP (write_gap_hardware)
        if getattr(b, "is_spacer", False):
            # Spacer interposers get a fab set too — .kicad_pcb (2-layer:
            # outline + NPTH + LGA lands + filled through-vias + Eco1/Eco2
            # pocket outlines) + gerbers + the _cam.md callout, so an
            # unrouted fit-check run can be ordered without the 3D
            # pipeline. Their STEP/STL bodies stay cadquery territory
            # (write_all_spacer_steps); no panel arg — a spacer has no
            # flex-launch chords to notch.
            if b.geometry is None:
                continue
            tile_dir = out_dir / name
            tile_dir.mkdir(parents=True, exist_ok=True)
            tile_pcb = tile_dir / f"{project_name(name)}.kicad_pcb"
            with board_refdes(b, letter.get(name, "")) as refs:
                write_kicad_pcb(design, b, tile_pcb, link_schematic=True)
                write_blank_drawing_sheet(tile_pcb)
                _board_sch(name, b, tile_dir, refs.mapping)
            written.append(tile_pcb)
            n_pcb += 1
            from smash.export.spacer_step import write_spacer_cam_notes
            write_spacer_cam_notes(b, tile_dir / f"{project_name(name)}_cam.md",
                                   thickness_mm=b.thickness_mm)
            if gcli is not None:
                try:
                    write_gerbers(tile_pcb, b, kicad_cli=gcli)
                    ok_gerber += 1
                except Exception as e:           # keep run resilient
                    failed_gerber.append(f"{name}({type(e).__name__})")
            continue
        if getattr(b, "kind", "rigid") == "flex":
            # Flex antenna tiles (nfc + the two Yagi tiles) are polyimide
            # carriers — they're meant to bend around the sonde body,
            # not be FDM-printed as solid parts. Skip both STEP and STL.
            # (camera_module / qpd_module are RIGID sensor tiles on flex
            # connectors, so they fall through and DO get exported.)
            continue
        if b.geometry is None:        # no outline to build a body from
            continue
        # board-per-folder layout: each tile lives in its own out_dir/<name>/
        tile_dir = out_dir / name
        tile_dir.mkdir(parents=True, exist_ok=True)
        tile_pcb = tile_dir / f"{project_name(name)}.kicad_pcb"
        with board_refdes(b, letter.get(name, "")) as refs:
            write_kicad_pcb(design, b, tile_pcb, panel=panel,
                            link_widths_mm=link_widths,
                            cutouts_override=(cutouts_ref or {}).get(name),
                            link_schematic=True)
            write_blank_drawing_sheet(tile_pcb)
            _board_sch(name, b, tile_dir, refs.mapping)
        written.append(tile_pcb)
        n_pcb += 1
        # (2026-11-19) The board's export bundle (gerbers, kicad-cli STEP,
        # split STLs, layered STEP) is cached on its final .kicad_pcb + stackup
        # + exporter code (smash.export.export_cache): unchanged boards are
        # restored instead of re-exported (~20 s each).
        from smash.export import export_cache
        from smash.layout.placer.cache import _canon
        bkey = export_cache.key(
            [tile_pcb, name, b.thickness_mm, repr(_canon(b.stackup or [], {})),
             repr(fab), gcli is not None, cli is not None, _PRINT_STL], cli=cli or gcli)
        res, _hit = export_cache.run_cached(
            bkey, tile_dir,
            lambda: _board_export_bundle(name, b, tile_dir, tile_pcb, gcli, cli, fab),
            exclude=[tile_pcb])
        ok_gerber += res["gerber"]
        failed_gerber += res["failed_gerber"]
        ok += res["step"]
        failed += res["failed_step"]
        ok_stl += res["stl"]
        failed_stl += res["failed_stl"]
        ok_layered += res["layered"]
        failed_layered += res["failed_layered"]
    # Portable projects — LAST, so kicad-cli plotted gerbers/STEP against the
    # absolute library + 3D-model paths first. Each board directory becomes a
    # standalone KiCad project: its own <Lib>.pretty, its own 3dmodels/, and
    # an fp-lib-table pointing at both, so an EE can open the board, edit a
    # footprint and "Update Footprints from Library" without this repo.
    portable_msg = ""
    if written:
        n_lib, n_mdl, warn = 0, 0, []
        for pcb in written:
            try:
                r = write_portable_project(pcb)
            except Exception as e:                 # keep the run resilient
                warn.append(f"{pcb.stem}({type(e).__name__})")
                continue
            n_lib += r["n_footprints"]
            n_mdl += r["n_models"]
            if r["missing_models"]:
                warn.append(f"{pcb.stem}: {len(r['missing_models'])} model(s) "
                            "not found")
            if r["conflicts"]:
                warn.append(f"{pcb.stem}: {', '.join(r['conflicts'])} differ "
                            "between instances")
        portable_msg = (f", portable libs {n_lib} footprints + {n_mdl} 3D models")
        if warn:
            portable_msg += "; PORTABLE WARN: " + "; ".join(warn)

    gerber_msg = (f", {ok_gerber} gerber zips" if gcli is not None
                  else ", gerbers off")
    gerber_msg += f", {ok_sch} schematics"
    if failed_sch:
        gerber_msg += f" (SCHEMATIC FAILED: {', '.join(failed_sch)})"
    if cli is None:
        msg = (f"{n_pcb} per-board .kicad_pcb{gerber_msg}{portable_msg} → "
               f"{out_dir.relative_to(REPO)}/ (STEP export off)")
        if failed_gerber:
            msg += f"; GERBERS FAILED: {', '.join(failed_gerber)}"
        return msg
    msg = (f"{n_pcb} .kicad_pcb, {ok} STEP{gerber_msg}{portable_msg} → "
           f"{out_dir.relative_to(REPO)}/ (+{ok_stl} STL, +{ok_layered} layered)")
    if failed:
        msg += f"; STEP FAILED: {', '.join(failed)}"
    if failed_stl:
        msg += f"; STL FAILED: {', '.join(failed_stl)}"
    if failed_layered:
        msg += f"; LAYERED FAILED: {', '.join(failed_layered)}"
    if failed_gerber:
        msg += f"; GERBERS FAILED: {', '.join(failed_gerber)}"
    return msg


_EE_LAYOUT_JSON = (pathlib.Path(__file__).parent
                   / "application/src/smash/data/companion_ee_layout.json")
_ACTIVATION_EE_JSON = (pathlib.Path(__file__).parent
                       / "application/src/smash/data/"
                         "activation_interface_ee_layout.json")
_POWER_LANDS_EE_JSON = (pathlib.Path(__file__).parent
                        / "application/src/smash/data/"
                          "power_board_ee_lands.json")
_AFT_END_LANDS_EE_JSON = (pathlib.Path(__file__).parent
                          / "application/src/smash/data/"
                            "aft_end_board_ee_lands.json")
_FIN_BLE_LANDS_EE_JSON = (pathlib.Path(__file__).parent
                          / "application/src/smash/data/"
                            "fin_ble_board_ee_lands.json")


# Courtyard overlaps on the final routed boards, accepted 2026-10-12 so their
# placements lock exactly as routed (the routed boards are fabbed as-is; the
# generator only has to cut matching spacers). Courtyard only — KiCad DRC on
# the routed files reports no copper clearance error for any of these pairs.
_ACCEPTED_LOCKED_OVERLAPS = (
    # Sjoert's power_board (WIP/Sjoert/power_board_generated), bottom face.
    ("power_board", "C_BAT_BULK1", "U_COMP_BOOST"),
    ("power_board", "CBAT2", "D_BOOST_COMP"),
    ("power_board", "CBAT3", "D_BOOST_COMP"),
    ("power_board", "U_COMP_BOOST", "D_BOOST_COMP"),
    ("power_board", "L_BOOST_COMP", "D_BOOST_COMP"),
    ("power_board", "D_BOOST_COMP", "C_BOOST_OUT2_4"),
    ("power_board", "C_USB_VBUS_1", "Q_USB_WAKE"),
    ("power_board", "C_USB_VBUS_2", "Q_USB_WAKE"),
    # (Francesco's wakeup_board entries dropped 2026-11-16: every wakeup
    # lock was released for the re-route, so nothing there is locked.)
)


def _power_board_pinned_lands() -> dict:
    """EE-pinned LGA fields for BOTH of power_board's joints, captured from
    Sjoert's final routed board, WIP/Sjoert/power_board_generated/ (his part
    placements are pinned in locked_placements.json). Rather than re-route
    the board, each spacer and the far neighbour adopt its fields; see
    `place_lga_lands(pinned=...)`, which warns if a pinned land leaves the
    joint's free region or a crossing net goes uncarried. Configs inherit
    them through the maximalist joint capture.

    Companion side (top, 66 lands): also what WIP/Sjoert/companion_compute's
    bottom field was routed against. The earlier 2026-09-03 capture
    (WIP/Sjoert/power_board/) had 68 lands — two extra (USB_VBUS, 3V3) that
    shifted the net order of everything from land 47 on.

    Wakeup side (bottom, 65 lands): Sjoert's redone field. The 2026-09-03
    field was packed around the old wrong-diagonal potting holes and cut
    into the board's own Ø3 holes; this one clears them."""
    if not _POWER_LANDS_EE_JSON.exists():
        return {}
    return json.loads(_POWER_LANDS_EE_JSON.read_text())["joints"]


def _aft_end_pinned_lands() -> dict:
    """EE-pinned LGA field for aft_end_board's activation-side joint, from the
    final routed aft_end_board (Review/aft_end_board). Net names are mapped
    FIRE -> ACTIVATE (renamed after routing). The reviewed activation_interface
    and spacer predate the fin full-pair change and do not match this field."""
    if not _AFT_END_LANDS_EE_JSON.exists():
        return {}
    return json.loads(_AFT_END_LANDS_EE_JSON.read_text())["joints"]


def _fin_ble_pinned_lands() -> dict:
    """EE-pinned LGA field for fin_ble_board's wakeup-side joint, from the
    final routed fin_ble_board (Review/fin_ble_board2). Francesco's routed
    wakeup_board carries the same 69-land field on its bottom face, so pinning
    keeps the spacer mating both — left to the packer, the field drifts as
    soon as either neighbour's locked parts reshape the joint's free region."""
    if not _FIN_BLE_LANDS_EE_JSON.exists():
        return {}
    return json.loads(_FIN_BLE_LANDS_EE_JSON.read_text())["joints"]



_ACTIVATION_EE_REFERENCE_ACTIVE = False


def _apply_activation_reference_layout(d, boards: dict) -> None:
    """Adopt the EE's component placement for activation_interface.

    The board was routed externally (Freerouting-assisted, see
    `Finalized/activation_interface/`), so its 791 tracks, 88 vias and 4
    plane zones are drawn against THESE component positions. Re-placing
    them on a later run silently invalidates that routing, which is the
    same failure the companion reference guards against.

    Imported by `tools/import_ee_layout.py <src> --board
    activation_interface`. The delta at import time was a single part —
    L_ACTIVATE, nudged 0.29 mm during routing — so this is not about moving
    anything today. It is about pinning what the copper was drawn on, so
    the packer cannot drift the board out from under the routing when a
    footprint or a neighbour changes.

    COPPER IS IMPORTED VERBATIM — 791 tracks over 9 layers, 88 through
    vias and the 4 plane zones (FLEX_GND In1/In12, 3V3 In2, COMP_5V In11),
    all attached with note="ee-ref". Unlike companion_compute nothing is
    dropped: every component here is top-face, so the B.Cu copper is the
    EE's own routing rather than stitching for an unplaced pile.

    ⚠ WIDTH CAVEAT: Freerouting was driven from a DSN carrying ONE rule —
    100 µm track, 75 µm clearance, a single 0.45/0.20 via — so all 42 nets
    come in at 4 mil, ACTIVATE_HV (33 V) and BAT_RAW included, alongside the
    SWD pins. That is a routing input, not a considered choice, and the
    EE's own notes still list track-width DRC errors on ACTIVATE_HV, FLEX_GND,
    3V3 and NRST. Re-derive the power widths per net class before fab.

    Also NOT imported: the TN0018 keepout under U_HACC (a KiCad keepout
    zone with no net; the model has no equivalent) and the EE's
    activation_interface.kicad_dru.

    Unlike companion_compute this locks BOTH faces: the only bottom-face
    entry is the P_ land field at the origin, where it already sits, so
    there is no unplaced-pile problem to work around here."""
    b = boards.get("activation_interface")
    if b is None or not _ACTIVATION_EE_JSON.exists():
        return
    # (2026-11-15) Retired: the board is re-laid-out from scratch after the
    # aft reorder (28 aft_end parts joined it); the EE placement only
    # fragmented the face and re-locked parts over freshly packed ones.
    if not _ACTIVATION_EE_REFERENCE_ACTIVE:
        return
    from smash.layout.locked import load_locked_placements
    data = json.loads(_ACTIVATION_EE_JSON.read_text())
    ref_place = data.get("placements") or {}
    # An explicit entry in locked_placements.json OUTRANKS the import. Those
    # carry a recorded engineering reason; a routing nudge does not get to
    # overwrite one silently. L_ACTIVATE is the live case: locked at (-7.5,-4.0)
    # on 2026-07-31 so its cavity merges with the activate-bank pocket instead of
    # notching the perimeter interconnect ring, and the EE's 0.29 mm nudge
    # puts it 0.14 mm into the spacer FR4 (check_spacer_chip_clearance
    # catches it). To adopt such a move, change the lock and its reason.
    pinned = set(load_locked_placements())
    moved = n_lock = 0
    refused = []
    for i, pl in enumerate(b.chip_placements):
        ref = getattr(pl.item, "ref", None)
        ee = ref_place.get(ref)
        if not ee:
            continue                       # MECH1/MECH2 have no model ref
        pos = tuple(ee["pos"])
        if ref in pinned and (abs(pos[0] - pl.position_mm[0]) > 1e-4
                              or abs(pos[1] - pl.position_mm[1]) > 1e-4):
            refused.append(ref)
            continue
        if (abs(pos[0] - pl.position_mm[0]) > 1e-4
                or abs(pos[1] - pl.position_mm[1]) > 1e-4):
            moved += 1
        b.chip_placements[i] = pl._replace(
            position_mm=pos, rotation_deg=ee["rot"],
            face=ee["face"], locked=True)
        n_lock += 1
    # Copper, verbatim. Every part on this tile is top-face, so there is no
    # bottom-face pile to guard against the way companion_compute needs.
    from smash.state.routing.track import Track
    from smash.state.routing.via import Via
    from smash.state.routing.zone import Zone
    # (2026-11-15 aft reorder) aft_end's 28 top-face parts moved onto this
    # board, so the EE's routed copper no longer matches it — placement is
    # kept as a seed, copper is NOT imported until the board is re-routed.
    data = dict(data, tracks=[], vias=[], zones=[])
    for t in data.get("tracks") or []:
        b.tracks.append(Track(
            net=t["net"], layer=t["layer"], width_mm=t["width"],
            path=[tuple(q) for q in t["path"]], note="ee-ref"))
    for v in data.get("vias") or []:
        b.vias.append(Via(
            net=v["net"], position_mm=(v["x"], v["y"]),
            drill_mm=v["drill"], pad_diameter_mm=v["size"],
            from_layer=v["from"], to_layer=v["to"], kind=v["kind"],
            filled=True, note="ee-ref"))
    for z in data.get("zones") or []:
        b.zones.append(Zone(
            net=z["net"], layer=z["layer"],
            outline_mm=[tuple(q) for q in z["outline"]],
            fill_polygons_mm=[
                {"layer": f.get("layer"), "pts": [tuple(q) for q in f["pts"]]}
                for f in (z.get("fills") or [])],
            note="ee-ref"))
    widths = sorted({t["width"] for t in (data.get("tracks") or [])})
    msg = (f"activation_interface: EE reference layout applied "
           f"({n_lock} placements locked, {moved} moved, {len(b.tracks)} "
           f"tracks, {len(b.vias)} vias, {len(b.zones)} zones; "
           f"copper dropped — re-route after the 2026-11-15 aft reorder)")
    if refused:
        msg += (f"; REFUSED {len(refused)} that locked_placements.json pins "
                f"with a recorded reason: {', '.join(sorted(refused))}")
    print(msg)
    from smash.validators import assert_no_locked_overlaps
    assert_no_locked_overlaps(boards, accepted=_ACCEPTED_LOCKED_OVERLAPS)


def _apply_companion_reference_layout(d, boards: dict) -> None:
    """Adopt the EE reference PLACEMENT for companion_compute.

    His TOP-face placements only — imported by tools/import_ee_layout.py
    into the board frame. The reference was laid out against THIS netlist
    (it carries our refs and net names, including the VREFCA divider +
    ALERT_N pull-up parts we already author), so it lands without netlist
    changes. Bottom-face parts are left to smash's placer (his bottom
    decaps are an unplaced pile).

    THE COPPER WAS REMOVED 2026-09-03. The `testcercacompo1306` drop is not
    manufacturable and the board is being re-routed, so carrying its 1121
    tracks / 234 vias / 8 zones meant every regeneration shipped fab data
    with routing known to be bad — and its zones carried no fill polygons,
    so the plane layers plotted as empty copper on top of that. Better to
    generate the board unrouted, where the gap is obvious, than to ship
    wrong copper. The capture is in git if it is ever wanted again.

    The PLACEMENT stays: documentation/ee_companion_compute_review.md
    accepted it ("38 major parts identical to our generated reference",
    the decaps and bias resistors properly placed and no longer a pile),
    and the re-route will be drawn against it.

    To take a new drop: re-run `tools/import_ee_layout.py <src>` — it now
    captures `filled_polygon` fills too, which the old capture predates —
    then re-add a track/via/zone attach here. Revisit two things at that
    point: the import's `_DENY` net list (companion-specific exclusions
    that may be stale once re-routed) and the old B.Cu-copper drop, which
    existed because that drop's bottom decaps were unplaced."""
    b = boards.get("companion_compute")
    if b is None or not _EE_LAYOUT_JSON.exists():
        return
    data = json.loads(_EE_LAYOUT_JSON.read_text())
    moved = 0
    for i, pl in enumerate(b.chip_placements):
        ref = getattr(pl.item, "ref", None)
        ee = data["placements"].get(ref)
        # Lock ONLY the routed TOP face. The EE hand-places the top side
        # (and we lock it) because his DDR4 copper is routed against it;
        # the BOTTOM side of every board is left to smash's placer. His
        # file leaves the bottom decoupling caps in KiCad's unplaced pile
        # — a heap of ~60 overlapping 0805s near the origin — and locking
        # those verbatim merged their pads, shorting every power rail to
        # FLEX_GND (86 DRC shorts + 272 unconnected). Bottom-face refs
        # keep their native, collision-free placement; the test-locked
        # overlap validator guards the top face. See [[ddr4-ee-layout]].
        if ee and ee.get("face") == "top":
            # Placement is a NamedTuple — replace, don't mutate
            b.chip_placements[i] = pl._replace(
                position_mm=tuple(ee["pos"]),
                rotation_deg=ee["rot"], face=ee["face"], locked=True)
            moved += 1
    print(f"companion_compute: EE reference PLACEMENT applied "
          f"({moved} top-face placements; copper REMOVED 2026-09-03 — the "
          f"drop is not manufacturable, board is being re-routed)")
    # Guard the locks we just applied: a locked part the placer can't move
    # must never overlap another component. This is what catches an EE drop
    # that locks an unplaced pile (overlapping bottom decaps -> merged pads
    # -> power-to-GND shorts) — fail the build here, not at the fab's DRC.
    from smash.validators import assert_no_locked_overlaps
    assert_no_locked_overlaps(boards, accepted=_ACCEPTED_LOCKED_OVERLAPS)


_TALL_ZONE_REFS = ("L_ACTIVATE", "L_BOOST_COMP")   # power top ↔ compute bottom keepout


def _mark_locked_pth_pin_keepouts(d: Design, boards: dict, locks: dict) -> int:
    """(2026-11-21) A LOCKED part's through-hole pins come out on the other
    face: each drilled pad becomes a square keep-out (pad + 0.3 mm) on the
    OPPOSITE face, so the packer never puts a part on a pin (the QPD TO-8's
    pins under the TIAs / VREF cap were the case)."""
    import math as _m
    from smash.state.board_geometry import Keepout
    n = 0
    for c in d.chips:
        e = locks.get(c.ref)
        b = boards.get(getattr(c, "board_tag", None))
        fp = getattr(c, "footprint", None)
        if e is None or b is None or fp is None or getattr(b, "geometry", None) is None:
            continue
        face = getattr(e, "face", None) or "top"
        other = "B.Cu" if face == "top" else "F.Cu"
        th = _m.radians(getattr(e, "rotation_deg", 0) or 0)
        cx, cy = e.position_mm
        for p in fp.pads:
            if getattr(p, "drill_mm", None) is None:
                continue
            px, py = p.position_mm
            x, y = px * _m.cos(th) - py * _m.sin(th), px * _m.sin(th) + py * _m.cos(th)
            if face == "bottom":
                x = -x
            h = max(p.size_mm) / 2 + 0.3
            X, Y = cx + x, cy + y
            b.geometry.keepouts.append(Keepout(
                polygon=[(X - h, Y - h), (X + h, Y - h), (X + h, Y + h), (X - h, Y + h)],
                layers=(other,), scope="component", tag="pth_pin",
                note=f"{c.ref} pin {p.num} comes through here"))
            n += 1
    return n


def _mark_preplace_keepouts(d: Design, boards: dict) -> None:
    """Keepouts the placer must see BEFORE place_design (chip_placements aren't
    set yet):

      1. The USB nose's NORTH column around the locked J_USB_C: the
         connector mouth exits through the N chord notch and the cup's USB
         window (smash.export.nose_radome), so no tall radar chip may crowd it.
         (2026-11-18: the nose_cap aperture keepout went with the nose_cap PCB.)"""
    from smash.state.board_geometry import Keepout
    # (2026-11-18) USB-C is vertical at the USB nose's centre — no rim keepout.

    # 3. Battery-bracket tuck (triple mode): the compartment's two bracket
    #    faces — fin_ble's BOTTOM (the ceiling) and cell_floor's TOP — must
    #    keep their parts INSIDE the cell bore (the 2026-07-31 rule: parts
    #    tuck into the ~1 mm headroom over the cell tops). Un-enforced, the
    #    packer scatters them into the perimeter land ring and
    #    _mark_battery_chip_clearance then "heals" them into a huge scalloped
    #    pocket blob cut through EVERY battery spacer (the artifact caught on
    #    the spacers 2026-08-28) while eating the column's LGA ring. The
    #    packer only understands axis-aligned keepout AABBs, so the not-bore
    #    region is rasterized into a grid of small rects; cells are blocked
    #    unless fully inside bore−0.7 mm, so a packed body (+0.3 mm clearance
    #    box) always lands ≥0.4 mm inside the through-cut and the clearance
    #    pass drops every pocket.
    from shapely.geometry import box as _box
    bore_in = _battery_bore_polygon().buffer(-0.7)
    STEP = 1.0
    rects = []
    k = 17                      # grid spans ±17 mm (the Ø34 tile)
    for gj in range(-k, k):
        run_start = None        # merge each row's blocked cells into runs
        for gi in range(-k, k + 1):
            blocked = gi < k and not bore_in.contains(
                _box(gi * STEP, gj * STEP,
                     (gi + 1) * STEP, (gj + 1) * STEP))
            if blocked and run_start is None:
                run_start = gi
            elif not blocked and run_start is not None:
                rects.append((run_start * STEP, gj * STEP,
                              gi * STEP, (gj + 1) * STEP))
                run_start = None
    # fin_ble's bottom: since the 2026-11-14 headroom it is FREE inside
    # the holder's edge ring (r < 15.8) — only the ring band is blocked.
    import math as _m
    from smash.export.spacer_step import (BATT_TOP_RING_R_IN_MM,
                                          BATT_PART_CLEARANCE_MM)
    ring_rects = _ring_band_rects(BATT_TOP_RING_R_IN_MM - BATT_PART_CLEARANCE_MM)
    # (2026-11-20) no tabs any more (Tadiran /P cells wired to aft_end); the
    # board sits over the 1 mm headroom (cell + pin → wire joints).
    # (2026-11-20, user) TALL ZONE: the locked 2.8 mm boost inductors on
    # power_board's top get a matching PLAIN keepout on companion_compute's
    # BOTTOM (same stack frame), so no part stacks over them — the gap is then
    # their height + clearance, not their height + a 1.45 mm cap's.
    from smash.layout.locked import load_locked_placements as _llp
    _locks = _llp()
    cb = boards.get("companion_compute")
    if cb is not None and getattr(cb, "geometry", None) is not None:
        for _ref in _TALL_ZONE_REFS:
            e = _locks.get(_ref)
            if e is None:
                continue
            x, y = e.position_mm
            h = 3.625 + 0.35         # (2026-11-22) IHLP-2020 courtyard ±3.625 (was XGL5020 ±3.27) + packer margin
            cb.geometry.keepouts.append(Keepout(
                polygon=[(x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h)],
                layers=("B.Cu",), scope="component", tag="tall_zone",
                note=f"over {_ref} (power_board top, 2.8 mm)"))
    # (2026-11-20, user) …revised: LOW parts (≤ 0.8 mm, face_split) may use it,
    # outside the holder's edge-ring band and clear of the cells' + pin joints
    # and their AWG 28 wires to the potting channel (plain keepouts; the
    # packer only knows axis-aligned rects → the corridors are 1 mm squares).
    fb = boards.get("activation_interface")   # the ceiling since 2026-11-15
    if fb is not None and getattr(fb, "geometry", None) is not None:
        def _sq(x, y, h, tag, note):
            fb.geometry.keepouts.append(Keepout(
                polygon=[(x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h)],
                layers=("B.Cu",), scope="component", tag=tag, note=note))
        for (x0, y0, x1, y1) in ring_rects:
            fb.geometry.keepouts.append(Keepout(
                polygon=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                layers=("B.Cu",), scope="component", tag="battery_ring_band",
                note="battery holder edge ring (r 16–17) bears here"))
        from smash.export.spacer_step import cell_centres_xy, _batt_channel_xy
        chx, chy = _batt_channel_xy()
        for cx, cy in cell_centres_xy():
            _sq(cx, cy, 1.5, "cell_pin_joint", "cell + pin → wire solder joint")
            n_st = max(1, int(_m.hypot(chx - cx, chy - cy) / 0.8))
            for k in range(n_st + 1):
                t = k / n_st
                _sq(cx + (chx - cx) * t, cy + (chy - cy) * t, 1.0, "cell_wire",
                    "cell + wire to the potting channel")
    _mark_locked_pth_pin_keepouts(d, boards, _locks)
    for bname, cu in (("cell_floor_board", "F.Cu"),):
        b = boards.get(bname)
        if b is None or getattr(b, "geometry", None) is None:
            continue
        for (x0, y0, x1, y1) in rects:
            b.geometry.keepouts.append(Keepout(
                polygon=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                layers=(cu,), scope="component", tag="battery_bore_tuck",
                note="battery-facing face: parts stay INSIDE the cell "
                     "bore (compartment headroom) — see "
                     "_mark_battery_chip_clearance."))


def _ring_band_rects(r_free: float, step: float = 0.5, k_mm: float = 17.0) -> list:
    """Axis-aligned rects covering r > r_free inside the ±k_mm tile, on a fine
    grid (a cell is blocked only if one of its corners lies past r_free), row
    runs merged. The old 1 mm grid over-blocked ~70 mm² per face."""
    n = int(round(k_mm / step))
    rects = []
    for gj in range(-n, n):
        y0 = gj * step
        run_start = None
        for gi in range(-n, n + 1):
            x0 = gi * step
            blocked = gi < n and any(x * x + y * y > r_free ** 2 for x, y in (
                (x0, y0), (x0 + step, y0), (x0, y0 + step), (x0 + step, y0 + step)))
            if blocked and run_start is None:
                run_start = x0
            elif not blocked and run_start is not None:
                rects.append((run_start, y0, x0, y0 + step))
                run_start = None
    return rects


def _mark_ring_band_keepouts(panel, boards: dict) -> int:
    """(2026-11-15) Every non-battery gap is an Al ring (r 16-17): block the
    ring band (r > RING_R_IN - clearance) on both faces it bears on — the
    lower board's TOP, the upper board's BOTTOM — as packer keepouts (the
    packer only takes axis-aligned rects, so the band is rasterized like the
    battery ring's). Returns the number of faces marked."""
    from smash.state.board_geometry import Keepout
    from smash.export.spacer_step import (gap_kind, RING_CLEARANCE_MM,
                                          ring_open_sector, ring_spec)
    from smash.parts.castellations import board_fold_transforms
    import math as _m
    chain = list(panel.snake_chain or [])
    fold_M = board_fold_transforms(panel, chain)

    def in_opening(M, x, y, osec):     # C-ring (2026-11-17): no ring there
        if not osec:
            return False
        px, py = M[0][0] * x + M[0][1] * y, M[1][0] * x + M[1][1] * y
        return osec[0] + 3.0 <= _m.degrees(_m.atan2(py, px)) % 360.0 <= osec[1] - 3.0

    n = 0
    for sp, before, after in _gap_neighbours(chain, boards):
        if gap_kind(sp) != "ring":
            continue
        for nbr, cu in ((before, "F.Cu"), (after, "B.Cu")):
            b = boards.get(nbr) if nbr else None
            if b is None or getattr(b, "geometry", None) is None:
                continue
            M = fold_M.get(nbr, ((1, 0), (0, 1)))
            rs = ring_spec(sp)
            for (x0, y0, x1, y1) in _ring_band_rects(rs.r_in - RING_CLEARANCE_MM):
                if all(in_opening(M, x, y, ring_open_sector(sp))
                       for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))):
                    continue
                b.geometry.keepouts.append(Keepout(
                    polygon=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                    layers=(cu,), scope="component", tag="al_ring_band",
                    note=f"{rs.label} of {sp} (r {rs.r_in:g}-{rs.r_out:g}) bears here"))
            n += 1
    # (2026-11-18) The compute↔payload gap's ring is the nose ANCHOR ring:
    # snap HOOKS hang in the bore at nose_interface.HOOK_ANGLES_DEG
    # → keep compute's TOP and every nose payload's BOTTOM clear there; the
    # payload leaves (qpd / camera / usb_nose) also get the ring band.
    from smash.export import nose_interface as NI
    from smash.parts.castellations import _local_xy
    anchor = next((sp for sp, b0, b1 in _gap_neighbours(chain, boards)
                   if b0 == NI.HOST and b1 in NI.PAYLOAD_BOARDS), None) if NI.MODULAR else None
    if anchor is not None and NI.HOST in fold_M:
        M = fold_M[NI.HOST]
        # (2026-11-20) snap: the hook legs + barbs hang inside the bore at the
        # hook angles (r ≥ HOOK_NOTCH_R) down to HOOK_TIP_CLEAR over compute
        r0, r1 = NI.HOOK_NOTCH_R_MM - 0.3, RING_R_BAND_MM
        faces = [(NI.HOST, "F.Cu")] + [(pb, "B.Cu") for pb in NI.PAYLOAD_BOARDS if pb in boards]
        rs = ring_spec(anchor)
        for bname, cu in faces:
            b = boards[bname]
            if getattr(b, "geometry", None) is None:
                continue
            if cu == "B.Cu":
                # (2026-11-19) the Ø34 payload SITS on the nose cone's land ring
                # (r CROWN_R_IN → edge): its bottom face is bare there
                for (x0, y0, x1, y1) in _ring_band_rects(NI.CROWN_R_IN_MM - 0.3):
                    b.geometry.keepouts.append(Keepout(
                        polygon=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                        layers=(cu,), scope="component", tag="nose_land_ring",
                        note=f"nose land ring (r {NI.CROWN_R_IN_MM:g}+) bears here"))
                n += 1
                continue                       # the band screws are below it
            n += _hook_keepouts(b, M, cu, r0, r1)
        # (2026-11-20, user) the hook LEGS pass each payload board's EDGE NOTCH
        # (kicad_pcb cuts it): keep its top face clear there too
        for pb in NI.PAYLOAD_BOARDS:
            if pb in boards and getattr(boards[pb], "geometry", None) is not None \
                    and fold_M.get(pb) is not None:
                n += _hook_keepouts(boards[pb], fold_M[pb], "F.Cu",
                                    NI.HOOK_NOTCH_R_MM - 0.3, 17.0)
    return n


RING_R_BAND_MM = 16.2


def _hook_keepouts(b, M, cu: str, r0: float, r1: float) -> int:
    """(2026-11-20) plain keepout round each snap HOOK (r0–r1, ±notch half
    width + 0.3) on face `cu` of board `b` (fold transform M)."""
    import math
    from smash.export import nose_interface as NI
    from smash.parts.castellations import _local_xy
    from smash.state.board_geometry import Keepout
    da_b = math.degrees((0.5 * NI.HOOK_NOTCH_W_MM + 0.3) / r0)
    for ang in NI.HOOK_ANGLES_DEG:
        pts = [_local_xy(M, ang + da, rr) for da in (-da_b, da_b) for rr in (r0, r1)]
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        b.geometry.keepouts.append(Keepout(
            polygon=[(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))],
            layers=(cu,), scope="component", tag="nose_hook",
            note=f"snap hook at {ang:g}° (leg r {NI.HOOK_R_IN_MM}–{NI.HOOK_R_IN_MM + NI.HOOK_T_MM})"))
    return 1


def _mark_battery_pockets(boards: dict) -> None:
    """ONE merged through-cut per battery-compartment spacer. Triple mode: a
    trefoil union of the 3 Ø14.8 vertical cells (triangle around the spin axis,
    overlapping, thin centre web filled). Single mode (lowprofile): a stadium
    for the 1 horizontal Ø15.1×27.4 cell laid along X. The LGA lands + filled
    vias pack the remaining perimeter ring. Call AFTER place_design (clears
    cavity_placements) and BEFORE place_lga_lands (so the land packer's free
    region excludes the cutout)."""
    _apply_battery_bore(boards, _battery_bore_polygon())


def _battery_bore_polygon():
    """The battery compartment bore as a shapely Polygon, in the active
    battery mode. ONE source of truth: `_mark_battery_pockets` stamps it as
    the spacers' through-cut and `_mark_preplace_keepouts` uses it to keep
    the bracket tiles' battery-facing parts tucked INSIDE it (the
    2026-07-31 rule) — the two must never drift apart."""
    import math as _m
    from shapely.geometry import Polygon as _ShPoly
    from shapely.ops import unary_union
    n = 48

    def _circle(cx, cy, r):
        return [(cx + r * _m.cos(2 * _m.pi * i / n),
                 cy + r * _m.sin(2 * _m.pi * i / n)) for i in range(n)]

    CELL_R, CLUSTER_R = 7.6, 8.6     # Ø14.8 cell + ~0.4 clr; triangle radius
    centres = [(CLUSTER_R * _m.cos(_m.pi / 2 + 2 * _m.pi * k / 3),
                CLUSTER_R * _m.sin(_m.pi / 2 + 2 * _m.pi * k / 3))
               for k in range(3)]
    bore = unary_union([_ShPoly(_circle(cx, cy, CELL_R)) for cx, cy in centres])
    if bore.geom_type != "Polygon":      # not connected → enclose them
        bore = bore.convex_hull
    return bore


def _apply_battery_bore(boards: dict, bore) -> None:
    """Stamp a battery bore polygon onto every spacer_battery_* tile and thread
    EVERY perimeter potting hole through the whole column to the aft floor.

    A hole whose centre sits past the bore (in the perimeter ring) is CONTINUED
    as a through-channel down every battery spacer and tied into the bore by a
    finger on the aft-most spacer (spacer_battery_1); a hole already inside the
    bore just vents straight into it and needs neither. The projected holes come
    from the run's RIGID bracket tiles (triple: cell_floor + the fin_ble ceiling
    since the 2026-07-31 reorder; single: aft_end + activation). For the single
    cell BOTH ceiling holes sit just past the bore's short-edge ends (r≈14 vs
    the bore's 13.9), so both become full-length channels to the aft floor —
    potting injected at one fills the cell cavity upward and vents out the
    other; they already carry the spacer fold mirror, so they land under the
    real tile holes. (The 3-cell trefoil has one hole inside a lobe → only
    the other, outside, hole is threaded.)"""
    from shapely.geometry import LineString as _LS, Point as _ShPt
    from shapely.ops import unary_union
    from smash.state.geometry.cavity import CavityRegion
    from smash.state.topology.placement import Placement
    from smash.layout.cavities import (POTTING_CHANNEL_WIDTH_MM as _PW,
                                       POTTING_HOLE_DIA_MM as _PHD)
    from smash.state.board_geometry import Hole

    # Every distinct perimeter (outside-bore) potting hole across the column —
    # each gets its own full-length channel + bore finger. Deduped by position
    # (holes are only projected onto the spacers adjacent to a RIGID end tile —
    # activation_interface, and in triple mode the cell_floor floor tile, whose
    # projections coincide; sibling-spacer projection is skipped in
    # attach_cavities_to_spacers — but the channel is replicated onto all of
    # them below). Thread EVERY perimeter potting hole straight DOWN through
    # every battery spacer as a through-drill, so the end tiles' potting holes
    # continue all the way down the column to the aft floor. (These holes are
    # outside the bore, in the land ring.)
    channels: list = []
    vents: list = []
    for nm, b in boards.items():
        if not nm.startswith("spacer_battery") or b.geometry is None:
            continue
        for h in b.geometry.holes:
            if getattr(h, "tag", None) != "potting":
                continue
            xy = (round(h.position_mm[0], 4), round(h.position_mm[1], 4))
            if not bore.contains(_ShPt(*h.position_mm)):
                if xy not in channels:
                    channels.append(xy)
            elif xy not in vents:
                vents.append(xy)
    # A vent hole whose CENTRE is inside a bore lobe can still poke its Ø3
    # circle a hair past the bore 48-gon chord (fin_ble's SE hole sits 6.11 mm
    # from the 330° cell centre → circle reaches 7.61 vs the 7.6 bore). Left
    # alone, the tile's drill then ends on a ~0.25 mm sliver LEDGE of spacer
    # FR4 — unmillable, and the lens-shaped potting facet breaks the
    # full-stack FEA's fragment imprint (gmsh 'overlapping facets'). Swallow
    # each vent's full disc (+0.3 clearance) into the bore so the vent drops
    # cleanly into the compartment.
    if vents:
        bore = unary_union(
            [bore] + [_ShPt(*xy).buffer(_PHD / 2.0 + 0.3, quad_segs=16)
                      for xy in vents])
        if bore.geom_type != "Polygon":
            bore = bore.convex_hull
    bore_plain = [(x, y) for x, y in bore.exterior.coords][:-1]
    # Tie each through-drill into the cell compartment with a finger on the AFT-MOST
    # spacer (spacer_battery_1) only. Single vertical cell: a SHORT cutout from the
    # drill to the NEAREST bore edge (a small breach into the compartment, NOT the
    # long diagonal centre finger). Multi-cell: the original centre finger.
    if channels:
        fingered = unary_union([bore] + [_LS([(0.0, 0.0), xy]).buffer(_PW / 2.0)
                                         for xy in channels])
        if fingered.geom_type != "Polygon":
            fingered = fingered.convex_hull
        bore_fingered = [(x, y) for x, y in fingered.exterior.coords][:-1]
    else:
        bore_fingered = bore_plain

    for nm, b in boards.items():
        if not nm.startswith("spacer_battery"):
            continue
        # Only the aft-most battery spacer (spacer_battery_1, on the aft floor
        # side) gets the fingers that tie each channel into the bore.
        poly = bore_fingered if nm == "spacer_battery_1" else bore_plain
        b.cavity_placements.clear()
        b.cavity_placements.append(Placement(
            position_mm=(0.0, 0.0), rotation_deg=0.0, face="top",
            item=CavityRegion(name="cell_bores_merged", face="through",
                              exterior_polygon=poly, depth_mm=b.thickness_mm)))
        # Carry EVERY perimeter potting hole straight down as a through-channel.
        if b.geometry is not None:
            kept = [h for h in b.geometry.holes
                    if getattr(h, "tag", None) != "potting"]
            for xy in channels:
                kept.append(Hole(position_mm=xy, diameter_mm=_PHD,
                                 plated=False, tag="potting"))
            b.geometry.holes = kept


_PIEZO_DISC_R_MM = 5.0      # Ø10 Steminc SMD10T04R111 disc (SMD on fin_ble top)


# ── aft bench-array silkscreen groups ────────────────────────────────────
# Each functional run of pads gets a box on the BOTTOM silkscreen with its
# name above it. This is the legend a bench user reads before touching
# anything: which pads belong together, and — with the square pin-1 pad —
# which end a run starts at. Boxes are drawn AFTER _mark_spacer_cavity_silk
# (which clears every board's overlays before drawing the spacer-cut ghosts),
# so ordering of the two calls matters.
# (2026-11-19) The aft public interface moved onto the aft_end_cap's crown
# (smash.export.aft_cap). Pads that STAY on aft_end_board's bottom face:
AFT_CAP = "aft_end_cap"                       # virtual board tag of the cap contacts
_AFT_CUTTER_PADS = ("TP_ACT_CONFIRM", "TP_PARACHUTE_CUTTER_SET")
# Cap crown order (functional groups, cyclic): every group but the parachute ones.
AFT_CAP_GROUPS = None                         # filled below from _AFT_SILK_GROUPS_ALL
_AFT_SILK_GROUPS_ALL = [
    ("SPI",           ["TP_SPI_MOSI", "TP_SPI_CS_FIN", "TP_SPI_MISO", "TP_SPI_SCLK"]),
    ("FIN 1",         ["TP_FIN1_A1", "TP_FIN1_A2", "TP_FIN1_B1", "TP_FIN1_B2"]),
    ("FIN 3",         ["TP_FIN3_A1", "TP_FIN3_A2", "TP_FIN3_B1", "TP_FIN3_B2"]),
    ("FIN 2",         ["TP_FIN2_A1", "TP_FIN2_A2", "TP_FIN2_B1", "TP_FIN2_B2"]),
    ("FIN 4",         ["TP_FIN4_A1", "TP_FIN4_A2", "TP_FIN4_B1", "TP_FIN4_B2"]),
    ("CAN",           ["TP_CAN_N", "TP_CAN_P"]),
    ("BAT",           ["TP_BAT_RAW", "TP_BAT_PROT"]),
    ("PARACHUTE WIRES", [f"P_ACT_COL_{c}" for c in range(4)]),
    ("GROUND",        ["TP_GND_ACT"]),
    ("PARACHUTE CUTTER", ["TP_ACT_CONFIRM", "TP_PARACHUTE_CUTTER_SET"]),  # set + rail monitor
    ("HALL",          ["TP_FIN_HALL", "TP_HALL_VIN"]),
    ("I2C",           ["TP_I2C_SDA", "TP_I2C_SCL"]),
    ("JUMPSTART",     ["TP_JUMP_WAKE", "TP_JUMP_GND"]),
    ("PROGRAM_MP25",  ["TP_VDD", "TP_SWDIO", "TP_NRST", "TP_SWCLK",
                       "TP_MP25_GND1", "TP_SWO", "TP_MP25_GND2", "TP_BOOT0"]),
    ("GPIO",          ["TP_GPIO_0", "TP_GPIO_1", "TP_GPIO_2", "TP_GPIO_3"]),
    # (2026-11-21, user) dev board: console + SWD for the WBA55 and the G0B1
    ("CONSOLE",       ["TP_CONS_TX", "TP_CONS_RX"]),
    ("PROGRAM_WBA",   ["TP_WBA_SWDIO", "TP_WBA_SWCLK", "TP_WBA_NRST"]),
    ("PROGRAM_FIN",   ["TP_FIN_SWDIO", "TP_FIN_SWCLK", "TP_FIN_NRST"]),
]
AFT_CAP_GROUPS = [(lb, refs) for lb, refs in _AFT_SILK_GROUPS_ALL
                  if lb not in ("PARACHUTE WIRES", "PARACHUTE CUTTER")]
# aft_end_board's own bottom silk: the cutter pads (centre) + the clamp-tab ring
_AFT_SILK_GROUPS = [(lb, refs) for lb, refs in _AFT_SILK_GROUPS_ALL
                    if lb in ("PARACHUTE WIRES", "PARACHUTE CUTTER")]
# Schematic: aft_end's bottom-face pads drawn as these same groups (the
# PARACHUTE WIRES group also takes the 16 outbound restraint-wire pads).
_SCH_PAD_GROUPS = {"aft_end_board": [
    (label, refs + [f"P_ACT_WIRE_{i}" for i in range(16)] if label == "PARACHUTE WIRES" else refs)
    for label, refs in _AFT_SILK_GROUPS]}
_AFT_SILK_PAD_R_MM = 1.0     # Ø2.0 pad → 1.0 half-width
_AFT_SILK_MARGIN_MM = 0.15   # box clearance beyond the pad edge
                             # (kept tight: the caption for each row has
                             #  to fit in the gap to the row above)


# (2026-11-15) The launch piezo + comparator column live on aft_end's TOP,
# in the battery holder floor's underside pocket (spacer_step.piezo_pocket).
_PIEZO_POCKET_REFS = ("P_PIEZO", "R_PIEZO_BLEED", "R_COMP_SER", "R_THR1",
                      "R_THR2", "U_COMP_PZ", "C_COMP_PZ",
                      "R_PZ_TX", "C_PZ_TX",      # vibration-beacon coupling (2026-11-18)
                      "L_HEALTH_COIL")            # embedded coil (copper only)


def _place_health_coil(d, boards: dict) -> None:
    """Embed the magnetic health-beacon coil (smash.parts.coils) in
    aft_end_board, centred, after place_design and BEFORE the castellation
    contract (its BAT_PROT / HEALTH_COIL_RET nets need lanes). Copper only:
    manf="project", so it is exempt from the overlap guard and the BOM."""
    if "aft_end_board" not in boards or any(c.ref == "L_HEALTH_COIL" for c in d.chips):
        return
    from smash.state.topology.placement import Placement
    coil = add_health_coil(d, ref="L_HEALTH_COIL", board_tag="aft_end_board")
    _net(d, "BAT_PROT").connect(coil.pin("1"))
    _net(d, "HEALTH_COIL_RET").connect(coil.pin("2"))
    boards["aft_end_board"].chip_placements.append(Placement(
        position_mm=(0.0, 0.0), rotation_deg=0.0, item=coil, face="top", locked=True))


def _empty_aft_end_top(d) -> int:
    """(2026-11-15 aft reorder) aft_end_board keeps ONLY its bottom-face
    interface pads; every other part moves up to activation_interface (the
    battery-compartment ceiling) and reaches the pads through castellations
    + sleeve lanes. Its bare top face is where the Al compartment is glued
    and screwed on."""
    n = 0
    for c in d.chips:
        ref = getattr(c, "ref", "")
        if (getattr(c, "board_tag", None) == "aft_end_board"
                and not ref.startswith(("TP_", "P_ACT", "J_CAST_", "P_CELL_", "D_ACT_WIRE_"))
                and ref not in _PIEZO_POCKET_REFS):
            c.board_tag = "activation_interface"
            n += 1
    return n


def _plug_groups(d) -> list:
    """[(label, [(ref, net)])] — the aft board's bottom interface pads, in
    silk-group order, for the sleeve's plug ring."""
    ref_net = {}
    for n in d.nets:
        for rf, _p in n.pins:
            ref_net.setdefault(rf, n.name)
    return [(label, [(rf, ref_net[rf]) for rf in refs if rf in ref_net])
            for label, refs in _SCH_PAD_GROUPS["aft_end_board"]]


def _mark_aft_bench_silk(boards: dict) -> None:
    """Box + label each bench-pad group on aft_end_board's BOTTOM silkscreen.

    Single-pad groups (parachute wires, GROUND) get a label only — a box around one pad
    adds nothing and the copper is already unambiguous. Must run AFTER
    `_mark_spacer_cavity_silk`, which clears every board's silk_overlays."""
    b = boards.get("aft_end_board")
    if b is None:
        return
    at = {}
    for pl in getattr(b, "chip_placements", []):
        ref = getattr(getattr(pl, "item", None), "ref", None)
        if ref:
            at[ref] = pl.position_mm
    for label, refs in _AFT_SILK_GROUPS:
        pts = [at[r] for r in refs if r in at]
        if not pts:
            continue
        pad = _AFT_SILK_PAD_R_MM + _AFT_SILK_MARGIN_MM
        x0 = min(p[0] for p in pts) - pad
        x1 = max(p[0] for p in pts) + pad
        y0 = min(p[1] for p in pts) - pad
        y1 = max(p[1] for p in pts) + pad
        if len(pts) > 1:
            b.silk_overlays.append(
                ("B.SilkS",
                 [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                 label))
        else:
            # label-only: a degenerate span just above the lone pad
            b.silk_overlays.append(
                ("B.SilkS", [(x0, y1), (x1, y1)], label))


def _gap_neighbours(chain: list, boards: dict) -> list:
    """[(spacer_name, before_rigid, after_rigid)] for every gap in `chain`.
    A run of battery spacers is ONE gap (cell_floor_board ↔ fin_ble_board)."""
    out = []
    i = 0
    while i < len(chain):
        n = chain[i]
        b = boards.get(n)
        if b is None or not getattr(b, "is_spacer", False):
            i += 1
            continue
        j = i
        if n.startswith("spacer_battery_"):
            while (j + 1 < len(chain)
                   and chain[j + 1].startswith("spacer_battery_")):
                j += 1
        before = chain[i - 1] if i > 0 else None
        after = chain[j + 1] if j + 1 < len(chain) else None
        out.append((n, before, after))
        i = j + 1
    return out


def _mark_gap_hardware_silk(panel, boards: dict, fold_M: dict) -> None:
    """Silkscreen where each gap's hardware lands (2026-11-14 spacer-less
    tower), on the two facing board faces — the lower board's TOP (F.SilkS)
    and the upper board's BOTTOM (B.SilkS), in each board's own folded frame:
      • Al ring gaps: the ring band ± RING_CLEARANCE_MM (the standoff
        distance) — keep parts and exposed copper out;
      • battery ring: its inner contact edge (− clearance);
      • PEEK-standoff gaps: each standoff footprint + clearance.
    Clears every board's silk_overlays first (replaces the old spacer-cutout
    windows: spacers are no longer milled PCBs)."""
    from smash.parts.castellations import _local_xy
    from smash.export.spacer_step import (
        gap_kind, RING_CLEARANCE_MM,
        STANDOFF_D_MM, STANDOFF_R_MM, STANDOFF_ANGLES_DEG,
        ring_open_sector, ring_spec, battery_holder_cavity)
    import math as _m

    def circle(cx, cy, r, n=72):
        return [(cx + r * _m.cos(2 * _m.pi * k / n),
                 cy + r * _m.sin(2 * _m.pi * k / n)) for k in range(n)]

    def sector(M, r_in, r_out, a0, a1, n=48):
        """Closed annular-sector outline (physical angles a0 → a1) in the
        board's local frame."""
        fwd = [_local_xy(M, a0 + (a1 - a0) * k / n, r_out) for k in range(n + 1)]
        back = [_local_xy(M, a1 - (a1 - a0) * k / n, r_in) for k in range(n + 1)]
        return fwd + back

    for b in boards.values():
        if getattr(b, "silk_overlays", None):
            b.silk_overlays.clear()
    chain = list(panel.snake_chain or [])
    for sp, before, after in _gap_neighbours(chain, boards):
        kind = gap_kind(sp)
        for nbr, layer in ((before, "F.SilkS"), (after, "B.SilkS")):
            if nbr is None or nbr not in boards or nbr not in fold_M:
                continue
            ov = boards[nbr].silk_overlays
            if kind == "ring":
                rs = ring_spec(sp)
                RING_R_IN_MM, RING_R_OUT_MM, RING_LABEL = rs.r_in, rs.r_out, rs.label
                osec = ring_open_sector(sp)
                if osec:            # C-ring (2026-11-17): open behind this gap's slot
                    o0, o1 = osec
                    ov.append((layer, sector(fold_M[nbr], RING_R_IN_MM - RING_CLEARANCE_MM,
                                             RING_R_OUT_MM + RING_CLEARANCE_MM, o1, o0 + 360.0),
                               f"{RING_LABEL} (C) r{RING_R_IN_MM:g}-{RING_R_OUT_MM:g} "
                               f"+{RING_CLEARANCE_MM:g} KEEPOUT (open {o0:g}-{o1:g} deg)"))
                else:
                    ov.append((layer, circle(0, 0, RING_R_OUT_MM + RING_CLEARANCE_MM), ""))
                    ov.append((layer, circle(0, 0, RING_R_IN_MM - RING_CLEARANCE_MM),
                               f"{RING_LABEL} r{RING_R_IN_MM:g}-{RING_R_OUT_MM:g} "
                               f"+{RING_CLEARANCE_MM:g} KEEPOUT"))
            elif kind == "battery_holder":
                # cell cavity outline: the holder's end face bears on the
                # board everywhere OUTSIDE it (E top: cell tabs only inside);
                # on the upper board (fin_ble bottom) the crescent POCKETS are
                # the only part space (≤ pocket depth − 0.2 mm tall).
                # lower board (aft_end top): the holder's CLOSED FLOOR bears
                # everywhere except its piezo pocket (2026-11-15).
                from smash.export.spacer_step import piezo_pocket
                pk = piezo_pocket().simplify(0.02)
                ov.append((layer, [_local_xy(fold_M[nbr], _m.degrees(_m.atan2(y, x)),
                                             _m.hypot(x, y))
                                   for x, y in list(pk.exterior.coords)[:-1]],
                           "PIEZO POCKET in holder floor; Al bears elsewhere"))
                if layer == "B.SilkS":
                    from smash.export.spacer_step import (
                        BATT_TOP_RING_R_IN_MM, BATT_PART_CLEARANCE_MM,
                        BATT_HEADROOM_MM)
                    ov.pop()        # upper board: no cavity outline, just the ring
                    ov.append((layer, circle(0, 0, BATT_TOP_RING_R_IN_MM
                                             - BATT_PART_CLEARANCE_MM),
                               f"BATTERY CEILING — NO PARTS ({BATT_HEADROOM_MM:g} mm over "
                               "the cells' + pin wires)"))
            elif kind == "standoffs":
                for k, ang in enumerate(STANDOFF_ANGLES_DEG):
                    x, y = _local_xy(fold_M[nbr], ang, STANDOFF_R_MM)
                    ov.append((layer, circle(x, y, STANDOFF_D_MM / 2.0
                                             + RING_CLEARANCE_MM, 24),
                               "PEEK STANDOFF" if k == 0 else ""))
    # Slot-antenna board keep-outs (2026-11-17, antenna_slots.board_keepouts):
    # copper-free board-edge wedges behind a slot that fills its gap (S4) —
    # on the board face toward the slot, ALL copper layers.
    from smash.export.sleeve_step import stack_z_map
    from smash.parts.antenna_slots import board_keepouts
    zmap = stack_z_map(boards, chain)
    mids = {n: 0.5 * (z0 + z1) for n, (z0, z1) in zmap.items()
            if n in boards and not boards[n].is_spacer}
    ts = [z1 - z0 for n, (z0, z1) in zmap.items() if n in mids]
    for b, face, a0, a1, r_in, sname in board_keepouts(mids, sum(ts) / len(ts) if ts else 1.315):
        if b not in boards or b not in fold_M:
            continue
        boards[b].silk_overlays.append(
            ("F.SilkS" if face == "top" else "B.SilkS",
             sector(fold_M[b], r_in, 17.0, a0, a1),
             f"ANT {sname} KEEPOUT: NO COPPER r>{r_in:g} (all layers)"))


def _check_gap_hardware_clearance(panel, boards: dict) -> list:
    """Warn-list of chips that collide with gap hardware on the faces it
    touches: an Al ring band (± clearance); the battery holder — on the
    lower board's top only pads may sit (cell tabs), on the upper board's
    bottom parts must lie inside a holder pocket."""
    from smash.export.spacer_step import (
        gap_kind, RING_CLEARANCE_MM, ring_spec)
    from smash.parts.castellations import board_fold_transforms
    import math as _m
    issues = []
    fold_M = board_fold_transforms(panel, list(panel.snake_chain or []))
    for sp, before, after in _gap_neighbours(list(panel.snake_chain or []), boards):
        kind = gap_kind(sp)
        if kind == "standoffs":
            continue
        for nbr, face in ((before, "top"), (after, "bottom")):
            b = boards.get(nbr) if nbr else None
            if b is None:
                continue
            for p in b.chip_placements:
                c = p.item
                if p.face != face or getattr(c, "manf_pn", None) in (
                        "CASTELLATIONS", "LGA_lands"):
                    continue
                # copper-only parts (explicit 0 mm height, e.g. the embedded
                # health coil) occupy no volume in the gap — nothing to collide.
                # Pads (P_/TP_/J_) keep the check: cell-lead stubs stand proud.
                if (not str(getattr(c, "ref", "")).startswith(("P_", "TP_", "J_"))
                        and (getattr(c, "height_mm", None) == 0.0
                             or getattr(getattr(c, "footprint", None), "height_mm", None) == 0.0)):
                    continue
                sz = getattr(c, "size_mm", None) or getattr(
                    getattr(c, "footprint", None), "size_mm", None) or (0, 0)
                x, y = p.position_mm
                if kind == "ring":
                    # C-ring (2026-11-17): no ring over the antenna sector
                    from smash.export.spacer_step import ring_open_sector as _ros
                    _OS = _ros(sp)
                    M = fold_M.get(nbr, ((1, 0), (0, 1)))
                    px_, py_ = (M[0][0] * x + M[0][1] * y, M[1][0] * x + M[1][1] * y)
                    ang = _m.degrees(_m.atan2(py_, px_)) % 360.0
                    if _OS and _OS[0] + 5.0 <= ang <= _OS[1] - 5.0:
                        continue
                    # farthest corner of the ROTATED body rect (the old
                    # half-diagonal circle flagged parts that sit clear)
                    th = _m.radians(getattr(p, "rotation_deg", 0.0) or 0.0)
                    w2, h2 = sz[0] / 2.0, sz[1] / 2.0
                    rmax = max(_m.hypot(x + u * _m.cos(th) - v * _m.sin(th),
                                        y + u * _m.sin(th) + v * _m.cos(th))
                               for u in (-w2, w2) for v in (-h2, h2))
                    lo = ring_spec(sp).r_in - RING_CLEARANCE_MM
                    if rmax > lo:
                        issues.append(f"{nbr}/{face}: {c.ref} reaches the gap ring "
                                      f"band of {sp} (corner at r {rmax:.2f} > {lo:g})")
                    continue
                ref = getattr(c, "ref", "")
                if ref.startswith(("P_", "TP_", "J_")):
                    continue                       # pads: cell tabs / contacts
                if face == "top" and (ref in _PIEZO_POCKET_REFS or ref.startswith("D_ACT_WIRE_")):
                    from smash.export.spacer_step import piezo_pocket
                    from shapely.geometry import box as _bx
                    w, h = (sz[0], sz[1]) if sz else (0.5, 0.5)
                    if not piezo_pocket().contains(_bx(x - w / 2, y - h / 2, x + w / 2, y + h / 2)):
                        issues.append(f"{nbr}/top: {ref} outside the holder's piezo pocket")
                    continue
                if face == "top":
                    issues.append(f"{nbr}/top: {ref} under the battery holder / "
                                  "cells (only cell-tab pads allowed)")
                    continue
                # (2026-11-20, user) only LOW parts on the battery ceiling
                from smash.export.spacer_step import (BATT_HEADROOM_MM,
                                                      BATT_PART_CLEARANCE_MM)
                ht = (getattr(c, "height_mm", None)
                      or getattr(getattr(c, "footprint", None), "height_mm", None) or 0)
                if ht > BATT_HEADROOM_MM - BATT_PART_CLEARANCE_MM:
                    issues.append(f"{nbr}/bottom: {ref} too tall for the battery "
                                  f"headroom ({ht:g} mm > {BATT_HEADROOM_MM - BATT_PART_CLEARANCE_MM:g})")
    return issues


def _mark_spacer_cavity_silk(panel, boards: dict) -> None:
    """Draw each spacer's FINAL through-cut window onto the facing
    silkscreens of its two rigid neighbours, fold-mirrored into each
    neighbour's own frame: the next tile's B.SilkS (its bottom-face
    chips pocket into this spacer) and the prev tile's F.SilkS. A
    layout engineer can then move face chips on the tile and see the
    existing cutout boundary directly — staying inside it means the
    spacer needs no re-mill. Call LAST among the cavity passes (after
    the battery/radar cut post-processing) so the outline matches what
    the spacer actually ships with; re-runnable (clears its own
    overlays first)."""
    from smash.layout.cavities import fold_project, fold_same_row
    from smash.state.geometry.cavity import CavityRegion
    chain = panel.snake_chain or []
    for b in boards.values():
        if getattr(b, "silk_overlays", None):
            b.silk_overlays.clear()
    for i, name in enumerate(chain):
        sp = boards.get(name)
        if sp is None or not getattr(sp, "is_spacer", False):
            continue
        regions = [pl.item for pl in sp.cavity_placements
                   if isinstance(pl.item, CavityRegion)
                   and pl.item.face == "through"]
        if not regions or name not in panel.tiles:
            continue
        sp_row = panel.tiles[name][1]
        for nbr_i, silk in ((i - 1, "F.SilkS"), (i + 1, "B.SilkS")):
            if not (0 <= nbr_i < len(chain)):
                continue
            nbr = boards.get(chain[nbr_i])
            if nbr is None or chain[nbr_i] not in panel.tiles:
                continue
            # RIGID neighbours only. A spacer's neighbour can itself be
            # a spacer (the battery column interleaves no boards) — but
            # spacers carry no movable chips, and the stack pose is
            # boards-upright/spacers-FLIPPED, so spacer↔spacer is
            # flip×flip = identity: the single fold-mirror below would
            # draw the neighbour's bore ROTATED onto a tile whose own
            # Edge.Cuts already shows the same cut (the ghost diamonds
            # the user caught on the battery spacers).
            if getattr(nbr, "is_spacer", False):
                continue
            same_row = fold_same_row(panel.tiles, chain, name, chain[nbr_i])
            for k, reg in enumerate(regions):
                pts = [fold_project(x, y, same_row)
                       for (x, y) in reg.exterior_polygon]
                nbr.silk_overlays.append(
                    (silk, pts, f"{name} cutout" if k == 0 else None))


def _mark_battery_chip_clearance(boards: dict, panel) -> None:
    """Clear the bracket-tile parts that poke into the end battery spacers —
    a TARGETED cut, not the placer's square-everything through-cut. BOTH
    battery modes: whatever rigid tile brackets the battery column gets its
    body-height parts pocketed. Triple: cell_floor's formed cell solder tabs
    (height_mm on the tab chips) aft; fin_ble's bottom face nose-ward (the
    ceiling since the 2026-07-31 reorder) — its flat + contact pads solder
    flush, and its body-height bottom parts (un-embedded passives tucked
    into the compartment) get hugging pockets via the generic path below.
    Single: aft_end is the aft bracket — its tab lands + activate-bank parts
    clear the same way.

    The piezo-DISC branch is a round special case (a thin disc at a locked
    centre → modelled as a round through-hole, a big drill not a square);
    since the reorder the disc rides fin_ble's TOP face and never brackets
    a battery spacer, so the branch is inert — kept for correctness if the
    disc ever returns to a bracket face. Everything else with body height
    gets hugging pockets unioned together. Flat pads solder flush and need
    no clearance, and there is NO milled potting channel (the column pots
    through the threaded holes), so neither the square nor the diagonal
    channel-band the placer emits belongs here. The lands clear this
    region by avoiding the placed components (the pocket-era keepouts are
    gone with the pocket — the SMD disc is just a placed part now).

    Call AFTER _mark_battery_pockets (which clears + re-stamps the bore).
    No-op without a panel (the projection needs the fold sense).

    SMASH_FEA_SIMPLE_BORE=1 skips the chip-clearance extras entirely
    (bore-only battery cavities): the full-stack FEA (tools/run_stack_fea.py)
    fragments the potted tower into a conformal monolith, and the healed
    clearance bumps — correct for fab — put small arc features on the
    coplanar spacer interfaces that intermittently break gmsh's boundary
    recovery (PLC/overlapping-facet errors, 2026-08-03/04, feature set
    varies with the run-to-run packing shuffle). The extras are ~1–2 mm²
    pockets with no structural role, so the FEA tower drops them; NEVER
    ship a STEP built with this flag."""
    import os as _os
    if _os.environ.get("SMASH_FEA_SIMPLE_BORE") == "1":
        return
    from shapely.geometry import box as _box, Point as _ShPt
    from shapely.ops import unary_union
    from smash.state.geometry.cavity import CavityRegion
    from smash.state.topology.placement import Placement
    from smash.layout.placer.grid import footprint_bbox_mm
    from smash.layout.cavities import (fold_project, fold_same_row,
                                       rotated_bbox_mm)
    if panel is None:
        return
    chain = list(getattr(panel, "snake_chain", None) or [])
    tiles = panel.tiles or {}
    CLR = 0.3
    col_extras: list = []       # healed clearance extras, WHOLE column
    col_spacers: list = []      # every battery spacer, extras or not
    for i, nm in enumerate(chain):
        if not nm.startswith("spacer_battery"):
            continue
        sp = boards.get(nm)
        if sp is None:
            continue
        sp_row = tiles.get(nm, (None, None))[1]
        regions: list = []
        for nbr_name, face in (((chain[i - 1] if i > 0 else None), "top"),
                               ((chain[i + 1] if i + 1 < len(chain) else None),
                                "bottom")):
            nbr = boards.get(nbr_name) if nbr_name else None
            if nbr is None or getattr(nbr, "is_spacer", False):
                continue
            same_row = (fold_same_row(tiles, chain, nm, nbr_name)
                        if nm in tiles and nbr_name in tiles
                        else tiles.get(nbr_name, (None, None))[1] == sp_row)
            for p in nbr.chip_placements:
                if getattr(p, "face", None) != face:
                    continue
                c = p.item
                if getattr(c, "manf_pn", None) == "LGA_lands":
                    continue
                fp = getattr(c, "footprint", None)
                # The round piezo disc — a thin disc, not a body-height chip, so
                # it's modelled by its real Ø10 footprint, centred (the fold of a
                # centred disc is the same disc).
                if getattr(c, "ref", "") == "P_PIEZO":
                    regions.append(_ShPt(0.0, 0.0).buffer(
                        _PIEZO_DISC_R_MM + CLR, quad_segs=24))
                    continue
                # Everything else: clear only parts with real body height (the
                # comparator ring); flat project pseudo-parts sit flush.
                h = (getattr(c, "height_mm", None)
                     or (getattr(fp, "height_mm", None) if fp else None))
                if fp is None or not h:
                    continue
                lo_x, lo_y, hi_x, hi_y = footprint_bbox_mm(fp)
                we, he = rotated_bbox_mm(hi_x - lo_x, hi_y - lo_y,
                                         getattr(p, "rotation_deg", 0) or 0)
                cx, cy = fold_project(p.position_mm[0], p.position_mm[1], same_row)
                regions.append(_box(cx - we / 2 - CLR, cy - he / 2 - CLR,
                                    cx + we / 2 + CLR, cy + he / 2 + CLR))
        # Heal each clearance against the spacer's existing cuts (the
        # bore stamped by _apply_battery_bore): the battery-facing faces
        # keep their parts INSIDE the bore circles (2026-07-31 rule), so
        # most chimneys are fully swallowed by the through-cut (drop
        # them), and a rim-hugging part's box can poke past the bore
        # 48-gon by a hair — unioned raw, that leaves a <0.3 mm sliver
        # bump that no mill can cut and that breaks the full-stack FEA's
        # fragment imprint ('overlapping facets'). Residuals thinner
        # than 2×CLR are inflated to a machinable ≥1.2 mm bump with
        # COARSE 45° arc facets (default polygonization + 3-dp rounding
        # emits 0.01–0.06 mm micro-chords → sliver tets → fake ~1.7 GPa
        # nodal peaks).
        from shapely.geometry import Polygon as _ShPoly2
        existing = []
        for pl in sp.cavity_placements:
            reg = getattr(pl, "item", None)
            if isinstance(reg, CavityRegion) and len(
                    reg.exterior_polygon) >= 3:
                existing.append(_ShPoly2(reg.exterior_polygon))
        bore_u = unary_union(existing) if existing else None
        if bore_u is not None:
            healed = []
            for reg in regions:
                resid = reg.difference(bore_u)
                if resid.is_empty:
                    continue                    # inside the bore — no cut needed
                # Margin-only graze: the part's BODY clears the through-cut and
                # only its +CLR safety ring laps the bore edge. No FR4 conflict
                # → no pocket (inflating these was the source of the scalloped
                # bump artifacts on every battery spacer, 2026-08-28).
                if reg.buffer(-CLR).difference(bore_u).is_empty:
                    continue
                if resid.buffer(-CLR).is_empty:
                    healed.append(resid.buffer(2 * CLR, join_style=1,
                                               quad_segs=2))
                else:
                    healed.append(reg)
            regions = healed
        col_extras.extend(regions)
        col_spacers.append(nm)

    # ── ONE SHARED cut for the whole column ──────────────────────────
    # Adjacent battery spacers are coplanar face-to-face in the potted
    # tower; if their cavity outlines differ by sub-0.05 mm anywhere,
    # the full-stack FEA's OCC fragment imprints two nearly-identical
    # loops onto the shared plane and emits degenerate self-intersecting
    # sliver curves (13 h gmsh grind / PLC errors, 2026-08-03/04). So
    # every spacer gets the IDENTICAL polygon: bore ∪ ALL clearance
    # extras of the column (battery_1 additionally keeps its potting
    # fingers — a big, clean feature that imprints fine). A mitre-close
    # (+0.2/−0.2, join_style=2 so straight bore chords round-trip
    # bit-exact) erases any remaining sub-0.4 mm FR4 sliver between a
    # bump and the bore. Cutting the extras through ALL spacers costs
    # ~1–2 mm² of ring each but also puts them inside the shared
    # `cell_bores_merged` union, so the column's LGA land pattern
    # (which subtracts exactly that union) can never park a land over a
    # clearance void.
    if not col_extras:
        return
    from shapely.geometry import Polygon as _ShPoly3
    extras_u = unary_union(col_extras)
    for nm in col_spacers:
        sp = boards[nm]
        existing = []
        for pl in sp.cavity_placements:
            reg = getattr(pl, "item", None)
            if (isinstance(reg, CavityRegion)
                    and len(reg.exterior_polygon) >= 3):
                existing.append(_ShPoly3(reg.exterior_polygon))
        merged = unary_union(existing + [extras_u])
        merged = (merged.buffer(0.2, join_style=2)
                  .buffer(-0.2, join_style=2))
        polys = (list(merged.geoms) if merged.geom_type == "MultiPolygon"
                 else [merged])
        sp.cavity_placements.clear()
        for j, poly in enumerate(polys):
            ring = [(round(x, 3), round(y, 3))
                    for x, y in poly.exterior.coords[:-1]]
            # Collapse sub-0.05 mm edges left by the union + 3-dp rounding
            # (an 8 µm chord survives the mitre-close on convex arcs) —
            # identical inputs → identical output on every spacer, so the
            # shared-outline contract holds.
            dedup = []
            for pt in ring:
                if (not dedup or (pt[0] - dedup[-1][0]) ** 2
                        + (pt[1] - dedup[-1][1]) ** 2 >= 0.05 ** 2):
                    dedup.append(pt)
            if len(dedup) >= 2 and ((dedup[0][0] - dedup[-1][0]) ** 2
                                    + (dedup[0][1] - dedup[-1][1]) ** 2
                                    < 0.05 ** 2):
                dedup.pop()
            sp.cavity_placements.append(Placement(
                position_mm=(0.0, 0.0), rotation_deg=0.0, face="top",
                item=CavityRegion(
                    name=("cell_bores_merged" if j == 0
                          else f"{nm}__bore_chip_clearance_{j}"),
                    face="through", exterior_polygon=dedup,
                    depth_mm=sp.thickness_mm)))




def _generate_config(name: str, board_set: set[str]) -> None:
    """Build, place, and export one board configuration to
    dist/<name>/ (per-board folders + <name>.kicad_pcb). Splits the
    board set into a fold-ordered snake + branch stubs (nfc/qpd/camera)."""
    _set_battery_mode(name)            # always triple (single-cell mode dropped 2026-11-16)
    board_set = _config_boards(name, board_set)   # single drops cell_floor_board
    d = Design()
    _prime_power_rails(d)
    # (2026-11-19) DETERMINISTIC build order: iterating the `board_set` set
    # followed Python's per-process string hashing, so chip / net order —
    # and with it the placement-cache key — changed from run to run.
    ordered = ([bn for bn in _BOARD_BUILDERS if bn in board_set]
               + sorted(bn for bn in board_set if bn not in _BOARD_BUILDERS))
    for bn in ordered:
        _BOARD_BUILDERS[bn](d)
    snake = [b for b in _MASTER_SNAKE if b in board_set]
    # (2026-11-21) fixed nose: the config's payload (QPD / camera / USB) is an
    # ordinary STACK tile above compute — sized gap + ring, like the radar —
    # not a branch leaf (that was the modular crown's model).
    from smash.export import nose_interface as _NI
    if not _NI.MODULAR:
        snake += [pb for pb in _NI.PAYLOAD_BOARDS if pb in board_set and pb not in snake]
    branches = [
        (_BRANCH_PARENT[leaf][0], leaf,
         Flex(length_mm=_BRANCH_PARENT[leaf][1],
              branch_side=_BRANCH_PARENT[leaf][2],
              s_fold=_BRANCH_PARENT[leaf][3]))
        for leaf in _BRANCH_PARENT
        if leaf in board_set and _BRANCH_PARENT[leaf][0] in board_set and leaf not in snake
    ]
    from smash.parts.coo import apply_coo
    from smash.parts.orderable import apply_orderable
    apply_orderable(d)                    # (2026-11-22) generic passives → orderable MPNs
    apply_coo(d)                               # (2026-11-21) Mouser origin data
    _empty_aft_end_top(d)
    panel, boards = build_config_panel(snake, branches=branches,
                                       straight=_STRAIGHT_SNAKE,
                                       battery_length_mm=_compartment_mm())
    build_spacers(d, boards)
    _mark_preplace_keepouts(d, boards)         # battery-bracket tuck (pre-place)
    _mark_ring_band_keepouts(panel, boards)    # Al ring bands (every non-battery gap)
    # Economies of scale: shared chips lock to their maximalist positions,
    # so every config packs (and later mills/cuts) the identical board.
    ref = _MAX_REF or {}
    extra_locks: dict = {}
    for bn in ordered:
        extra_locks.update(ref.get("placements", {}).get(bn, {}))
    place_design(d, panel, boards, extra_locks=extra_locks or None)
    _place_health_coil(d, boards)              # embedded beacon coil (copper only)
    # Size each backbone spacer to the gap it bridges (placement-dependent, so
    # post-place); battery spacers keep their cell-length override.
    size_backbone_spacers(panel, boards)
    # After place_design — the placer clears every board's cavity_placements,
    # so the metal-block through-cut is appended here (not before).
    _mark_battery_pockets(boards)
    _mark_battery_chip_clearance(boards, panel)   # round piezo + comparator clear
    # Backbone LGA interconnect — same post-processing as the maximalist panel,
    # so every shippable config carries the power/gnd/CAN lands through its
    # spacers (not just the maximalist build). Joints shared with the
    # maximalist build replay its patterns + nets verbatim (economies of
    # scale); truncated-away joints still fab their tile-face fields.
    # Castellations replay the maximalist lane contract (economies of scale:
    # identical board edges in every config; absent nets keep a bare pad).
    _cfgM = board_fold_transforms(panel, list(panel.snake_chain))
    _, _cast = place_castellations(
        d, panel, boards, connect=lambda net, pin: _net(d, net).connect(pin),
        contract=ref.get("castellations"))
    # (2026-11-15) No branch-flex launch strips: the QPD / camera links run on
    # the LDS nose cone from castellations (_CONE_EXITS → castellation contract).
    _apply_companion_reference_layout(d, boards)
    _apply_activation_reference_layout(d, boards)
    # Economies of scale: adjacency-conforming boards inherit the maximalist
    # cavities verbatim (they were milled from the same inherited chip
    # placements, but the maximalist copy is authoritative — panel-fold and
    # flex-chord clipping must not re-diverge them). Non-conforming boards
    # (novel adjacency, e.g. a re-ordered battery column) keep
    # their own and are reported.
    _conform, _nonconform = _reference_conforming(panel, boards, ref)
    _cav_n = 0
    _alias = _nose_slot_alias(ref.get("chain") or [])
    for bn in _conform:
        rc = (ref.get("cavities") or {}).get(
            _alias(bn) if getattr(boards[bn], "is_spacer", False) else bn)
        if rc is not None:
            boards[bn].cavity_placements[:] = list(rc)
            _cav_n += 1
    if _nonconform:
        print(f"  WARNING: {name}: non-conforming board(s) — NOT the shared "
              f"maximalist part: {', '.join(_nonconform)}", file=sys.stderr)
    _mark_gap_hardware_silk(panel, boards, _cfgM)   # Al rings / standoffs → silk
    _mark_aft_bench_silk(boards)                # bench-pad group boxes + labels
    # Self-contained config folder at dist/<config>/: <config>.kicad_pcb
    # + per-board <tile>/ subfolders (3D models next to each tile).
    # Folded-tower stackup for this config stays at dist/ (see below).
    cfg_dir = _PCB_OUT / name
    cfg_dir.mkdir(parents=True, exist_ok=True)
    out = cfg_dir / f"{name}.kicad_pcb"
    r = write_kicad_panel(d, panel, boards, out)
    write_blank_drawing_sheet(out)
    # This config's schematic (same projection as the maximalist one, but
    # only this config's boards/spacers/LGA nets) at <config>/schematic/.
    sch = write_kicad_schematic(d, cfg_dir / "schematic", project=name,
                                pad_groups=_SCH_PAD_GROUPS)
    for _w in sch["warnings"]:
        print(f"  WARN {name} schematic: {_w}")
    sch_msg = (f"schematic/{name}.kicad_sch ({sch['n_boards']} boards, "
               f"{sch['n_parts']} parts, {sch['n_nets']} nets)")
    # This config's spacers (cadquery). The snake adjacencies differ per
    # config — e.g. flight↔radar exists in core_radar but not the
    # maximalist panel — and a spacer's cavities are milled from its two
    # neighbours' chip faces in this fold, so each variant gets its own
    # spacer set under <config>/<spacer>/.
    # Per-board .kicad_pcb are ALWAYS written (cheap; the component stackup
    # assembly folds them) — _export_tile_steps skips its own STEP/STL when
    # SMASH_STEP_EXPORT=0. The heavy 3D bodies (cadquery spacers + stackup +
    # waveguide) stay gated so a fast netlist/panel run skips them.
    tiles_msg = _export_tile_steps(
        d, panel, boards, cfg_dir,
        cutouts_ref={bn: c for bn, c in (ref.get("cutouts") or {}).items()
                     if bn in _conform})
    if _STEP_ENABLED:
        from smash.export.spacer_step import write_gap_hardware
        sp = write_gap_hardware(boards, list(panel.snake_chain), cfg_dir)
        if _STACKUP_ALL:
            if _FEA_STEP:
                _export_stackup(d, boards, panel.snake_chain,
                                _DIST / f"stackup_{name}.step",
                                tiles=panel.tiles,
                                contract=ref.get("castellations"))
            print("  " + _export_components_stackup(
                boards, panel.snake_chain, cfg_dir,
                _DIST / f"stackup_{name}_components.step",
                tiles=panel.tiles, nose_key=name))
            if _PRINT_STL:
                _export_print_stls(boards, panel.snake_chain, cfg_dir, cfg_dir)
        wg_msg = (_export_waveguide_stubs(boards, cfg_dir / "waveguide_stubs.step")
                  if _FEA_STEP else "waveguide stubs skipped (SMASH_FEA_STEP=0)")
        steps_msg = f"{len(sp)} spacers; {name}/ {tiles_msg}; {wg_msg}"
    else:
        steps_msg = f"{name}/ {tiles_msg}; 3D STEP skipped"

    # Per-reflow board-to-board assembly files (opt-in). Runs LAST so the
    # board-as-component chips it appends don't perturb the panel/tile writes
    # above; 3D models attach from this config's STEP dir when present.
    asm_msg = ""
    if _GEN_ASSEMBLIES:
        from smash.export.stack_assembly import build_stack_assembly_files
        res = build_stack_assembly_files(
            d, panel, boards, _ASSEMBLY_DIR / name,
            connect=lambda net, pin: _net(d, net).connect(pin),
            step_dir=(_PCB_OUT / name) if _STEP_ENABLED else None)
        asm_msg = f"; {len(res)} reflow files → assembly/{name}/"

    print(f"  {name}: {out.name} "
          f"({r['n_tiles']} tiles, {r['n_footprints']} footprints, "
          f"{r['n_flex_strips']} flex strips, "
          f"{sum(_cast.values())} castellations, "
          f"stack {panel.stack_height_mm(boards):.1f} mm; {steps_msg}{asm_msg})")
    print(f"    {sch_msg}")
    print(f"    shared-part inheritance: {len(extra_locks)} placement locks, "
          f"{_cav_n} boards' cavities inherited"
          + (f"; NON-CONFORMING: {len(_nonconform)}" if _nonconform else ""))


def main() -> int:
    d = Design()
    _set_battery_mode("maximalist")  # triple — the 3-cell default (flip 2026-07-28)

    _prime_power_rails(d)

    # Boards (ordered smallest → largest)
    build_qpd_module(d)
    build_radar_nose_io(d)
    build_usb_nose(d)
    build_camera_module(d)
    build_aft_end_board(d)
    # (2026-11-15) cell_floor_board dropped in every mode (aft reorder).
    build_activation_interface(d)
    build_radar_module_awr1843aop(d)
    build_companion_compute(d)
    # companion_io dropped: its parallel NAND moved to companion_compute as
    # two SPI-NAND dies; its G0B1+TCAN CAN node is retired with the tile.
    build_power_board(d)
    build_wakeup_board(d)   # also folds in the IMU/mag (build_flight_board, board_tag="wakeup_board")
    build_fins_module(d)    # fin actuators — on fin_ble_board (2026-07-30 crowding split off wakeup)

    # Build the panel first: the fold optimiser picks the snake order and
    # materialises one spacer Board per gap, so the spacer chips can only
    # be created once those Boards exist.
    from smash.parts.coo import apply_coo
    from smash.parts.orderable import apply_orderable
    apply_orderable(d)                    # (2026-11-22) generic passives → orderable MPNs
    print(f"country of origin: {apply_coo(d)} parts from Mouser data (smash/data/coo_mouser.json)")
    _moved = _empty_aft_end_top(d)
    print(f"aft reorder: {_moved} aft_end top-face parts → activation_interface")
    panel, boards = build_panel(straight=_STRAIGHT_SNAKE,
                                battery_length_mm=_compartment_mm())
    build_spacers(d, boards)
    _mark_preplace_keepouts(d, boards)         # battery-bracket tuck (pre-place)
    _mark_ring_band_keepouts(panel, boards)    # Al ring bands (every non-battery gap)

    # ── place + export KiCad PCBs ────────────────────────────────────
    report = place_design(d, panel, boards)
    _place_health_coil(d, boards)              # embedded beacon coil (copper only)
    # Size each backbone spacer to the gap it bridges (placement-dependent, so
    # post-place); battery spacers keep their cell-length override.
    _sized = size_backbone_spacers(panel, boards)
    print(f"Backbone spacers sized to their gaps ({len(_sized)}): "
          + ", ".join(f"{v} mm" for v in _sized.values())
          + "  (was 4.0 mm fixed)")
    # After place_design — the placer clears every board's cavity_placements,
    # so the metal-block through-cut is appended here (not before).
    _mark_battery_pockets(boards)
    _mark_battery_chip_clearance(boards, panel)   # round piezo + comparator clear

    if report.untagged_refs:
        print(f"WARN: {len(report.untagged_refs)} chips have no board_tag "
              f"(skipped): {report.untagged_refs[:5]}{'…' if len(report.untagged_refs) > 5 else ''}")
    _unk = [r for r in report.unknown_board_refs if r[1] != AFT_CAP]   # cap contacts: virtual board
    if _unk:
        print(f"WARN: {len(_unk)} chips reference unknown boards: {_unk[:5]}")
    if report.any_overflow:
        bad = [s.board_name for s in report.per_board if s.overflow]
        print(f"WARN: {len(bad)} board(s) overflow: {bad}")

    # Geometric guard: a LOCKED placement overlapping anything is a hard
    # error (the placer can't move it); packed-vs-packed near-misses stay a
    # warning. assert_no_locked_overlaps raises on the former, returns the
    # latter.
    from smash.validators import assert_no_locked_overlaps
    overlaps = assert_no_locked_overlaps(boards,
                                         accepted=_ACCEPTED_LOCKED_OVERLAPS)
    if overlaps:
        print(f"WARN: {len(overlaps)} packed chip-overlap(s):")
        for iss in overlaps[:10]:
            print(f"  {iss}")

    print(f"Placed {sum(s.n_packed + s.n_locked for s in report.per_board)} chips "
          f"across {sum(1 for s in report.per_board if s.n_packed + s.n_locked > 0)} "
          f"boards; {report.n_cavities_added} cavities attached to spacers.")

    # Board-to-board LGA interconnect — POST-PROCESSING after the placer:
    # adaptive square solder lands packed into the FREE area of each joint
    # (around components / cavities / potting holes), carrying the power/gnd/CAN
    # backbone through the FR4-spacer interposers (replaces the snake flexes).
    # (2026-11-14) LGA lands REPLACED by board-edge castellations: the side-
    # wall interconnect runs on the LDS sleeve; each cross-board net owns a
    # fixed physical angle (lane) on the stack. Spacers are no longer PCBs.
    _foldM = board_fold_transforms(panel, list(panel.snake_chain))
    _cast_contract, _cast = place_castellations(
        d, panel, boards, connect=lambda net, pin: _net(d, net).connect(pin),
        cone_exits=_CONE_EXITS)
    # Lane budget under both policies (layout-EE ask: one lane per signal).
    from smash.parts.castellations import lane_budget
    for _pol, _b in lane_budget(d, panel, boards, cone_exits=_CONE_EXITS).items():
        print(f"  lane budget [{_pol}]: {_b['n_used']}/{_b['n_angles']} signal-sector angles"
              + (f", {len(_b['overflow'])} net(s) DON'T FIT: {', '.join(_b['overflow'])}"
                 if _b["overflow"] else ", all nets fit"))
    # (2026-11-15) No plug ring: aft_end_board's bottom-face interface stays
    # the external interface; `_plug_groups(d)` → place_castellations(…,
    # plug_groups=…) would move it onto the sleeve.
    # (2026-11-15) No branch-flex launch strips: the QPD / camera links run on
    # the LDS nose cone from castellations (_CONE_EXITS → castellation contract).
    _apply_companion_reference_layout(d, boards)
    _apply_activation_reference_layout(d, boards)
    _mark_gap_hardware_silk(panel, boards, _foldM)  # Al rings / standoffs → silk
    _mark_aft_bench_silk(boards)                # bench-pad group boxes + labels

    # ── capture the economies-of-scale reference for the config builds ──
    # Everything a config must fab IDENTICALLY comes from here: final chip
    # placements (post EE-layout), the LGA joint patterns + nets (the joint
    # capture above, scaffold radar↔nose joint included — its tile-face
    # lands survive the spacer drop), every board's milled cavities, and
    # each rigid tile's outline chords as cut in THIS panel.
    global _MAX_REF
    from types import SimpleNamespace as _NS
    from smash.export.kicad_pcb import (_cutouts_for_tile as _ref_cuts,
                                        _DEFAULT_FLEX_WIDTH_MM as _ref_fw)
    from smash.layout.placer.flex_sizing import compute_link_widths as _ref_clw
    _ref_lw, _ = _ref_clw(d, panel)
    _MAX_REF = {
        "joints": {},
        "castellations": _cast_contract,
        "chain": list(panel.snake_chain),
        "placements": {
            bn: {pl.item.ref: _NS(position_mm=pl.position_mm,
                                  rotation_deg=pl.rotation_deg,
                                  face=pl.face)
                 for pl in b.chip_placements
                 if getattr(pl.item, "ref", None)
                 and getattr(pl.item, "manf_pn", None) != "LGA_lands"}
            for bn, b in boards.items()
            if not getattr(b, "is_spacer", False)},
        "cavities": {bn: list(b.cavity_placements)
                     for bn, b in boards.items()},
        "cutouts": {bn: _ref_cuts(bn, panel, _ref_fw, _ref_lw)
                    for bn, b in boards.items()
                    if not getattr(b, "is_spacer", False)
                    and getattr(b, "kind", "rigid") != "flex"
                    and b.geometry is not None},
    }
    print(f"Castellations: {sum(_cast.values())} pads on {len(_cast)} boards, "
          f"{len(_cast_contract['lanes'])} nets on {_cast_contract['n_used']}/"
          f"{_cast_contract['n_angles']} lanes "
          f"({', '.join(f'{k}={v}' for k, v in _cast.items())})")

    # Geometric guard: no neighbour-tile chip may collide with a spacer's FR4
    # in the folded tower — each spacer cavity must clear the chips on the face
    # that points at it (fold-parity aware). Catches the class of bug where a
    # post-battery-compartment board folds inverted and the milled window lands
    # under the wrong face.
    _clr = _check_gap_hardware_clearance(panel, boards)
    if _clr:
        from collections import Counter as _C
        _by = _C(i.split(":", 1)[0] for i in _clr)
        print(f"WARN: {len(_clr)} part(s) collide with gap hardware (Al rings / "
              f"battery holder): " + ", ".join(f"{k}={v}" for k, v in _by.items()))
        for _iss in _clr[:10]:
            print(f"  {_iss}")

    out = _DIST / "maximalist_canonical_netlist.json"
    summary = write_canonical_netlist(d, out)
    print(f"Canonical netlist written to {out.relative_to(REPO)} "
          f"({summary['n_parts']} parts, {summary['n_nets']} nets)")

    # Whole-system schematic (documentation projection of the same netlist).
    sch_dir = _DIST / "schematic"
    shutil.rmtree(sch_dir, ignore_errors=True)
    # The LDS sleeve (2D unroll) joins the system schematic as its own
    # "sleeve" frame — on a COPY, so the PCB / BOM outputs never see it.
    import copy as _copy
    from smash.export.sleeve_layout import add_sleeve_schematic_parts
    _sch_d = _copy.deepcopy(d)
    _sl_refs = add_sleeve_schematic_parts(
        _sch_d, _cast_contract, connect=lambda net, pin: _net(_sch_d, net).connect(pin))
    _sch_groups = dict(_SCH_PAD_GROUPS or {})
    sch = write_kicad_schematic(_sch_d, sch_dir, pad_groups=_sch_groups)
    print(f"  sleeve in schematic: {', '.join(_sl_refs)}")
    print(f"KiCad schematic written to {sch_dir.relative_to(REPO)}/smash.kicad_sch "
          f"({sch['n_boards']} boards, {sch['n_parts']} parts, "
          f"{sch['n_nets']} nets, {sch['n_symbols']} symbols)")
    for _w in sch["warnings"]:
        print(f"  WARN schematic: {_w}")

    # Start dist/ clean of generated PCB/3D artifacts. Netlist above is
    # rewritten in place. Hand-edited .kicad_pcb files (stem ≠ directory
    # name and ≠ stackup) used to be salvaged to dist/kicad_pcbs_user/ (off since 2026-11-22).
    pcb_out = _DIST
    keep_root = _DIST / "kicad_pcbs_user"

    def _salvage_stray_pcbs(root: pathlib.Path) -> None:
        if not root.exists():
            return
        for f in sorted(root.rglob("*.kicad_pcb")):
            try:
                rel = f.relative_to(root)
            except ValueError:
                continue
            if keep_root in f.parents or f.stem in (f.parent.name, "stackup", "smash_evb_panel"):
                continue
            dest = keep_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            f.replace(dest)
            print(f"preserved hand-edit: {f.relative_to(REPO)} → "
                  f"{dest.relative_to(REPO)}")

    # (2026-11-22, user) salvage OFF: the tile PCBs are named by project
    # letter (H_boost, L_power, …), so every generated tile looked like a
    # "hand edit" and was copied — overwriting — into kicad_pcbs_user on each
    # run. Generated outputs are disposable; nothing is salvaged any more.
    shutil.rmtree(pcb_out / "kicad_pcbs_smash", ignore_errors=True)
    shutil.rmtree(_MAXIMALIST_DIR, ignore_errors=True)
    shutil.rmtree(_ASSEMBLY_DIR, ignore_errors=True)
    for cfg_name in CONFIGS:
        shutil.rmtree(pcb_out / cfg_name, ignore_errors=True)
    for name in (
        "smash_evb_panel.kicad_pcb", "smash_evb_panel.kicad_pro",
        "smash_evb_panel.kicad_prl", "smash_evb_panel.kicad_wks",
        "stackup.kicad_pcb", "stackup.kicad_pro",
        "stackup.kicad_prl", "stackup.kicad_wks",
        "stackup.kicad_sch", "stackup.kicad_sym", "sym-lib-table", "fp-lib-table",
        "stackup.step", "stackup_no_potting.step", "stackup_components.step",
        "consolidated_stackup.stl", "housing.stl", "waveguide_stubs.step",
    ):
        (pcb_out / name).unlink(missing_ok=True)
    for extra in pcb_out.glob("stackup_*.step"):
        extra.unlink(missing_ok=True)
    pcb_out.mkdir(parents=True, exist_ok=True)

    # Panel-level file (primary output — every board + flex strips on
    # one canvas, opens directly in KiCad).
    panel_path = pcb_out / "stackup.kicad_pcb"
    from smash.export.kicad_sch import panel_footprint_refs
    r = write_kicad_panel(d, panel, boards, panel_path,
                          link_schematic=set(panel_footprint_refs(panel, boards)))
    write_blank_drawing_sheet(panel_path)
    # The schematic joins the stackup PCB as ONE KiCad project
    # (stackup.kicad_pro → stackup.kicad_pcb + stackup.kicad_sch), every
    # footprint linked to its symbol like the per-board projects (net names,
    # Footprint and Datasheet fields as on the panel → clean schematic
    # parity). The sleeve frame stays in dist/schematic/smash.kicad_sch only
    # (it has no footprints on this PCB).
    _st_sch = write_panel_schematic(d, panel, boards, pcb_out, project="stackup",
                                    pad_groups=dict(_SCH_PAD_GROUPS or {}))
    try:
        _st_cli = find_kicad_cli()
    except KiCadCliNotFound:
        _st_cli = None
    if _st_cli is not None:
        relink_multi_unit_footprints(panel_path, pcb_out / "stackup.kicad_sch", _st_cli)
    print(f"KiCad schematic joined the stackup project: "
          f"{(pcb_out / 'stackup.kicad_sch').relative_to(REPO)} "
          f"({_st_sch['n_parts']} parts, {_st_sch['n_symbols']} symbols)")
    print(f"KiCad panel written to {panel_path.relative_to(REPO)} "
          f"({r['n_tiles']} tiles, {r['n_footprints']} footprints, "
          f"{r['n_flex_strips']} flex strips, {r['n_holes']} holes, "
          f"{r['n_cavities']} cavity polygons, "
          f"stack {panel.stack_height_mm(boards):.1f} mm)")
    # Per-board .kicad_pcb are ALWAYS written (cheap; the component stackup
    # folds them) — _export_tile_steps skips its own STEP/STL when
    # SMASH_STEP_EXPORT=0. The heavier 3D bodies (kicad-cli tile STEPs +
    # cadquery 4 mm spacer bodies + folded-tower stackup for FEA) stay gated so
    # a fast netlist/panel run skips them. KiCad's panel STEP uses a uniform
    # 1.6 mm thickness (wrong for the rigid-flex spacers), hence cadquery.
    print(f"  tile PCBs: {_export_tile_steps(d, panel, boards, _MAXIMALIST_DIR)}")
    # Gap hardware (Al rings, battery ring, PEEK standoffs) — cheap cadquery
    # bodies, written on every run; spacers are no longer PCBs.
    try:
        from smash.export.spacer_step import write_gap_hardware
        _gh = write_gap_hardware(boards, list(panel.snake_chain), _MAXIMALIST_DIR)
        print(f"  gap hardware STEPs: {len(_gh)} "
              f"({', '.join(sorted({r['kind'] for r in _gh}))}) → "
              f"{_MAXIMALIST_DIR.relative_to(REPO)}/<gap>/")
        from smash.export.sleeve_step import write_sleeve_and_mould
        _sl = write_sleeve_and_mould(boards, list(panel.snake_chain),
                                     _cast_contract, _MAXIMALIST_DIR)
        # (2026-11-19) aft public interface: the aft_end_cap crown
        from smash.export.aft_cap import write_aft_cap
        _ac = write_aft_cap(_cast_contract, _MAXIMALIST_DIR / "sleeve" / "aft_end_cap")
        if _ac:
            print(f"  aft_end_cap: {_ac['n_signal']} crown contacts, solid "
                  f"{'ok' if _ac['valid'] and _ac['solids'] == 1 else 'INVALID'} → "
                  f"{_ac['dir'].relative_to(REPO)}/ (+ contact map, face drawing)"
                  + (f"; ⚠ no tooth for {', '.join(_ac['missing'])}" if _ac["missing"] else ""))
        from smash.export.sleeve_layout import (write_unrolled_sleeve,
                                                write_sleeve_copper_step)
        _ul = write_unrolled_sleeve(boards, list(panel.snake_chain), _cast_contract,
                                    _sl["sleeve_dir"] / "sleeve_unrolled.kicad_pcb")
        from smash.export.sleeve_layout import merge_unrolled_sleeve_into_panel
        _mg = merge_unrolled_sleeve_into_panel(
            _sl["sleeve_dir"] / "sleeve_unrolled.kicad_pcb", panel_path)
        print(f"  2D unroll merged into {panel_path.name} ({_mg['n_items']} items, below the tiles)")
        _cu = write_sleeve_copper_step(boards, list(panel.snake_chain), _cast_contract,
                                       _sl["sleeve_dir"] / "sleeve_copper.step")
        print(f"  unrolled sleeve layout: {_ul['width_mm']:.1f} × {_ul['height_mm']:.1f} mm, "
              f"{_ul['n_lanes']} lanes, {_ul['n_vias']} vias, {_ul['n_plug']} plug-ring contacts, {_ul['n_antennas']} antenna "
              f"placeholders → sleeve/sleeve_unrolled.kicad_pcb (+ sleeve_copper.step, "
              f"{_cu['n_bodies']} bodies)")
        for _cfg, _c in _sl["cups"].items():
            print(f"  PEEK-LDS sleeve + nose cap {_cfg}: {_c['n_vias']} vias on "
                  f"{_c['n_active_lanes']} active lanes, nose {_c['nose_mm']:.2f} mm "
                  f"above the payload, {_c['height_mm']:.1f} mm → "
                  f"{_c['dir'].relative_to(REPO)}/ (+ pot-in-cup fixture)")
            for _w in _c["warnings"]:
                print(f"    WARNING: {_w}")
    except ImportError:
        print("  gap hardware STEPs: SKIPPED (cadquery not installed)")
    if _STEP_ENABLED:
        if _FEA_STEP:                    # mass-block FEA tower: opt-in
            print(f"  {_export_stackup(d, boards, panel.snake_chain, pcb_out / 'stackup.step', tiles=panel.tiles, contract=_cast_contract)}")
        print(f"  {_export_components_stackup(boards, panel.snake_chain, _MAXIMALIST_DIR, pcb_out / 'stackup_components.step', tiles=panel.tiles)}")
        if _PRINT_STL:                   # 3D-print STLs: opt-in
            print(f"  {_export_print_stls(boards, panel.snake_chain, pcb_out, _MAXIMALIST_DIR)}")
        if _FEA_STEP:
            print(f"  {_export_waveguide_stubs(boards, pcb_out / 'waveguide_stubs.step')}")
    else:
        print("  3D STEP (spacers + stackup): SKIPPED (SMASH_STEP_EXPORT=0); per-board PCBs written")
    # Stackup project made portable LAST (like the boards): its own
    # footprints/SmashStackup.pretty + 3dmodels/ + fp-lib-table, the PCB's
    # footprints renamed SmashStackup:<entry> — the names stackup.kicad_sch
    # already carries, so schematic parity and Update PCB from Schematic
    # resolve against the project's own library.
    from smash.export.portable_project import write_portable_project
    try:
        _pp = write_portable_project(panel_path)
        print(f"  stackup project portable: {_pp['n_footprints']} footprints, "
              f"{_pp['n_models']} 3D models"
              + (f"; conflicts: {', '.join(_pp['conflicts'])}" if _pp["conflicts"] else "")
              + (f"; {len(_pp['missing_models'])} model(s) not found" if _pp["missing_models"] else ""))
    except Exception as e:                       # keep the run resilient
        print(f"  WARN stackup portable project: {type(e).__name__}: {e}")

    # ── board-configuration variants ────────────────────────────────
    # Each config re-places + re-exports a separate panel, so for fast
    # iteration limit what gets built:
    #   SMASH_SKIP_CONFIGS=1   → skip them all (just the maximalist panel)
    #   SMASH_CONFIGS=a,b,...  → build only those (default: all). Unknown names
    #                            error so a typo doesn't silently build nothing.
    if os.environ.get("SMASH_SKIP_CONFIGS", "0") == "1":
        print("Board configurations: SKIPPED (SMASH_SKIP_CONFIGS=1)")
    else:
        sel = os.environ.get("SMASH_CONFIGS", "").strip()
        if sel:
            want = [s.strip() for s in sel.split(",") if s.strip()]
            unknown = [w for w in want if w not in CONFIGS]
            if unknown:
                raise SystemExit(
                    f"SMASH_CONFIGS: unknown config(s) {unknown}; "
                    f"valid: {sorted(CONFIGS)}")
            chosen = {w: CONFIGS[w] for w in want}
        else:
            chosen = dict(CONFIGS)
        print(f"Board configurations ({len(chosen)}/{len(CONFIGS)}"
              + (f": {', '.join(chosen)}" if sel else "") + "):")
        for cfg_name, cfg_boards in chosen.items():
            _generate_config(cfg_name, cfg_boards)

    # (2026-11-21) DRC / ERC summary — warnings, never a blocker
    if os.environ.get("SMASH_SKIP_CHECKS") != "1":
        from smash.export.checks import report as _check_report
        _cfg_pcbs = [pcb_out / c / f"{c}.kicad_pcb" for c in CONFIGS]
        _check_report(pcbs=[panel_path, *_cfg_pcbs],
                      schematics=[sch_dir / "smash.kicad_sch"], root=REPO)
        try:                                             # datasheet electrical rules
            from smash.validators.electrical import report as _erc_report
            _erc_report(d, "tower (maximalist netlist)")
        except Exception as _e:
            print(f"Electrical rules check: SKIPPED ({type(_e).__name__}: {_e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
