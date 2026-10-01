"""Pin — one electrical pin on a Chip."""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class Pin:
    """One pin on a Chip with its connected net.

    **Naming convention: use the datasheet's exact strings.** `num`
    is the datasheet ball-position or pin-number (e.g. "J4", "K10",
    "A1"). `name` is the datasheet's primary functional name for the
    pin (e.g. "PD0", "VDDA", "DDR_A0"). `aliases` are any additional
    names the datasheet uses for the same pin — typically alt-function
    labels (e.g. ["UART4_RX","TIM2_CH1"] for an STM32 GPIO with two
    documented alt functions). Don't paraphrase; don't simplify;
    match the PDF byte-for-byte.

    `chip_ref` is a back-reference to the parent Chip so connection
    code can pass Pin objects directly (no ambiguity between e.g.
    PD0-on-H562 and PD0-on-WLE5). Set automatically when a Pin is
    added to a Chip via `Design.add_chip(..., pins=...)`.

    Electrical-class fields (transcribed from the datasheet pin
    table):
      - `type`: one of "power", "ground", "io", "input", "output",
                "analog", "clock", "nc", "reserved". Use lowercase
                tokens; new categories added only when needed.
      - `voltage_domain`: name of the VDD rail this pin references
                (e.g. "VDDIO1", "VDDA", "VBAT"). For type="power"
                pins, the rail they FEED; for I/O pins, the rail
                that clamps their HIGH level.
      - `io_standard`: datasheet IO standard string ("LVCMOS33",
                "LVDS", "SSTL15", "HSTL18", etc.) for impedance-aware
                routing.
    """
    num: str                          # datasheet pad/ball position (e.g. "J4")
    name: str | None = None           # datasheet primary name (e.g. "PD0")
    aliases: list = dataclasses.field(default_factory=list)
                                      # alt-function names from datasheet
    type: str | None = None           # power|ground|io|input|output|
                                      # analog|clock|nc|reserved
    voltage_domain: str | None = None # name of the VDD rail referenced
    io_standard: str | None = None    # "LVCMOS33", "LVDS", "SSTL15", ...
    net: str | None = None            # net the pin connects to
    chip_ref: str | None = None       # back-ref to parent Chip
    # Alternate-function table — read-only ground truth from the part's
    # datasheet (transcribed verbatim from CubeMX XML for STM32 parts).
    # For an STM32 GPIO this is the full list of peripheral signals the
    # pin can be muxed to (e.g. ["UART4_TX", "TIM2_CH1", "SPI3_NSS",
    # "GPIO", ...]). Power / ground pins carry an empty list.
    alt_functions: list = dataclasses.field(default_factory=list)
    # Design choice: which AF this pin's firmware actually configures
    # at boot. Validated against `alt_functions` by the pinmux validator.
    # None when the pin isn't a programmable AF (power, ground, NRST,
    # fixed-function clock input) or when the engineer hasn't picked yet.
    af_assigned: str | None = None
    # Free-form human description of WHAT this pin's wire actually does
    # in the design. Captured at connect-time alongside the net name —
    # the net carries the signal identity, this carries the per-leg
    # purpose ("clock to TCAN chip", "WiFi SDIO clock to Murata module").
    # Pure documentation; the validator does NOT typecheck it.
    intent: str | None = None
    note: str | None = None           # free-form: anything not yet
                                      # structured (compliance comments,
                                      # bring-up reminders, etc.)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

