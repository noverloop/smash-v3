"""Disk cache for `place_design` (2026-11-19).

Placement is the slow step of both the generator (maximalist + every config)
and the test suite (several modules build and place the same design). The
result is a pure function of:

- the pre-placement state of (design, panel, boards) — fingerprinted by a
  canonical walk (sets sorted, cycles replaced by stable back-references),
- the `place_design` keyword arguments,
- `locked_placements.json` (read inside the placer),
- the source of `smash.layout` and `smash.state` (any code change there
  invalidates every entry).

A hit restores the pickled post-placement state IN PLACE (the caller's
design / panel / board objects keep their identity). Disable with
SMASH_PLACEMENT_CACHE=0; entries live in <repo>/.cache/placement/ (pruned
to the newest `_KEEP`).
"""
from __future__ import annotations

import functools
import hashlib
import os
import pathlib
import pickle

_SRC = pathlib.Path(__file__).resolve().parents[2]          # src/smash
_REPO = _SRC.parents[2]
_DIR = pathlib.Path(os.environ.get("SMASH_PLACEMENT_CACHE_DIR",
                                   _REPO / ".cache" / "placement"))
_KEEP = 40


def enabled() -> bool:
    return os.environ.get("SMASH_PLACEMENT_CACHE", "1") != "0"


@functools.lru_cache(maxsize=1)
def _code_hash() -> str:
    h = hashlib.sha256()
    for sub in ("layout", "state"):
        for p in sorted((_SRC / sub).rglob("*.py")):
            h.update(p.relative_to(_SRC).as_posix().encode())
            h.update(p.read_bytes())
    for data in ("locked_placements.json",):
        p = _SRC / "data" / data
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()


def _canon(obj, memo: dict):
    """Deterministic, hashable-by-repr structure for an object graph."""
    if obj is None or isinstance(obj, (bool, int, str, bytes)):
        return obj
    if isinstance(obj, float):
        return repr(round(obj, 9))
    oid = id(obj)
    if oid in memo:
        return ("@", memo[oid])
    memo[oid] = len(memo)
    if isinstance(obj, (list, tuple)):
        return [_canon(x, memo) for x in obj]
    if isinstance(obj, dict):
        items = [(repr(_canon(k, memo)), _canon(v, memo)) for k, v in obj.items()]
        return ("d", sorted(items, key=lambda kv: kv[0]))
    if isinstance(obj, (set, frozenset)):
        return ("s", sorted(repr(_canon(x, {})) for x in obj))
    if isinstance(obj, pathlib.PurePath):
        return ("p", str(obj))
    if callable(obj) and not hasattr(obj, "__dict__"):
        return ("f", getattr(obj, "__qualname__", type(obj).__name__))
    state = getattr(obj, "__dict__", None)
    if state is None and hasattr(obj, "__slots__"):
        state = {k: getattr(obj, k, None) for k in obj.__slots__}
    if state is None:
        return ("r", type(obj).__name__, repr(obj))
    return (type(obj).__qualname__, _canon(state, memo))


def key(design, panel, boards: dict, kwargs: dict) -> str:
    memo: dict = {}
    blob = repr((_canon(design, memo), _canon(panel, memo), _canon(boards, memo),
                 _canon(kwargs, memo)))
    k = hashlib.sha256((_code_hash() + blob).encode()).hexdigest()[:32]
    dbg = os.environ.get("SMASH_PLACEMENT_CACHE_DEBUG")
    if dbg:                                  # dump the fingerprint to diff misses
        pathlib.Path(dbg).mkdir(parents=True, exist_ok=True)
        (pathlib.Path(dbg) / f"{k}.txt").write_text(blob)
    return k


def load(k: str):
    p = _DIR / f"{k}.pkl"
    if not p.exists():
        return None
    try:
        with p.open("rb") as f:
            return pickle.load(f)
    except Exception:                       # stale / partial file → recompute
        return None


def store(k: str, payload) -> None:
    try:
        _DIR.mkdir(parents=True, exist_ok=True)
        tmp = _DIR / f"{k}.{os.getpid()}.tmp"
        with tmp.open("wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(_DIR / f"{k}.pkl")
        old = sorted(_DIR.glob("*.pkl"), key=lambda q: q.stat().st_mtime)[:-_KEEP]
        for q in old:
            q.unlink(missing_ok=True)
    except Exception:                       # caching is best-effort
        pass


def restore_into(design, panel, boards: dict, payload) -> None:
    """Copy the cached post-placement state into the caller's objects."""
    d2, p2, b2 = payload["design"], payload["panel"], payload["boards"]
    design.__dict__.clear()
    design.__dict__.update(d2.__dict__)
    if panel is not None and p2 is not None:
        panel.__dict__.clear()
        panel.__dict__.update(p2.__dict__)
    for name, b in b2.items():
        if name in boards and boards[name] is not b:
            boards[name].__dict__.clear()
            boards[name].__dict__.update(b.__dict__)
        elif name not in boards:
            boards[name] = b
