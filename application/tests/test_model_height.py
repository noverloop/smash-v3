"""Tests for smash.export.model_height — component-height resolution.

Spacer-gap clearance needs each footprint's height. The trustworthy chain is
datasheet `height_mm` → the height ENCODED in the IPC-7351 footprint name →
a worst-case assumption. (STEP bbox-Z is deliberately excluded — KiCad models
aren't consistently oriented, so a sideways model reports its body length as
height; the MT29F SPI-NAND is the canonical example: name says 0.65 mm, STEP
bbox-Z says 6.0 mm.)
"""
from __future__ import annotations

from types import SimpleNamespace

from smash.export.model_height import (
    footprint_height_mm,
    ipc_name_height_mm,
)


# ── IPC-name height field ─────────────────────────────────────────────

def test_ipc_name_height_son():
    # MT29F SPI-NAND: the model is sideways (bbox-Z 6.0) but the name's
    # trailing X65-8N encodes the true 0.65 mm height.
    assert ipc_name_height_mm("SON127P800X600X65-8N") == 0.65


def test_ipc_name_height_sop():
    assert ipc_name_height_mm("SOP65P640X120-17N") == 1.20


def test_ipc_name_height_sot23_5():
    assert ipc_name_height_mm("SOT95P280X145-5N") == 1.45


def test_ipc_name_height_non_ipc_names_are_none():
    for n in ("NFC_Antenna_Flex_27x50", "ODCSP-83_AR0234CS_10x5_KeyA1",
              "PiezoAttach_3pad", None, ""):
        assert ipc_name_height_mm(n) is None


def test_ipc_name_height_sanity_bounded():
    # An absurd encoded height (>30 mm) is rejected rather than injected.
    assert ipc_name_height_mm("FOO100P999X9999-2N") is None


# ── full resolution chain ─────────────────────────────────────────────

def _fp(name=None, height_mm=None):
    return SimpleNamespace(name=name, height_mm=height_mm)


def test_resolve_prefers_datasheet():
    h, src = footprint_height_mm(_fp(name="SON127P800X600X65-8N", height_mm=1.7))
    assert (h, src) == (1.7, "datasheet")


def test_resolve_falls_to_ipc_name():
    h, src = footprint_height_mm(_fp(name="SON127P800X600X65-8N"))
    assert (h, src) == (0.65, "name")


def test_resolve_worst_case_assumption():
    h, src = footprint_height_mm(_fp(name="NFC_Antenna_Flex_27x50"))
    assert (h, src) == (2.0, "assumed")
    # custom worst-case
    h2, _ = footprint_height_mm(_fp(name=None), assume_mm=1.5)
    assert h2 == 1.5


def test_resolve_none_footprint():
    assert footprint_height_mm(None) == (2.0, "assumed")
