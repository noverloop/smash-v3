# smash — Smash design data-model library

Pure-Python library carrying the canonical electrical-design schema for
the Smash radar sonde. Defines the data classes
(`Chip`, `Net`, `Design`, `Board`, `SmashState`) that every Smash tool
reads and writes, plus the validators that enforce design rules across
the whole state.

## Layering

```
SmashState   →   Design    →   BoardState              (in tools/)
config           electrical    PCB layout
boards+flags    chips+nets    mesh+chips+balls

|----------- this library -----------|--------- tools/ ---------|
                pcbnew-free                    pcbnew-bound
```

This library is **pcbnew-free** — it has no dependency on KiCad's
bundled Python and can run on any interpreter ≥3.9. Anything that
needs to read or write a `.kicad_pcb` lives outside this package
(see the project's `tools/` directory).

## Install (development mode)

```sh
cd Export/application
pip install -e ".[test]"
```

## Run tests

```sh
pytest
```

## Public API

```python
from smash import Design, Chip, Pin, Net, SmashState

# Declare a configuration
smash = SmashState.new().add_companion_computer().add_radar()

# Build the electrical design
design = Design()
mpu = design.add_chip(ref="U_MPU", manf_pn="STM32MP255FAK3",
                      board_tag="companion_compute", ...)
design.add_power_net("COMP_1V35", voltage_v=1.35) \
      .connect(mpu.pin("VDD"))

# Cross-state validation
for issue in design.validate():
    print(f"{issue.severity}: {issue.message}")

# Cost / weight rollup
print(smash.cost_summary(design))
```

## Layout

```
src/smash/             — importable package
  __init__.py          — public API
  design.py            — Chip, Pin, Net, Design + validators
  smash_state.py       — Board, SmashState (boards + features + netlist)
  components_md.py     — parser for the project's components.md
tests/                 — pytest, mirrors src/ layout
bin/                   — CLI utilities (smash-validate, smash-cost, ...)
```

## Design rules

- **Datasheet-exact naming.** Every string (pin number, pin name, alias,
  voltage rail, bus name) is transcribed verbatim from the chip's
  datasheet or the relevant application note. No paraphrasing,
  no normalization.
- **Don't encode what can be computed.** Policy (forbidden fab
  countries, capacitor-value → footprint mapping) lives in functions,
  not data objects.
- **Validators query the whole state.** Cross-design rules — "every
  DDR3 bus net has both MPU and DDR3 pads", "no part fab'd in CN/TW",
  "MIL-spec caps on critical rails" — operate on a fully-populated
  `Design` and yield structured `Issue` records.
