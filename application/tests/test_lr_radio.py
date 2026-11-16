"""LR2021 radio wiring vs the FINAL LR20xx datasheet (Rev 2.2) — the supply,
PA and DIO rules the preliminary datasheet did not give (2026-11-16)."""
from __future__ import annotations

import importlib
import pathlib
import sys

import pytest


@pytest.fixture(scope="module")
def design():
    repo = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))
    try:
        gen = importlib.import_module("generate_stackup")
    finally:
        sys.path.pop(0)
    d = gen.Design()
    gen._prime_power_rails(d)
    for fn in (gen.build_qpd_module, gen.build_nose_cap, gen.build_camera_module,
               gen.build_activation_interface, gen.build_radar_module,
               gen.build_fins_module, gen.build_companion_compute,
               gen.build_power_board, gen.build_wakeup_board):
        fn(d)
    return d


def _chip(d, ref):
    return next(c for c in d.chips if c.ref == ref)


def _net(d, chip, pin_name):
    n = chip.pin(pin_name).net
    if n is None:
        return None
    net = d.net_by_name(n) if isinstance(n, str) else n
    return net.name if net is not None else n


def _names(d, name):
    net = d.net_by_name(name)
    return {name} if net is None else {net.name, *(net.aliases or [])}


def test_vpax_is_its_own_net_not_vbat(design):
    """VPAX1 is the regulator's OUTPUT and must only feed VPAX2 (Fig 1-14)."""
    lr = _chip(design, "U_LR")
    vpax = _net(design, lr, "VPAX1")
    assert vpax is not None and vpax == _net(design, lr, "VPAX2")
    assert vpax not in _names(design, "3V3")
    assert vpax != _net(design, lr, "VBAT")
    assert _net(design, lr, "VDCC1") == _net(design, lr, "VDCC2")


def test_lf_pa_pins_are_tied(design):
    lr = _chip(design, "U_LR")
    assert _net(design, lr, "RFO_LF1") == _net(design, lr, "RFO_LF2") is not None


def test_both_pa_outputs_have_a_vr_pa_choke(design):
    lr = _chip(design, "U_LR")
    vr = _net(design, lr, "VR_PA")
    for rfo in ("RFO_LF1", "RFO_HF"):
        out = _net(design, lr, rfo)
        chokes = [c for c in design.chips if c.ref.startswith("L_")
                  and {_net(design, c, "1"), _net(design, c, "2")} == {vr, out}]
        assert chokes, f"no VR_PA choke on {rfo}"


def test_rf_switch_control_avoids_reset_pulled_up_dios(design):
    """DIO5/6 come up pulled HIGH after reset (DS §5.1.1) — they must not
    drive the TX/RX switches; one RF-switch DIO drives both."""
    lr = _chip(design, "U_LR")
    ctl_lf = _net(design, _chip(design, "U_LR_SW_LF"), "CTRL")
    ctl_hf = _net(design, _chip(design, "U_LR_SW_HF"), "CTRL")
    assert ctl_lf == ctl_hf == _net(design, lr, "DIO8")
    assert _net(design, lr, "DIO5") is None and _net(design, lr, "DIO6") is None


def test_host_lines_have_series_resistors(design):
    lr = _chip(design, "U_LR")
    for host, pin in (("LR_SPI_SCK", "SCK"), ("LR_SPI_MOSI", "MOSI"),
                      ("LR_NSS", "NSS"), ("LR_BUSY", "BUSY"),
                      ("LR_IRQ", "DIO7"), ("LR_NRESET", "NRESET")):
        pin_net = _net(design, lr, pin)
        assert pin_net != host
        bridges = [c for c in design.chips if c.ref.startswith("R_")
                   and {_net(design, c, "1"), _net(design, c, "2")} == {host, pin_net}]
        assert bridges, f"no series R between {host} and LR2021 {pin}"
