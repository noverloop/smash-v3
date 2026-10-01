"""Datasheet-derived pin spec — `pinspec.json` sidecars + loader.

Each chip in `parts/sources/<PN>/` may carry a `pinspec.json` recording
the datasheet-verified pin map: `(num, name, type, aliases?, note?)`
per pin. The `_v_factory_matches_pinspec` validator reads this and
compares against the live factory's `Chip.pins` — any drift fails.

Why a sidecar instead of inlining in the factory: the pinspec is
datasheet ground truth (sourced from the PDF, often a different person
than the factory author), the factory is a code translation. Keeping
them in separate files means a validator can cross-check the two —
catches both factory bugs and pinspec stale-ness.

A chip without a pinspec is not flagged — the framework is opt-in
per-chip. Use `_v_factory_matches_pinspec` as a CI gate to require
pinspecs for new factories once a critical mass exists.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path


@dataclass(frozen=True)
class PinSpecEntry:
    num: str
    name: str
    type: str
    aliases: tuple = ()
    note: str | None = None
    # Voltage constraints (optional, both per-pin per datasheet):
    #   voltage_v        — nominal/expected. For VOUT pins of LDOs/regs,
    #                      this is the regulated value (3.3, 1.8, ...).
    #                      For VDD pins of chips with a single operating
    #                      voltage, this is the spec voltage.
    #   voltage_range_v  — (min, max) abs-max range. For VIN pins of
    #                      regulators that accept a span (1.6–5.5 V on
    #                      LDL112), or for VDD pins of chips rated over
    #                      a wide range.
    # The validators check `net.voltage_v` against whichever is provided.
    voltage_v: float | None = None
    voltage_range_v: tuple | None = None
    # Frequency constraints (optional, per datasheet):
    #   frequency_hz       — point value. For an oscillator OUTPUT pin
    #                        this is the chip's nominal output (32768
    #                        on an LSE, 8e6 on a DSC1001-008.0000).
    #   frequency_range_hz — (min, max) acceptable range for an INPUT
    #                        clock pin (e.g. STM32 HSE accepts 4-50 MHz).
    # Validator: if a clock net's frequency_hz is set, it must match
    # the pin's frequency_hz (output) OR fall in frequency_range_hz
    # (input).
    frequency_hz: float | None = None
    frequency_range_hz: tuple | None = None


@dataclass(frozen=True)
class PinSpec:
    manf_pn: str
    datasheet: str
    package: str | None
    pins: tuple


def _sources_root() -> Path:
    return Path(__file__).resolve().parent / "sources"


@cache
def load_pinspec(manf_pn: str) -> PinSpec | None:
    """Return the `PinSpec` for `manf_pn`, or None if no sidecar exists.

    The lookup walks `parts/sources/<dir>/pinspec.json` for any dir
    whose folder name matches `manf_pn` (case-sensitive). Tolerant of
    chips without sidecars — those just return None.
    """
    candidates = [
        _sources_root() / manf_pn / "pinspec.json",
        _sources_root() / manf_pn.replace(":", "_") / "pinspec.json",
        _sources_root() / manf_pn.replace("/", "_") / "pinspec.json",
    ]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        return None
    raw = json.loads(path.read_text())
    meta = raw.get("_meta", {})
    pins = tuple(
        PinSpecEntry(
            num=str(p["num"]),
            name=p["name"],
            type=p["type"],
            aliases=tuple(p.get("aliases", [])),
            note=p.get("note"),
            voltage_v=p.get("voltage_v"),
            voltage_range_v=(tuple(p["voltage_range_v"])
                             if "voltage_range_v" in p else None),
            frequency_hz=p.get("frequency_hz"),
            frequency_range_hz=(tuple(p["frequency_range_hz"])
                                if "frequency_range_hz" in p else None),
        )
        for p in raw["pins"]
    )
    return PinSpec(
        manf_pn=meta.get("manf_pn", manf_pn),
        datasheet=meta.get("datasheet", ""),
        package=meta.get("package"),
        pins=pins,
    )


def _norm(s: str) -> str:
    """Normalize a pin-name string for tolerant comparison. Strips
    whitespace, lowers case, treats `_` and space as equivalent so
    "CLK Out" and "CLK_OUT" compare equal."""
    return s.strip().lower().replace(" ", "_")


def _names_for(p) -> set:
    """All ways this pin can be referred to: primary name + aliases."""
    out: set = set()
    if p.name:
        out.add(_norm(p.name))
    for a in (p.aliases or ()):
        out.add(_norm(a))
    return out


def compare(chip, spec: PinSpec) -> list:
    """Return a list of disagreements between `chip.pins` and `spec.pins`.

    Each entry is a `(rule, message)` tuple ready to be wrapped in an
    `Issue`. Mismatch categories:

      - pinspec_missing_pin   spec lists a pin number not in chip
      - pinspec_extra_pin     chip has a pin number not in spec
      - pinspec_name_mismatch the datasheet's canonical name is NOT
                              present in the factory's name+alias set
                              for this pin number (whitespace and
                              case-normalized, `_`↔space-folded)
      - pinspec_type_mismatch same num, different type (strict —
                              type is a functional declaration, not a
                              naming convention)
    """
    out: list = []
    by_num_spec = {p.num: p for p in spec.pins}
    by_num_chip = {p.num: p for p in chip.pins}

    for num, sp in by_num_spec.items():
        cp = by_num_chip.get(num)
        if cp is None:
            out.append((
                "pinspec_missing_pin",
                f"pin {num!r} in pinspec ({sp.name!r}) absent from factory",
            ))
            continue
        # Name check: datasheet's canonical name (or any datasheet alias)
        # must appear in factory's name-or-alias set, normalized.
        chip_names = _names_for(cp)
        spec_names = {_norm(sp.name), *(_norm(a) for a in sp.aliases)}
        if not (chip_names & spec_names):
            out.append((
                "pinspec_name_mismatch",
                f"pin {num!r}: factory name={cp.name!r} (aliases={list(cp.aliases or ())}) "
                f"shares no name with pinspec name={sp.name!r} "
                f"(aliases={list(sp.aliases)})",
            ))
        # Type check: strict.
        if (cp.type or "") != sp.type:
            out.append((
                "pinspec_type_mismatch",
                f"pin {num!r} ({sp.name!r}): factory type={(cp.type or '')!r}, "
                f"pinspec type={sp.type!r}",
            ))

    for num, cp in by_num_chip.items():
        if num not in by_num_spec:
            out.append((
                "pinspec_extra_pin",
                f"pin {num!r} ({cp.name!r}, type={cp.type!r}) is in the "
                f"factory but not in the pinspec",
            ))
    return out
