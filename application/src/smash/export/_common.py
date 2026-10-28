"""Shared helpers across the export writers.

Every writer consumes a `Design`, iterates components (chips + batteries
as siblings), and emits a single file. This module concentrates the
iteration / sanitization patterns so the per-format modules stay small.
"""

from __future__ import annotations

import re
from typing import Iterable

from smash.state import Design, Chip, Battery, Net


def all_components(design: Design) -> list:
    """Return chips + batteries + antennas as a single sorted-by-ref list.

    BOM, netlist, and footprint inventory all treat them as siblings.
    Sort by (board_tag, ref) so output diffs stay stable across runs.
    """
    components: list = []
    components.extend(design.chips)
    components.extend(design.batteries)
    components.extend(getattr(design, "antennas", []))
    components.sort(key=lambda c: (getattr(c, "board_tag", "") or "",
                                     c.ref))
    return components


def nets_with_pins(design: Design) -> list:
    """Return nets that have at least one connection. Sorted by name
    for stable output."""
    return sorted(
        (n for n in design.nets if n.pins),
        key=lambda n: n.name,
    )


def net_connections(net: Net) -> list:
    """Return (part_ref, pin_num) tuples for a Net, sorted for stable
    output. Net.pins is already a list of (ref, num) tuples — this just
    normalizes types and sorts.

    Strips the smash-internal `BALL_` prefix from pin numbers. The
    prefix exists in some BGA factories (e.g. AS4C DDR3) to namespace
    physical ball coords away from logical pin names; downstream EDA
    tools (KiCad, Allegro, PADS) need to see the raw ball coord ("A9",
    not "BALL_A9") to match the footprint's pad numbering.
    """
    return sorted(
        ((str(ref), _strip_ball_prefix(str(num))) for ref, num in net.pins),
        key=lambda t: (t[0], t[1]),
    )


def _strip_ball_prefix(num: str) -> str:
    """Strip the smash-internal `BALL_` prefix from a pin number for
    EDA-tool output. See `net_connections` docstring."""
    return num[len("BALL_"):] if num.startswith("BALL_") else num


def footprint_name(component) -> str:
    """Extract the footprint name string from a Chip/Battery.

    Returns the bare name without any KiCad library prefix
    ("Package_BGA:BGA-100_..." → "BGA-100_..."). Returns "UNDEFINED"
    if the component has no footprint yet.
    """
    fp = getattr(component, "footprint", None)
    if fp is None:
        return "UNDEFINED"
    name = getattr(fp, "name", None) or ""
    if ":" in name:
        return name.split(":")[-1]
    return name or "UNDEFINED"


def footprint_full(component) -> str:
    """Full footprint string verbatim from the Footprint dataclass —
    whatever the factory stored. Writers that need the `library:name`
    form should compose it themselves; this helper just hands back
    the raw `Footprint.name`."""
    fp = getattr(component, "footprint", None)
    if fp is None:
        return ""
    return getattr(fp, "name", "") or ""


_SHORT_REFS: dict = {}      # design ref → short refdes, while board_refdes is active
_REF_PREFIX = [""]          # the active board_refdes prefix (board-only refs: MH1 → AMH1)


def ref_prefix() -> str:
    """The board letter `board_refdes` is naming parts with ("" outside it)."""
    return _REF_PREFIX[0]


def kicad_ref(ref: str) -> str:
    """The refdes a part carries in KiCad files and the BOM. KiCad treats a
    reference that doesn't end in a digit as unannotated (refusing Update
    PCB from Schematic, and renumbering it if annotated), so a descriptive
    ref gets a `1`: `U_PMIC` → `U_PMIC1`; `U_IMU2` is left alone. Inside
    `board_refdes` a part on that board gets its short refdes instead.
    Internal keys (uuids, net lookups) keep the design ref."""
    if ref in _SHORT_REFS:
        return _SHORT_REFS[ref]
    return ref if ref[-1:].isdigit() else ref + "1"


_REFDES_CLASSES = {"TP", "SP", "BT", "FB", "SW", "LED", "ANT", "MH"}


def short_refdes(refs: Iterable[str], prefix: str = "") -> dict:
    """{design ref: classic refdes} for one board's parts: the ref's class
    letters (`R_ACTIVATE_MON1` → R, `TP_BAT_RAW` → TP, and a run-on word
    to its first letter: `CBOOST_IN1` → C, `RPU_I2C2_SCL` → R) numbered
    1, 2, … in natural order of the design refs, so the names stay put
    across regenerations while the part set does. `prefix` (the board's
    stack letter) goes in front — `AR1`, `ATP4` — making the names unique
    across the stack."""
    def nat(s):
        return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]
    count: dict = {}
    out = {}
    for ref in sorted(set(refs), key=nat):
        cls = (re.match(r"[A-Za-z]+", ref) or [""])[0].upper() or "X"
        if cls not in _REFDES_CLASSES:
            cls = cls[0]
        count[cls] = count.get(cls, 0) + 1
        out[ref] = f"{prefix}{cls}{count[cls]}"
    return out


def stack_letter(i: int) -> str:
    """A, B, … Z, AA, AB, … for stack level `i` (0 = the aft end)."""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(ord("A") + r) + s
    return s


class board_refdes:
    """`with board_refdes(board, prefix): ...` — every per-board writer
    (board, schematic, Protel netlist) names the board's parts R1, R2,
    Q1, … (after `prefix`, the board's stack letter) for the duration.
    Without a prefix the names are unique per board only, so multi-board
    outputs (panel, system schematic, project BOM) stay outside it.
    `.mapping` holds the {design ref: short refdes} table."""

    def __init__(self, board, prefix: str = ""):
        from smash.state import Chip
        self.prefix = prefix
        from smash.state.antenna import Antenna
        self.mapping = short_refdes(
            (pl.item.ref for pl in board.chip_placements
             if isinstance(pl.item, (Chip, Antenna)) and pl.item.footprint is not None),
            prefix)

    def __enter__(self):
        _SHORT_REFS.clear()
        _SHORT_REFS.update(self.mapping)
        _REF_PREFIX[0] = self.prefix
        return self

    def __exit__(self, *exc):
        _SHORT_REFS.clear()
        _REF_PREFIX[0] = ""


def board_datasheet(component) -> str:
    """The Datasheet field a part carries inside a board project: its PDF
    as copied to `datasheets/<part folder>/` beside the board, so the link
    works wherever the folder goes. URLs pass through."""
    ds = getattr(component, "datasheet", None) or ""
    if not ds or re.match(r"\w+://", ds):
        return ds
    parts = ds.replace("\\", "/").split("/")
    return "${KIPRJMOD}/datasheets/" + "/".join(parts[-2:])


def component_value(component) -> str:
    """The Value field a part carries in both the KiCad schematic and the
    board (they must agree, or schematic-parity DRC flags every part):
    its value ("10k"), else its MPN, else its ref."""
    return (getattr(component, "value", None) or getattr(component, "manf_pn", None)
            or component.ref)


# ── identifier sanitization (per-format) ─────────────────────────────────

def sanitize_ascii(s: str) -> str:
    """Replace non-ASCII characters with reasonable substitutes; drop
    anything that can't be transliterated. Used by EDIF + any other
    writer that requires printable-ASCII tokens.
    """
    _map = {
        "—": "-", "–": "-", "−": "-",
        "°": "deg", "±": "+/-", "×": "x", "÷": "/",
        "…": "...",
        "‘": "'", "’": "'", "“": '"', "”": '"',
        "µ": "u", "μ": "u",
        "Ø": "Dia", "ø": "dia",
        "≤": "<=", "≥": ">=", "≠": "!=",
        "½": "1/2", "¼": "1/4", "¾": "3/4",
        "Ω": "Ohm",
        "€": "EUR", "£": "GBP",
        "©": "(c)", "®": "(R)", "™": "(TM)",
        "→": "->", "←": "<-",
        " ": " ",
        # Western European letters seen in manufacturer names
        "ä": "a", "ö": "o", "ü": "u", "ß": "ss",
        "Ä": "A", "Ö": "O", "Ü": "U",
        "á": "a", "à": "a", "â": "a", "ã": "a", "å": "a",
        "Á": "A", "À": "A", "Â": "A", "Ã": "A", "Å": "A",
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "É": "E", "È": "E", "Ê": "E", "Ë": "E",
        "í": "i", "ì": "i", "î": "i", "ï": "i",
        "ó": "o", "ò": "o", "ô": "o", "õ": "o",
        "ú": "u", "ù": "u", "û": "u",
        "ñ": "n", "Ñ": "N", "ç": "c", "Ç": "C",
        "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE",
    }
    s = str(s)
    for u, a in _map.items():
        s = s.replace(u, a)
    s = s.encode("ascii", errors="replace").decode("ascii").replace("?", "_")
    return "".join(ch if 32 <= ord(ch) <= 126 else "_" for ch in s)


def sanitize_edif_id(s: str) -> str:
    """EDIF identifier: must start with letter, contain only [A-Za-z0-9_]."""
    s = re.sub(r"[^A-Za-z0-9_]", "_", str(s))
    if not s or not s[0].isalpha():
        s = "X_" + s
    return s


def sanitize_pads_id(s: str) -> str:
    """PADS allows [A-Za-z0-9_.+-]; replace anything else with '_'."""
    return re.sub(r"[^A-Za-z0-9_.+\-]", "_", str(s)) or "X"


def sanitize_protel_id(s: str) -> str:
    """Protel/Tango/Altium netlist identifier — same charset as PADS."""
    return re.sub(r"[^A-Za-z0-9_.+\-]", "_", str(s)) or "X"


# Telesis (Allegro third-party) special chars — replaced with '_' in
# footprint/device names. Includes ',' and ':' to handle Nexperia
# "PMEG2010EJ,115" and Micron "MT41K256M16TW-107:P TR" suffixes.
ALLEGRO_SPECIAL_CHARS = " +-/\\.,:"


def sanitize_allegro_id(s: str) -> str:
    """Telesis $PACKAGES name: strip all special chars to '_'. Leading
    digits get an '_' prefix so identifiers stay valid."""
    s = str(s) or "X"
    for c in ALLEGRO_SPECIAL_CHARS:
        s = s.replace(c, "_")
    if s and s[0].isdigit():
        s = "_" + s
    return s


def allegro_net_name(s: str) -> str:
    """Telesis net-name rule: quote in single quotes unless the name
    is a bare identifier (letter or underscore + alnum/underscore).
    Allegro otherwise rejects '+3.3V', 'N$1', etc. with SPMHNI-113.
    """
    s = str(s)
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", s):
        return s
    return "'" + s + "'"


# ── BOM-side helpers ─────────────────────────────────────────────────────


def component_cost_usd(component) -> float | None:
    """Best-effort USD cost. Returns price_1pc directly if currency=='USD',
    None otherwise. Currency conversion is the caller's responsibility
    (the BOM writer takes an explicit fx_rates parameter)."""
    price = getattr(component, "price_1pc", None)
    currency = getattr(component, "currency", None)
    if price is None:
        return None
    if currency in (None, "USD"):
        return float(price)
    return None  # caller can override via fx-conversion in write_bom
