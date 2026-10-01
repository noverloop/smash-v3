"""Tests for smash.export.kicad_pcb."""
from __future__ import annotations

import pathlib
import re
import tempfile

import pytest

from smash.export import write_kicad_pcb
from smash.state import Board, Design
from smash.state.chip import Chip
from smash.state.footprint import Footprint
from smash.state.pad import Pad
from smash.state.topology.placement import Placement


# ── tiny S-expression parser (parens-balance is the bare minimum,
# this gives us real structural assertions) ───────────────────────────

def _parse_sexp(text: str):
    """Return a nested list of tokens from a Lisp-style S-expression."""
    def _p(s, pos):
        while pos < len(s) and s[pos] in " \t\n":
            pos += 1
        if pos >= len(s):
            return None, pos
        if s[pos] == "(":
            pos += 1; out = []
            while True:
                while pos < len(s) and s[pos] in " \t\n":
                    pos += 1
                if pos >= len(s):
                    raise ValueError("unclosed (")
                if s[pos] == ")":
                    return out, pos + 1
                item, pos = _p(s, pos)
                out.append(item)
        if s[pos] == '"':
            start = pos + 1; pos = start
            while pos < len(s) and s[pos] != '"':
                if s[pos] == "\\": pos += 1
                pos += 1
            return s[start:pos], pos + 1
        start = pos
        while pos < len(s) and s[pos] not in " \t\n()":
            pos += 1
        return s[start:pos], pos
    sexp, _ = _p(text.strip(), 0)
    return sexp


def _find_all(sexp, head):
    """Yield every list whose first element is `head`."""
    if isinstance(sexp, list):
        if sexp and sexp[0] == head:
            yield sexp
        for s in sexp:
            yield from _find_all(s, head)


# ── helpers ───────────────────────────────────────────────────────────

@pytest.fixture
def tmp_pcb(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "out.kicad_pcb"


def _chip(d: Design, ref: str, fp_name: str = "Generic:X",
          *, package_class: str = "QFN", w: float = 1.0, h: float = 1.0,
          board_tag: str = "test_board") -> Chip:
    fp = Footprint(
        name=fp_name, package_class=package_class,
        pads=[Pad(num="1", position_mm=(0, 0), size_mm=(w, h))],
    )
    return d.add_chip(ref=ref, manf_pn="X", footprint=fp,
                      board_tag=board_tag)


# ── header + layers ───────────────────────────────────────────────────

def test_writes_valid_sexp(tmp_pcb):
    d = Design(); board = Board("test_board")
    write_kicad_pcb(d, board, tmp_pcb)
    text = tmp_pcb.read_text()
    assert text.count("(") == text.count(")"), "unbalanced parens"
    assert text.startswith("(kicad_pcb")
    assert text.endswith(")\n")


def test_layers_block_emitted(tmp_pcb):
    d = Design(); board = Board("test_board")
    write_kicad_pcb(d, board, tmp_pcb)
    text = tmp_pcb.read_text()
    for layer in ('"F.Cu"', '"B.Cu"', '"Edge.Cuts"',
                  '"F.SilkS"', '"B.SilkS"',
                  '"F.Mask"', '"B.Mask"',
                  '"Eco1.User"', '"Eco2.User"'):
        assert layer in text, f"missing layer {layer}"


def test_generator_is_smash(tmp_pcb):
    d = Design(); board = Board("test_board")
    write_kicad_pcb(d, board, tmp_pcb)
    assert '(generator "smash")' in tmp_pcb.read_text()


# ── outline ───────────────────────────────────────────────────────────

def test_circle_outline_emitted_for_circle_board(tmp_pcb):
    d = Design(); board = Board("flight_board")  # Ø34
    write_kicad_pcb(d, board, tmp_pcb)
    sexp = _parse_sexp(tmp_pcb.read_text())
    circles = list(_find_all(sexp, "gr_circle"))
    assert len(circles) >= 1
    # First gr_circle is the outline — centred at (0,0), radius 17
    outline = circles[0]
    centre = next(c for c in outline if isinstance(c, list) and c[0] == "center")
    end    = next(c for c in outline if isinstance(c, list) and c[0] == "end")
    assert centre[1:] == ["0", "0"]
    assert end[1] == "17"   # diameter / 2


def test_rect_outline_emitted_for_rect_board(tmp_pcb):
    from smash.state.board_geometry import BoardGeometry
    d = Design()
    board = Board("rect_test_tile",  # explicit rect (nfc_antenna_flex is now round)
                  geometry=BoardGeometry(shape="rect", rect_dimensions=(21.0, 36.0)))
    write_kicad_pcb(d, board, tmp_pcb)
    sexp = _parse_sexp(tmp_pcb.read_text())
    lines = list(_find_all(sexp, "gr_line"))
    edge_cut_lines = [
        l for l in lines
        if any(isinstance(c, list) and c[0] == "layer" and c[1] == "Edge.Cuts"
               for c in l)
    ]
    assert len(edge_cut_lines) == 4   # 4 corners → 4 segments


def test_dxf_outline_raises(tmp_pcb):
    from smash.state.board_geometry import BoardGeometry
    d = Design()
    board = Board("custom", geometry=BoardGeometry(shape="dxf",
                                                    dxf_path="x.dxf"))
    with pytest.raises(NotImplementedError, match="DXF outline"):
        write_kicad_pcb(d, board, tmp_pcb)


# ── holes ─────────────────────────────────────────────────────────────

def test_potting_holes_emitted(tmp_pcb):
    d = Design(); board = Board("flight_board")
    write_kicad_pcb(d, board, tmp_pcb)
    sexp = _parse_sexp(tmp_pcb.read_text())
    # flight_board has 2 potting holes — emitted as NPTH footprints with an
    # np_thru_hole pad each, NOT Edge.Cuts circles, so KiCad can't mistake
    # them for outline cutouts and bounding-box-fallback the whole board.
    pads = list(_find_all(sexp, "pad"))
    npth = [p for p in pads if len(p) > 2 and p[2] == "np_thru_hole"]
    assert len(npth) == 2
    for p in npth:                       # Ø3 drill, size == drill (no annulus)
        drill = next(c for c in p if isinstance(c, list) and c[0] == "drill")
        size  = next(c for c in p if isinstance(c, list) and c[0] == "size")
        assert drill[1] == "3"
        assert size[1:] == ["3", "3"]
    # the only gr_circle left is the board outline
    assert len(list(_find_all(sexp, "gr_circle"))) == 1


def test_camera_module_no_potting_holes(tmp_pcb):
    """camera_module has potting_holes=false."""
    d = Design(); board = Board("camera_module")
    write_kicad_pcb(d, board, tmp_pcb)
    sexp = _parse_sexp(tmp_pcb.read_text())
    assert len(list(_find_all(sexp, "gr_circle"))) == 1   # just the outline
    pads = list(_find_all(sexp, "pad"))
    assert not [p for p in pads if len(p) > 2 and p[2] == "np_thru_hole"]


# ── footprints ────────────────────────────────────────────────────────

def test_single_footprint_emitted(tmp_pcb):
    d = Design(); board = Board("test_board")
    c = _chip(d, "U1")
    board.chip_placements.append(Placement(
        position_mm=(5.0, 3.0), rotation_deg=90, item=c, face="top",
    ))
    write_kicad_pcb(d, board, tmp_pcb)
    sexp = _parse_sexp(tmp_pcb.read_text())
    fps = list(_find_all(sexp, "footprint"))
    assert len(fps) == 1
    fp = fps[0]
    # (footprint "Generic:X" ...)
    assert fp[1] == "Generic:X"
    # (at x y rot) — y is flipped (math-y-up → KiCad-y-down)
    at = next(c for c in fp if isinstance(c, list) and c[0] == "at")
    assert at == ["at", "5", "-3", "90"]


def test_bottom_face_uses_b_cu(tmp_pcb):
    d = Design(); board = Board("test_board")
    c = _chip(d, "U_BOT")
    board.chip_placements.append(Placement(
        position_mm=(0, 0), rotation_deg=0, item=c, face="bottom",
    ))
    write_kicad_pcb(d, board, tmp_pcb)
    sexp = _parse_sexp(tmp_pcb.read_text())
    fp = next(_find_all(sexp, "footprint"))
    layer = next(c for c in fp if isinstance(c, list) and c[0] == "layer")
    assert layer == ["layer", "B.Cu"]


def test_chip_without_footprint_skipped(tmp_pcb):
    d = Design(); board = Board("test_board")
    c = d.add_chip(ref="P_PAD", manf_pn="project")    # no footprint
    board.chip_placements.append(Placement(
        position_mm=(0, 0), rotation_deg=0, item=c, face="bottom",
    ))
    result = write_kicad_pcb(d, board, tmp_pcb)
    assert result["n_footprints"] == 0
    sexp = _parse_sexp(tmp_pcb.read_text())
    assert list(_find_all(sexp, "footprint")) == []


# ── pads + net binding ────────────────────────────────────────────────

def test_pad_carries_net_name(tmp_pcb):
    d = Design()
    gnd = d.add_ground_net("GND")
    board = Board("test_board")
    fp = Footprint(name="R", pads=[Pad("1", (-0.5, 0), (0.6, 0.7)),
                                    Pad("2", ( 0.5, 0), (0.6, 0.7))])
    c = d.add_chip(ref="R1", manf_pn="R", footprint=fp,
                   pins=[("1",), ("2",)], board_tag="test_board")
    gnd.connect(c.pin("1"))
    board.chip_placements.append(Placement(
        position_mm=(0, 0), rotation_deg=0, item=c, face="top",
    ))
    write_kicad_pcb(d, board, tmp_pcb)
    text = tmp_pcb.read_text()
    # Pad 1 must reference net GND; pad 2 has no net so no net entry
    sexp = _parse_sexp(text)
    pads = list(_find_all(sexp, "pad"))
    assert len(pads) == 2
    pad1 = next(p for p in pads if p[1] == "1")
    pad2 = next(p for p in pads if p[1] == "2")
    nets1 = [c for c in pad1 if isinstance(c, list) and c[0] == "net"]
    nets2 = [c for c in pad2 if isinstance(c, list) and c[0] == "net"]
    assert nets1 == [["net", "GND"]]
    assert nets2 == []


def test_namespaced_bga_ball_pad_binds_net(tmp_pcb):
    """Regression: a BGA ball coord that collides with a logical pin
    name gets a `BALL_` prefix on the chip pin (DDR3 ball A1 collides
    with address-bit name A1 → pin number 'BALL_A1'). The KiCad export
    must strip that prefix so the raw footprint pad 'A1' still binds its
    net — otherwise the 6 collided DDR3 balls (A1/A2/A3/A7/A8/A9) export
    netless (the canonical-netlist path already strips it)."""
    from smash.parts import add_as4c512m16d3lc_12bin
    d = Design()
    ddr = add_as4c512m16d3lc_12bin(d, ref="U_DDR3", board_tag="flight_board")
    d.add_net("TEST_VDDQ").connect(ddr.pin("BALL_A1"))   # ball A1 = VDDQ
    board = Board("flight_board")
    board.chip_placements.append(Placement(
        position_mm=(0, 0), rotation_deg=0, item=ddr, face="top"))
    write_kicad_pcb(d, board, tmp_pcb)
    sexp = _parse_sexp(tmp_pcb.read_text())
    pad_a1 = next(p for p in _find_all(sexp, "pad")
                  if len(p) > 1 and p[1] == "A1")
    nets = [c for c in pad_a1 if isinstance(c, list) and c[0] == "net"]
    assert nets == [["net", "TEST_VDDQ"]], \
        f"BALL_A1 must bind its net on raw pad A1; got {nets}"


def test_smd_pad_layers_top(tmp_pcb):
    d = Design(); board = Board("test_board")
    fp = Footprint(name="R", pads=[Pad("1", (0, 0), (1, 1))])
    c = d.add_chip(ref="R1", manf_pn="R", footprint=fp,
                   board_tag="test_board")
    board.chip_placements.append(Placement(
        position_mm=(0, 0), rotation_deg=0, item=c, face="top",
    ))
    write_kicad_pcb(d, board, tmp_pcb)
    text = tmp_pcb.read_text()
    # SMD on top should list F.Cu F.Mask F.Paste
    assert '"F.Cu" "F.Mask" "F.Paste"' in text


def test_smd_pad_layers_bottom(tmp_pcb):
    d = Design(); board = Board("test_board")
    fp = Footprint(name="R", pads=[Pad("1", (0, 0), (1, 1))])
    c = d.add_chip(ref="R1", manf_pn="R", footprint=fp,
                   board_tag="test_board")
    board.chip_placements.append(Placement(
        position_mm=(0, 0), rotation_deg=0, item=c, face="bottom",
    ))
    write_kicad_pcb(d, board, tmp_pcb)
    text = tmp_pcb.read_text()
    assert '"B.Cu" "B.Mask" "B.Paste"' in text


def test_pth_pad_emitted_as_thru_hole(tmp_pcb):
    d = Design(); board = Board("test_board")
    fp = Footprint(name="MOUNTING", pads=[
        Pad("1", (0, 0), (2.5, 2.5), drill_mm=1.5),
    ])
    c = d.add_chip(ref="MTG1", manf_pn="hole", footprint=fp,
                   board_tag="test_board")
    board.chip_placements.append(Placement(
        position_mm=(0, 0), rotation_deg=0, item=c, face="top",
    ))
    write_kicad_pcb(d, board, tmp_pcb)
    text = tmp_pcb.read_text()
    assert "thru_hole" in text
    assert "(drill 1.5)" in text
    assert '"*.Cu" "*.Mask"' in text


# ── y-flip ────────────────────────────────────────────────────────────

def test_y_axis_flipped_for_position(tmp_pcb):
    d = Design(); board = Board("test_board")
    c = _chip(d, "U1")
    board.chip_placements.append(Placement(
        position_mm=(0, 5),    # +5 in math-y-up → -5 in KiCad y-down
        rotation_deg=0, item=c, face="top",
    ))
    write_kicad_pcb(d, board, tmp_pcb)
    sexp = _parse_sexp(tmp_pcb.read_text())
    fp = next(_find_all(sexp, "footprint"))
    at = next(c for c in fp if isinstance(c, list) and c[0] == "at")
    assert at == ["at", "0", "-5", "0"]


# ── return dict ───────────────────────────────────────────────────────

def test_return_dict_summary(tmp_pcb):
    d = Design(); board = Board("flight_board")
    c1 = _chip(d, "U1", board_tag="flight_board")
    c2 = _chip(d, "U2", board_tag="flight_board")
    board.chip_placements.extend([
        Placement(position_mm=(0,0), rotation_deg=0, item=c1),
        Placement(position_mm=(5,0), rotation_deg=0, item=c2),
    ])
    r = write_kicad_pcb(d, board, tmp_pcb)
    assert r["n_footprints"] == 2
    assert r["n_holes"] == 2       # flight_board has 2 potting holes
    assert r["n_cavities"] == 0
    assert r["output_path"] == str(tmp_pcb)


# ── full-twin smoke test ──────────────────────────────────────────────

# ── panel-level export ────────────────────────────────────────────────

def test_panel_export_includes_all_tiles(tmp_path):
    """The panel file should hold every tile's outline + footprints."""
    from smash.export import write_kicad_panel
    from smash.layout.boards.smash_evb_v1 import build_panel
    d = Design()
    panel, boards = build_panel()
    # Add a chip to one board so the panel has something to render
    fp = Footprint(name="X", pads=[Pad("1", (0,0), (1,1))])
    d.add_chip(ref="U_TEST", manf_pn="X", footprint=fp,
               board_tag="wakeup_board")
    boards["wakeup_board"].chip_placements.append(Placement(
        position_mm=(0, 0), rotation_deg=0,
        item=d.chips[0], face="top",
    ))
    out = tmp_path / "panel.kicad_pcb"
    r = write_kicad_panel(d, panel, boards, out)
    # 9 rigid boards (incl. aft_end_board + the THIN cell_floor_board
    # reinstated 2026-07-30 + fin_ble_board from the same-day crowding
    # split) + 13 spacers (7 normal + the 6-spacer battery compartment
    # between cell_floor_board and activation_interface) + 2 deploy
    # branches (qpd, camera; nfc deleted) + 2 Yagi antenna flex tiles
    # (off wakeup_board) = 26.
    assert r["n_tiles"] == 26
    assert r["n_footprints"] >= 1
    # Snake flex is removed (panel.snake_flex False) — the snake tiles are
    # joined by the board-to-board LGA lands through the spacers, so the
    # snake links draw NO strips. Only the 4 perpendicular branch/module
    # flexes remain (Yagi-A, Yagi-B, qpd, camera; nfc deleted 2026-07-30).
    assert r["n_flex_strips"] == 4
    # Round-trip parses
    sexp = _parse_sexp(out.read_text())
    assert sexp[0] == "kicad_pcb"


def test_panel_version_matches_kicad_10(tmp_path):
    """Header must declare version 20260206 to avoid KiCad's
    'created with an older version' dialog."""
    from smash.export import write_kicad_panel
    from smash.layout.boards.smash_evb_v1 import build_panel
    d = Design()
    panel, boards = build_panel()
    out = tmp_path / "panel.kicad_pcb"
    write_kicad_panel(d, panel, boards, out)
    text = out.read_text()
    assert "(version 20260206)" in text


def test_panel_flex_strip_lines_present(tmp_path):
    """Each flex strip emits 2 gr_lines on Edge.Cuts."""
    from smash.export import write_kicad_panel
    from smash.layout.boards.smash_evb_v1 import build_panel
    d = Design()
    panel, boards = build_panel()
    out = tmp_path / "panel.kicad_pcb"
    r = write_kicad_panel(d, panel, boards, out)
    text = out.read_text()
    # 15 strips × 2 lines = 30 flex gr_lines (plus the outline gr_lines)
    # We don't easily distinguish flex from outline lines just by text
    # match, but n_flex_strips × 2 must be ≤ total gr_line count.
    assert text.count("(gr_line") >= r["n_flex_strips"] * 2


# ── stackup + substrate callouts ──────────────────────────────────────

def test_stackup_block_emitted(tmp_pcb):
    d = Design(); board = Board("flight_board")
    write_kicad_pcb(d, board, tmp_pcb)
    text = tmp_pcb.read_text()
    assert "(stackup" in text
    # 14L FR4 needs all 12 In*.Cu copper layers
    for n in range(1, 13):
        assert f'"In{n}.Cu"' in text


def test_layers_block_includes_inner_copper(tmp_pcb):
    d = Design(); board = Board("flight_board")
    write_kicad_pcb(d, board, tmp_pcb)
    text = tmp_pcb.read_text()
    # In1/In2/In11/In12 declared as power (planes); In3..In10 as signal
    assert '(4 "In1.Cu" power)' in text
    assert '(8 "In3.Cu" signal)' in text
    assert '(26 "In12.Cu" power)' in text


def test_no_substrate_callout_for_fr4_default(tmp_pcb):
    """Boards without an override stay clean — no F.Fab text."""
    d = Design(); board = Board("flight_board")    # FR4, no Al
    write_kicad_pcb(d, board, tmp_pcb)
    text = tmp_pcb.read_text()
    assert "ROGERS" not in text
    assert "AL BACKING" not in text


def test_radar_module_is_plain_fr4_no_rogers(tmp_pcb):
    """radar_module is now plain FR4 — NOT Rogers. With the forward-end
    rearchitecture the 77 GHz SIW launches couple directly into the machined
    aluminium waveguide/horn block bonded above the tile, so the PCB laminate
    never sees RF and the Rogers RO4350B top dielectric is dropped. The 20L
    copper count stays for MECHANICAL stiffness (the setback/bend envelope),
    not RF. No dedicated tile-Al backing either (the Al spacers above/below
    carry the BGA composite stiffness; WR-10 pass-throughs go through the
    adjacent Al spacer only)."""
    from smash.layout.boards.smash_evb_v1 import build_panel
    _, boards = build_panel()
    d = Design()
    write_kicad_pcb(d, boards["radar_module"], tmp_pcb)
    text = tmp_pcb.read_text()
    assert "ROGERS" not in text          # Rogers dropped — RF into the Al block
    assert 'AL BACKING' not in text      # no dedicated tile-Al any more


def test_al_backing_only_callout(tmp_pcb):
    """camera_module has al_backing_mm=0.5 but no substrate override —
    only the BOTTOM label appears."""
    from smash.layout.boards.smash_evb_v1 import build_panel
    _, boards = build_panel()
    d = Design()
    write_kicad_pcb(d, boards["camera_module"], tmp_pcb)
    text = tmp_pcb.read_text()
    assert "ROGERS" not in text
    assert 'gr_text "BOTTOM: 0.5 mm AL BACKING"' in text


# ── copper polylines (NFC antenna spiral) ────────────────────────────

def test_body_outline_and_courtyard_emitted(tmp_pcb):
    """A footprint with body_outline + courtyard polygons should emit
    them as fp_poly blocks on F.Fab + F.CrtYd respectively."""
    d = Design()
    fp = Footprint(
        name="QFN8",
        pads=[Pad("1", (0, 0), (0.5, 0.5))],
        body_outline=[(-2, -2), (2, -2), (2, 2), (-2, 2)],
        courtyard=[(-2.5, -2.5), (2.5, -2.5), (2.5, 2.5), (-2.5, 2.5)],
    )
    chip = d.add_chip(ref="U1", manf_pn="X", footprint=fp,
                      board_tag="test_board")
    board = Board("test_board")
    board.chip_placements.append(Placement(
        position_mm=(0, 0), rotation_deg=0, item=chip, face="top",
    ))
    write_kicad_pcb(d, board, tmp_pcb)
    text = tmp_pcb.read_text()
    assert text.count("(fp_poly") == 2
    assert '(layer "F.Fab")' in text
    assert '(layer "F.CrtYd")' in text


def test_body_outline_on_bottom_face_uses_b_fab(tmp_pcb):
    """Flipping to the bottom face moves body to B.Fab + courtyard
    to B.CrtYd."""
    d = Design()
    fp = Footprint(
        name="X", pads=[Pad("1", (0, 0), (1, 1))],
        body_outline=[(-1, -1), (1, -1), (1, 1)],
        courtyard=[(-1.5, -1.5), (1.5, -1.5), (1.5, 1.5)],
    )
    chip = d.add_chip(ref="U2", manf_pn="X", footprint=fp,
                      board_tag="test_board")
    board = Board("test_board")
    board.chip_placements.append(Placement(
        position_mm=(0, 0), rotation_deg=0, item=chip, face="bottom",
    ))
    write_kicad_pcb(d, board, tmp_pcb)
    text = tmp_pcb.read_text()
    assert '(layer "B.Fab")' in text
    assert '(layer "B.CrtYd")' in text
    assert '(layer "F.Fab")' not in text     # nothing on the top
    assert '(layer "F.CrtYd")' not in text


def test_refdes_hidden_on_silkscreen(tmp_pcb):
    """Reference (and Value) must be HIDDEN — this is a potted assembly
    with no printed silkscreen anywhere; the refdes is kept only for
    KiCad netlist/DRC association, not plotted to the silk gerber."""
    d = Design()
    fp = Footprint(name="X", pads=[Pad("1", (0, 0), (1, 1))])
    chip = d.add_chip(ref="R_HIDDEN", manf_pn="X", footprint=fp,
                      board_tag="test_board")
    board = Board("test_board")
    board.chip_placements.append(Placement(
        position_mm=(0, 0), rotation_deg=0, item=chip, face="top",
    ))
    write_kicad_pcb(d, board, tmp_pcb)
    text = tmp_pcb.read_text()
    import re
    m = re.search(r'\(property "Reference" "R_HIDDEN"(.*?)\)\s*\(property',
                  text, re.DOTALL)
    assert m is not None
    assert "(hide yes)" in m.group(1)


def test_footprint_copper_lines_emitted_as_fp_lines(tmp_pcb):
    """A footprint with non-pad copper polylines should emit one
    fp_line per segment inside its footprint block."""
    d = Design()
    fp = Footprint(name="SPIRAL_TEST",
                   pads=[Pad("1", (0, 0), (0.5, 0.5))])
    fp.copper_lines.append({
        "layer":    "F.Cu",
        "width_mm": 0.3,
        "points":   [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)],   # square
    })
    chip = d.add_chip(ref="SPIRAL1", manf_pn="X", footprint=fp,
                      board_tag="test_board")
    board = Board("test_board")
    board.chip_placements.append(Placement(
        position_mm=(0, 0), rotation_deg=0, item=chip, face="top",
    ))
    write_kicad_pcb(d, board, tmp_pcb)
    text = tmp_pcb.read_text()
    # 4 segments → 4 fp_lines
    assert text.count("(fp_line") == 4
    assert '(layer "F.Cu")' in text
    assert "(stroke (width 0.2)" in text


# ── 3D models ─────────────────────────────────────────────────────────

def test_footprint_with_model_emits_model_block(tmp_pcb):
    d = Design()
    fp = Footprint(name="X", pads=[Pad("1", (0, 0), (1, 1))],
                   model_3d_path="library_kicad/3dmodels/X.stp")
    chip = d.add_chip(ref="U1", manf_pn="X", footprint=fp,
                      board_tag="test_board")
    board = Board("test_board")
    board.chip_placements.append(Placement(
        position_mm=(0, 0), rotation_deg=0, item=chip, face="top",
    ))
    write_kicad_pcb(d, board, tmp_pcb)
    text = tmp_pcb.read_text()
    assert "(model " in text
    # Path is resolved to absolute
    import pathlib
    from smash.roots import git_repo_root
    assert str(git_repo_root() / "library_kicad/3dmodels/X.stp") in text


def test_footprint_without_model_omits_block(tmp_pcb):
    d = Design()
    fp = Footprint(name="X", pads=[Pad("1", (0, 0), (1, 1))])
    chip = d.add_chip(ref="R1", manf_pn="R", footprint=fp,
                      board_tag="test_board")
    board = Board("test_board")
    board.chip_placements.append(Placement(
        position_mm=(0, 0), rotation_deg=0, item=chip, face="top",
    ))
    write_kicad_pcb(d, board, tmp_pcb)
    text = tmp_pcb.read_text()
    assert "(model " not in text


def test_full_twin_exports_clean(tmp_path):
    """Build the twin, place it, write every .kicad_pcb file.
    Each file must be a balanced S-expression."""
    import importlib, pathlib, sys
    repo = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))
    try:
        gen = importlib.import_module("generate_maximalist_system")
    finally:
        sys.path.pop(0)
    from smash.layout.boards.smash_evb_v1 import build_panel
    from smash.layout.placer import place_design

    d = gen.Design()
    gen._prime_power_rails(d)
    for fn in [gen.build_qpd_module,
               gen.build_yagi_antenna_a_flex, gen.build_yagi_antenna_b_flex,
               gen.build_nose_cap, gen.build_camera_module,
               gen.build_activation_interface, gen.build_radar_module,
               gen.build_fins_module,
               gen.build_companion_compute,
               gen.build_power_board, gen.build_wakeup_board,
               gen.build_spacers]:   # wakeup_board folds in the IMU/mag (build_flight_board)
        fn(d)

    panel, boards = build_panel()
    place_design(d, panel, boards)

    total_fps = 0
    for name, board in boards.items():
        out = tmp_path / f"{name}.kicad_pcb"
        r = write_kicad_pcb(d, board, out)
        total_fps += r["n_footprints"]
        text = out.read_text()
        assert text.count("(") == text.count(")"), \
            f"unbalanced parens in {name}.kicad_pcb"
        # Parse the file all the way to the end
        sexp = _parse_sexp(text)
        assert sexp[0] == "kicad_pcb"
    # Footprint count in the twin. History: 550 baseline → 525 (wba52-helix
    # rearch + companion_io radio consolidation) → 509 (companion_io retired,
    # NAND→2× SPI-NAND on the MPU tile) → 471: spinbrake_module retired (its
    # DRV8833 brake driver dropped, FINBOOST moved to fins) and the 4 fin
    # drivers swapped DRV8711 pre-driver + externals → integrated DRV8428E
    # (471), then the fin VREF divider dropped for a DAC-driven global VREF
    # (469) → 440: CAN eliminated (5× TCAN1042 + their bypass caps + 120 Ω
    # term + the WBA55 CAN-bridge G0B1 and its reset/decoupling network) and
    # power simplified (companion-3V3 LDO + AON_GATED load-switch removed),
    # net of +2 activation-bench pads (SYS_SPI/fin probes vs CAN/spin-brake);
    # then the 12 V FINBOOST shrank to a small 5 V boost (−2: no 6 A inductor
    # / tantalum / Schottky); then flight control consolidated onto the MP25
    # Cortex-M33 — the H562 + its QSPI NOR, HSE/LSE oscillators, status LED,
    # VCAP/decoupling network, and flash testpoints removed (flight_board is
    # now a sensor/analog tile), one TCAN1042 back as the MP25 EXT_CAN gateway
    # (exposed at activation + nose), and the 2 nose status LEDs dropped for
    # the companion↔flight sensor-joint land budget (→ 407).
    # → 412: depot service interface — MP25 USB-FS (SSH + DFU) on the nose +
    # the MP25 JTAG/SWD/NRST/BOOT0 re-pointed to the aft array (factory
    # programming) + their reset/boot passives; the 3rd sensor I²C bus dropped
    # (3 IMUs now on 2 buses via SA0) to free the lands for the USB pair. The
    # eFuse's True Reverse Blocking isolates the cells when depot power on
    # BAT_PROT exceeds the cell voltage (the service tool does the USB→~4 V
    # step-down + drives BAT_PROT directly); BAT_RAW kept as an unfused
    # high-peak-power payload tap (draw-only, keyed fixture).
    # → 401: merged the two 5V boosts — dropped the fins' standalone U_FINBOOST +
    # its inductor/caps/FB-divider; the DRV8428E VM now taps the shared COMP_5V
    # boost (COMP_5V_RAW) one gap away, with an LC filter (L_PMIC_FILT) isolating
    # the PMIC's COMP_5V from motor-switching noise.
    # → 409: depot power — PMIC BUCK2 now makes COMP_3V3 (the MP25 IO rail) so the
    # compute tile boots from COMP_5V alone; the nose gains a VBUS pad + a Schottky
    # (D_USB_PWR) ORing USB 5V into COMP_5V (single-cable USB-C depot power).
    # → 402: nose thinned to 7 pads (the 4 legacy BAT_PROT/BAT_RAW/EXT_CAN pads +
    # 2 spare GND dropped) for the 8 inter-cardinal slots around the radar
    # metal-block cutout; BLE chip antenna + its π-match removed (metal would
    # detune it); + the contact-switch pad pair & its pull-up.
    # → 404: addressable RGB status LED (SK6812MINI, D_NOSE_LED) + its cap in the
    # free 337.5° nose slot — full colour on one GPIO (MP25 PG7 → WS2812 DIN).
    # → 405: launch-detect consolidated onto activation_interface — the piezo
    # shock/launch disk gets 2 aft solder pads (P_PIEZO, below the battery) + a
    # charge-bleed R; the LMV331 comparator + its threshold network + 3V3
    # decoupling (C_COMP_PZ) relocate there from flight_board (so the high-Z
    # piezo node is local; only COMP_OUT crosses to the M33 PD5 EXTI). The
    # hardware confirm AND-gate (U_AND_CONFIRM) is retired — ACTIVATE_SET /
    # ACTIVATE_CONFIRM are firmware GPIOs. Net +1 (−U_AND_CONFIRM, +P_PIEZO,
    # +R_PIEZO_BLEED; comparator + caps relocated, not added).
    # → 402: nose contact switch deleted (−J_NOSE_CONTACT_A/B pads + their
    # R_NOSE_CONTACT_PU pull-up) — the aft piezo disk already senses impact via
    # the deceleration, so the tip switch was redundant. Nose down to 5 pads.
    # → 393: radar power switch deleted (−Q_RADAR_SW P-FET, −Q_RADAR_LVL BSS138
    # level-shifter, −R_RADAR_GATE_PU, −C_RADAR_BAT1/2) — the AWR buck + LDO now
    # tap always-on BAT_PROT and self-gate via their EN pins tied to RADAR_EN;
    # the RADAR_EN pull-down re-homes flight→radar. −5 parts + −4 LGA lands (the
    # adaptive densify recomputes as BAT_PROT/RADAR_EN move onto compute↔radar
    # while RADAR_BAT drops off 3 gaps) = −9.
    # → 396: nose status LED reverted from the 1-part SK6812MINI to a green/red
    # 0603 pair (D_NOSE_G + D_NOSE_R) + 2 current-limit resistors — the SK6812's
    # 5 V VDD needed a 3.5 V WS2812 DIN, out of spec for the 3.3 V GPIO. Both
    # LEDs V_F ~2 V, common-anode on BAT_PROT, M33 sinks each cathode (PG7/PG8).
    # Net +3 parts (merge of feat/nose-status-led-rg onto the radar-gating base).
    # → 395: launch comparator swapped LMV331 → TLV3691 (nanopower, ~0.15 µA) so it
    # stops being an ~80 µA shelf load on the always-on 3V3. Its push-pull output
    # drops the R_COMP_PU pull-up (−1 — which also killed the ~33 µA the open-drain
    # sank whenever COMP_OUT was low ≈ always); the comparator is a 1:1 swap.
    # → 394: wakeup_board + flight_board consolidated into one tile (each was left
    # with only a handful of chips). The IMU/mag cluster folds onto wakeup_board;
    # the snake drops from 8 tiles + 7 spacers to 7 + 6, so −1 spacer footprint
    # (the chips just re-tag; the land densify nets out across the shifted gaps).
    # → 398: companion_compute gains its external MP25 clocks — a 40 MHz HSE
    # (DSC1001 MEMS) + a 32.768 kHz LSE (SiT1630 MEMS), each with a 100 nF VDD
    # decoupling cap (+2 osc +2 caps). On-tile nets, so no LGA-land change.
    # MERGE of two reworks; both deltas apply to the same panel:
    # → nose_connector → nose_cap (radar forward-end, this branch): 5 USB pogo
    #   pads (−5) → 1 UJ31 USB-C mid-mount (+1) + 2 CC 5.1 kΩ Rd (+2); OR-Schottky
    #   MBRS340→MBRS540 + VBUS cap + status LEDs re-tag/re-home. Net −2.
    # → aft battery-compartment reorg (origin): aft_end_board + cell_floor_board
    #   split (piezo pocket + comparator + pogos + cell − contacts + Cu coin) and
    #   a run of 6 battery spacers; NFC/H3LIS/TCAN back to activation_interface.
    #   +10 (to 406 with the old nose_connector) over the pre-aft baseline.
    # Merged = 406 (aft, nose_connector) − 2 (nose_cap) − 1 (fins_module tile
    # folded onto wakeup_board: its parts re-home to wakeup, the tile's board-level
    # fp drops) = 403.
    # → 406: eFuse power-good pass (datasheet audit) — PGTH divider
    #   (R_EFUSE_PGTH1/2, was strapped to GND which held PGOOD low) + the
    #   R_EFUSE_PGOOD_PU pull-up closing the BAT_PGOOD net to MP25 PG10
    #   (the eFuse end was floating). R_EFUSE_FLT_PU retargeted from the
    #   dead WLE5_VDD rail to COMP_3V3 (no count change).
    # → 410: activation-tile datasheet audit — TCAN1042GV VCC re-fed from
    #   COMP_5V (3V3 was below the 4.5 V UVLO → bus dead); the rail now
    #   spans power→wakeup→activation (land densify nets out — no land
    #   delta). C_NFC_TUNE 30 pF deleted (stale trim cap detuning the
    #   13.56 MHz tank) offset by +CNFC_VCC2 10 nF (DS decap, ECM-DNP).
    #   The +4 is C_HACC2: the DS-recommended 1 µF → 10 µF upsize
    #   dispatches to the 5×2.2 µF 0603 array (smash parallelisation
    #   rule), replacing the single 0805. H3LIS pin 15 Reserved
    #   restrapped GND→Vdd per DS9012 (net move only).
    # → 416: wakeup-tile datasheet audit — G0B1 VREF+ tied to 3V3 (was
    #   floating with the FIN_VREF DAC active) + its 100 nF ECM-DNP decap
    #   (+1); shared DRV8428 VM bulk C_FIN_VM_BULK 10 µF → 5×2.2 µF 0603
    #   array (+5, keeps stepper pulses off the LGA lands). Zero-count
    #   fixes: DECAY straps 47k → 44.2k ±1% (TI seven-level windows),
    #   ISM330 OCS_Aux/SDO_Aux unstrapped from GND → float per DS13012,
    #   IIS2MDC C1 100 nF → 220 nF (set/reset reservoir, 0402→0603).
    # → 419: power-tile datasheet audit — the TPS61085 boost had no
    #   energy path (L was SW→VOUT with NO rectifier; non-synchronous
    #   part): L re-homed IN→SW + D_BOOST_COMP MBRS340 SW→VOUT (+1);
    #   FB divider 909k→309k (12.5 V FINBOOST fossil → 5.06 V); COMP
    #   gets the DS 51 kΩ series R (+1, R_BOOST_COMP) with C_BOOST_COMP
    #   100 nF→1.1 nF; FREQ re-strapped GND→IN (true 1.2 MHz). TMP117
    #   ALERT gains its DS-required open-drain pull-up (+1,
    #   R_TMP1_ALERT_PU 10k → COMP_3V3).
    # → 428: MP25 power tree completed (the deferred "STPMIC2 power-tree
    #   pass" — VDDCORE + 49 other power/strap balls were FLOATING; DS
    #   requires VDD+VDDA18AON+VDDCPU+VDDCORE just to start). New
    #   COMP_0V82 rail from PMIC BUCK5 (+L_PMIC_BUCK5 +2 caps, −2 old
    #   BUCK5 TERM caps), RTXRTUNE 200 Ω (+1), +7 MP25-local decaps
    #   (1×2.2 µF bulk + 6×100 nF ECM-DNP). BUCK5 L + bulk ride power's
    #   BOTTOM face — their cavities overflowed the saturated
    #   power↔companion joint (53 nets) from the top.
    # → 430: genuine always-on wake path — the RF-powered ST25DV GPO now
    #   ORs onto QMAIN's gate (D_NFC_WAKE BAT64-06 common-anode Schottky
    #   + R_NFC_WAKE 3.3k, capping the CMAIN_HOLD discharge under the
    #   GPO's 1.5 mA sink limit): an NFC tap turns the round on from
    #   TRUE shelf (QMAIN off, no MCU alive); the WBA takes the hold
    #   over via PB4 once 3V3 rises.
    # → 432: WBA hold hardened for TRUE shelf — the bare R_WBA_WAKE 10k
    #   from PB4 to MAIN_SW_GATE leaked the gate down through the DEAD
    #   WBA's pin (sub-µA × 1 MΩ ≈ 1 V sag → QMAIN half-on). Replaced
    #   with the QHOLD pattern: QHOLD2 BSS138 + RHOLD2_G 100Ω +
    #   RHOLD2_PD 100k (+3, −1). Firmware: PB4 HIGH now = hold (was low).
    # → 436: the wake gates EVERYTHING — Q_EFEN (IRLML6402, gate shared
    #   with QMAIN) holds the eFuse EN divider dead in shelf (IQ falls
    #   ~200 µA → ~9 µA; shelf ~10 µA ≈ 4 y); RMAIN_PU + R_NFC_GPO_PU
    #   re-railed BAT_PROT→BAT_RAW (no count change). Depot-USB plug is
    #   an explicit wake: Q_USB_WAKE BSS138 + R_USBWK_G 10k +
    #   R_USBWK_PD 100k join the MAIN_SW_GATE open-drain OR; the load
    #   runs from USB while the eFuse TRB keeps the cells at zero
    #   load-current. (+4: Q_EFEN, Q_USB_WAKE, 2 R.)
    # → 444: 3V3_AON nanopower standby domain — TPS7A0233PDBVR (25 nA
    #   IQ) directly off BAT_RAW on activation, powering WBA + H3LIS +
    #   ST25DV VCC + TLV3691 + SPDT so Standby runs with the eFuse AND
    #   the main path OFF (~320 µA/26 d → ~28 µA/~10 mo on the 1-cell
    #   pack). AON-EN latch: Q_AON_EN + RAON_PU + D_NFC_WAKE2 (shared
    #   3.3 k GPO limiter) + Q_USB_WAKE2 (shared USBWK divider) +
    #   RHOLD_AON 1 k from WBA PB15 (push HIGH = hold; the old
    #   AON_GATED pin, reborn). (+8: LDO, 2 caps, 2 FETs, diode, 2 R.)
    # → 448: STPMIC25 BOM conformance (DS14278 Table 2) + inductor
    #   binding fixes: L_PWR/L_BOOST_COMP/L_AWR_BUCK12/13 were bound to
    #   a NONEXISTENT "WE-KI 0402 4.7 µH" (RF family, ~120 nH/mA max) →
    #   real TMS201210ALM 2.2 µH (each converter's DS range verified);
    #   PMIC BUCK2/3/4 1 µH → 2.2 µH per ST Table 2 (≥1.8 V rails);
    #   +4×2.2 µF distributed BUCKxIN input caps (C_PMIC_VIN3..6).
    #   Output banks deliberately stay 1×22 µF/rail: the ST 3-4×22 µF
    #   tantalum equivalent threw 21 nets off the SATURATED
    #   power↔companion joint when tried — justified-deviation comment
    #   at the caps. L_BOOST_COMP joins the bottom face (joint budget).
    # → 450: TPS61085 → TPS61175 boost upsize (the rail-audit "⚠ UPSIZE
    #   before tape-out" item): 3 A min switch limit vs 2 A, HTSSOP-14.
    #   L_BOOST_COMP rebound TMS 2.2 µH (Isat 1.2 A, marginal) →
    #   WE-PD 744043100 10 µH/Isat 6 A; D_BOOST_COMP MBRS340 → MBRS540
    #   (5 A); fSW 600 kHz via R_BOOST_FREQ 176 k; soft-start C_BOOST_SS
    #   47 nF (closes the QMAIN-inrush audit note); comp RC re-derived
    #   1.6 k/220 nF. Chip joins L on power's bottom face — the bigger
    #   body overflowed the saturated power↔companion joint by 5 lands.
    #   (+2: R_BOOST_FREQ, C_BOOST_SS.)
    # → 452: rule-sweep F1 fix — MP25→WBA reset made open-drain
    #   (Q_WBA_RST BSS138 + R_WBARST_PD 100k on wakeup, bottom face:
    #   top threw WBA_UART_* off the wakeup↔power lands). PB3 is a TT
    #   pin clamped to VDDIO4/COMP_3V3; tied directly onto the
    #   3V3_AON-pulled WBA_NRST it back-fed ~280 µA through the dead
    #   MP25 all standby. Gate has no clamp path; PB3 HIGH = reset.
    #   (+2: Q_WBA_RST, R_WBARST_PD.)
    # → 501: aft activation array — 12-sector capacitive-discharge
    #   (all on aft_end_board). TPS61175 #2 charges a
    #   25SVPF330M (Panasonic polymer, beside the cell) to ~19.7 V
    #   ACTIVATE_HV; CD74HC4514 4-to-16 decoder (BAT_PROT-powered, GPIO_EXT
    #   address) → 12× DMN6075 low-side select NFETs; DMP6110 high-side
    #   ACTIVATION (ACTIVATE_SET, resistor-divider gate clamp) isolates the
    #   charged cap until unlock; HV monitor → ACTIVATE_CONFIRM ADC;
    #   bleed + 12 nichrome-wire pads + common. (+49: boost+L+D+FB/
    #   FREQ/SS/COMP/IN(5×2.2µF), C_ACTIVATE, bleed, 2 monitor R, ARM PFET +
    #   BSS138 + 2 divider R, decoder, 12 NFETs, 13 pads.)
    # → 501 (unchanged count, reworked): the array went CAP-FREE. At the
    #   33 V / ~20 mA operating point the wire needs ~0.65 W, which the
    #   TPS61175 (now 33 V off COMP_5V, FB 261k/10k) sources directly —
    #   no firing reservoir. Removed the 25SVPF330M (+ its lock) and the
    #   100 nF HF cap; added a 4.7 µF/50 V output ceramic (loop stability)
    #   → net ±0 footprints. 60 V FETs + the ARM gate divider (V_GS now
    #   -16.5 V) carry over unchanged; only the cap and 3 resistor values
    #   moved. Drops the tall-can placement problem entirely.
    # → 505: back-fill for two committed reworks that missed this tally
    #   (caught 2026-07-20 when the count came out 4 high):
    #   e5cb7ba5 — activation array 12 → 16 sectors (+4 DMN6075 select
    #   NFETs Q_ACTIVATE_N12..15, +4 nichrome pads P_ACT_WIRE_12..15); the
    #   firing chain's aft_end → activation-bottom re-home was ±0
    #   (C_ACTIVATE + C_ACTIVATE_HF out, 2× C_ACTIVATE_OUT in). ebaea823/f7dd0003 —
    #   eFuse retired for the nanopower ideal-diode shelf: −13 (U_EFUSE,
    #   C_EFUSE_DVDT/EN, 9× R_EFUSE_*, Q_EFEN) + 9 (Q_ISO/Q_ISO_DRV/
    #   Q_ISO_USB, 6× R_ISO_* incl. the R_ISO_EN_S interlock) = −4.
    #   Net +4.
    # → 502: ANT_NOSE cleanup — the BGS12 SPDT (U_SPDT + C_SPDT_VDD +
    #   TP_ANT_NOSE) dropped from wakeup_board. Its nose-chip-antenna
    #   throw died when the antenna was deleted in the nose-thinning
    #   pass (→ 402, metal block detunes it), leaving one live throw;
    #   the π-match now feeds the Wilkinson directly (WBA_RF_M) and
    #   BLE programming/arming rides the Yagi pair. Frees WBA PA12
    #   (ANT_SEL/RF_ANTSW0) + PC15 (SPDT_PWR); nets ANT_NOSE /
    #   YAGI_SPLIT_IN / SPDT_PWR / ANT_SEL deleted (all tile-local,
    #   no LGA-land change). (−3.)
    # → 503: IR-wake change (2026-07-27) — D_IR_WAKE VBPW34FAS photodiode
    #   on radar_module (Standby→Chambered optical arming; net IR_WAKE →
    #   WBA PA12/EXTI12, re-occupying the ball the SPDT cleanup freed)
    #   + RPU_IR_WAKE/C_IR_WAKE bias-filter pair on wakeup_board; the
    #   H3LIS moved off 3V3_AON onto main 3V3 + the M33's I2C3 bus,
    #   retiring its dedicated RPU_HACC_SCL/SDA pull-up pair.
    #   +1 +2 −2 = net +1.
    # → 505: IR-link wave 2 (2026-07-27) — status LEDs RETIRED (muzzle
    #   state now queried over the IR service link, power_states §4a):
    #   −D_NOSE_G/−D_NOSE_R/−R_NOSE_LED_G/−R_NOSE_LED_R/−C_NOSE_LED.
    #   D_IR_TX VSMB1940X01 940 nm emitter + tile-local keyer on
    #   radar_module (+Q_IR_TX BSS138, +R_IR_TX_A/B split current pair,
    #   +R_IR_TX_G/+R_IR_TX_PD gate parts, +C_IR_TX burst reservoir);
    #   gate net IR_TX → WBA PA6. ST25DV VCC session-gated from WBA PA7
    #   (net ST25DV_VCC — rail move only, ±0 parts; its CNFC_VCC/VCC2
    #   decoupling followed the net). −5 +7 = net +2.
    # → 511: back-fill for the wake rework pair (2026-07-30 — BOTH wake
    #   commits landed with this test collection-broken on stale
    #   build_nfc_antenna_flex refs, so the tally sat unverified; count
    #   re-measured against fa5ac19b). NFC subsystem out (−9: U_NFC,
    #   CNFC_VCC/VCC2, R_NFC_GPO_PU, R_NFC_WAKE, D_NFC_WAKE/2, TP_NFC_GPO
    #   + ANT_NFC with its flex tile). In (+15): RR123 TMR shelf ear
    #   (U_MAG_SHELF, R/C_MAG_SHELF, U/C_TMR_LDO), DRV5032FC arming Hall
    #   (U_MAG_WAKE, RPU/C_MAG_WAKE), jumpstart pads (TP_JUMP_WAKE/GND,
    #   D_JUMP_WAKE, R_JUMP_PAD/PU/WAKE), AON wake-OR diode D_AON_WAKE.
    #   Net +6.
    # → 513: battery side-solder-tab rework (2026-07-30, cells ordered with
    #   SIDE solder tabs instead of end pins). −P_CELL_CONTACTS_AFT (3-pad
    #   centre cluster) +3 discrete P_CELL_TAB_NEG1..3 side-tab lands in the
    #   trefoil valleys. Net +2. (Same day: cell_floor_board briefly deleted
    #   — cells on the piezo — then reinstated THIN (6L, no coin, potting
    #   pass-through) because the aft LGA joint starved and the comparator
    #   belongs on the piezo's face; the tile swap itself is ±0 footprints,
    #   the tab lands just re-homed aft_end → cell_floor.)
    # → 514: fin_ble_board crowding split (2026-07-30) — the fin actuation
    #   block (4× DRV8428E + G0B1 node + Hall pads) moved wakeup_board → the
    #   NEW fin_ble_board between activation and wakeup. (The STM32WBA55 BLE
    #   cluster + Yagi leaves briefly moved with it and came BACK 2026-07-31:
    #   the wake/arm ladder must survive core_radar dropping the fins tile.)
    #   All moved footprints are ±0 (re-homed, not added); the +1 is the
    #   new gap's mechanical spacer chip (SP). Joint land arrays re-label
    #   with the new gap names (±0). (2026-07-31 stack reorder: activation
    #   moved down between aft_end and cell_floor, fin_ble_board became the
    #   battery ceiling — P_CELL_CONTACTS + the piezo cluster re-homed onto
    #   it, ±0 — and fin_ble_board is now in EVERY config; core_radar sheds
    #   only the Yagi leaves, RF-dark.) This maximalist twin keeps
    #   everything.
    assert total_fps == 514



# ── Cu coin silkscreen annotation ─────────────────────────────────────

def _silk_lines(sexp, layer):
    return [
        l for l in _find_all(sexp, "gr_line")
        if any(isinstance(c, list) and c[0] == "layer" and c[1] == layer
               for c in l)
    ]


def test_cu_coin_outline_on_both_silks(tmp_pcb):
    """A coined board draws its coin on F.SilkS AND B.SilkS: a dashed
    flange loop + ladder loop + a label, so the layout EE sees the
    absorbed-layer keepout from either face."""
    from smash.state.cu_coin import CuCoinInsert
    d = Design(); board = Board("flight_board")  # Ø34, no chips
    board.cu_coin_inserts = [CuCoinInsert(
        position_mm=(2.0, 3.0),
        length_mm=10.0, width_mm=6.0,
        ladder_length_mm=6.0, ladder_width_mm=4.0,   # Q = 2/1 mm
        thickness_mm=1.5, z_top_mm=1.55, flange_thickness_mm=0.5,
        kind="T",
    )]
    write_kicad_pcb(d, board, tmp_pcb)
    sexp = _parse_sexp(tmp_pcb.read_text())
    # No chamfer → flange + ladder are plain rects: 4 + 4 segments/side.
    for layer in ("F.SilkS", "B.SilkS"):
        assert len(_silk_lines(sexp, layer)) == 8
    # Flange corners land at position ± half-extents, y flipped to
    # KiCad y-down: x ∈ {-3, 7}, y ∈ {-6, 0}.
    f_pts = {
        tuple(float(v) for v in next(c for c in l if c[0] == "start")[1:])
        for l in _silk_lines(sexp, "F.SilkS")
    }
    for corner in ((7.0, -6.0), (-3.0, -6.0), (-3.0, 0.0), (7.0, 0.0)):
        assert corner in f_pts
    # Label on both silks, mirrored on the bottom.
    texts = [t for t in _find_all(sexp, "gr_text") if "Cu coin" in t[1]]
    assert len(texts) == 2
    assert all("10x6x1.5mm" in t[1] for t in texts)


def test_cu_coin_label_names_absorbed_layers():
    """A coined board's coin label names its absorbed-layer keepout span on
    both silks. No production board carries a coin any more (radar +
    companion removed 2026-07-04 by the coin audit; cell_floor_board deleted
    2026-07-30 with its compression coin), but the emit machinery stays live
    for coin restoration — exercised here on a synthetic 20L tile."""
    from smash.export.kicad_pcb import _emit_coin_outlines
    from smash.layout.boards.smash_evb_v1 import (
        _lower_coins_for_top_routing)
    from smash.state import Board, CuCoinInsert
    b = Board("synthetic_coined", copper_layers=20)
    b.set_fitted_stackup()
    b.cu_coin_inserts = [CuCoinInsert(
        position_mm=(0.0, 0.0), length_mm=20.0, width_mm=20.0,
        ladder_length_mm=16.0, ladder_width_mm=16.0,
        thickness_mm=3.0, flange_thickness_mm=0.5,
        z_top_mm=3.15, corner_chamfer_radius_mm=5.0, kind="T")]
    _lower_coins_for_top_routing({"synthetic_coined": b})
    out = "\n".join(_emit_coin_outlines(b))
    assert "absorbs In" in out and "(keepout)" in out
    assert '(layer "F.SilkS")' in out and '(layer "B.SilkS")' in out
    # The chamfered flange polygonizes to 4 arcs of 8 chords (36 pts)
    # + the 4-segment ladder rect, on each of the two silk layers.
    assert out.count("(gr_line") == 2 * (36 + 4)
