"""Primary-cell / battery factories.

These build `Battery` records (not `Chip`), matching the smash schema's
first-class `Battery` dataclass for chemistry / capacity / pulse-current /
hazmat fields that don't fit cleanly on Chip.
"""

from __future__ import annotations

from smash.state import Battery, Pin, Footprint
from smash.parts._artifacts import (
    pads_from_kicad_mod, outline_polygon, src, datasheet_ref,
)
from smash.parts._slug import canonical_id


# ═════════════════════════════════════════════════════════════════════════
# Tadiran TLM-1520HPM/S — High-power Li-MnO₂ organic primary cell
# Smash's current cell. 3× in parallel = 375 mAh / 5.25 A continuous /
# 11.25 A pulse pack.
# ═════════════════════════════════════════════════════════════════════════

def add_tlm_1520hpms(design, ref: str, **overrides) -> Battery:
    """Tadiran TLM-1520HPM/S — high-power Lithium Organic (Li-MnO₂)
    primary cell. Ø14.8 × 21 mm cylindrical, 125 mAh, 1.75 A continuous,
    3.75 A 1-second pulse. Smash uses 3× in parallel on `power_board`
    (375 mAh / 5.25 A cont / 11.25 A pulse pack).

    No discrete soldered footprint — the cell mates to `power_board`'s
    `CellAttach_3x2_TLM1520` pad cluster via solder tabs. So the
    Battery's `footprint=None` here; the host-side footprint is
    `add_cellattach_3x2_tlm1520`.

    Datasheet: TLM-1520HPM (Preliminary), Tadiran Rev A July 2016
    ECN 6102980.
    """
    pn = "TLM-1520HPM/S"
    part_dir = "TLM-1520HPM_S"   # filesystem-safe variant of the PN
    fields = dict(
        manf="Tadiran",
        manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn,
        description=(
            "High-power Li-MnO₂ organic primary cell, Ø14.8×21 mm "
            "cylindrical, 125 mAh, 1.75 A continuous, 3.75 A 1-s pulse"
        ),
        datasheet=datasheet_ref(part_dir, "TLM-1520HPM_S.pdf"),

        # Chemistry / electrical (datasheet §2.2)
        chemistry="Li-MnO₂ organic (lithium manganese dioxide)",
        capacity_mah=125.0,                # @ 5 mA RT to 2.8 V
        nominal_voltage_v=4.0,             # mid-OCV (3.95-4.07 V range)
        ocv_min_v=3.95,                    # fresh cell, RT, ≤1 yr storage
        ocv_max_v=4.07,
        ccv_min_v=3.88,                    # @ 0.125 A, 0.1 s
        i_continuous_a=1.75,               # to 2.5 V cutoff (§2.2.3)
        i_pulse_a=3.75,                    # 1 s pulse to 2.6 V (§2.2.3)
        pulse_duration_s=1.0,
        impedance_mohm=100.0,              # <100 mΩ @ 1 kHz RT (§2.5)

        # Storage / self-discharge (datasheet §2.4 — capacity-loss table)
        # 1 year @ 22 °C ambient = 3 % capacity loss → ~3 %/yr
        self_discharge_pct_per_year=3.0,
        shelf_life_years=20.0,             # 18% loss @ 22 °C over 20 yrs

        # Mechanical (datasheet §2.1)
        package="Ø14.8 × 21 mm cylindrical",
        size_mm=(14.8, 21.0),              # diameter, length
        height_mm=21.0,
        temp_range_c=(-40, 85),
        body_material="stainless steel can",   # standard for TLM family
        lead_material="Ni solder tab",
        weight_g=9.0,                      # 9 g max per §2.1.3

        # Compliance / hazmat
        standards=["UN 38.3", "IEC 60086"],
        hazmat_class="UN3090",             # Li metal primary cells

        # Sourcing
        fab_country="IL",                  # Tadiran HQ + manufacturing — Israel
        currency=None,
        price_1pc=None,
        price_20kpc=None,

        # Smash pack convention (3 cells in parallel)
        pack_count=3,
        pack_config="3P",

        # Two-terminal cell — standard "+" and "-" pins.
        # No PCB footprint here; cells mate to power_board's
        # CellAttach_3x2_TLM1520 pad cluster via solder tabs.
        pins=[
            Pin(num="1", name="+", aliases=["VBAT", "POS"],
                type="power",
                note="solder tab — feeds 200 mΩ isolation resistor to BAT_RAW"),
            Pin(num="2", name="-", aliases=["GND", "NEG"],
                type="ground",
                note="solder tab — direct to GND"),
        ],
        footprint=None,                    # cells aren't soldered as a chip;
                                           # see add_cellattach_3x2_tlm1520
                                           # for the host-side footprint

        note=(
            "Tadiran TLM-1520HPM/S — high-power variant of the Li-MnO₂ "
            "organic cell family. The 'HPM' suffix distinguishes this "
            "from the lower-current TLM-1520M (300 mA cont) and from "
            "the TLM-1550M/S (AA size). The '/S' indicates solder-tab "
            "termination (vs '/SR' for spring contacts).\n\n"
            "Capacity declines with discharge rate:\n"
            "  - 125 mAh @ 5 mA continuous to 2.8 V\n"
            "  - 100 mAh @ 125 mA continuous to 2.8 V\n"
            "  - 75-80 mAh under pulse-heavy missions (datasheet §2.6 fig)\n\n"
            "Smash pack = 3× in parallel:\n"
            "  - 375 mAh capacity\n"
            "  - 5.25 A continuous (to 2.5 V)\n"
            "  - 11.25 A 1-s pulse (to 2.6 V)\n\n"
            "Storage characteristic (datasheet §2.4): well-behaved\n"
            "  @ 22 °C — 3 %/yr capacity loss. Mission storage at\n"
            "  ambient temperature is the design target.\n\n"
            "Predecessor in earlier Smash builds: TLM-1550M/S (AA size,\n"
            "470 mAh, 15 A pulse). Swapped to TLM-1520HPM/S for tighter\n"
            "axial fit in the Ø14.8 mm cell-attach cluster on power_board."
        ),
    )
    fields.update(overrides)
    return design.add_battery(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# Tadiran TLM-1530M/S — 2/3-AA High-Power Li Metal Oxide primary cell
# The low-profile single-cell option: ONE cell laid HORIZONTAL fits Ø34 and
# drops the battery compartment from 21 mm (vertical TLM-1520) to 15.1 mm.
# 200 mAh / 2.5 A continuous / 6.5 A 1-s pulse. Gun-hardened (20 kgₙ tested).
# ═════════════════════════════════════════════════════════════════════════

def add_tlm_1530m(design, ref: str, **overrides):
    """Tadiran TLM-1530M/S — 2/3-AA high-power Lithium Metal Oxide (Li-MnO₂)
    primary cell. Ø15.1 × 27.4 mm cylindrical, 200 mAh, 2.5 A continuous,
    6.5 A 1-second pulse. Used as a SINGLE cell in the `lowprofile` config,
    laid horizontal so its 15.1 mm diameter (not its 27.4 mm length) sets the
    compartment height — fits Ø34 (Ø31.8 bounding) and saves ~5.9 mm vs the
    3× vertical TLM-1520HPM pack.

    Crucially MIL-STD-810G rated: 50 000 gₙ theoretical /
    20 000 gₙ tested + 30 000 rpm spin.

    No discrete soldered footprint — '/S' = solder-tab termination; the two
    side tabs land on the P_CELL_TAB_POS/NEG `add_cell_solder_tab` pads on
    aft_end_board (the cell lies directly on the aft floor).

    Datasheet: TLM-1530M, Tadiran Rev D November 2025 ECN 6105040.
    """
    pn = "TLM-1530M/S"
    part_dir = "TLM-1530M_S"
    fields = dict(
        manf="Tadiran",
        manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn,
        description=(
            "2/3-AA high-power Li-MnO₂ metal-oxide primary cell, "
            "Ø15.1×27.4 mm, 200 mAh, 2.5 A continuous, 6.5 A 1-s pulse"
        ),
        datasheet=datasheet_ref(part_dir, "TLM-1530M_S.pdf"),

        # Chemistry / electrical (datasheet p1)
        chemistry="Li-MnO₂ organic (lithium metal oxide)",
        capacity_mah=200.0,                # @ 20 mA RT to 2.8 V (190 @ 225 mA)
        nominal_voltage_v=4.0,             # mid-OCV (3.95-4.07 V range)
        ocv_min_v=3.95,
        ocv_max_v=4.07,
        ccv_min_v=3.83,                    # @ 0.5 A, 0.1 s
        i_continuous_a=2.5,                # to 2.5 V cutoff
        i_pulse_a=6.5,                     # 1 s pulse to 2.6 V
        pulse_duration_s=1.0,
        impedance_mohm=175.0,              # <175 mΩ @ 1 kHz RT

        # Storage / self-discharge (datasheet accumulated-capacity-loss table)
        self_discharge_pct_per_year=3.0,   # 3 % @ 22 °C yr-1
        shelf_life_years=20.0,             # 18 % loss @ 22 °C over 20 yrs

        # Mechanical (datasheet p1)
        package="Ø15.1 × 27.4 mm (2/3 AA) cylindrical",
        size_mm=(15.1, 27.4),              # diameter, length
        height_mm=27.4,
        temp_range_c=(-40, 85),
        body_material="stainless steel can (glass-to-metal seal)",
        lead_material="Ni solder tab",
        weight_g=12.0,                     # 12 g max

        # Compliance / hazmat
        standards=["UN 38.3", "IEC 60086", "MIL-STD-810G"],
        hazmat_class="UN3090",

        # Sourcing (price_1pc/20k come from the assumptions.json overlay:
        # $61.52 @ 1pc → $39.99 @ 1080+ qty, Tadiran list)
        fab_country="IL",
        currency=None,
        price_1pc=None,
        price_20kpc=None,

        # Single-cell pack in the lowprofile config.
        pack_count=1,
        pack_config="1S",

        pins=[
            Pin(num="1", name="+", aliases=["VBAT", "POS"],
                type="power",
                note="solder tab (cell end) — direct to BAT_RAW (single cell, "
                     "no isolation resistor)"),
            Pin(num="2", name="-", aliases=["GND", "NEG"],
                type="ground",
                note="solder tab (other end) — direct to GND"),
        ],
        footprint=None,                    # see add_cell_contacts_1h

        note=(
            "Tadiran TLM-1530M/S — 2/3-AA military-grade Li metal oxide cell, "
            "the low-profile SINGLE-cell option. The 'M' is the high-power "
            "variant; '/S' = solder-tab termination (vs '/T', '/TP').\n\n"
            "Capacity vs rate (datasheet p1):\n"
            "  - 200 mAh @ 20 mA RT to 2.8 V\n"
            "  - 190 mAh @ 225 mA RT to 2.8 V\n\n"
            "Single-cell pack (lowprofile config):\n"
            "  - 200 mAh capacity (190 mAh sustained)\n"
            "  - 2.5 A continuous (to 2.5 V)\n"
            "  - 6.5 A 1-s pulse (to 2.6 V)\n\n"
            "Laid HORIZONTAL: 27.4×15.1 footprint → Ø31.8 bounding (fits Ø34), "
            "compartment height = the 15.1 mm diameter (vs 21 mm vertical).\n\n"
            "Gun-launch hardened (MIL-STD-810G): 50 000 gₙ theoretical / "
            "20 000 gₙ tested, 30 000 rpm — fixes the TLM-1520HPM's unconfirmed "
            "HPM gun rating. Pricing: $61.52 @ 1pc, 35 % off ($39.99) at 1080+."
        ),
    )
    fields.update(overrides)
    return design.add_battery(ref=ref, **fields)
