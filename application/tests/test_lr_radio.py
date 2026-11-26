"""LR2021 radio wiring vs the FINAL LR20xx datasheet (Rev 2.2) — the supply,
PA and DIO rules the preliminary datasheet did not give (2026-11-16).
HF-only since 2026-11-17: sub-GHz dropped; LR2021 and BLE SHARE slot S1 via an owner switch,
no band / owner switching."""
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
    for fn in (gen.build_qpd_module, gen.build_radar_nose_io, gen.build_camera_module,
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


def test_unused_lf_pins_left_open(design):
    """Sub-GHz dropped (2026-11-17): DS v2.2 §23.5 — unused RF pins unconnected."""
    lr = _chip(design, "U_LR")
    for p in ("RFO_LF1", "RFO_LF2", "RFI_LF"):
        assert _net(design, lr, p) is None, p


def test_hf_pa_output_has_a_vr_pa_choke(design):
    lr = _chip(design, "U_LR")
    vr = _net(design, lr, "VR_PA")
    out = _net(design, lr, "RFO_HF")
    chokes = [c for c in design.chips if c.ref.startswith("L_")
              and {_net(design, c, "1"), _net(design, c, "2")} == {vr, out}]
    assert chokes, "no VR_PA choke on RFO_HF"


def test_rf_switch_control_avoids_reset_pulled_up_dios(design):
    """DIO5/6 come up pulled HIGH after reset (DS §5.1.1) — they must not
    drive the TX/RX switch; the RF-switch DIO8 does."""
    lr = _chip(design, "U_LR")
    assert _net(design, _chip(design, "U_LR_SW_HF"), "CTRL") == _net(design, lr, "DIO8")
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


# ── HF slot feeds, VBAT bead (2026-11-16; dedicated slots 2026-11-17) ──

_GND = {"GND", "FLEX_GND"}   # the ground net's canonical name / alias


def _two_ended(d, c):
    return {_net(d, c, "1"), _net(d, c, "2")}


def _gndize(nets):
    return {"GND" if n in _GND else n for n in nets}


def test_vbat_through_ferrite_bead(design):
    lr = _chip(design, "U_LR")
    fb = _chip(design, "FB_LR_VBAT")
    assert fb.manf_pn == "BLM18PG221SN1D"
    vbat = _net(design, lr, "VBAT")
    assert vbat not in _names(design, "3V3")
    assert _two_ended(design, fb) == {_net(design, fb, "1"), vbat}
    assert _net(design, fb, "1") in _names(design, "3V3")


def test_hf_chain_feeds_slot_s1_through_the_owner_switch(design):
    """LR switch common → IF switch RF1 (S1 default; RF2 = S4 transverter IF,
    2026-11-18) → DC block → DTC π → owner switch RF2 → DC block → ANT_HF_S1."""
    rfin = _net(design, _chip(design, "U_LR_SW_HF"), "RFIN")
    ifsw = _chip(design, "U_LR_IFSW")
    assert _net(design, ifsw, "RFIN") == rfin
    s1 = _net(design, ifsw, "RF1")
    blk = _chip(design, "C_LR_HF_ANTBLK")
    assert s1 in _two_ended(design, blk)
    mid = (_two_ended(design, blk) - {s1}).pop()
    lpf = _chip(design, "L_LR_HF_ANT_LPF")
    out = (_two_ended(design, lpf) - {mid}).pop()
    sw = _chip(design, "U_ANTSW_S1")
    assert _net(design, sw, "RF2") == out
    com = _net(design, sw, "RFIN")
    assert _two_ended(design, _chip(design, "C_ANT_S1_DCBLK")) == {com, "ANT_HF_S1"}


def test_ble_shares_slot_s1_by_default(design):
    """S3 merged into S1 (2026-11-17): BLE → DC block → owner switch RF1, the
    pull-down default; switch on 3V3 (both radios run only in Ready), CTRL from
    LR2021 DIO9."""
    blk = _chip(design, "C_BLE_DCBLK")
    sw = _chip(design, "U_ANTSW_S1")
    assert _two_ended(design, blk) == {"BLE_RF", _net(design, sw, "RF1")}
    assert _net(design, sw, "VDD") in _names(design, "3V3")
    ctrl = _net(design, sw, "CTRL")
    assert ctrl == _net(design, _chip(design, "U_LR"), "DIO9") == "ANTSW_S1_LR"
    pd = _chip(design, "R_ANTSW_S1_PD")
    assert ctrl in _two_ended(design, pd)
    assert design.net_by_name("ANT_HF_S3") is None


def test_no_rf_switching_or_lf_left(design):
    refs = {c.ref for c in design.chips}
    assert not refs & {"U_LR_BAND", "U_ANTSW_2G4", "U_LR_SW_LF", "R_LR_HF_LOAD"}
    for n in ("RF_LF_EXT", "ANT_HF_S2", "ANTSW_2G4_CTRL", "LR_BAND_SEL0",
              "LR_BAND_SEL1", "ANT_SUBG_FEED", "ANT_2G4_FEED"):
        assert design.net_by_name(n) is None, n


def test_s1_tuner_is_two_dtcs_around_the_series_l(design):
    """2026-11-17: the S1 π-match is tunable — PE64906 DTCs shunt on both
    sides of the 3.9 nH, RF- grounded, shared SCL/SDA, one SEN each, all
    from the WBA's former spare pins."""
    lpf = _chip(design, "L_LR_HF_ANT_LPF")
    ends = _two_ended(design, lpf)
    wba = _chip(design, "U_WBA")
    for ref, sen, wpin in (("U_LR_DTC1", "LR_DTC_SEN1", "PA9"),
                           ("U_LR_DTC2", "LR_DTC_SEN2", "PB6")):   # normal-speed pins (SEN edges ≤ 6.5 ns)
        dtc = _chip(design, ref)
        assert dtc.manf_pn == "PE64904D-Z"     # (2026-11-22) PE64906B-Z 0 stock
        rf = {_net(design, dtc, p) for p in ("RF+_1", "RF+_2")}
        assert len(rf) == 1 and rf <= ends
        gnd = _net(design, _chip(design, "U_LR"), "GND")
        assert {_net(design, dtc, p) for p in ("RF-_1", "RF-_2", "GND_1", "GND_2")} == {gnd}   # PE64904: no EP
        # direct 3.3 V drive: PE64904 VIH 1.2–3.6 V (DS Table 2) — no divider
        assert _net(design, dtc, "SEN") == sen == _net(design, wba, wpin)
        assert _net(design, dtc, "SCL") == "LR_DTC_SCL" == _net(design, wba, "PA7")
        assert _net(design, dtc, "SDA") == "LR_DTC_SDA" == _net(design, wba, "PA8")
    assert _net(design, _chip(design, "U_LR_DTC1"), "RF+_1") != \
        _net(design, _chip(design, "U_LR_DTC2"), "RF+_1")
