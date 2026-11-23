"""Altium KiCad-import test kit (2026-11-23): which line / track / 3D-model-path
forms survive Altium's KiCad importer. The dev-board import dropped every 3D model
and logged 7,335 "Import is not implemented for: KiCadLib.PCB.PCBLine" errors.

write(out, model) builds out/{test_k10,test_k8}.kicad_pcb (+ .kicad_pro, 3dmodels/,
README.txt); export_unrouted.py writes it to Unrouted/altium_import_test/."""
import pathlib, shutil, sys, uuid
import itertools
_N = itertools.count()
U = lambda: f'(uuid "{uuid.uuid5(uuid.NAMESPACE_URL, f"smash-altium-test/{next(_N)}")}")'   # stable across exports
LAYERS = '''	(layers
		(0 "F.Cu" signal)
		(2 "B.Cu" signal)
		(5 "F.SilkS" user "F.Silkscreen")
		(1 "F.Mask" user)
		(13 "F.Paste" user)
		(25 "Edge.Cuts" user)
		(31 "F.CrtYd" user "F.Courtyard")
		(35 "F.Fab" user)
	)'''
def text(s, x, y, k8):
    eff = '(effects (font (size 1 1) (thickness 0.15)) (justify left))'
    return f'\t(gr_text "{s}" (at {x} {y} 0) (layer "F.SilkS") {U()} {eff})'
def stroke(w, k8): return f'(stroke (width {w}) (type solid))'
def resistor(ref, x, y, model, net, k8):
    n = f'(net 1 "N1")' if k8 else '(net "N1")'
    pads = "".join(f'''
		(pad "{i}" smd roundrect (at {dx} 0) (size 0.8 0.95) (layers "F.Cu" "F.Mask" "F.Paste") (roundrect_rratio 0.25) {n} {U()})'''
                   for i, dx in ((1, -0.825), (2, 0.825)))
    return f'''	(footprint "test:R_0603_{ref}" (layer "F.Cu") {U()} (at {x} {y})
		(property "Reference" "{ref}" (at 0 -1.6 0) (layer "F.SilkS") {U()} (effects (font (size 0.8 0.8) (thickness 0.12))))
		(property "Value" "R" (at 0 1.6 0) (layer "F.Fab") {U()} (effects (font (size 0.8 0.8) (thickness 0.12))))
		(fp_line (start -0.8 -0.4) (end 0.8 -0.4) {stroke(0.1, k8)} (layer "F.Fab") {U()})
		(fp_line (start -0.8 0.4) (end 0.8 0.4) {stroke(0.1, k8)} (layer "F.Fab") {U()}){pads}
		(model "{model}" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))
	)'''
def board(k8: bool) -> str:
    hdr = ("(kicad_pcb (version 20240108) (generator \"pcbnew\") (generator_version \"8.0\")"
           if k8 else '(kicad_pcb\n\t(version 20260206)\n\t(generator "smash")\n\t(generator_version "10.0")')
    out = [hdr, '\t(general (thickness 1.6))', '\t(paper "A4")', LAYERS, '\t(setup (pad_to_mask_clearance 0))']
    if k8: out += ['\t(net 0 "")', '\t(net 1 "N1")']
    # Edge.Cuts outline as 4 gr_lines (the form the exports use)
    for (a, b) in (((0, 0), (60, 0)), ((60, 0), (60, 45)), ((60, 45), (0, 45)), ((0, 45), (0, 0))):
        out.append(f'\t(gr_line (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) {stroke(0.1, k8)} (layer "Edge.Cuts") {U()})')
    out.append(text(f"ALTIUM IMPORT TEST ({'KiCad 8 syntax' if k8 else 'KiCad 10 syntax, as exported'})", 2, 3, k8))
    y = 7
    out.append(text("L1 gr_line + stroke (as exported)", 20, y, k8))
    out.append(f'\t(gr_line (start 3 {y}) (end 18 {y}) {stroke(0.25, k8)} (layer "F.SilkS") {U()})'); y += 4
    out.append(text("L2 gr_line + width (KiCad 6 form)", 20, y, k8))
    out.append(f'\t(gr_line (start 3 {y}) (end 18 {y}) (width 0.25) (layer "F.SilkS") {U()})'); y += 4
    out.append(text("L3 gr_rect", 20, y, k8))
    out.append(f'\t(gr_rect (start 3 {y-1}) (end 18 {y+1}) {stroke(0.25, k8)} (fill none) (layer "F.SilkS") {U()})'); y += 4
    out.append(text("L4 gr_poly", 20, y, k8))
    out.append(f'\t(gr_poly (pts (xy 3 {y+1}) (xy 10 {y-1}) (xy 18 {y+1})) {stroke(0.25, k8)} (fill none) (layer "F.SilkS") {U()})'); y += 4
    out.append(text("L5 gr_arc", 20, y, k8))
    out.append(f'\t(gr_arc (start 3 {y+1}) (mid 10.5 {y-1}) (end 18 {y+1}) {stroke(0.25, k8)} (layer "F.SilkS") {U()})'); y += 4
    out.append(text("T1 copper track N1", 20, y, k8))
    n = "(net 1)" if k8 else '(net "N1")'
    out.append(f'\t(segment (start 3 {y}) (end 18 {y}) (width 0.25) (layer "F.Cu") {n} {U()})'); y += 5
    for i, (lab, model) in enumerate((("M1 ${KIPRJMOD}/3dmodels/R.step", "${KIPRJMOD}/3dmodels/R_0603.step"),
                                      ("M2 3dmodels/R.step (relative)", "3dmodels/R_0603.step"),
                                      ("M3 3dmodels\\\\R.step (Windows)", "3dmodels\\\\R_0603.step"))):
        out.append(resistor(f"R{i+1}", 8, y, model, "N1", k8))
        out.append(text(lab, 14, y, k8)); y += 6
    return "\n".join(out) + "\n)\n"
def write(OUT: pathlib.Path, SRC_MODEL: pathlib.Path) -> None:
    global _N
    OUT.mkdir(parents=True, exist_ok=True); (OUT / "3dmodels").mkdir(exist_ok=True)
    shutil.copy2(SRC_MODEL, OUT / "3dmodels" / "R_0603.step")
    for k8, name in ((False, "test_k10"), (True, "test_k8")):
        _N = itertools.count()
        (OUT / f"{name}.kicad_pcb").write_text(board(k8))
        (OUT / f"{name}.kicad_pro").write_text('{"meta": {"filename": "%s.kicad_pro", "version": 1}}\n' % name)
    (OUT / "README.txt").write_text(
        "Altium KiCad-import test. Import test_k10.kicad_pcb and test_k8.kicad_pcb (keep 3dmodels/ next to them).\n"
        "For each board, please report (screenshot is fine):\n"
        "  - is the 60x45 board outline there?\n"
        "  - which of the silkscreen lines L1-L5 are there?\n"
        "  - is the copper track T1 there?\n"
        "  - which of the resistors R1/R2/R3 show a 3D body in the 3D view (key 3)?\n"
        "and send the import .LOG files.\n")

