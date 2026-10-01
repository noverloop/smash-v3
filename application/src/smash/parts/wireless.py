"""Wireless module factories (WiFi/BT, cellular, etc.)."""

from __future__ import annotations

from smash.state import Chip, Footprint
from smash.parts._artifacts import (
    pads_from_kicad_mod, outline_polygon, build_pins, src, datasheet_ref,
)
from smash.parts._slug import canonical_id


def add_lbee5kl1yn_814(design, ref: str, **overrides) -> Chip:
    """Murata LBEE5KL1YN-814 — WiFi 4 (802.11 b/g/n 2.4 GHz) + Bluetooth
    5.0 module, Cypress CYW43012-based, SDIO + UART interfaces,
    LGA-style module package."""
    pn = "LBEE5KL1YN-814"
    fp_mod = src(pn, "LBEE5KL1YN814.kicad_mod")
    fields = dict(
        manf="Murata", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "WiFi 4 + BT 5.0 module (Cypress CYW43012), SDIO + UART, "
            "embedded antenna option"
        ),
        datasheet=datasheet_ref(pn, "LBEE5KL1YN.pdf"),
        package="Murata Type 1YN module",
        temp_range_c=(-40, 85),
        vcc_nominal_v=3.3,
        # ── thermal (Murata LBEE5KL1YN datasheet, no thermal section) ──
        # Module DS quotes module-level current at VBAT=3.6V, not
        # junction temp or ΘJC (it's a packaged module — silicon is
        # the Cypress CYW43012, not directly accessible). Smash use
        # case: BT idle most of the time (programming uplink only
        # active on-ground), Wi-Fi TX bursts when programming.
        p_active_w=0.10,                    # 28 mA × 3.6V — BT idle DH5 typ (DS §11.4)
        p_max_w=1.33,                       # 370 mA × 3.6V — Wi-Fi 11b TX peak (DS §11.x)
        rth_jc_cw=5.0,                      # *estimate (NOT DS) — LGA-module
                                            # internal SoC (Cypress CYW43012)
                                            # junction-to-module-bottom typical
        tj_max_c=105.0,                     # *estimate (NOT DS) — internal Si
                                            # industrial junction limit; module
                                            # DS only quotes operating Top -30..+70
        standards=["RoHS"],
        pins=build_pins(src(pn, f"{pn}.kicad_sym")),
        footprint=Footprint(
            name="LBEE5KL1YN814", package_class="LGA-module",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=(
            "Murata Type 1YN — based on Cypress (Infineon) CYW43012 "
            "single-chip WiFi 4 + BT 5.0. The -814 suffix denotes the "
            "tape & reel pack format. Module has its own RF approvals "
            "(FCC, IC, CE) — significantly reduces certification work "
            "vs a chip-down WiFi design. Antenna trace required on the "
            "host PCB (or external antenna via U.FL)."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
