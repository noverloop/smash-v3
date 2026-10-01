"""Operational-amplifier factories."""

from __future__ import annotations

from smash.state import Chip, Pin, Pad, Footprint


# ═════════════════════════════════════════════════════════════════════════
# Analog Devices AD8603AUJZ-R2 — single precision micropower rail-to-rail
# CMOS op-amp, 5-Lead TSOT (UJ suffix)
# ═════════════════════════════════════════════════════════════════════════

_AD8603_NOTE = """\
Datasheet extras (AD8603/AD8607/AD8609 family, Analog Devices Rev D).
Family doc covering single (AD8603), dual (AD8607), quad (AD8609).

This factory covers **AD8603AUJZ-R2**:
  AD8603 : single op-amp
  A      : industrial grade
  UJ     : 5-Lead TSOT package
  Z      : Pb-free
  -R2    : reel of 250 (vs -REEL = 10000, -REEL7 = 3000)

>>> Research/ filename caveat: the PDF in `Research/` is named
    `AD8603ARJZ-R2.pdf` — the "R" suffix would normally indicate
    SOIC-8, but the contents are the AD8603/AD8607/AD8609 family
    datasheet (Rev D) which lists AD8603AUJZ-R2 in the Ordering
    Guide. Treat the filename as a labelling typo; this factory
    uses the canonical SamacSys part name `AD8603AUJZ-R2`.

Headline features (datasheet p1):
  Low offset voltage : 50 µV maximum
  Low input bias     : 1 pA maximum
  Single supply      : 1.8 V to 5 V (or ±0.9 to ±2.5 V dual)
  Low noise          : 22 nV/√Hz
  Micropower         : 50 µA max supply current
  Low distortion
  No phase reversal
  Unity gain stable

Operating temperature (Ordering Guide):
  AD8603AUJZ-R2 : -40 °C to +125 °C

Applications (datasheet p1):
  Battery-powered instrumentation
  Multipole filters
  Sensors
  Low-power ASIC input/output amplifiers

Package (5-Lead TSOT, "UJ-5" outline drawing):
  Footprint name (SamacSys IPC): SOT95P280X100-5N
  Body 2.9 × 1.6 mm, height 1.0 mm max
  Pitch 0.95 mm

Pin layout (datasheet Figure 1 + KiCad symbol — note that pinmap.txt
has "PIN" on pin 3 due to the "+" being stripped during text
extraction; the KiCad symbol holds the correct name "+IN"):
  1 = OUT  (output)
  2 = V-   (negative supply / GND for single-supply use)
  3 = +IN  (non-inverting input)
  4 = -IN  (inverting input)
  5 = V+   (positive supply)

Mechanical (NOT in datasheet headline): body_material, lead_material,
weight_g, fab_country.

Distributor (SamacSys metadata): Mouser part number not captured.
"""


def _ad8603_tsot5_footprint() -> Footprint:
    """5-Lead TSOT (UJ) footprint per SamacSys SOT95P280X100-5N.kicad_mod.

    Body 2.9 × 1.6 mm, height 1.0 mm (vs the SOT-23-5 DBV variant's
    1.45 mm height — TSOT is the thinner profile).

    Pad geometry (extracted in earlier batch artifact processing):
      pad 1 : (-1.25, -0.95)  0.6 × 1.2 mm
      pad 2 : (-1.25,  0.00)  0.6 × 1.2 mm
      pad 3 : (-1.25, +0.95)  0.6 × 1.2 mm
      pad 4 : (+1.25, +0.95)  0.6 × 1.2 mm
      pad 5 : (+1.25, -0.95)  0.6 × 1.2 mm
    """
    return Footprint(
        name="SOT95P280X100-5N",
        package_class="TSOT-5 (UJ)",
        pads=[
            Pad(num="1", position_mm=(-1.25, 0.95), size_mm=(1.15, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="2", position_mm=(-1.25, 0.0),   size_mm=(1.15, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="3", position_mm=(-1.25, -0.95), size_mm=(1.15, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="4", position_mm=(1.25, -0.95), size_mm=(1.15, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="5", position_mm=(1.25, 0.95), size_mm=(1.15, 0.6), shape="rect", layer="F.Cu"),
        ],
        body_outline=[(-0.8, -1.45), (0.8, -1.45), (0.8, 1.45), (-0.8, 1.45)],
        courtyard=[(-2.1, -1.775), (2.1, -1.775), (2.1, 1.775), (-2.1, 1.775)],
        pitch_mm=0.95,
        size_mm=(2.9, 1.6),
        height_mm=1.0,
        model_3d_path="application/src/smash/parts/sources/AD8603AUJZ-R2/AD8603AUJZ-R2.stp",
        source="samacsys",
    )


_AD8603_BASE_FIELDS = dict(
    manf="Analog Devices",
    manf_pn="AD8603AUJZ-R2",
    canonical_id="ad8603aujz_r2",
    name="AD8603AUJZ-R2",
    value="AD8603AUJZ-R2",
    datasheet="application/src/smash/parts/sources/AD8603AUJZ-R2/AD8603-AD8607-AD8609-family.pdf",
    fab_country=None, currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
    standards=[],
    eccn=None, itar=None,
    package="TSOT-5 (UJ-5)",
    size_mm=(2.9, 1.6),
    height_mm=1.0,
    temp_range_c=(-40, 125),
    body_material=None, lead_material=None,
    voltage_rating_v=None,
    vcc_nominal_v=None,
    i_rms_a=None,
    power_rating_w=None,
    rth_jc_cw=None, rth_ja_cw=None,
    tj_max_c=None,
    note=_AD8603_NOTE,
)


def add_ad8603aujz_r2_single_supply(design, ref: str, **overrides) -> Chip:
    """AD8603AUJZ-R2 wired for **single-supply** operation.

    Pin 2 ("V-") is typed as `ground` — single-supply use ties V- to
    the system GND rail. The datasheet supports V_S = 1.8 V to 5 V in
    this mode. Use this variant when the design has only one positive
    rail (e.g. the QPD TIA stages in Smash, where each AD8603 runs on
    3 V3 single-supply with V- = GND).

    Pick `add_ad8603aujz_r2_dual_supply` instead when wiring V- to a
    negative rail (V_S = ±0.9 V to ±2.5 V symmetric, or asymmetric
    with a small negative bias)."""
    fields = dict(_AD8603_BASE_FIELDS,
        description=(
            "Precision micropower CMOS op-amp, single-supply config, "
            "V_OS=50 µV max, I_B=1 pA max, V_S=1.8..5 V, "
            "I_Q=50 µA max, 5-Lead TSOT"
        ),
        pins=[
            Pin(num="1", name="OUT", type="output"),
            Pin(num="2", name="V-",  type="ground",
                note="single-supply mode: tied to system GND"),
            Pin(num="3", name="+IN", aliases=["IN+", "VINP"], type="input"),
            Pin(num="4", name="-IN", aliases=["IN-", "VINN"], type="input"),
            Pin(num="5", name="V+",  aliases=["VCC", "VDD"], type="power"),
        ],
        footprint=_ad8603_tsot5_footprint(),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_ad8603aujz_r2_dual_supply(design, ref: str, **overrides) -> Chip:
    """AD8603AUJZ-R2 wired for **dual-supply** operation.

    Pin 2 ("V-") is typed as `power` — wired to a negative rail (VEE).
    Datasheet supports V_S = ±0.9 V to ±2.5 V. Use this variant when
    the design has a generated negative rail (e.g. via a charge-pump
    inverter) and the op-amp output needs to swing below 0 V."""
    fields = dict(_AD8603_BASE_FIELDS,
        description=(
            "Precision micropower CMOS op-amp, dual-supply config, "
            "V_OS=50 µV max, I_B=1 pA max, V_S=±0.9..±2.5 V, "
            "I_Q=50 µA max, 5-Lead TSOT"
        ),
        pins=[
            Pin(num="1", name="OUT", type="output"),
            Pin(num="2", name="V-",  aliases=["VEE"], type="power",
                note="dual-supply mode: negative rail"),
            Pin(num="3", name="+IN", aliases=["IN+", "VINP"], type="input"),
            Pin(num="4", name="-IN", aliases=["IN-", "VINN"], type="input"),
            Pin(num="5", name="V+",  aliases=["VCC", "VDD"], type="power"),
        ],
        footprint=_ad8603_tsot5_footprint(),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
