"""Tests for smash.export.kicad_step — kicad-cli STEP wrapper.

The argv builder and CLI resolution are tested without invoking
kicad-cli. A real round-trip export runs only when a kicad-cli is
actually resolvable AND a generated panel exists; otherwise it skips.
"""
from __future__ import annotations

import pathlib

import pytest

from smash.export import kicad_step as ks


# ── argv construction (no kicad-cli needed) ─────────────────────────────

def test_build_step_argv_defaults():
    argv = ks.build_step_argv("kc", "in.kicad_pcb", "out.step")
    assert argv[:4] == ["kc", "pcb", "export", "step"]
    # twin defaults: force + subst-models + no-dnp on, others off.
    assert "--force" in argv
    assert "--subst-models" in argv
    assert "--no-dnp" in argv
    assert "--board-only" not in argv
    assert "--no-unspecified" not in argv
    # output flag immediately precedes the input file, both last.
    assert argv[-3:] == ["-o", "out.step", "in.kicad_pcb"]


def test_build_step_argv_toggles():
    argv = ks.build_step_argv(
        "kc", "in.kicad_pcb", "out.step",
        no_dnp=False, subst_models=False, board_only=True,
        no_unspecified=True, force=False,
        extra_args=("--include-tracks",),
    )
    assert "--no-dnp" not in argv
    assert "--subst-models" not in argv
    assert "--force" not in argv
    assert "--board-only" in argv
    assert "--no-unspecified" in argv
    assert "--include-tracks" in argv


# ── CLI resolution ──────────────────────────────────────────────────────

def test_find_kicad_cli_explicit(tmp_path):
    fake = tmp_path / "kicad-cli"
    fake.write_text("#!/bin/sh\n")
    assert ks.find_kicad_cli(str(fake)) == str(fake)


def test_find_kicad_cli_env(tmp_path, monkeypatch):
    fake = tmp_path / "kicad-cli"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setenv("KICAD_CLI", str(fake))
    assert ks.find_kicad_cli() == str(fake)


def test_find_kicad_cli_not_found(monkeypatch):
    monkeypatch.delenv("KICAD_CLI", raising=False)
    monkeypatch.setattr(ks.shutil, "which", lambda _: None)
    monkeypatch.setattr(ks, "_BUNDLE_PATHS", ())
    with pytest.raises(ks.KiCadCliNotFound):
        ks.find_kicad_cli()


# ── error paths ─────────────────────────────────────────────────────────

def test_write_kicad_step_missing_pcb(tmp_path):
    with pytest.raises(FileNotFoundError):
        ks.write_kicad_step(tmp_path / "nope.kicad_pcb")


# ── real round-trip (skips without kicad-cli or a generated panel) ──────

from smash.roots import export_dir, git_repo_root

_SAMPLE_PCB = (export_dir() / "dist" / "core" / "core.kicad_pcb")
if not _SAMPLE_PCB.is_file():
    _SAMPLE_PCB = (git_repo_root() / "output" / "kicad_pcbs_smash"
                   / "core" / "core.kicad_pcb")


def test_real_export_round_trip(tmp_path):
    try:
        cli = ks.find_kicad_cli()
    except ks.KiCadCliNotFound:
        pytest.skip("kicad-cli not available")
    if not _SAMPLE_PCB.is_file():
        pytest.skip(f"no sample panel at {_SAMPLE_PCB} — run the generator")
    out = tmp_path / "core.step"
    r = ks.write_kicad_step(_SAMPLE_PCB, out, kicad_cli=cli)
    assert out.is_file() and out.stat().st_size > 0
    assert r["size_bytes"] == out.stat().st_size
    assert out.read_text(errors="ignore").startswith("ISO-10303-21")
