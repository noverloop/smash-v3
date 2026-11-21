"""Post-generation DRC / ERC summary (2026-11-21, user: "can't harm to add,
but as warnings; not blockers").

Runs kicad-cli on the generated boards and schematics and prints one WARN
line per violation category, so a regression (e.g. a wrong layer stack or a
new short) shows up in the generator's own log. Never raises: a missing
kicad-cli or a failed run is reported and skipped.
"""
from __future__ import annotations

import collections
import json
import pathlib
import subprocess
import tempfile


def _cli():
    try:
        from smash.export.kicad_step import find_kicad_cli
        return find_kicad_cli()
    except Exception:                      # never a blocker
        return None


def _run(cli, args) -> dict | None:
    with tempfile.TemporaryDirectory() as td:
        out = pathlib.Path(td) / "report.json"
        try:
            subprocess.run([str(cli), *args, "--format", "json", "-o", str(out)],
                           capture_output=True, timeout=900, check=False)
            return json.loads(out.read_text())
        except Exception:
            return None


def drc_summary(pcb) -> collections.Counter | None:
    """Error-severity DRC violations by type (unrouted connections are not
    counted: the boards are generated unrouted on purpose)."""
    cli = _cli()
    if cli is None:
        return None
    j = _run(cli, ["pcb", "drc", "--severity-error", str(pcb)])
    if j is None:
        return None
    return collections.Counter(v["type"] for v in j.get("violations", []))


def erc_summary(sch) -> collections.Counter | None:
    cli = _cli()
    if cli is None:
        return None
    j = _run(cli, ["sch", "erc", "--severity-error", str(sch)])
    if j is None:
        return None
    return collections.Counter(v["type"] for s in j.get("sheets", [])
                               for v in s.get("violations", []))


def report(pcbs=(), schematics=(), root=None) -> None:
    """Print a WARN block per file with violations; one OK line otherwise."""
    rel = (lambda p: pathlib.Path(p).relative_to(root)) if root else (lambda p: p)
    print("DRC / ERC check (warnings only — not a build gate):")
    for kind, files, fn in (("DRC", pcbs, drc_summary), ("ERC", schematics, erc_summary)):
        for f in files:
            if not pathlib.Path(f).exists():
                continue
            try:
                c = fn(f)
            except Exception:
                c = None
            if c is None:
                print(f"  {kind} {rel(f)}: SKIPPED (kicad-cli unavailable or failed)")
            elif not c:
                print(f"  {kind} {rel(f)}: clean")
            else:
                cats = ", ".join(f"{k} {n}" for k, n in c.most_common())
                print(f"  WARN {kind} {rel(f)}: {sum(c.values())} error(s) — {cats}")
