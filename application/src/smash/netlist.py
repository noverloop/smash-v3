"""Wiring helpers — passive-laying conveniences on top of the catalog.

Replaces the inline `cap_to_gnd` / `res_between` / `ind_between` /
`add_i2c_pullups` helpers from `system.py`. Each helper:

  1. Picks the right catalog factory based on the value string and
     (for caps) any value-class hints (footprint, embedded-cap flag).
  2. Adds the part to the design via the factory.
  3. Wires it to the supplied net(s) with optional `intent=` text.

For the **2.2–10 µF range**, `cap_to_gnd` issues an N×0603 array
instead of a single 1206 part — lower Z, lower ESR/ESL, solder-joint
redundancy under launch shock (Smash-specific design choice; see
`smash.parts.passives` module doc).

For the **≤100 nF range** with `embedded_cap_absorbs=True`, the part
is created normally (so the netlist has the connection) and is marked
DNP so the BOM writer drops it — but ONLY when the module-level
`ECM_ABSORB` switch is on. It is **off by default**; see the switch
for why. With it off the flag is recorded in the part note and the
cap is populated like any other.
"""

from __future__ import annotations

import os

from smash.state import Design, Chip
from smash.parts._passives_util import parse_capacitance_f
from smash.parts.passives import (
    add_resistor_0402_vishay,
    add_capacitor_x7r_0402_kemet,
    add_capacitor_x7r_0603_kemet_mil,
    add_capacitor_x7r_0805_kemet_mil,
    add_capacitor_c0g_0603_avx_sqcs,
    add_capacitor_tantalum_3528_kemet_t491,
    add_capacitor_polymer_7343_kemet_t528,
)


# ── ECM absorption switch ───────────────────────────────────────────────

# When ON, a cap built with `embedded_cap_absorbs=True` is marked DNP: the
# flight build deletes the physical part and expects the stackup's
# embedded-capacitance plane pair to supply that bypass instead.
#
# OFF by default (2026-09-15). The fitted embedded-cap dielectric is 50 µm
# "FR4 thin" (εr 4.2 — `state/fab/default.py`), which yields ~74 pF/cm² →
# ~1.4 nF per Ø34 tile across both plane pairs, against the 4.81 µF of
# discrete bypass the flag deletes. The pairs also have no `Layer.rail`
# assigned, so no rail is actually plane-coupled yet. Until a high-k
# laminate is specified and the pairs are railed, the caps stay populated.
#
# The `embedded_cap_absorbs=` call sites are left in place — they record
# which positions are ECM candidates. Set SMASH_ECM_ABSORB=1 to restore
# the absorbing build.
ECM_ABSORB = os.environ.get("SMASH_ECM_ABSORB", "0").strip().lower() \
    not in ("", "0", "false", "no", "off")


# ── cap dispatch by value ───────────────────────────────────────────────


def _cap_factory_for_value(value: str, *, force_c0g: bool = False):
    """Pick the right cap factory + how-many-in-parallel for a value.

    Returns `(factory, n_parallel)`. `n_parallel > 1` means the
    caller emits N instances on the same net (e.g. 10 µF → 5×0603).

    Dispatch policy (mirrors system.py `_cap_fp` + the parallelisation
    decision documented in `passives` module doc):

      Value (F)              Factory                        N
      ------------------     ----------------------------   -
      pF range               add_capacitor_c0g_0603_avx_sqcs 1
                                            (or force_c0g=True)
      ≤ 100 nF               add_capacitor_x7r_0402_kemet   1
      220 nF – 1 µF          add_capacitor_x7r_0603_kemet_mil 1
      1 – < 2.2 µF           add_capacitor_x7r_0805_kemet_mil 1
      2.2 µF                 add_capacitor_x7r_0603_kemet_mil 1
                                  (1× 2.2 µF in 0603 X7R MIL)
      ≥ 2.2 µF, ≤ 10 µF      add_capacitor_x7r_0603_kemet_mil N
                                  (N = ceil(value/2.2 µF))
      ≥ 11 µF, < 47 µF       add_capacitor_tantalum_3528_kemet_t491 1
      ≥ 47 µF                add_capacitor_polymer_7343_kemet_t528 1

    `force_c0g=True` forces the AVX SQCS C0G factory even at higher
    capacitances — used for RF / TIA feedback positions where the
    C0G dielectric matters (no DC-bias droop, low ESR).
    """
    if force_c0g:
        return add_capacitor_c0g_0603_avx_sqcs, 1
    farads = parse_capacitance_f(value)
    # pF-range RF caps default to C0G when explicitly < 1 nF
    if farads < 1e-9:
        return add_capacitor_c0g_0603_avx_sqcs, 1
    if farads <= 100.1e-9:
        return add_capacitor_x7r_0402_kemet, 1
    if farads < 0.9e-6:
        return add_capacitor_x7r_0603_kemet_mil, 1
    if farads < 2.2e-6:
        # 0.9–<2.2 µF goes to 0805 — system.py's `_cap_fp` boundary;
        # below 0.9 µF stays in 0603.
        return add_capacitor_x7r_0805_kemet_mil, 1
    if farads <= 10.1e-6:
        # Parallelise N×0603 of 2.2 µF rather than a single 1206
        n = max(1, int(round(farads / 2.2e-6)))
        return add_capacitor_x7r_0603_kemet_mil, n
    if farads < 47e-6:
        return add_capacitor_tantalum_3528_kemet_t491, 1
    return add_capacitor_polymer_7343_kemet_t528, 1


# ── cap_to_gnd ──────────────────────────────────────────────────────────


def cap_to_gnd(design: Design,
               net: str,
               value: str,
               *,
               ref: str | None = None,
               gnd_net: str = "GND",
               embedded_cap_absorbs: bool = False,
               embedded_plane: bool = False,
               force_c0g: bool = False,
               intent: str | None = None,
               **overrides) -> list[Chip]:
    """Add one or more bypass caps from `net` to ground.

    Picks the factory + parallelisation count based on `value`. For
    the 2.2–10 µF range, this issues an N-of-0603 array on the same
    net pair (replaces the single-1206 approach from system.py).

    Args:
      design:               the Design to add into.
      net:                  signal net name to bypass.
      value:                e.g. "100nF", "10uF", "22uF/16V".
      ref:                  base refdes; arrays append "_1", "_2", ...
      gnd_net:              ground net name (default "GND").
      embedded_cap_absorbs: mark cap as an ECM-laminate candidate.
                            DNP'd only when `ECM_ABSORB` is on
                            (off by default) — otherwise populated.
      embedded_plane:       mark cap as embedded-plane-implemented
                            (no discrete part on flight; e.g. bulk
                            decoupling done by a dedicated rail plane).
      force_c0g:            override the X7R dispatch and use AVX SQCS
                            C0G — for RF / TIA feedback positions.
      intent:               human description (passed through to the
                            `connect(..., intent=...)` calls).
      **overrides:          forwarded to the factory.

    Returns the list of created Chip objects (1 element for the
    single-part case, N for arrays).
    """
    factory, n = _cap_factory_for_value(value, force_c0g=force_c0g)
    # For N×0603 parallel arrays (2.2–10 µF range), each instance is a
    # single 2.2 µF; the array sums to the requested total value.
    per_instance_value = "2.2uF" if n > 1 else value
    base_ref = ref or f"C_{net.replace('-', '_')}"
    chips: list[Chip] = []
    for i in range(n):
        instance_ref = base_ref if n == 1 else f"{base_ref}_{i+1}"
        chip = factory(design, ref=instance_ref,
                       value=per_instance_value, **overrides)
        absorbed = embedded_cap_absorbs and ECM_ABSORB
        chip.dnp = absorbed or embedded_plane
        if absorbed:
            chip.note = (chip.note or "") + (
                "\n\n[ECM-absorbed] On flight build this position is "
                "absorbed by the 3M ECM / FaradFlex embedded-capacitance "
                "laminate. Marked DNP in the BOM."
            )
        elif embedded_cap_absorbs:
            chip.note = (chip.note or "") + (
                "\n\n[ECM candidate — POPULATED] Flagged as absorbable by "
                "an embedded-capacitance plane pair, but ECM absorption is "
                "off on this build (smash.netlist.ECM_ABSORB), so the part "
                "is placed and appears in the BOM."
            )
        if embedded_plane:
            chip.note = (chip.note or "") + (
                "\n\n[Embedded plane] On flight build this position is "
                "implemented by a dedicated rail plane in the laminate "
                "stack. No discrete part; marked DNP in the BOM."
            )
        design.connect(net, chip.pin("1"), intent=intent)
        design.connect(gnd_net, chip.pin("2"))
        chips.append(chip)
    return chips


# ── res_between ─────────────────────────────────────────────────────────


def res_between(design: Design,
                 n1: str,
                 n2: str,
                 value: str,
                 *,
                 ref: str | None = None,
                 intent: str | None = None,
                 **overrides) -> Chip:
    """Add a 0402 Vishay CRCW resistor between two nets.

    Args:
      design:  the Design.
      n1, n2:  net names — order is electrically irrelevant; n1 →
               chip.pin("1"), n2 → chip.pin("2") by convention.
      value:   "100", "4.7k", "49k9", etc. (see `parse_resistance_ohm`).
      ref:     defaults to "R_<n1>_<n2>".
      intent:  human description.
    """
    r = add_resistor_0402_vishay(
        design,
        ref=ref or f"R_{n1.replace('-', '_')}_{n2.replace('-', '_')}",
        value=value, **overrides,
    )
    design.connect(n1, r.pin("1"), intent=intent)
    design.connect(n2, r.pin("2"))
    return r


# ── ind_between ─────────────────────────────────────────────────────────


def ind_between(design: Design,
                 n1: str,
                 n2: str,
                 value: str,
                 *,
                 ref: str | None = None,
                 family: str = "auto",
                 intent: str | None = None,
                 **overrides) -> Chip:
    """Add an inductor between two nets.

    Args:
      design:  the Design.
      n1, n2:  net names; n1 → pin 1, n2 → pin 2.
      value:   "10nH", "1uH", "4.7uH", "10uH".
      ref:     defaults to "L_<n1>_<n2>".
      family:  "auto" (default) picks WE-KI 0402 for ≤ 220 nH;
               TDK TMS201210ALM for 220 nH < L ≤ 2.2 µH;
               raises for higher L (use add_we_744043100 directly
               for the 10 µH @ 6 A VMOT slot).
      intent:  human description.
    """
    from smash.parts._passives_util import parse_inductance_h
    from smash.parts.passives import (
        add_inductor_we_ki_0402_wurth,
        add_inductor_tms201210alm_tdk,
    )
    l_h = parse_inductance_h(value)
    if family == "we-ki" or (family == "auto" and l_h <= 220e-9):
        factory = add_inductor_we_ki_0402_wurth
    elif family == "tms" or (family == "auto" and l_h <= 2.2e-6):
        factory = add_inductor_tms201210alm_tdk
    else:
        raise ValueError(
            f"no auto-dispatch inductor factory for {value} "
            f"(L={l_h*1e6:g} µH). Use add_we_744043100 directly "
            f"for 10 µH @ 6 A, or add a new factory for this range."
        )
    l = factory(
        design,
        ref=ref or f"L_{n1.replace('-', '_')}_{n2.replace('-', '_')}",
        value=value, **overrides,
    )
    design.connect(n1, l.pin("1"), intent=intent)
    design.connect(n2, l.pin("2"))
    return l


# ── add_i2c_pullups ─────────────────────────────────────────────────────


def add_i2c_pullups(design: Design,
                     scl_net: str,
                     sda_net: str,
                     *,
                     vdd_net: str = "VDD",
                     value: str = "4.7k",
                     prefix: str = "RPU",
                     intent: str | None = None) -> tuple[Chip, Chip]:
    """Add the standard pair of I²C pull-ups (default 4.7 kΩ to VDD).

    Args:
      design:    the Design.
      scl_net:   SCL net name.
      sda_net:   SDA net name.
      vdd_net:   pull-up rail (default "VDD").
      value:     resistor value (default "4.7k").
      prefix:    refdes prefix (defaults to "RPU"; e.g. "RPU_I2C2"
                 yields RPU_I2C2_SCL + RPU_I2C2_SDA).
      intent:    human description; suffixed with " (SCL)" / " (SDA)"
                 per leg.

    Returns the (R_scl, R_sda) tuple.
    """
    intent_scl = (intent + " (SCL pull-up)") if intent else "I²C SCL pull-up"
    intent_sda = (intent + " (SDA pull-up)") if intent else "I²C SDA pull-up"
    r_scl = res_between(design, vdd_net, scl_net, value,
                        ref=f"{prefix}_{scl_net}", intent=intent_scl)
    r_sda = res_between(design, vdd_net, sda_net, value,
                        ref=f"{prefix}_{sda_net}", intent=intent_sda)
    return r_scl, r_sda
