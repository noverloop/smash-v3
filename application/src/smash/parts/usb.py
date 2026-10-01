"""USB connector factories."""

from __future__ import annotations

from smash.state import Chip, Footprint
from smash.parts._artifacts import (
    pads_from_kicad_mod, outline_polygon, build_pins, src, datasheet_ref,
)
from smash.parts._slug import canonical_id


def add_uj31_ch_3_msmt_tr_67(design, ref: str, **overrides) -> Chip:
    """Same Sky UJ31-CH-3-MSMT-TR-67 — full USB-C 3.2 receptacle, horizontal
    **mid-mount** SMT (the body drops into a milled board cutout). 24 contacts
    (A1-12 / B1-12) + 4 through-hole shield/retention posts (S1-4).

    Carries USB2 (DP1/DN1, DP2/DN2 — both orientations), USB3 SuperSpeed pairs
    (SSTX/SSRX ×2), CC1/CC2, SBU1/2, and multi VBUS/GND/SHIELD. In Smash only
    the **power + USB2** subset is used (depot power-in + the MP25 USB-FS link);
    the SuperSpeed + SBU contacts are left unconnected.

    The vendored footprint (CUI_UJ31-CH-3-MSMT-TR-67) includes its own
    Edge.Cuts pocket — the mid-mount cavity the connector body sits in. The
    smash model imports the pads + F.Fab/F.CrtYd outlines; the milling cavity
    is materialised separately on the carrier tile at placement.

    3D model: the kicad_mod's (model) block carries a hand-tuned pose —
    rotate (90, 0, 90) + offset (4.5, 2.5, 0) mm — dialed in via the render
    harness (tools/render_board.py + the sweep/offset helpers) to seat CUI's
    STEP over their own footprint. CUI's STEP and footprint frames don't
    natively agree, so the seat is a best compromise (a hair off on the left)."""
    base = "UJ31-CH-3-MSMT-TR-67"
    fp_mod = src(base, "CUI_UJ31-CH-3-MSMT-TR-67.kicad_mod")
    pads = pads_from_kicad_mod(fp_mod)
    pins = build_pins(src(base, f"{base}.kicad_sym"))
    if {p.num for p in pins} != {p.num for p in pads}:
        raise ValueError(f"{base}: pin/pad mismatch")
    fields = dict(
        manf="Same Sky", manf_pn=base, canonical_id=canonical_id(base),
        name=base, value=base,
        description=(
            "USB Type-C 3.2 receptacle, horizontal mid-mount SMT, 24-contact + "
            "4 shield posts (USB2 + USB3 SuperSpeed + CC + SBU)"
        ),
        datasheet=datasheet_ref(base, f"{base}.pdf"),
        package="USB-C receptacle (horizontal mid-mount SMT)",
        pins=pins,
        footprint=Footprint(
            name="CUI_UJ31-CH-3-MSMT-TR-67", package_class="USB-C",
            pads=pads,
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            model_3d_path=datasheet_ref(base, f"{base}.step"),
            source="samesky",
        ),
        note=(
            "Mid-mount: the connector body recesses into a milled board cutout "
            "(the footprint's own Edge.Cuts pocket). Only power + USB2 are wired "
            "in Smash; USB3 SuperSpeed + SBU contacts are unconnected."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_uj20_c_h_g_msmt_1a_p16_tr_67(design, ref: str, **overrides) -> Chip:
    """Same Sky UJ20-C-H-G-MSMT-1A-P16-TR-67 — USB-C **2.0** receptacle,
    horizontal **mid-mount** SMT, **IP67**, 16 contacts. The compact sibling of
    the UJ31: USB2-only (no SuperSpeed), so a shorter body that protrudes less —
    and exactly the power + USB2 subset Smash uses.

    True mid-mount: the body straddles the board edge, embedded ~50%, with the
    contact plane at the board's TOP surface (datasheet recommends 1.0 mm board).
    20 Vdc / 5 A power rating; gasketed (OR-170 silica o-ring) for the sonde.

    16 pins: the USB2 receptacle ties the A/B sides internally, so the pads are
    combined — SH1-4 (TH shield/retention posts) + A1_B12/B1_A12 (GND), A4_B9/
    B4_A9 (VBUS), A5/B5 (CC1/CC2), A6/B6 (DP1/DP2), A7/B7 (DN1/DN2), A8/B8
    (SBU1/2). Wired by pad number in the carrier (the symbol's repeated names
    arrive as VBUS__1 / GND__1 / SHIELD__1.. — KiCad's de-dup — so number is the
    unambiguous key). SBU left open.

    No (model) block ships in the vendored kicad_mod; one is added + hand-tuned
    via the render harness (tools/render_board.py) for the 50%-embed pose."""
    base = "UJ20-C-H-G-MSMT-1A-P16-TR-67"
    fp_mod = src(base, f"SAMESKY_{base}.kicad_mod")
    pads = pads_from_kicad_mod(fp_mod)
    pins = build_pins(src(base, f"{base}.kicad_sym"))
    if {p.num for p in pins} != {p.num for p in pads}:
        raise ValueError(f"{base}: pin/pad mismatch")
    fields = dict(
        manf="Same Sky", manf_pn=base, canonical_id=canonical_id(base),
        name=base, value=base,
        description=(
            "USB Type-C 2.0 receptacle, horizontal mid-mount SMT, IP67, "
            "16-contact (power + USB2), 20 Vdc / 5 A"
        ),
        datasheet=datasheet_ref(base, f"{base}.pdf"),
        package="USB-C 2.0 receptacle (horizontal mid-mount SMT, IP67)",
        size_mm=(11.5, 7.45), height_mm=4.3,
        voltage_rating_v=20.0, i_rms_a=5.0, temp_range_c=(-45, 85),
        body_material="PA10T housing (UL 94 V-0), SUS304 shell, SUS316 mid-plate",
        standards=["RoHS", "IP67", "UL 94 V-0"],
        pins=pins,
        footprint=Footprint(
            name=f"SAMESKY_{base}", package_class="USB-C",
            pads=pads,
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            model_3d_path=datasheet_ref(base, f"Same_Sky_{base}.step"),
            source="samesky",
        ),
        note=(
            "USB2-only IP67 mid-mount; the shorter, gasketed alternative to the "
            "UJ31. Body straddles the board edge embedded ~50% (contact plane at "
            "the board top surface; datasheet board = 1.0 mm). Only power + USB2 "
            "wired; SBU1/2 open. A/B sides tied internally (combined pads)."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
