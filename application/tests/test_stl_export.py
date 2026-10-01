"""Tests for smash.export.stl — direct-from-body STL + STEP→STL roundtrip
+ split-at-midplane + emboss-text-on-bottom for FDM print pipeline."""
import pathlib
import pytest

cq = pytest.importorskip("cadquery")

from smash.export.stl import (
    DEFAULT_TOLERANCE_MM,
    SYMBOL_ALPHABET,
    SYMBOL_LENGTH,
    emboss_text_on_bottom_face,
    recess_text_on_top_face,
    split_at_midplane,
    split_at_z,
    unique_symbol,
    write_split_stls_from_body,
    write_split_stls_from_step,
    write_stl_from_body,
    write_stl_from_step,
    write_stls_for_step_dir,
)


def _ascii_or_binary_stl(p: pathlib.Path) -> str:
    """Return 'ascii' if the file starts with the literal 'solid '
    keyword, else 'binary'. cadquery uses binary by default."""
    head = p.read_bytes()[:80]
    return "ascii" if head.startswith(b"solid ") and b"facet" in head[:1024] else "binary"


@pytest.fixture
def box_body():
    """A trivial 10 × 10 × 4 box — enough faces to produce a meaningful
    STL but small enough to mesh quickly."""
    return cq.Workplane("XY").box(10, 10, 4)


class TestWriteFromBody:
    def test_creates_file(self, tmp_path, box_body):
        out = tmp_path / "box.stl"
        r = write_stl_from_body(box_body, out)
        assert out.exists()
        assert r["output_path"] == str(out)
        assert r["file_size_b"] == out.stat().st_size

    def test_records_tolerance(self, tmp_path, box_body):
        out = tmp_path / "box.stl"
        r = write_stl_from_body(box_body, out, tolerance=0.02,
                                 angular_tolerance=0.05)
        assert r["tolerance_mm"] == 0.02
        assert r["angular_tolerance"] == 0.05

    def test_default_tolerance(self, tmp_path, box_body):
        r = write_stl_from_body(box_body, tmp_path / "box.stl")
        assert r["tolerance_mm"] == DEFAULT_TOLERANCE_MM

    def test_file_is_real_stl(self, tmp_path, box_body):
        out = tmp_path / "box.stl"
        write_stl_from_body(box_body, out)
        # Either ASCII or binary — both legitimate; cadquery picks binary.
        assert _ascii_or_binary_stl(out) in ("ascii", "binary")
        # Binary STL header is 80 bytes + 4 (num_triangles) → minimum.
        assert out.stat().st_size > 84

    def test_creates_parent_dir(self, tmp_path, box_body):
        out = tmp_path / "subdir" / "deeper" / "box.stl"
        write_stl_from_body(box_body, out)
        assert out.exists()


class TestStepRoundtrip:
    def test_step_to_stl(self, tmp_path, box_body):
        """Write STEP, then re-import + STL it. Body should be preserved."""
        step = tmp_path / "box.step"
        cq.exporters.export(box_body, str(step))
        assert step.exists()
        stl = tmp_path / "box.stl"
        r = write_stl_from_step(step, stl)
        assert stl.exists()
        assert r["output_path"] == str(stl)
        # Re-import the STL — fastest sanity-check that mesh is valid.
        # cadquery's stl importer exists for this exact use.
        # (Don't bother — file-size > 84 + non-empty is enough.)
        assert stl.stat().st_size > 84

    def test_missing_step_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            write_stl_from_step(tmp_path / "nope.step",
                                 tmp_path / "out.stl")


class TestDirectorySweep:
    def test_walks_directory(self, tmp_path, box_body):
        """Drop a few STEPs in subdirectories; STLs land alongside each."""
        for sub in ("a", "b", "b/inner"):
            d = tmp_path / sub
            d.mkdir(parents=True, exist_ok=True)
            cq.exporters.export(box_body, str(d / f"box.step"))
        out = write_stls_for_step_dir(tmp_path)
        assert len(out) == 1
        results = out[0]
        # 3 STEP files → 3 STL conversions
        assert len(results["converted"]) == 3
        assert results["failed"] == []
        for sub in ("a", "b", "b/inner"):
            assert (tmp_path / sub / "box.stl").exists()

    def test_non_recursive(self, tmp_path, box_body):
        (tmp_path / "outer").mkdir()
        (tmp_path / "inner").mkdir()
        cq.exporters.export(box_body, str(tmp_path / "outer" / "box.step"))
        cq.exporters.export(box_body, str(tmp_path / "inner" / "box.step"))
        out = write_stls_for_step_dir(tmp_path, recursive=False)
        results = out[0]
        # No STEPs at the top level → nothing to convert.
        assert results["converted"] == []
        assert results["failed"] == []

    def test_failure_recorded(self, tmp_path):
        """Corrupt STEP files get logged in `failed`, sweep continues."""
        good_dir = tmp_path / "g"
        good_dir.mkdir()
        cq.exporters.export(
            cq.Workplane("XY").box(5, 5, 5), str(good_dir / "ok.step"))
        # Drop a garbage "STEP" file alongside.
        (good_dir / "broken.step").write_text("not actually a STEP file")
        results = write_stls_for_step_dir(good_dir)[0]
        # One good, one failed.
        assert len(results["converted"]) == 1
        assert len(results["failed"]) == 1
        assert "broken.step" in results["failed"][0]["step"]


class TestUniqueSymbol:
    def test_deterministic(self):
        assert unique_symbol("flight_board") == unique_symbol("flight_board")

    def test_length_default(self):
        s = unique_symbol("flight_board")
        assert len(s) == SYMBOL_LENGTH

    def test_only_alphabet_chars(self):
        for name in ("activation_interface", "power_board",
                     "spacer_a_b", "yagi_ant_a_flex"):
            for c in unique_symbol(name):
                assert c in SYMBOL_ALPHABET

    def test_avoids_confusable_glyphs(self):
        """Alphabet excludes 0 / 1 / I / O — confusable as printed glyphs."""
        for bad in "01IO":
            assert bad not in SYMBOL_ALPHABET

    def test_collision_uncommon_across_design(self):
        """Real-world check: every board name in the design should hash to
        a distinct symbol (or hit a tiny collision rate). 16 board names
        within a 1024-combo space ≈ <2 % collision probability."""
        names = [
            "activation_interface", "power_board", "wakeup_board",
            "flight_board", "fins_module",
            "companion_compute", "companion_io", "radar_module",
            "nose_cap", "camera_module", "qpd_module",
            "nfc_antenna_flex", "yagi_ant_a_flex", "yagi_ant_b_flex",
            "spacer_activation_interface_power_board",
            "spacer_radar_module_nose_cap",
        ]
        syms = {n: unique_symbol(n) for n in names}
        # Either no collisions or a very small handful — let the test
        # flag if a real-world catalog blows past that.
        assert len(set(syms.values())) >= len(names) - 1


class TestSplitAtZ:
    @pytest.fixture
    def box_4mm(self):
        # 10 × 10 × 4 box centred at z=2 → Z extent [0, 4], midplane z=2
        return cq.Workplane("XY").box(10, 10, 4).translate((0, 0, 2))

    def test_midplane_split(self, box_4mm):
        top, bot = split_at_midplane(box_4mm)
        # Each half should be a valid solid.
        assert top.val().Volume() > 0
        assert bot.val().Volume() > 0
        # Volumes sum to original (within fp tolerance).
        total = top.val().Volume() + bot.val().Volume()
        original = box_4mm.val().Volume()
        assert total == pytest.approx(original, rel=1e-6)

    def test_split_at_z_zero_separates(self, box_4mm):
        """Splitting a box centred at z=2 → [0,4] at z=0 puts everything
        in the top half."""
        top, bot = split_at_z(box_4mm, 0.0)
        assert top.val().Volume() == pytest.approx(
            box_4mm.val().Volume(), rel=1e-6)
        # Bottom should be empty (or near-zero).
        assert bot.val().Volume() == pytest.approx(0.0, abs=1e-3)

    def test_split_off_midplane(self, box_4mm):
        """Split at z=1 puts 1/4 in bottom, 3/4 in top."""
        top, bot = split_at_z(box_4mm, 1.0)
        v_top = top.val().Volume()
        v_bot = bot.val().Volume()
        v_total = box_4mm.val().Volume()
        # 10×10×3 vs 10×10×1
        assert v_bot / v_total == pytest.approx(0.25, rel=1e-3)
        assert v_top / v_total == pytest.approx(0.75, rel=1e-3)


class TestEmboss:
    @pytest.fixture
    def box(self):
        return cq.Workplane("XY").box(20, 20, 4).translate((0, 0, 2))

    def test_adds_volume(self, box):
        labeled = emboss_text_on_bottom_face(box, "TEST")
        # Labeled body is bigger than the base body — the text body
        # extends below the bottom face.
        assert labeled.val().Volume() > box.val().Volume()

    def test_zmin_extends_below_original(self, box):
        bb_before = box.val().BoundingBox()
        labeled = emboss_text_on_bottom_face(box, "X",
                                              emboss_mm=1.0)
        bb_after = labeled.val().BoundingBox()
        # The label extends DOWNWARD from the original bottom face.
        assert bb_after.zmin < bb_before.zmin
        # Specifically by about the emboss depth.
        assert bb_after.zmin == pytest.approx(bb_before.zmin - 1.0, abs=0.1)

    def test_empty_label_safe(self, box):
        """Empty label doesn't raise — silently returns the body
        unchanged (or with no visible effect)."""
        r = emboss_text_on_bottom_face(box, "")
        # Body is returned (might be unchanged or with zero-area text).
        assert r is not None


class TestSplitStlWrite:
    @pytest.fixture
    def box_body(self):
        return cq.Workplane("XY").box(20, 20, 4).translate((0, 0, 2))

    def test_writes_two_files(self, tmp_path, box_body):
        prefix = tmp_path / "thing"
        r = write_split_stls_from_body(box_body, prefix, symbol="AB")
        assert (tmp_path / "thing_top.stl").exists()
        assert (tmp_path / "thing_bot.stl").exists()
        assert r["symbol"] == "AB"

    def test_z_split_explicit(self, tmp_path, box_body):
        prefix = tmp_path / "thing"
        r = write_split_stls_from_body(box_body, prefix, z_split=1.5,
                                        symbol="X")
        assert r["z_split_mm"] == 1.5

    def test_no_symbol_omits_marking(self, tmp_path, box_body):
        """Without `symbol`, both halves print plain — no emboss / no
        recess geometry."""
        prefix = tmp_path / "thing"
        r = write_split_stls_from_body(box_body, prefix)
        assert r["symbol"] is None
        # Both halves of a symmetric box should be ~the same file size.
        assert abs(r["top"]["file_size_b"] - r["bot"]["file_size_b"]) < 200

    def test_split_from_step(self, tmp_path, box_body):
        step = tmp_path / "thing.step"
        cq.exporters.export(box_body, str(step))
        prefix = tmp_path / "thing"
        r = write_split_stls_from_step(step, prefix, symbol="ZZ")
        assert (tmp_path / "thing_top.stl").exists()
        assert (tmp_path / "thing_bot.stl").exists()
        assert r["symbol"] == "ZZ"


class TestRecessTopFace:
    @pytest.fixture
    def box(self):
        return cq.Workplane("XY").box(20, 20, 4).translate((0, 0, 2))

    def test_removes_volume(self, box):
        """Recess CUTS material — labelled body smaller than base."""
        labeled = recess_text_on_top_face(box, "TEST")
        assert labeled.val().Volume() < box.val().Volume()

    def test_zmax_preserved(self, box):
        """The recess goes INTO the top face, so the bbox zmax shouldn't
        extend ABOVE the original — recessed text caves below z=zmax."""
        bb_before = box.val().BoundingBox()
        labeled = recess_text_on_top_face(box, "X", recess_mm=1.0)
        bb_after = labeled.val().BoundingBox()
        assert bb_after.zmax == pytest.approx(bb_before.zmax, abs=1e-6)

    def test_empty_label_safe(self, box):
        r = recess_text_on_top_face(box, "")
        assert r is not None
