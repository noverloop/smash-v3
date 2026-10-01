"""Structural validator for Specctra DSN files.

Catches the most common breakage modes that ship the DSN to
FreeRouting / Allegro / DeepPCB and surface as cryptic parser errors:

  - mismatched parentheses (the LISP-style syntax is unforgiving)
  - required top-level sections present (`structure`, `library`,
    `placement`, `network`, `wiring`)
  - net entries reference padstack/image identifiers that the
    `(library ...)` section actually defines
  - pin tokens in `(net ...)` match `<REF>-<PIN>` form that the
    KiCad-derived DSN uses

This is a structural validator only — it does not check geometry
(boundary closure, courtyard overlap, etc.). Pair with the
TypeScript `tools/dsn-validate` for schema validation; this Python
validator catches issues fast in unit tests without needing a Node
runtime.

Usage:
  from smash.validators.specctra import validate_specctra_dsn
  issues = validate_specctra_dsn(path_or_text)
  if any(i.severity == "error" for i in issues):
      ...
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Iterable


@dataclasses.dataclass
class DsnIssue:
    """One validation finding."""
    severity: str        # "error" | "warning" | "info"
    rule: str            # short tag, e.g. "balanced_parens"
    message: str
    line: int | None = None


_REQUIRED_TOP_LEVEL_SECTIONS = (
    "structure", "library", "placement", "network", "wiring",
)


def validate_specctra_dsn(
    source: str | Path,
) -> list[DsnIssue]:
    """Validate a Specctra DSN. `source` may be a file path or the raw
    DSN text. Returns a list of issues — empty if the file passes."""
    text = _load(source)
    issues: list[DsnIssue] = []
    issues.extend(_check_balanced_parens(text))
    issues.extend(_check_required_sections(text))
    issues.extend(_check_pin_token_form(text))
    issues.extend(_check_net_refs_to_padstacks(text))
    return issues


# ── helpers ──────────────────────────────────────────────────────────────


def _load(source: str | Path) -> str:
    """Accept a path or raw text. Heuristic: if the value looks like a
    file path that exists, read it; otherwise treat as text."""
    if isinstance(source, Path):
        return source.read_text()
    if isinstance(source, str) and "\n" not in source and len(source) < 4096:
        p = Path(source)
        if p.exists():
            return p.read_text()
    return str(source)


def _check_balanced_parens(text: str) -> Iterable[DsnIssue]:
    """LISP-style parens must balance. Quoted strings may contain `(`
    and `)` — track quote state. DSN's `(string_quote ")` metadata
    declaration carries a lone `"` character that's NOT a quote
    delimiter; strip it before counting."""
    # `(string_quote ")` declares the string-quote character for the
    # rest of the document. The `"` inside is a literal datum, not a
    # quote opener. Same for `(string_quote ')` if the document chose
    # single-quote as the string char.
    text = re.sub(r"\(string_quote\s+.\s*\)", "", text)
    depth = 0
    in_quote = False
    line_no = 1
    for ch in text:
        if ch == "\n":
            line_no += 1
            continue
        if ch == '"':
            in_quote = not in_quote
            continue
        if in_quote:
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                yield DsnIssue(
                    severity="error",
                    rule="balanced_parens",
                    message="closing paren with no matching opener",
                    line=line_no,
                )
                return
    if depth != 0:
        yield DsnIssue(
            severity="error",
            rule="balanced_parens",
            message=f"{depth} unclosed paren(s) at EOF",
            line=line_no,
        )


def _check_required_sections(text: str) -> Iterable[DsnIssue]:
    """Each of `structure`, `library`, `placement`, `network`,
    `wiring` must appear as a top-level `(<section> ...)` opener.
    `(wiring)` may be empty per the tscircuit/specctra-dsn-json schema.
    """
    for sect in _REQUIRED_TOP_LEVEL_SECTIONS:
        # match "(<sect>" at any indentation, must be followed by space
        # or close-paren (in case of an empty section)
        if not re.search(rf"\(\s*{re.escape(sect)}\b", text):
            yield DsnIssue(
                severity="error",
                rule="required_section",
                message=f"missing required `(<{sect}> ...)` section",
            )


def _check_pin_token_form(text: str) -> Iterable[DsnIssue]:
    """Pin tokens inside `(net ...)` follow `<REF>-<PIN>` form in the
    Smash export (e.g. `U_MPU-A12`). If a `(pins ...)` block contains
    a token without `-`, flag it as suspect.
    """
    in_pins = False
    line_no = 0
    for line in text.splitlines():
        line_no += 1
        stripped = line.strip()
        if stripped.startswith("(pins"):
            in_pins = True
            continue
        if in_pins:
            if stripped.startswith(")"):
                in_pins = False
                continue
            for tok in stripped.split():
                if tok and tok != "(" and tok != ")":
                    if "-" not in tok:
                        yield DsnIssue(
                            severity="warning",
                            rule="pin_token_form",
                            message=(
                                f"pin token {tok!r} doesn't match "
                                f"<REF>-<PIN> form"
                            ),
                            line=line_no,
                        )


def _check_net_refs_to_padstacks(text: str) -> Iterable[DsnIssue]:
    """`(pin <padstack> ...)` lines in the `library` section must
    reference padstack identifiers that have a matching
    `(padstack <id> ...)` definition.
    """
    padstacks = set(re.findall(r"\(padstack\s+(\S+)", text))
    # The `(pin <padstack> ...)` lines inside `(image ...)` blocks
    pin_padstack_refs = set(re.findall(r"\(pin\s+(\S+)\s", text))
    for ref in pin_padstack_refs:
        if ref not in padstacks:
            yield DsnIssue(
                severity="error",
                rule="padstack_ref",
                message=f"image pin references undefined padstack {ref!r}",
            )
