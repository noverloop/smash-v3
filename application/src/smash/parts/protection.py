"""ESD / transient protection and pulse-path parts (electrical audit, 2026-11-25).

Lands are the datasheets' recommended footprints; pins are the datasheets'
pinning tables. Country of origin and second-distributor stock are confirmed
in the sourcing round (availability/rounds).
"""
from __future__ import annotations

from smash.state import Chip, Pin, Pad, Footprint
from smash.parts._artifacts import datasheet_ref
from smash.parts._slug import canonical_id


def _fp(name, pads, size, height, note, part_dir=None):
    w, h = size
    fp = Footprint(name=name, package_class=name, pads=pads,
                   body_outline=[(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2),
                                 (-w / 2, h / 2), (-w / 2, -h / 2)],
                   courtyard=[], size_mm=size, height_mm=height,
                   source="datasheet", note=note)
    return fp.ensure_courtyard_clearance()


def _chip(design, ref, *, pn, part_dir, manf, package, size, height, fp, pins,
          description, value=None, **overrides):
    fields = dict(manf=manf, manf_pn=pn, canonical_id=canonical_id(pn), name=pn,
                  value=value or pn, description=description,
                  datasheet=datasheet_ref(part_dir, f"{part_dir}.pdf"),
                  package=package, size_mm=size, height_mm=height, pins=pins, footprint=fp)
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_pesd5v0l4uf(design, ref: str, **overrides) -> Chip:
    """Nexperia PESD5V0L4UF,115 — 4-line unidirectional ESD array, SOT886
    (XSON6, 1.45 × 1.0 × 0.50 mm max). V_RWM 5 V, V_BR 6.46-7.14 V, I_RM 25 nA
    max, C_d 16 typ / 19 max pF, V_CL 8 V at 1 A, IEC 61000-4-2 > ±8 kV
    contact (PESDxL4UF/G/W DS Rev 04, Tables 3, 7-9). Pins 1, 3, 4, 6 =
    cathodes (I/O), 2 and 5 = common anode (GND). Land: DS Fig. 13 (0.325 ×
    0.37 lands, 0.675 between columns, 0.5 row pitch). 0.5 mm tall: fits the
    floor plate's 0.7 mm underside pocket. Round 30: Malaysia, Mouser +
    Digi-Key."""
    pads = [Pad(num=n, position_mm=(x, y), size_mm=(0.325, 0.37))
            for n, x, y in (("1", -0.3375, 0.5), ("2", -0.3375, 0.0), ("3", -0.3375, -0.5),   # y-up top view:
                            ("4", 0.3375, -0.5), ("5", 0.3375, 0.0), ("6", 0.3375, 0.5))]     # pins wind CCW
    fp = _fp("Nexperia_SOT886", pads, (1.0, 1.45), 0.50, "Nexperia PESDxL4UF DS Fig. 13 SOT886 reflow footprint")
    pins = [Pin(num="2", name="GND", aliases=["A"], type="power"),
            Pin(num="5", name="GND_2", aliases=["A2"], type="power")] + [
        Pin(num=n, name=f"IO{k}", type="passive") for k, n in enumerate(("1", "3", "4", "6"), 1)]
    return _chip(design, ref, pn="PESD5V0L4UF,115", part_dir="PESD5V0L4UF_115", manf="Nexperia",
                 package="SOT886 (XSON6)", size=(1.0, 1.45), height=0.50, fp=fp, pins=pins,
                 description="4-line ESD array 5 V, 16 pF, IEC 61000-4-2 ±8 kV, SOT886 0.5 mm",
                 **overrides)


def add_pesd2canfd24v_qbz(design, ref: str, **overrides) -> Chip:
    """Nexperia PESD2CANFD24V-QBZ (type PESD2CANFD24V-QB) — 2-line
    bidirectional CAN / CAN FD ESD protection, DFN1110D-3 / SOT8015 with
    side-wettable flanks (1.1 × 1.0 × 0.48 mm, 0.50 max). V_RWM 24 V, V_BR
    25.5-35.5 V, C_d 6 pF max, V_CL 33 V typ at 1 A, IEC 61000-4-2 contact
    23 kV (DS 30 Sep 2020, Tables 1, 2, 5, 6). Pin 1 K1 and pin 2 K2 to
    CANH / CANL, pin 3 CC to GND. Land + 3D: SamacSys, = DS Fig. 13: pads 1-2
    0.35 × 0.5 at 0.65; pin 3 is a T (0.9 × 0.44 bar + 0.3 × 0.34 stem), drawn
    as two copper pads that both carry number 3. Courtyard: body + 0.15 mm
    (the SamacSys one is 3.1 × 3.5 mm). 0.5 mm tall: fits the floor plate's
    0.7 mm pocket over aft_end's top."""
    from smash.parts._artifacts import pads_from_kicad_mod, src
    pn = "PESD2CANFD24V-QBZ"
    pads = pads_from_kicad_mod(src(pn, "PESD2CANFD24UQBZ.kicad_mod"))
    for pad in pads:
        if pad.num == "4":
            pad.num = "3"                  # T-stem of the pin-3 land
    c = 0.15
    fp = Footprint(name="Nexperia_SOT8015", package_class="DFN1110D-3", pads=pads,
                   body_outline=[(-0.55, -0.5), (0.55, -0.5), (0.55, 0.5), (-0.55, 0.5), (-0.55, -0.5)],
                   courtyard=[(-0.55 - c, -0.75 - c), (0.55 + c, -0.75 - c), (0.55 + c, 0.75 + c),
                              (-0.55 - c, 0.75 + c), (-0.55 - c, -0.75 - c)],
                   pitch_mm=0.65, size_mm=(1.1, 1.0), height_mm=0.50,
                   model_3d_path=datasheet_ref(pn, f"{pn}.stp"), source="samacsys",
                   note="Nexperia PESD2CANFD24V-QB DS Fig. 13 (SamacSys land)")
    pins = [Pin(num="1", name="K1", aliases=["CATHODE1"], type="passive"),
            Pin(num="2", name="K2", aliases=["CATHODE2"], type="passive"),
            Pin(num="3", name="CC", aliases=["COMMON"], type="passive")]
    return _chip(design, ref, pn=pn, part_dir=pn, manf="Nexperia",
                 package="DFN1110D-3 (SOT8015)", size=(1.1, 1.0), height=0.50, fp=fp, pins=pins,
                 description="CAN FD ESD protection, 2 lines, 24 V, 6 pF, IEC 61000-4-2 23 kV, DFN1110D-3",
                 **overrides)


def add_df2s8_2fs(design, ref: str, **overrides) -> Chip:
    """Toshiba DF2S8.2FS,L3M — unidirectional ESD diode, V_RWM 6.5 V (I_R
    0.5 µA max), V_Z 7.7-8.7 V, IEC 61000-4-2 ±30 kV contact, SOD-923
    (1.0 × 0.6 × 0.45 mm max). Pin 1 = cathode (band). Land: DS Fig. 7.1
    (2 × 0.325 × 0.4 at 0.875 pitch). Round 30: Thailand at all three."""
    pads = [Pad(num="1", position_mm=(-0.4375, 0.0), size_mm=(0.325, 0.4)),
            Pad(num="2", position_mm=(0.4375, 0.0), size_mm=(0.325, 0.4))]
    fp = _fp("Toshiba_SOD-923", pads, (1.0, 0.6), 0.45, "Toshiba DF2S8.2FS DS Fig. 7.1 land pattern")
    pins = [Pin(num="1", name="K", aliases=["Cathode"], type="passive"),
            Pin(num="2", name="A", aliases=["Anode"], type="passive")]
    return _chip(design, ref, pn="DF2S8.2FS,L3M", part_dir="DF2S8.2FS_L3M", manf="Toshiba",
                 package="SOD-923", size=(1.0, 0.6), height=0.45, fp=fp, pins=pins,
                 description="ESD diode 6.5 V standoff, unidirectional, SOD-923", **overrides)


def add_pesd36vs1ul(design, ref: str, **overrides) -> Chip:
    """Nexperia PESD36VS1ULSYL — unidirectional ESD diode, V_RWM 36 V (I_RM
    10 nA), V_BR 38.2-39.8 V, V_CL 58 V at 1 A, IEC 61000-4-2 30 kV,
    DFN1006BD-2 / SOD882BD side-wettable (1.0 × 0.6 × 0.50 mm max). Pin 1 =
    cathode. Land: the SOD882 reflow footprint (2 × 0.4 × 0.7, 0.7 pitch;
    PESD36VS1UL DS Fig. 10) — the BD terminals sit inside it. Round 30:
    Malaysia at Mouser + Digi-Key."""
    pads = [Pad(num="1", position_mm=(-0.35, 0.0), size_mm=(0.4, 0.7)),
            Pad(num="2", position_mm=(0.35, 0.0), size_mm=(0.4, 0.7))]
    fp = _fp("Nexperia_SOD882", pads, (1.0, 0.6), 0.50, "Nexperia DFN1006-2 reflow footprint (PESD36VS1UL DS Fig. 10)")
    pins = [Pin(num="1", name="K", aliases=["Cathode"], type="passive"),
            Pin(num="2", name="A", aliases=["Anode"], type="passive")]
    return _chip(design, ref, pn="PESD36VS1ULSYL", part_dir="PESD36VS1ULSYL", manf="Nexperia",
                 package="DFN1006BD-2 (SOD882BD)", size=(1.0, 0.6), height=0.50, fp=fp, pins=pins,
                 description="ESD diode 36 V standoff, unidirectional, DFN1006-2", **overrides)


def add_ssm3k339r(design, ref: str, **overrides) -> Chip:
    """Toshiba SSM3K339R,LF — N-FET 40 V / 2.0 A, V_th 0.85-1.2 V, R_DS(on)
    238 mΩ max at V_GS 2.5 V / 0.5 A (390 mΩ at 1.8 V), V_GS ±12 V, gate-source
    protection diode, SOT-23F (2.9 × 2.4 × 0.88 mm max). Pins 1 G, 2 S, 3 D —
    the SSM3J372R's SOT-23F land. Low side of the parachute-cutter columns:
    guaranteed on at the fin MCU's 3.3 V gate."""
    from smash.parts.devboard import _sam
    pins = [Pin(num="1", name="G", aliases=["Gate"], type="input"),
            Pin(num="2", name="S", aliases=["Source"], type="io"),
            Pin(num="3", name="D", aliases=["Drain"], type="io")]
    return _sam(design, ref, pn="SSM3K339R,LF", part_dir="SSM3J372R_LF", mod="SSM3J372RLF.kicad_mod",
                package="SOT-23F", height_mm=0.88, size_mm=(2.9, 2.4), manf="Toshiba",
                description="N-MOSFET 40 V 2 A, 238 mΩ @ 2.5 V, SOT-23F", pins=pins, ring_courtyard=True,
                datasheet=datasheet_ref("SSM3K339R_LF", "SSM3K339R_LF.pdf"),
                note="SOT-23F land shared with the SSM3J372R (same package, same pin order).",
                **overrides)


def add_erj3bsfr20v(design, ref: str, **overrides) -> Chip:
    """Panasonic ERJ-3BSFR20V — 0.2 Ω ±1 % thick-film current-sense chip,
    0603, 0.25 W at 70 °C, overload 2.5 × rated voltage for 5 s (ERJ 2B/3B
    sheet). Per-cell isolation resistor (≈ 0.42 W per chirp + cutter pulse)."""
    from smash.parts.passives import _stock_smd_2pad, _two_pin
    fp = _stock_smd_2pad(name="Resistor_SMD:R_0603_1608Metric", size_mm=(1.6, 0.8),
                         height_mm=0.55, pad_size=(0.8, 0.95), pad_pitch_mm=1.65,
                         package_class="0603")
    return _chip(design, ref, pn="ERJ-3BSFR20V", part_dir="ERJ-3BSFR20V", manf="Panasonic",
                 package="0603", size=(1.6, 0.8), height=0.55, fp=fp, pins=_two_pin(),
                 value="200m", description="0.2 Ω 1 % 0.25 W 0603 current-sense resistor",
                 resistance_ohm=0.2, power_rating_w=0.25, **overrides)


def add_max9117exk(design, ref: str, **overrides) -> Chip:
    """ADI MAX9117EXK+T — nanopower comparator with a 1.252 V internal
    reference (1.196-1.308 V over temperature), push-pull output, 1.6-5.5 V,
    1.3 µA max, SC70-5. Pins (DS Pin Description): 1 OUT, 2 VEE, 3 IN+, 4 REF
    (the inverting input is the reference), 5 VCC. Dev board only. Land:
    generic SC70-5 (0.65 pitch) — confirm against ADI's land pattern."""
    pads = [Pad(num="1", position_mm=(-0.65, -0.95), size_mm=(0.40, 0.75)),
            Pad(num="2", position_mm=(0.0, -0.95), size_mm=(0.40, 0.75)),
            Pad(num="3", position_mm=(0.65, -0.95), size_mm=(0.40, 0.75)),
            Pad(num="4", position_mm=(0.65, 0.95), size_mm=(0.40, 0.75)),
            Pad(num="5", position_mm=(-0.65, 0.95), size_mm=(0.40, 0.75))]
    fp = _fp("SC70-5", pads, (2.0, 1.25), 1.1, "generic SC70-5 land (0.65 pitch)")
    pins = [Pin(num="1", name="OUT", type="output"), Pin(num="2", name="VEE", aliases=["GND"], type="power"),
            Pin(num="3", name="IN+", type="input"), Pin(num="4", name="REF", type="output"),
            Pin(num="5", name="VCC", aliases=["V+"], type="power")]
    return _chip(design, ref, pn="MAX9117EXK+T", part_dir="MAX9117EXK_T", manf="Analog Devices",
                 package="SC70-5", size=(2.0, 1.25), height=1.1, fp=fp, pins=pins,
                 description="Nanopower comparator + 1.252 V reference, push-pull, SC70-5",
                 **overrides)


def add_ltc4365its8(design, ref: str, **overrides) -> Chip:
    """ADI LTC4365ITS8#TRPBF — overvoltage / undervoltage / reverse-supply
    protection controller driving back-to-back N-FETs; VIN protected −40…60 V,
    operating 2.5-34 V; UV / OV comparators 0.5 V (25 mV hysteresis), 36 ms
    recovery; GATE up to 9.8 V enhancement. TSOT-23-8 (TS8): 1 VIN, 2 UV, 3 OV,
    4 GND, 5 SHDN, 6 FAULT, 7 VOUT, 8 GATE (DS Pin Configuration). Land: the
    DS "recommended solder pad layout" (0.40 × 0.62 pads, 0.65 pitch, rows
    2.62 / 3.85 mm). Dev board only."""
    y = (2.62 / 2 + 3.85 / 2) / 2
    xs = (-0.975, -0.325, 0.325, 0.975)
    pads = ([Pad(num=str(k + 1), position_mm=(xs[k], -y), size_mm=(0.40, 0.62)) for k in range(4)]
            + [Pad(num=str(8 - k), position_mm=(xs[k], y), size_mm=(0.40, 0.62)) for k in range(4)])
    fp = _fp("TSOT-23-8", pads, (2.9, 1.6), 1.0, "LTC4365 DS TS8 recommended solder pad layout")
    names = {"1": ("VIN", "power"), "2": ("UV", "input"), "3": ("OV", "input"), "4": ("GND", "power"),
             "5": ("SHDN", "input"), "6": ("FAULT", "output"), "7": ("VOUT", "input"), "8": ("GATE", "output")}
    pins = [Pin(num=n, name=v[0], type=v[1]) for n, v in names.items()]
    return _chip(design, ref, pn="LTC4365ITS8#TRPBF", part_dir="LTC4365ITS8_TRPBF", manf="Analog Devices",
                 package="TSOT-23-8", size=(2.9, 1.6), height=1.0, fp=fp, pins=pins,
                 description="OV/UV/reverse-supply protection controller, back-to-back N-FET, TSOT-23-8",
                 **overrides)
