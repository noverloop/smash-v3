"""P4 (pinspec abs max) — static net voltage vs datasheet absolute maximums."""
from __future__ import annotations

import pytest

from smash.state import Design
from smash.validators import pinspec_rules as P


def _mini(v_rail: float, r_top: str = "100k", r_bot: str | None = None):
    """A 'U1' whose pin 1 sits on a rail-fed node (pull-up, or divider with
    r_bot), pin 2 on GND, pin 3 on the rail."""
    d = Design()
    d.add_power_net("VR", v_rail)
    d.add_ground_net("GND")
    u = d.add_chip("U1", manf_pn="FAKE_P4", pins=[("1", "IN"), ("2", "GND"), ("3", "VDD")])
    rt = d.add_chip("R1", value=r_top, pins=[("1", "1"), ("2", "2")])
    d.add_net("NODE")
    d.connect("NODE", u.pin("IN"), rt.pin("1"))
    d.connect("VR", rt.pin("2"), u.pin("VDD"))
    d.connect("GND", u.pin("GND"))
    if r_bot:
        rb = d.add_chip("R2", value=r_bot, pins=[("1", "1"), ("2", "2")])
        d.connect("NODE", rb.pin("1"))
        d.connect("GND", rb.pin("2"))
    return d


@pytest.fixture
def spec(monkeypatch):
    """Feed P4 a fake pinspec: IN abs max 3.6 V, IN ≤ VDD + 0.3."""
    from smash.parts import _pinspec

    class _S:
        pins = []

    class _Pin:
        def __init__(self, num, name, type_):
            self.num, self.name, self.type, self.voltage_range_v = num, name, type_, None

    s = _S()
    s.pins = [_Pin("1", "IN", "input"), _Pin("2", "GND", "power"), _Pin("3", "VDD", "power")]
    raw = {"1": {"num": "1", "name": "IN", "max_v": 3.6, "max_v_to": {"GND": 3.6}},
           "2": {"num": "2"}, "3": {"num": "3"}}
    monkeypatch.setattr(_pinspec, "load_pinspec", lambda pn: s if pn == "FAKE_P4" else None)
    monkeypatch.setattr(P, "_raw_pins", lambda pn: raw if pn == "FAKE_P4" else {})
    return raw


def _p4(d):
    return [f for f in P.check(d) if f[0] == "P4"]


def test_pull_up_within_abs_max(spec):
    assert _p4(_mini(3.3)) == []                      # 3.3 × 1.05 = 3.465 ≤ 3.6


def test_pull_up_over_abs_max(spec):
    bad = _p4(_mini(5.0))
    assert bad and all(f[1] == "U1" and f[2] == "1" for f in bad)


def test_divider_brings_it_inside(spec):
    assert _p4(_mini(5.0, "100k", "100k")) == []      # 2.625 V


def test_max_over_supply(spec):
    spec["1"] = {"num": "1", "name": "IN", "max_over": {"pin": "VDD", "v": 0.3}}
    assert _p4(_mini(5.0)) == []                      # IN pulled to the same rail as VDD


def test_ohms_parser():
    assert P._ohms("100k") == 100e3
    assert P._ohms("4k7") == 4700
    assert P._ohms("1M") == 1e6
    assert P._ohms("220") == 220
    assert P._ohms("0R") == 0
    assert P._ohms("DNP") is None


def test_signed_range(spec):
    """[lo, hi] on V(this) − V(other): IN 3.465 V above GND breaks hi = 3.0."""
    spec["1"] = {"num": "1", "name": "IN", "max_v_to": {"GND": [-12, 3.0]}}
    assert len(_p4(_mini(3.3))) == 1
    spec["1"] = {"num": "1", "name": "IN", "max_v_to": {"GND": [-12, 6]}}
    assert _p4(_mini(3.3)) == []
