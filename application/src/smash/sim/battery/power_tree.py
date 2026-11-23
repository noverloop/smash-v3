"""Power tree from the pack to every load rail, with per-converter limits.

Mirrors generate_stackup.py as of 2026-11-22 (maximalist build). Loads are
currents AT THEIR OWN RAIL; the tree turns them into the pack current at a
given pack voltage, so switching converters behave as constant power
(I_pack rises as the cells sag) and LDOs as constant current.

Rail "BAT" lumps BAT_RAW / BAT_PROT / REG_IN_MAIN (QMAIN + Q_ISO + interconnect
sit in mission.R_WIRING). "PMIC_OUT" is a 1.0 V bookkeeping rail: the
STPMIC25's many outputs are entered as WATTS (amps at 1.0 V) behind one
efficiency, because the per-rail split does not change what the pack sees.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Converter:
    ref: str
    src: str                 # input rail
    out: str                 # output rail
    kind: str                # "boost" | "buck" | "ldo"
    v_out: float
    eta: float = 1.0
    iq_a: float = 0.0
    vin_min: float = 0.0     # recommended-operating minimum (steady phases)
    vin_uvlo: float = 0.0    # dropout point for ms-class dips
    l_h: float | None = None
    f_hz: float | None = None
    i_sw_max_a: float | None = None      # peak switch / inductor current limit
    i_out_max_a: float | None = None
    i_bypass_max_a: float | None = None  # boost pass-through (VIN >= VOUT) abs max
    dropout_v: float = 0.0
    v_out_min: float = 0.0   # LDO: lowest output its loads accept (dropout is fine above it)
    basis: str = ""


# fmt: off
_PRE_R21: tuple[Converter, ...] = (   # the tree before the 2026-11-23 swaps
    Converter("U_AON_LDO", "BAT", "3V3_AON", "ldo", 3.3, iq_a=0.1e-6, dropout_v=0.25,
              v_out_min=1.8,   # WBA55 1.71 V, TLV3691 0.9 V
              basis="S-1318 nano-LDO (AON domain off BAT_RAW)"),
    Converter("U_BOOST", "BAT", "BOOST_OUT", "boost", 3.87, eta=0.88, iq_a=19e-6,
              vin_min=0.8, vin_uvlo=0.35, l_h=2.2e-6, f_hz=500e3,
              i_sw_max_a=0.80, i_out_max_a=0.35, i_bypass_max_a=0.40,
              basis="MCP1640C DS: 800 mA peak input limit (typ only), "
                    "350 mA out typ @3.3->5.0 V, 400 mA bypass abs max"),
    Converter("U_PWR", "BOOST_OUT", "3V3", "ldo", 3.3, iq_a=50e-6, dropout_v=0.35,
              v_out_min=3.0,   # ADF4351 / LTC5552 3.0 V min class
              i_out_max_a=1.2, basis="LDL112PV33R, 350 mV dropout @1.2 A"),
    Converter("U_XV_BOOST", "BAT", "XV_5V", "boost", 4.95, eta=0.85, iq_a=19e-6,
              vin_min=0.8, vin_uvlo=0.35, l_h=2.2e-6, f_hz=500e3,
              i_sw_max_a=0.80, i_out_max_a=0.35,
              basis="MCP1640D on REG_IN_MAIN (2026-11-22), PA 110 mA @ 4.95 V"),
    Converter("U_COMP_BOOST", "BAT", "COMP_5V", "boost", 5.03, eta=0.88, iq_a=3.5e-3,
              vin_min=2.9, vin_uvlo=2.7, l_h=4.7e-6, f_hz=600e3,
              i_sw_max_a=3.0,
              basis="TPS61175 SLVS892F: VIN 2.9 V min, UVLO 2.7 V typ, "
                    "switch limit 3.0 min / 3.8 typ / 5.0 max"),
    Converter("U_PMIC", "COMP_5V", "PMIC_OUT", "buck", 1.0, eta=0.85,
              basis="STPMIC25 lumped (loads entered in W on the 1.0 V book rail)"),
    Converter("U_ACT_BOOST", "COMP_5V", "ACTIVATE_HV", "boost", 33.0, eta=0.85, iq_a=3.5e-3,
              vin_min=2.9, vin_uvlo=2.7, l_h=10e-6, f_hz=600e3, i_sw_max_a=3.0,
              basis="TPS61175 cutter boost, 10 uH (L_ACTIVATE)"),
    Converter("U_AWR_BUCK12", "BAT", "AWR_1V2", "buck", 1.2, eta=0.80, iq_a=1.5e-3,
              vin_min=3.0, vin_uvlo=3.0, i_out_max_a=1.0,
              basis="LMR10510Y: VIN 3.0-5.5 V, 1 A (UVLO taken = 3.0 V, conservative)"),
    Converter("U_AWR_BUCK13", "BAT", "AWR_1V3", "buck", 1.3, eta=0.80, iq_a=1.5e-3,
              vin_min=3.0, vin_uvlo=3.0, i_out_max_a=1.0,
              basis="LMR10510Y, RF front-end rail (AWR1843 draws up to 2.0 A here: "
                    "SWRS236C T6-3)"),
    Converter("U_AWR_LDO18", "BAT", "AWR_1V8", "ldo", 1.8, iq_a=50e-6, dropout_v=0.35,
              v_out_min=1.71,
              i_out_max_a=1.2, basis="LDL112PV18R"),
)
# fmt: on

# (2026-11-23) camera VB1943 core: own TPS62822 buck at 1.15 V from BAT_PROT
_CAM_BUCK = Converter("U_CAM_BUCK_VCORE", "BAT", "CAM_VCORE", "buck", 1.15, eta=0.85, iq_a=4e-6,
                      vin_min=2.4, vin_uvlo=2.2, i_out_max_a=2.0,
                      basis="TPS62822DLC at 1.15 V (VB1943 VCORE, ~0.12-0.21 A)")

RAIL_V_NOM = {c.out: c.v_out for c in _PRE_R21 + (_CAM_BUCK,)}


@dataclass(frozen=True)
class Load:
    name: str
    rail: str
    amps: float
    basis: str = "est"


@dataclass
class ConvState:
    conv: Converter
    v_in: float
    v_out: float
    i_out: float
    i_in: float
    i_pk: float | None
    mode: str                      # "reg" | "bypass" | "dropout" | "off"
    flags: list[str] = field(default_factory=list)


@dataclass
class TreeState:
    v_bat: float
    i_bat: float
    convs: dict[str, ConvState]

    def flags(self) -> list[str]:
        return [f"{c.conv.ref}: {f}" for c in self.convs.values() for f in c.flags]


def _rail_loads(loads: list[Load]) -> dict[str, float]:
    out: dict[str, float] = {}
    for ld in loads:
        out[ld.rail] = out.get(ld.rail, 0.0) + ld.amps
    return out


def solve_tree(loads: list[Load], v_bat: float, fast: bool = False,
               convs: tuple[Converter, ...] | None = None) -> TreeState:
    """Pack current + every converter's operating point at pack voltage v_bat.

    fast=True checks ms-class dips against each converter's UVLO instead of
    its recommended-operating VIN minimum."""
    CONVS = CONVERTERS if convs is None else convs
    direct = _rail_loads(loads)
    states: dict[str, ConvState] = {}

    def v_rail(rail: str) -> float:
        """Rail voltage — load-independent (boost bypass / LDO dropout only
        depend on the upstream voltage), so no recursion through currents."""
        if rail == "BAT":
            return v_bat
        c = next(c for c in CONVS if c.out == rail)
        v_in = v_rail(c.src)
        if c.kind == "boost" and v_in >= c.v_out:
            return v_in
        if c.kind == "ldo" and v_in < c.v_out + c.dropout_v:
            return max(v_in - c.dropout_v, 0.0)
        return c.v_out

    def i_rail(rail: str) -> float:
        i = direct.get(rail, 0.0)
        for c in CONVS:
            if c.src == rail:
                i += conv(c).i_in
        return i

    def conv(c: Converter) -> ConvState:
        if c.ref in states:
            return states[c.ref]
        i_out = i_rail(c.out)
        v_in = v_rail(c.src)
        if i_out <= 0.0:
            st = ConvState(c, v_in, 0.0, 0.0, 0.0, None, "off")
            states[c.ref] = st
            return st
        flags: list[str] = []
        v_floor = c.vin_uvlo if fast else c.vin_min
        if v_in < v_floor:
            flags.append(f"VIN {v_in:.2f} V < {'UVLO' if fast else 'min'} {v_floor} V")
        i_pk = None
        if c.kind == "ldo":
            mode = "reg" if v_in >= c.v_out + c.dropout_v else "dropout"
            v_out = c.v_out if mode == "reg" else max(v_in - c.dropout_v, 0.0)
            if mode == "dropout" and v_out < c.v_out_min:
                flags.append(f"dropout: out {v_out:.2f} V < {c.v_out_min} V needed")
            i_in = i_out + c.iq_a
        elif c.kind == "boost":
            if v_in >= c.v_out:
                mode, v_out, i_in = "bypass", v_in, i_out + c.iq_a
                if c.i_bypass_max_a is not None and i_out > c.i_bypass_max_a:
                    flags.append(f"bypass I_OUT {i_out*1e3:.0f} mA > "
                                 f"{c.i_bypass_max_a*1e3:.0f} mA abs max")
            else:
                mode, v_out = "reg", c.v_out
                i_in = c.v_out * i_out / (c.eta * max(v_in, 0.1)) + c.iq_a
                i_pk = i_in
                if c.l_h and c.f_hz:
                    i_pk += v_in * (1 - v_in / c.v_out) / (c.l_h * c.f_hz) / 2
                if c.i_sw_max_a is not None and i_pk > c.i_sw_max_a:
                    flags.append(f"peak switch {i_pk:.2f} A > {c.i_sw_max_a:.2f} A limit")
        else:  # buck
            mode, v_out = "reg", c.v_out
            i_in = c.v_out * i_out / (c.eta * max(v_in, 0.1)) + c.iq_a
            i_pk = i_out
            if c.l_h and c.f_hz and v_in > c.v_out:
                i_pk += (v_in - c.v_out) * c.v_out / (v_in * c.l_h * c.f_hz) / 2
        if c.i_out_max_a is not None and i_out > c.i_out_max_a and mode != "bypass":
            flags.append(f"I_OUT {i_out*1e3:.0f} mA > {c.i_out_max_a*1e3:.0f} mA rating")
        st = ConvState(c, v_in, v_out, i_out, i_in, i_pk, mode, flags)
        states[c.ref] = st
        return st

    for c in CONVS:
        conv(c)
    return TreeState(v_bat, i_rail("BAT"), states)


_RADAR_REFS = ("U_AWR_BUCK12", "U_AWR_BUCK13", "U_AWR_LDO18")


# What-if regulator swaps (2026-11-22). Placeholder SPECS, not parts: each
# needs the sourcing round (datasheet, 2 distributors, COO incl. fab/assembly)
# before it goes into the generator.
COMP_BOOSTS = {
    "tps61175": {},   # as built: 2.9 V min, 3.0 A min switch limit
    "A": dict(vin_min=2.7, vin_uvlo=2.5, i_sw_max_a=6.0, eta=0.90, l_h=1.0e-6,
              f_hz=1.0e6, iq_a=1e-3,
              basis="what-if: 2.7 V / 6 A non-sync boost class (TPS61088-like)"),
    # LTC3124EDHC (DS 3124f): VIN 1.8 V start / 0.5 V after start, 2 phases
    # x 2.5 A min peak limit; 4.7 uH per phase at 1 MHz -> modelled as one
    # 5 A stage with L/2. Below ~2.5 V the PACK UV cutoff (to be added) is
    # the floor, not the part.
    "LTC3124": dict(vin_min=2.5, vin_uvlo=2.5, i_sw_max_a=5.0, eta=0.92, l_h=2.35e-6,
                    f_hz=1.0e6, iq_a=0.6e-3,
                    basis="LTC3124EDHC (R21): 2 x 2.5 A min, floor = planned 2.5 V pack UV cutoff"),
    "B": dict(vin_min=1.8, vin_uvlo=1.6, i_sw_max_a=8.0, eta=0.92, l_h=0.47e-6,
              f_hz=1.0e6, iq_a=0.1e-3,
              basis="what-if: ~1.8 V / 8 A synchronous boost class (TPS61022-like); "
                    "needs a ~2.5 V pack UV cutoff"),
}


_TPS62822 = dict(kind="buck", vin_min=2.4, vin_uvlo=2.2, eta=0.88, iq_a=4e-6,
                 dropout_v=0.0, v_out_min=0.0, i_out_max_a=2.0,
                 basis="TPS62822DLC (R21): VIN 2.4-5.5 V, UVLO ~2.2 V, 2 A, ILIM 2.7 A min")
_TPS62088 = dict(kind="buck", vin_min=2.4, vin_uvlo=2.2, eta=0.88, iq_a=4e-6,
                 i_out_max_a=3.0, basis="TPS62088YFP (R21 alt): VIN 2.4-5.5 V, 3 A")
RADAR_REGS = {
    "pre_r21": {},
    # R21 picks: TPS62822 on 1.2 V and 1.8 V (one part type), 3 A TPS62088
    # on the 1.3 V RF rail (AWR1843 up to 2.0 A there)
    "r21": {"U_AWR_BUCK12": _TPS62822, "U_AWR_BUCK13": _TPS62088,
            "U_AWR_LDO18": _TPS62822},
}


def converters(radar_from: str = "BAT", radar_bucks_low_v: bool = False,
               radar_1v8_buck: bool = False, comp_boost: str = "LTC3124",
               radar_regs: str = "r21") -> tuple[Converter, ...]:
    """The tree as built (all defaults = generate_stackup.py since 2026-11-23:
    LTC3124 COMP boost, TPS62822 / TPS62088 radar regulators), or what-ifs:
      radar_from="COMP_5V"  radar bucks + 1.8 V regulator behind the 5 V boost;
      radar_bucks_low_v     LMR10510 -> buck rated to 2.4 V VIN (85 % at idle);
      radar_1v8_buck        LDL112PV18R LDO -> small buck (85 %, 2.4 V VIN);
      comp_boost            "LTC3124" (as built) | "tps61175" (pre-r21) | "A" | "B";
      radar_regs            "r21" (as built) | "pre_r21" (LMR10510 x2 + LDO)."""
    out = []
    for c in _PRE_R21:
        if c.ref in _RADAR_REFS and radar_from != "BAT":
            c = replace(c, src=radar_from)
        if radar_bucks_low_v and c.ref in ("U_AWR_BUCK12", "U_AWR_BUCK13"):
            c = replace(c, vin_min=2.4, vin_uvlo=2.3, eta=0.85,
                        basis="what-if: buck rated to 2.4 V VIN (TPS6208x/6282x class)")
        if radar_1v8_buck and c.ref == "U_AWR_LDO18":
            c = replace(c, kind="buck", eta=0.85, iq_a=20e-6, vin_min=2.4, vin_uvlo=2.3,
                        dropout_v=0.0, v_out_min=0.0, i_out_max_a=0.6,
                        basis="what-if: 1.8 V buck instead of the LDO")
        if c.ref in RADAR_REGS[radar_regs]:
            c = replace(c, **RADAR_REGS[radar_regs][c.ref])
        if c.ref == "U_COMP_BOOST" and COMP_BOOSTS[comp_boost]:
            c = replace(c, **COMP_BOOSTS[comp_boost])
        out.append(c)
    out.append(_CAM_BUCK)
    return tuple(out)


CONVERTERS = converters()   # as built


def load_power_w(loads: list[Load]) -> float:
    """Sum of load power at the rails (before conversion losses)."""
    return sum(ld.amps * (RAIL_V_NOM.get(ld.rail, 4.0)) for ld in loads)
