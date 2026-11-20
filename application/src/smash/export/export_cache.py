"""Disk cache for per-board export bundles (2026-11-19).

A board's Gerbers, kicad-cli STEP, split STLs and layered STEP are a pure
function of its final `.kicad_pcb` (deterministic uuid5 ids), its stackup /
thickness, the fab profile, the exporter source and the kicad-cli binary.
Unchanged boards — most of them on any given edit — are restored from
<repo>/.cache/exports/<key>/ instead of being re-exported (~20 s each).

`run_cached(key_parts, out_dir, produce)`: on a hit, copy the stored files
back into `out_dir` and return the stored result; on a miss, call
`produce()`, collect every file it wrote / rewrote under `out_dir`, store
them with the result. Disable with SMASH_EXPORT_CACHE=0.
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
import pathlib
import shutil

_SRC = pathlib.Path(__file__).resolve().parents[1]          # src/smash
_REPO = _SRC.parents[2]
_DIR = pathlib.Path(os.environ.get("SMASH_EXPORT_CACHE_DIR", _REPO / ".cache" / "exports"))
_KEEP = 400
_CODE = ("export/gerbers.py", "export/kicad_step.py", "export/stl.py",
         "export/layered_step.py", "export/export_cache.py")


def enabled() -> bool:
    return os.environ.get("SMASH_EXPORT_CACHE", "1") != "0"


@functools.lru_cache(maxsize=None)
def _code_hash(cli: str | None) -> str:
    h = hashlib.sha256()
    for rel in _CODE:
        p = _SRC / rel
        if p.exists():
            h.update(rel.encode())
            h.update(p.read_bytes())
    if cli:
        try:
            st = pathlib.Path(cli).resolve().stat()
            h.update(f"{cli}:{st.st_size}:{int(st.st_mtime)}".encode())
        except OSError:
            h.update(str(cli).encode())
    return h.hexdigest()


def key(parts: list, cli: str | None = None) -> str:
    h = hashlib.sha256(_code_hash(cli).encode())
    for p in parts:
        if isinstance(p, pathlib.Path):
            h.update(p.name.encode())
            h.update(p.read_bytes())
        elif isinstance(p, bytes):
            h.update(p)
        else:
            h.update(repr(p).encode())
    return h.hexdigest()[:32]


def run_cached(k: str, out_dir: pathlib.Path, produce, exclude=()):
    """→ (result, hit). `produce()` returns a JSON-able result (e.g. counters)."""
    out_dir = pathlib.Path(out_dir)
    entry = _DIR / k
    man = entry / "manifest.json"
    if enabled() and man.exists():
        try:
            m = json.loads(man.read_text())
            for rel in m["files"]:
                dst = out_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(entry / "files" / rel, dst)
            os.utime(entry)
            return m["result"], True
        except Exception:
            pass                                    # broken entry → recompute
    before = {p: p.stat().st_mtime_ns for p in out_dir.rglob("*") if p.is_file()}
    result = produce()
    if not enabled():
        return result, False
    try:
        ex = {pathlib.Path(e).resolve() for e in exclude}
        files = [p for p in out_dir.rglob("*") if p.is_file()
                 and before.get(p) != p.stat().st_mtime_ns and p.resolve() not in ex]
        tmp = _DIR / f"{k}.{os.getpid()}.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        rels = []
        for p in files:
            rel = p.relative_to(out_dir).as_posix()
            (tmp / "files" / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, tmp / "files" / rel)
            rels.append(rel)
        (tmp / "manifest.json").write_text(json.dumps({"files": rels, "result": result}))
        shutil.rmtree(entry, ignore_errors=True)
        tmp.rename(entry)
        olds = sorted((d for d in _DIR.iterdir() if d.is_dir() and not d.name.endswith(".tmp")),
                      key=lambda d: d.stat().st_mtime)[:-_KEEP]
        for d in olds:
            shutil.rmtree(d, ignore_errors=True)
    except Exception:
        pass                                        # caching is best-effort
    return result, False
