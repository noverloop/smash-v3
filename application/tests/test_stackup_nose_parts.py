"""(2026-11-19) The components stackup finds each config's sleeve / nose parts
(written by sleeve_step.write_sleeve_and_mould) — optical configs per band."""
from __future__ import annotations

from smash.export.stackup_step import _nose_variant_dir


def test_nose_variant_dir_finds_plain_and_banded_configs(tmp_path):
    sd = tmp_path / "sleeve"
    (sd / "core").mkdir(parents=True)
    (sd / "core" / "nose_cone.step").write_text("x")
    (sd / "core_qpd" / "ir").mkdir(parents=True)
    (sd / "core_qpd" / "ir" / "nose_cone.step").write_text("x")
    (sd / "core_qpd" / "laser").mkdir(parents=True)
    (sd / "core_qpd" / "laser" / "nose_cone.step").write_text("x")
    assert _nose_variant_dir(sd, "core") == sd / "core"
    assert _nose_variant_dir(sd, "core_qpd") == sd / "core_qpd" / "ir"
    assert _nose_variant_dir(sd, "core_radar") is None
    assert _nose_variant_dir(sd, None) is None
