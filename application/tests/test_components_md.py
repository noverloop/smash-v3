"""Unit tests for smash.components_md — parser for the components.md
reference table."""

import pathlib

import pytest

from smash import components_md


COMPONENTS_MD = components_md.COMPONENTS_MD


@pytest.fixture(scope="module")
def db():
    if not COMPONENTS_MD.exists():
        pytest.skip(f"components.md not found at {COMPONENTS_MD}")
    return components_md.parse()


# ── basic parser sanity ──────────────────────────────────────────────────

def test_components_md_resolves(db):
    """Path-finding worked — we have at least one entry."""
    assert len(db) > 10


def test_known_chip_present(db):
    assert "STM32MP255DAL3" in db
    assert "STM32H562AIIx" in db
    assert "AR0234CSSM00SUKA0-CP" in db


# ── field types ─────────────────────────────────────────────────────────

def test_size_mm_parsed_as_tuple(db):
    mpu = db.get("STM32MP255DAL3", {})
    if mpu.get("size_mm") is None:
        pytest.skip("STM32MP255DAL3 main-table row absent in this snapshot")
    assert isinstance(mpu["size_mm"], tuple)
    assert len(mpu["size_mm"]) == 2


def test_temp_range_parsed_as_tuple(db):
    h562 = db.get("STM32H562AIIx", {})
    if h562.get("temp_range_c") is None:
        pytest.skip("STM32H562AIIx temp_range_c absent")
    lo, hi = h562["temp_range_c"]
    assert lo < hi
    assert lo == -40


def test_price_parsed_as_float(db):
    h562 = db.get("STM32H562AIIx", {})
    if h562.get("price_1pc_eur") is None:
        pytest.skip("STM32H562AIIx price_1pc_eur absent")
    assert isinstance(h562["price_1pc_eur"], float)


def test_critical_boolean(db):
    h562 = db.get("STM32H562AIIx", {})
    if "critical" not in h562:
        pytest.skip("critical column absent")
    assert h562["critical"] in (True, False)


# ── thermal-table merging ────────────────────────────────────────────────

def test_thermal_fields_present_for_thermal_listed_chips(db):
    """STM32MP255DAL3 appears in both the main table and the thermal
    characteristics table. Both rows should merge into one entry."""
    mpu = db.get("STM32MP255DAL3", {})
    if mpu.get("p_active_w") is None:
        pytest.skip("MPU thermal row absent in this snapshot")
    assert mpu["p_active_w"] > 0


def test_unparsable_values_become_none(db):
    """`TBD`, `TBQ`, `—` should all parse to None — not crash."""
    # Find any chip with at least one None field (typically the
    # `TBQ` rows where 20K price isn't quoted yet).
    has_unparseable = any(
        any(v is None for k, v in c.items() if k != "name")
        for c in db.values()
    )
    assert has_unparseable, "no unparseable fields — expected at least one TBD/TBQ"
