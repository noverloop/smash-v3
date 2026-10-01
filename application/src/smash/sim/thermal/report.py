"""Markdown + JSON sidecar writer for `StackThermalResult`.
"""
from __future__ import annotations

import json
import pathlib


def _fmt_t(t: float | None) -> str:
    return "—" if t is None else f"{t:+6.1f}"


def _fmt_h(h: float | None) -> str:
    return "—" if h is None else f"{h:+6.1f}"


def write_report(result, out_dir) -> dict:
    """Write `report.md` + `report.json` to `out_dir`. Returns the
    same dict that goes into report.json."""
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── JSON sidecar (full numerical state) ────────────────────────
    payload = {
        "t_ambient_c": result.t_ambient_c,
        "use_p_max": result.use_p_max,
        "p_total_w": result.p_total_w,
        "chain": result.chain,
        "temperatures_c": result.temps,
        "dies": [
            {
                "ref": d.ref, "tile": d.tile, "p_w": d.p_w,
                "t_die_c": d.t_die_c, "t_body_c": d.t_body_c,
                "delta_t_k": d.delta_t_k, "tj_max_c": d.tj_max_c,
                "headroom_k": d.headroom_k, "verdict": d.verdict,
            } for d in result.dies
        ],
        "tiles": [
            {"tile": t.tile, "kind": t.kind, "t_body_c": t.t_body_c}
            for t in result.tiles
        ],
        "worst_die": (
            None if result.worst_die is None
            else {
                "ref": result.worst_die.ref,
                "tile": result.worst_die.tile,
                "t_die_c": result.worst_die.t_die_c,
                "headroom_k": result.worst_die.headroom_k,
                "verdict": result.worst_die.verdict,
            }
        ),
    }
    (out_dir / "report.json").write_text(json.dumps(payload, indent=2))

    # ── Markdown summary ──────────────────────────────────────────
    md: list = []
    md.append(f"# Thermal sim — steady-state snake stack")
    md.append("")
    label = "P_max" if result.use_p_max else "P_active"
    md.append(f"Mode: **{label}** · ambient T = "
              f"**{result.t_ambient_c:.0f} °C** · total injected power "
              f"= **{result.p_total_w:.3f} W**")
    md.append("")

    # Per-chip table, sorted hottest-first.
    md.append("## Dies (hottest first)")
    md.append("")
    md.append("| ref | tile | P (W) | T_die °C | T_body °C | ΔT (K) | "
              "T_jmax °C | headroom K | verdict |")
    md.append("|---|---|---:|---:|---:|---:|---:|---:|---|")
    for d in sorted(result.dies, key=lambda d: -d.t_die_c):
        sym = {"pass": "✓", "warn": "⚠", "fail": "✗", "unknown": "·"}.get(
            d.verdict, "?")
        md.append(
            f"| `{d.ref}` | `{d.tile}` | {d.p_w:.3f} | "
            f"{_fmt_t(d.t_die_c)} | {_fmt_t(d.t_body_c)} | "
            f"{d.delta_t_k:+5.1f} | "
            f"{('—' if d.tj_max_c is None else f'{d.tj_max_c:.0f}')} | "
            f"{_fmt_h(d.headroom_k)} | {sym} {d.verdict} |"
        )
    md.append("")

    # Snake-chain body temperatures.
    md.append("## Tile / spacer body temperatures (chain order)")
    md.append("")
    md.append("| order | kind | tile | T_body °C |")
    md.append("|---:|---|---|---:|")
    chain_order = {t: i for i, t in enumerate(result.chain)}
    for t in sorted(result.tiles, key=lambda t: chain_order.get(t.tile, 999)):
        md.append(f"| {chain_order.get(t.tile, '—')} | {t.kind} | "
                  f"`{t.tile}` | {_fmt_t(t.t_body_c)} |")
    md.append("")

    # Summary verdict.
    md.append("## Summary")
    md.append("")
    if result.worst_die is not None:
        d = result.worst_die
        if d.headroom_k is not None:
            md.append(f"- **Worst headroom**: `{d.ref}` on `{d.tile}` — "
                      f"T_die = {d.t_die_c:+.1f} °C vs T_jmax = "
                      f"{d.tj_max_c:.0f} °C → "
                      f"**{d.headroom_k:+.1f} K headroom** (verdict: "
                      f"**{d.verdict}**)")
        else:
            md.append(f"- **Hottest die**: `{d.ref}` on `{d.tile}` — "
                      f"T_die = {d.t_die_c:+.1f} °C (T_jmax not in "
                      f"catalog — verdict: unknown)")
    fails = [d for d in result.dies if d.verdict == "fail"]
    warns = [d for d in result.dies if d.verdict == "warn"]
    if fails:
        md.append(f"- **✗ THERMAL FAIL**: {len(fails)} die(s) exceed "
                  f"T_jmax — "
                  f"{', '.join(f'`{d.ref}`' for d in fails)}")
    elif warns:
        md.append(f"- **⚠ Tight margin** on {len(warns)} die(s): "
                  f"{', '.join(f'`{d.ref}`' for d in warns)}")
    else:
        md.append("- **✓ Thermal margin OK** for every rated die "
                  f"(>{int(10)} K headroom)")
    md.append("")

    (out_dir / "report.md").write_text("\n".join(md) + "\n")
    return payload
