"""Datasheet land overrides (smash.parts.lands)."""
from __future__ import annotations

from smash.parts.lands import LANDS, apply_land
from smash.state import Design
from smash.state.footprint import Footprint
from smash.state.pad import Pad


def _fp(pads):
    return Footprint(name="T", pads=[Pad(num=n, position_mm=xy, size_mm=s) for n, xy, s in pads])


def test_sot23_to_nexperia_land():
    fp = _fp([("1", (-1.05, 0.95), (1.3, 0.6)), ("2", (-1.05, -0.95), (1.3, 0.6)),
              ("3", (1.05, 0.0), (1.3, 0.6))])
    assert apply_land("NX7002AK,215", fp)
    assert [(p.position_mm, p.size_mm) for p in fp.pads] == [
        ((-1.0, 0.95), (0.7, 0.6)), ((-1.0, -0.95), (0.7, 0.6)), ((1.0, 0.0), (0.7, 0.6))]


def test_idempotent_and_unknown_part():
    fp = _fp([("1", (-0.35, 0), (0.4, 0.7)), ("2", (0.35, 0), (0.4, 0.7))])
    assert apply_land("PESD36VS1ULSYL", fp)
    assert not apply_land("PESD36VS1ULSYL", fp)            # second call is a no-op
    assert fp.pads[1].position_mm == (0.4, 0) and fp.pads[1].size_mm == (0.5, 0.7)
    assert not apply_land("NOT_A_PART", _fp([("1", (0, 0), (1, 1))]))


def test_qfn_snaps_inch_rounded_pins():
    """ADF4351: pin centres snap to the exact 0.50 pitch, 2.30 from centre."""
    pads = [("1", (-2.413, 1.753), (0.813, 0.305)), ("9", (-1.753, -2.413), (0.305, 0.813)),
            ("17", (2.413, -0.762), (0.813, 0.305)), ("33", (0, 0), (3.251, 3.251))]
    fp = _fp(pads)
    apply_land("ADF4351BCPZ-RL7", fp)
    got = {p.num: (p.position_mm, p.size_mm) for p in fp.pads}
    assert got["1"] == ((-2.30, 1.75), (0.50, 0.30))
    assert got["9"] == ((-1.75, -2.30), (0.30, 0.50))
    assert got["17"] == ((2.30, -0.75), (0.50, 0.30))
    assert got["33"] == ((0, 0), (3.251, 3.251))


def test_add_chip_applies_the_land():
    d = Design()
    fp = _fp([("1", (-1.6, 0), (0.92, 1.08)), ("2", (1.6, 0), (0.92, 1.08))])
    c = d.add_chip("D1", manf_pn="PNS40010AERX", footprint=fp, pins=[("1", "K"), ("2", "A")])
    assert [p.size_mm for p in c.footprint.pads] == [(1.2, 1.2), (1.2, 1.2)]
    assert "land per Nexperia" in c.footprint.source


def test_every_entry_cites_a_datasheet():
    for pn, (fn, ref) in LANDS.items():
        assert callable(fn) and len(ref) > 20, pn


def test_oval_drill_survives_import():
    """(drill oval W H) in a vendor .kicad_mod stays a slot, not a round hole."""
    from smash.parts._artifacts import pads_from_kicad_mod
    from smash.roots import git_repo_root
    mod = (git_repo_root() / "application/src/smash/parts/sources/UJ20-C-H-G-MSMT-1A-P16-TR-67"
           / "SAMESKY_UJ20-C-H-G-MSMT-1A-P16-TR-67.kicad_mod")
    sh = {p.num: p for p in pads_from_kicad_mod(str(mod)) if p.num.startswith("SH")}
    assert sh and all(p.drill_slot_mm == (0.65, 1.2) for p in sh.values())
