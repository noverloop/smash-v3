"""Specctra DSN validator — structural + full-schema.

Two layers of checking, both surfaced through one entrypoint:

  - **Structural** (`structural.py`): fast regex checks that catch the
    bulk of authoring bugs without a full parse — balanced parens,
    required top-level sections, pin-token form, padstack references.
    Cheap to run in unit tests.
  - **Full schema** (this package): port of
    `tools/dsn-validate/lib/*.ts` (tscircuit/specctra-dsn-json). Parses
    the file into typed dataclasses (`DsnPcbDesign`) and surfaces
    field-level issues — the same checks the TS reference runs against
    real KiCad/FreeRouting/Allegro DSNs.

Public API:

    from smash.validators.specctra import (
        validate_specctra_dsn,   # all checks; returns list[DsnIssue]
        parse_dsn,               # full parse → DsnPcbDesign
        DsnIssue,
        DsnPcbDesign,
    )

`validate_specctra_dsn(source)` runs the structural checks first; if
they pass it does a full parse and returns any field-level issues. If
the structural checks fail, the full parse is skipped (it would
cascade into noise).
"""

from __future__ import annotations

from pathlib import Path

from smash.validators.specctra.structural import (
    validate_specctra_dsn as _validate_structural,
    DsnIssue,
)
from smash.validators.specctra._sexp import parse_sexp
from smash.validators.specctra._schema import (
    DsnPcbDesign, Parser, Resolution, Structure, Network, Wiring,
)
from smash.validators.specctra._interpreters import (
    parse_sexpr_parser, parse_sexpr_structure, parse_sexpr_placement,
    parse_sexpr_library, parse_sexpr_network, parse_sexpr_wiring,
)


__all__ = [
    "validate_specctra_dsn",
    "parse_dsn",
    "DsnIssue",
    "DsnPcbDesign",
]


# ── full-schema parser ──────────────────────────────────────────────────


def parse_dsn(source: str | Path) -> DsnPcbDesign:
    """Parse a DSN file (path or raw text) into a `DsnPcbDesign`
    dataclass. Raises `ValueError` on syntax errors or missing
    required sections.

    Mirrors `parseDsnToJson` in tscircuit/specctra-dsn-json — parse
    the s-expression, then dispatch each section to its interpreter,
    then assemble the top-level dataclass.
    """
    text = _load(source)
    sexp = parse_sexp(text)
    if not sexp or sexp[0] != "pcb":
        raise ValueError(
            f"top-level node must be `(pcb ...)`, got {sexp[0]!r}"
        )
    pcb_id = sexp[1] if len(sexp) > 1 else ""

    parser: Parser | None = None
    resolution: Resolution | None = None
    unit: str = ""
    structure: Structure | None = None
    placement: list = []
    library: list = []
    network: Network = Network()
    wiring: Wiring = Wiring()

    for element in sexp[2:]:
        if not isinstance(element, list) or not element:
            continue
        kind = element[0]
        body = element[1:]
        if kind == "parser":
            parser = parse_sexpr_parser(body)
        elif kind == "resolution":
            # body looks like ["um", "10"]
            resolution = Resolution(unit=body[0], value=float(body[1]))
        elif kind == "unit":
            unit = body[0]
        elif kind == "structure":
            structure = parse_sexpr_structure(body)
        elif kind == "placement":
            placement = parse_sexpr_placement(body)
        elif kind == "library":
            library = parse_sexpr_library(body)
        elif kind == "network":
            network = parse_sexpr_network(body)
        elif kind == "wiring":
            wiring = parse_sexpr_wiring(body)
        # Unknown top-level keys ignored — DSN files commonly carry
        # tool-specific extras that aren't part of the formal schema.

    # Required-field guards mirror the zod schema's parse-time enforcement
    if parser is None:
        raise ValueError("DSN missing required `(parser ...)` section")
    if resolution is None:
        raise ValueError("DSN missing required `(resolution ...)` section")
    if not unit:
        raise ValueError("DSN missing required `(unit ...)` declaration")
    if structure is None:
        raise ValueError("DSN missing required `(structure ...)` section")
    if not structure.layers:
        raise ValueError("structure missing layers")
    if not structure.boundaries:
        raise ValueError("structure missing boundaries")
    if structure.via is None:
        raise ValueError("structure missing `(via ...)` declaration")

    return DsnPcbDesign(
        pcb_id=pcb_id, parser=parser, resolution=resolution, unit=unit,
        structure=structure, placement=placement, library=library,
        network=network, wiring=wiring,
    )


# ── unified validator (structural + full schema) ───────────────────────


def validate_specctra_dsn(source: str | Path) -> list[DsnIssue]:
    """Run all checks against a DSN file. Returns a list of issues —
    empty if the file passes.

    Order:
      1. Structural checks (balanced parens, required sections,
         padstack refs, pin-token form). If any errors, skip step 2 —
         those errors would cascade through the full parse.
      2. Full-schema parse via `parse_dsn`. Translates any
         ValueError raised into a `DsnIssue` with rule="schema".
    """
    issues = _validate_structural(source)
    if any(i.severity == "error" for i in issues):
        return issues
    # Structural pass — try the full parse
    try:
        parse_dsn(source)
    except ValueError as e:
        issues.append(DsnIssue(
            severity="error",
            rule="schema",
            message=str(e),
        ))
    return issues


# ── helper ──────────────────────────────────────────────────────────────


def _load(source: str | Path) -> str:
    if isinstance(source, Path):
        return source.read_text()
    if isinstance(source, str) and "\n" not in source and len(source) < 4096:
        p = Path(source)
        if p.exists():
            return p.read_text()
    return str(source)
