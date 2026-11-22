"""S4 transverter, 4.4-5.0 GHz (user-approved plan 2026-11-18): IF tap on the
LR2021 HF path, ADF4351 LO + LTC5549 mixer, GRF5126 PA on a switched 5 V
boost, GRF2073W LNA, BGS12P2L6 T/R switches → ANT_HF_S4. Plus the sourcing
rule: no Chinese fab / assembly on the radio parts."""
from __future__ import annotations

import importlib
import re
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


def _two_ended(d, chip):
    return {_net(d, chip, "1"), _net(d, chip, "2")}


def _names(d, name):
    net = d.net_by_name(name)
    return {name} if net is None else {net.name, *(net.aliases or [])}


def _gnd(d):
    return _net(d, _chip(d, "U_LR"), "GND")      # GND is merged into FLEX_GND


def _other_end(d, ref, net):
    ends = _two_ended(d, _chip(d, ref))
    assert net in ends, (ref, net, ends)
    return (ends - {net}).pop()


def test_if_switch_keeps_s1_as_the_default(design):
    """U_LR_IFSW sits between the T/R common and the S1 π; RF1 (CTRL 0, the
    pull-down default) is the S1 path, CTRL on LR2021 DIO10."""
    sw = _chip(design, "U_LR_IFSW")
    assert sw.manf_pn == "BGS12P2L6E6327XTSA1"
    assert _net(design, sw, "RFIN") == _net(design, _chip(design, "U_LR_SW_HF"), "RFIN")
    assert _net(design, sw, "RF1") in _two_ended(design, _chip(design, "C_LR_HF_ANTBLK"))
    ctrl = _net(design, sw, "CTRL")
    assert ctrl == _net(design, _chip(design, "U_LR"), "DIO10") == "LR_XV_SEL"
    assert _two_ended(design, _chip(design, "R_LR_XV_SEL_PD")) == {ctrl, _gnd(design)}


def test_if_switch_rf2_feeds_the_mixer_if(design):
    sw, mix = _chip(design, "U_LR_IFSW"), _chip(design, "U_XV_MIX")
    # (2026-11-22) LTC5552: differential IF through the 1:1 balun T_XV_IF (NCS1-292+)
    bal = _chip(design, "T_XV_IF")
    assert bal.manf_pn == "NCS1-292+"
    assert _other_end(design, "C_XV_MIX_IF", _net(design, sw, "RF2")) == _net(design, bal, "UNBAL")
    assert _net(design, bal, "BAL_P") == _net(design, mix, "IF+")
    assert _net(design, bal, "BAL_N") == _net(design, mix, "IF-")
    assert _net(design, bal, "GND_DC") == _net(design, bal, "NU_GND") == _gnd(design)


def test_lo_drives_the_mixer_lo_from_the_shared_tcxo(design):
    lo, mix = _chip(design, "U_XV_LO"), _chip(design, "U_XV_MIX")
    assert lo.manf_pn == "ADF4351BCPZ-RL7" and mix.manf_pn == "LTC5552IUDB#TRMPBF"   # (2026-11-22) mixer round 18
    # reference = the LR2021 TCXO output, AC-coupled
    assert _other_end(design, "C_XV_LO_REF", "LR_TCXO_OUT") == _net(design, lo, "REFIN")
    # RFOUTA+ → 100 pF → π pad → 100 pF → LO
    pad_i = _other_end(design, "C_XV_LO_OUTP", _net(design, lo, "RFOUTA+"))
    pad_o = _other_end(design, "R_XV_LO_PAD2", pad_i)
    assert _other_end(design, "C_XV_MIX_LO", pad_o) == _net(design, mix, "LO")
    assert _net(design, mix, "GND_7") == _gnd(design)              # LTC5552 pin 8 (LTC5549's X2)
    # LO SPI shares the DTC bus; LE/CE/MUXOUT on spare WBA GPIO
    wba = _chip(design, "U_WBA")
    assert _net(design, lo, "CLK") == "LR_DTC_SCL" and _net(design, lo, "DATA") == "LR_DTC_SDA"
    for lpin, net, wpin in (("LE", "XV_LO_LE", "PB14"), ("CE", "XV_LO_CE", "PA10"),
                            ("MUXOUT", "XV_LO_MUX", "PB11")):
        assert _net(design, lo, lpin) == net == _net(design, wba, wpin)


def test_lo_supplies_are_ferrite_isolated_and_decoupled(design):
    lo = _chip(design, "U_XV_LO")
    fb = _chip(design, "FB_XV_LO")
    assert _two_ended(design, fb) == {_net(design, fb, "1"), "XV_LO_3V3"}
    assert _net(design, fb, "1") in _names(design, "3V3")
    for pn in ("AVDD", "DVDD", "SDVDD", "VP", "VVCO", "VVCO_2"):
        assert _net(design, lo, pn) == "XV_LO_3V3", pn
        assert _two_ended(design, _chip(design, f"C_XV_LO_{pn}")) == {"XV_LO_3V3", _gnd(design)}
    assert _other_end(design, "R_XV_LO_RSET", _gnd(design)) == _net(design, lo, "RSET")


def test_tr_switches_follow_lr_dio11_and_default_to_rx(design):
    lr = _chip(design, "U_LR")
    tx = _net(design, lr, "DIO11")
    assert tx == "XV_TX"
    assert _two_ended(design, _chip(design, "R_XV_TX_PD")) == {tx, _gnd(design)}
    tr1, tr2, mix = (_chip(design, r) for r in ("U_XV_TR1", "U_XV_TR2", "U_XV_MIX"))
    for sw in (tr1, tr2):
        assert sw.manf_pn == "BGS12P2L6E6327XTSA1"
        assert _net(design, sw, "CTRL") == tx
        assert _net(design, sw, "VDD") in _names(design, "3V3")
    assert _other_end(design, "C_XV_MIX_RF", _net(design, mix, "RF")) == _net(design, tr1, "RFIN")


def test_tx_chain_pad_pa_and_switched_5v(design):
    tr1, tr2, pa = (_chip(design, r) for r in ("U_XV_TR1", "U_XV_TR2", "U_XV_PA"))
    assert pa.manf_pn == "GRF5126"
    pad_o = _other_end(design, "R_XV_TX_PAD2", _net(design, tr1, "RF2"))
    assert _other_end(design, "C_XV_PA_IN", pad_o) == _net(design, pa, "RF_IN")
    out = _net(design, pa, "RF_OUT")
    assert _other_end(design, "C_XV_PA_OUT", out) == _net(design, tr2, "RF2")
    assert _two_ended(design, _chip(design, "L_XV_PA_CHOKE")) == {"XV_5V", out}
    # Guerrilla 4400-5000 MHz tune bias: 2740 / 2320 Ω from the 5 V rail
    for pin, ref, val in (("VBIAS1", "R_XV_PA_VB1", "2.74k"), ("VBIAS2", "R_XV_PA_VB2", "2.32k")):
        r = _chip(design, ref)
        assert _two_ended(design, r) == {"XV_5V", _net(design, pa, pin)}
        assert r.value == val
    vg = _net(design, pa, "VGAIN")
    assert vg in _two_ended(design, _chip(design, "R_XV_PA_VG1"))
    # XV_5V: MCP1640D (true output disconnect) enabled by WBA PB7, off by default
    bst = _chip(design, "U_XV_BOOST")
    assert bst.manf_pn == "MCP1640D-I/MC"       # DFN-8 (2026-11-20); tube code (2026-11-22)
    assert _net(design, bst, "VOUTP") == _net(design, bst, "VOUTS") == "XV_5V"
    assert _net(design, bst, "VIN") in _names(design, "REG_IN_MAIN")   # (2026-11-22) off the 3V3 budget
    en = _net(design, bst, "EN")
    assert en == "XV_PA_EN" == _net(design, _chip(design, "U_WBA"), "PB7")
    assert _two_ended(design, _chip(design, "R_XV_PA_EN_PD")) == {en, _gnd(design)}
    assert design.net_by_name("XV_5V").voltage_v == 5.0


def test_rx_chain_lna_between_the_switches(design):
    tr1, tr2, lna = (_chip(design, r) for r in ("U_XV_TR1", "U_XV_TR2", "U_XV_LNA"))
    assert lna.manf_pn == "GRF2073W"
    assert _other_end(design, "C_XV_LNA_IN", _net(design, tr2, "RF1")) == _net(design, lna, "RF_IN")
    assert _other_end(design, "C_XV_LNA_OUT", _net(design, lna, "RF_OUT")) == _net(design, tr1, "RF1")
    ven = _net(design, lna, "VENABLE")
    assert _other_end(design, "R_XV_LNA_VEN", ven) == "XV_LNA_EN" == \
        _net(design, _chip(design, "U_WBA"), "PB6")
    assert _net(design, _chip(design, "U_XV_MIX"), "EN") == "XV_MIX_EN" == \
        _net(design, _chip(design, "U_WBA"), "PA11")


def test_antenna_side_reaches_ant_hf_s4_on_wakeup(design):
    tr2 = _chip(design, "U_XV_TR2")
    assert _net(design, tr2, "RFIN") in _two_ended(design, _chip(design, "L_XV_BPF_SER"))
    assert _two_ended(design, _chip(design, "C_ANT_S4_MATCH")) == {"XV_BPF_O", "ANT_HF_S4"}
    net = design.net_by_name("ANT_HF_S4")
    assert net is not None
    assert {_chip(design, r).board_tag for r, _p in net.pins} == {"wakeup_board"}


def test_transverter_lives_on_wakeup(design):
    refs = [c for c in design.chips if c.ref.startswith("U_XV_") or c.ref == "U_LR_IFSW"]
    assert len(refs) == 8
    assert {c.board_tag for c in refs} == {"wakeup_board"}


_RADIO_ICS = ("U_LR", "U_LR_SW_HF", "U_ANTSW_S1", "U_LR_IFSW", "U_XV_LO", "U_XV_MIX",
              "U_XV_TR1", "U_XV_TR2", "U_XV_PA", "U_XV_LNA")


def test_no_chinese_fab_or_assembly_on_the_radio_ics(design):
    """Sourcing rule (user, 2026-11-18): no Chinese chips, incl. fab /
    assembly / test sites. Every radio/transverter IC carries a recorded
    origin and none lists CN."""
    for ref in _RADIO_ICS:
        c = _chip(design, ref)
        assert c.fab_country, f"{ref} ({c.manf_pn}): fab_country not recorded"
        assert not re.search(r"\bCN\b|CHINA", c.fab_country.upper()), (ref, c.fab_country)


def test_rejected_bgs12wn6_no_longer_placed(design):
    assert not [c.ref for c in design.chips if c.manf_pn == "BGS12WN6E6327XTSA1"]
