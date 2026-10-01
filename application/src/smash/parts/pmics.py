"""Power management IC (PMIC) factories."""

from __future__ import annotations

from smash.state import Chip, Footprint
from smash.parts._artifacts import (
    pads_from_kicad_mod, outline_polygon, build_pins, src, datasheet_ref,
)
from smash.parts._slug import canonical_id


def add_stpmic25apqr(design, ref: str, **overrides) -> Chip:
    """ST STPMIC25APQR — companion PMIC for STM32MP25 family.
    Multiple buck converters + LDOs + load switches, I²C control,
    VFQFPN-56 with EP."""
    pn = "STPMIC25APQR"
    fp_mod = src(pn, "QFN40P650X650X90-57N-D.kicad_mod")
    fields = dict(
        manf="STMicroelectronics", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "Companion PMIC for STM32MP25 — multi-rail (bucks + LDOs "
            "+ switches), I²C control, VFQFPN-56 with EP"
        ),
        datasheet=datasheet_ref(pn, f"{pn}.pdf"),
        package="VFQFPN-56 (6.5×6.5 mm)",
        size_mm=(6.5, 6.5), height_mm=0.9,
        temp_range_c=(-40, 105),
        # ── thermal (ST STPMIC25 DS14278 Rev 6, Table 5 p8) ──────────
        # ΘJC quoted directly. PMIC quiescent current is tiny (~2 mA
        # in RUN mode @ VIN=3.6V); actual package dissipation is the
        # buck/LDO conduction losses (~85-90 % efficient on the
        # MP25-feeding rails). p_active uses the components.md
        # engineering estimate for the "MP25 + DDR3 + companion
        # peripherals" total load served by this PMIC.
        p_active_w=0.12,                    # estimated buck/LDO losses, MP25 typical load
        p_max_w=0.20,                       # peak conversion loss at MP25 max + boost edges
        rth_jc_cw=6.0,                      # VFQFPN-56 (exposed pad) ΘJC, DS Tab 5 p8
        tj_max_c=150.0,                     # absolute max Tj, DS Tab 5 p8 (op'l TA max 105°C)
        standards=["RoHS", "ECOPACK2"],
        pins=build_pins(src(pn, f"{pn}.kicad_sym")),
        footprint=Footprint(
            name="QFN40P650X650X90-57N-D", package_class="VFQFPN-56",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.4, size_mm=(6.5, 6.5), height_mm=0.9,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=(
            "STPMIC25 = companion PMIC purpose-built for STM32MP25. "
            "Reference-design rail mapping per ST AN5746 (or "
            "equivalent). Multiple buck converters and LDOs feed the "
            "MP25's voltage domains; I²C interface for runtime control "
            "from the SoC. Exposed pad (pin 57) MUST be soldered to "
            "GND for thermal."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
