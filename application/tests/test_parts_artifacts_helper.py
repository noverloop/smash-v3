"""Verify the `parts._artifacts` parser helper on known good artifacts.

Cross-checks against IRLML6402TRPBF (3-pin SOT-23) and AD8603AUJZ-R2
(5-pin TSOT with the '+IN' that pinmap.txt mangles to 'PIN').
"""

from __future__ import annotations

import pathlib

import pytest

from smash.state import Pad
from smash.parts._artifacts import (
    pins_from_kicad_sym,
    pads_from_kicad_mod,
    outline_polygon,
    build_pins,
)


REPO = pathlib.Path(__file__).resolve().parents[2]
SRC = REPO / "application/src/smash/parts/sources"


# ─── KiCad symbol parsing ────────────────────────────────────────────────

class TestPinsFromKicadSym:
    def test_irlml6402(self):
        # Known: 3 pins, G/S/D on 1/2/3
        pins = pins_from_kicad_sym(
            str(SRC / "IRLML6402TRPBF" / "IRLML6402TRPBF.kicad_sym"))
        assert len(pins) == 3
        nums = {p[0] for p in pins}
        names = {p[1] for p in pins}
        assert nums == {"1", "2", "3"}
        assert names == {"G", "S", "D"}

    def test_ad8603_plus_in_preserved(self):
        # The whole point — pinmap.txt has "PIN" (the "+" stripped).
        # The KiCad sym has "+IN" verbatim.
        pins = pins_from_kicad_sym(
            str(SRC / "AD8603AUJZ-R2" / "AD8603AUJZ-R2.kicad_sym"))
        names = {p[1] for p in pins}
        assert "+IN" in names
        assert "-IN" in names
        assert "V+" in names
        assert "V-" in names
        assert "OUT" in names

    def test_tps25940_bar_notation_preserved(self):
        # The KiCad sym uses escaped bar-notation `F\\L\\T\\` for /FLT
        pins = pins_from_kicad_sym(
            str(SRC / "TPS25940AQRVCTQ1" / "TPS25940AQRVCTQ1.kicad_sym"))
        # Should be 21 pins including EP
        assert len(pins) == 21
        names = {p[1] for p in pins}
        # FLT pin name carries the bar-notation backslashes
        assert any("F" in n and "L" in n for n in names)


# ─── Footprint parsing ───────────────────────────────────────────────────

class TestPadsFromKicadMod:
    def test_irlml6402_sot23(self):
        # 3 SMD rect pads at known positions
        pads = pads_from_kicad_mod(
            str(SRC / "IRLML6402TRPBF" / "SOT95P237X112-3N.kicad_mod"))
        assert len(pads) == 3
        # Look up pad 1. The .kicad_mod is screen-y-down (pad 1 at y=-0.95);
        # the importer converts to the smash math-y-up model, so Y is negated
        # (the kicad_pcb exporter flips it back at the boundary). See
        # pads_from_kicad_mod.
        p1 = next(p for p in pads if p.num == "1")
        assert p1.position_mm == pytest.approx((-1.05, 0.95))
        # The .kicad_mod pad carries a 90° rotation with (size 0.6 1.3);
        # the model's Pad has no rotation field, so the importer bakes
        # the rotation into the size: 1.3 wide × 0.6 tall.
        assert p1.size_mm == pytest.approx((1.3, 0.6))
        assert p1.shape == "rect"
        assert p1.layer == "F.Cu"
        assert p1.drill_mm is None      # SMD, no drill

    def test_iis2mdc_lga12(self):
        # 12 LGA pads
        pads = pads_from_kicad_mod(
            str(SRC / "IIS2MDCTR" / "IIS2MDCTR.kicad_mod"))
        assert len(pads) == 12
        nums = {p.num for p in pads}
        assert nums == {str(i) for i in range(1, 13)}


# ─── Outline polygons ────────────────────────────────────────────────────

class TestOutlinePolygon:
    def test_irlml6402_courtyard_is_4_vertices(self):
        verts = outline_polygon(
            str(SRC / "IRLML6402TRPBF" / "SOT95P237X112-3N.kicad_mod"),
            "F.CrtYd")
        # Courtyard rectangle: 4 distinct vertices
        assert len(verts) == 4


# ─── build_pins overlay convenience ──────────────────────────────────────

class TestBuildPins:
    def test_overlay_by_pin_number(self):
        pins = build_pins(
            str(SRC / "IRLML6402TRPBF" / "IRLML6402TRPBF.kicad_sym"),
            types={"1": "input", "2": "io", "3": "io"},
            aliases={"1": ["Gate"], "2": ["Source"], "3": ["Drain"]},
        )
        p1 = next(p for p in pins if p.num == "1")
        assert p1.name == "G"
        assert p1.type == "input"
        assert p1.aliases == ["Gate"]

    def test_overlay_by_pin_name(self):
        # Same overlay keyed by name instead of number — both should work
        pins = build_pins(
            str(SRC / "IRLML6402TRPBF" / "IRLML6402TRPBF.kicad_sym"),
            types={"G": "input"},
            notes={"G": "MOSFET gate"},
        )
        pg = next(p for p in pins if p.name == "G")
        assert pg.type == "input"
        assert pg.note == "MOSFET gate"

    def test_caching_doesnt_share_pin_objects(self):
        # Calling build_pins twice should return distinct Pin objects
        # (so per-Design mutation doesn't bleed across calls).
        a = build_pins(str(SRC / "IRLML6402TRPBF" / "IRLML6402TRPBF.kicad_sym"))
        b = build_pins(str(SRC / "IRLML6402TRPBF" / "IRLML6402TRPBF.kicad_sym"))
        assert a is not b
        for x, y in zip(a, b):
            assert x is not y


# ─── Double-underscore -> single-underscore auto-alias ───────────────────
#
# SamacSys often spells multi-word pin names with `__` separators
# (`VIDDA__10RF1`, `MSS_MIBSPIA__CS0`). The catalog keeps those names
# verbatim and `build_pins` adds a single-underscore alias so callers can
# use either form. Collision-safety is critical: if collapsing `__` to
# `_` produces a name that already exists on another pin, the alias is
# suppressed to avoid an ambiguous lookup.

class TestDoubleUnderscoreAliases:
    def _write(self, tmp_path, body):
        sym = tmp_path / "fake.kicad_sym"
        sym.write_text(
            '(kicad_symbol_lib (version 20211014) (generator test)\n'
            '  (symbol "FAKE" (in_bom yes) (on_board yes)\n'
            f'{body}\n'
            '  )\n'
            ')\n'
        )
        return str(sym)

    def _pin(self, num, name):
        return (
            f'    (pin power_in line (at 0 0 0) (length 5.08)\n'
            f'      (name "{name}" (effects (font (size 1.27 1.27))))\n'
            f'      (number "{num}" (effects (font (size 1.27 1.27))))\n'
            f'    )'
        )

    def test_collapsed_alias_added_when_no_collision(self, tmp_path):
        sym = self._write(tmp_path, "\n".join([
            self._pin("1", "VIDDA__10RF1"),
            self._pin("2", "VDD_3V3"),
        ]))
        pins = build_pins(sym)
        p1 = next(p for p in pins if p.num == "1")
        assert p1.name == "VIDDA__10RF1"
        # Single-underscore alias added (no collision)
        assert "VIDDA_10RF1" in p1.aliases

    def test_collapsed_alias_skipped_when_collides_with_other_primary(self, tmp_path):
        # Pin 1 (`FOO__BAR`) and pin 2 (`FOO_BAR`) both exist on the
        # same part. Collapsing `FOO__BAR` -> `FOO_BAR` would shadow
        # pin 2's primary name. The alias MUST be suppressed.
        sym = self._write(tmp_path, "\n".join([
            self._pin("1", "FOO__BAR"),
            self._pin("2", "FOO_BAR"),
        ]))
        pins = build_pins(sym)
        p1 = next(p for p in pins if p.num == "1")
        p2 = next(p for p in pins if p.num == "2")
        assert "FOO_BAR" not in p1.aliases   # alias suppressed
        assert p2.name == "FOO_BAR"          # primary name intact

    def test_collapsed_alias_skipped_when_two_pins_collapse_to_same(self, tmp_path):
        # Two distinct double-underscore names both collapse to the
        # same single-underscore form -> ambiguous, suppress on both.
        # (Hypothetical; SamacSys doesn't actually do this, but if it
        # ever happens we don't want a silent collision.)
        sym = self._write(tmp_path, "\n".join([
            self._pin("1", "A__B_C"),     # collapses to "A_B_C"
            self._pin("2", "A_B__C"),     # collapses to "A_B_C"
        ]))
        pins = build_pins(sym)
        p1 = next(p for p in pins if p.num == "1")
        p2 = next(p for p in pins if p.num == "2")
        assert "A_B_C" not in p1.aliases
        assert "A_B_C" not in p2.aliases

    def test_real_awr2944_alias_resolves(self):
        # Smoke-check against the real AWR2944 part: a double-
        # underscore name should be reachable via both forms.
        from smash import Design
        from smash.parts import add_awr2944abgaltrq1
        d = Design()
        c = add_awr2944abgaltrq1(d, ref="U_AWR")
        verbatim = c.pin("VIDDA__10RF1")
        collapsed = c.pin("VIDDA_10RF1")
        assert verbatim is collapsed
        assert verbatim.num == collapsed.num
