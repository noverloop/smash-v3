"""Flight-pack drawdown report.

    python -m smash.sim.battery                    # default run + sweep
    python -m smash.sim.battery --shelf-years 15 --temp -20 --sectors 2
    python -m smash.sim.battery --validate         # cell model vs datasheet
"""
from __future__ import annotations

import argparse

from smash.sim.battery import loads as L
from smash.sim.battery.cells import PACKS, validate_rows
from smash.sim.battery.mission import (MissionResult, build_profile, first_failure,
                                       max_descent_s, run_mission)


def _opts(args) -> dict:
    return dict(xv_tx=args.xv, fins=args.fins, radar_in_ready=not args.radar_off_in_ready)


def _tree(args) -> dict:
    return dict(radar_from="COMP_5V" if args.radar_from_5v else "BAT",
                radar_bucks_low_v=args.radar_bucks_2v4,
                radar_1v8_buck=args.radar_1v8_buck, comp_boost=args.comp_boost)


def _profile(args, shelf: float):
    return build_profile(shelf_years=shelf, standby_days=args.standby_days,
                         ready_h=args.ready_h, descent_s=args.descent_s,
                         sectors=args.sectors, cutter_w=args.cutter_w,
                         **_opts(args))


def print_run(r: MissionResult) -> None:
    print(f"\n== {r.cell.name}: shelf {r.shelf_years:g} y, mission {r.mission_temp:g} C "
          f"-> {'PASS' if r.ok else 'FAIL'} ==")
    print(f"{'phase':<20}{'mAh used':>10}{'mWh':>10}{'V min':>8}{'I max':>8}  status")
    q_prev = 0.0
    for p in r.phases:
        print(f"{p.phase.name:<20}{p.q_end_mah - q_prev:>10.2f}{p.mwh:>10.2f}"
              f"{p.v_min:>8.2f}{p.i_max:>8.3f}  {p.fail or 'ok'}")
        q_prev = p.q_end_mah
    print(f"  (shelf/standby mAh include calendar aging; mWh counts load energy only)")
    print(f"  load energy used {r.used_mwh:.0f} mWh; still deliverable at descent load "
          f"{r.spare_mwh:.0f} mWh = {r.spare_descent_s:.0f} s more descent")
    print(f"\n{'peak (ms-class, at phase end)':<44}{'V pack':>8}{'I pack':>8}{'rating':>8}  result")
    for pk in r.peaks:
        print(f"{pk.phase + ': ' + pk.peak:<44}{pk.v_pack:>8.2f}{pk.i_pack:>8.2f}"
              f"{pk.i_rating:>8.2f}  {'; '.join(pk.fail) or 'ok'}")
    worst = min(r.peaks, key=lambda p: p.v_pack, default=None)
    if worst and worst.tree:
        print(f"\nconverters at the deepest peak ({worst.phase}: {worst.peak}):")
        print(f"  {'ref':<14}{'mode':<8}{'VIN':>6}{'I_OUT':>8}{'I_IN':>8}{'I_PK':>8}{'limit':>8}")
        for c in worst.tree.convs.values():
            if c.mode == "off":
                continue
            lim = c.conv.i_sw_max_a if c.i_pk is not None and c.conv.kind == "boost" \
                else c.conv.i_out_max_a
            pk = f"{c.i_pk:.2f}" if c.i_pk is not None else "-"
            print(f"  {c.conv.ref:<14}{c.mode:<8}{c.v_in:>6.2f}{c.i_out:>8.3f}"
                  f"{c.i_in:>8.3f}{pk:>8}{(f'{lim:.2f}' if lim else '-'):>8}"
                  f"  {'; '.join(c.flags)}")


def sweep(args) -> None:
    temps = [float(t) for t in args.temps.split(",")]
    ages = [float(a) for a in args.ages.split(",")]
    kw = dict(standby_days=args.standby_days, ready_h=args.ready_h,
              sectors=args.sectors, cutter_w=args.cutter_w, **_opts(args))
    for key in args.packs.split(","):
        cell = PACKS[key]
        print(f"\n== {cell.name}: longest descent that still passes "
              f"(after {args.ready_h:g} h Ready; pulses checked at its end) ==")
        print(f"{'shelf y':>8}" + "".join(f"{t:>+13.0f} C" for t in temps))
        fails: dict[str, str] = {}
        for age in ages:
            row = f"{age:>8g}"
            for t in temps:
                s, r = max_descent_s(cell, {**kw, "shelf_years": age},
                                     args.storage_temp, t, args.cold_alpha,
                                     tree=_tree(args))
                if s < 0:
                    tag = f"x{len(fails) + 1}"
                    fails[tag] = f"{age:g} y, {t:+g} C: {first_failure(r)}"
                    row += f"{'FAIL ' + tag:>15}"
                else:
                    row += f"{s:>13.0f} s"
            print(row)
        for tag, why in fails.items():
            print(f"  {tag}: {why}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pack", default="3x1520hpm", choices=sorted(PACKS))
    ap.add_argument("--packs", default="3x1520hpm,3x1520m", help="packs for the sweep")
    ap.add_argument("--shelf-years", type=float, default=10.0)
    ap.add_argument("--standby-days", type=float, default=0.0,
                    help="separate standby before Ready (default 0: magnetic wake goes straight to Ready)")
    ap.add_argument("--ready-h", type=float, default=1.0)
    ap.add_argument("--descent-s", type=float, default=90.0)
    ap.add_argument("--sectors", type=int, default=1, help="cutter sectors fired at once")
    ap.add_argument("--cutter-w", type=float, default=L.CUTTER_W_PER_SECTOR)
    ap.add_argument("--xv", action="store_true",
                    help="S4 transverter keyed for the whole descent (default off; S1 is the link)")
    ap.add_argument("--fins", action="store_true",
                    help="fins on this pack (default off: fin builds get a larger pack)")
    ap.add_argument("--radar-from-5v", action="store_true",
                    help="what-if: radar bucks + 1.8 V LDO fed from COMP_5V instead of BAT_PROT")
    ap.add_argument("--radar-bucks-2v4", action="store_true",
                    help="what-if: radar bucks rated to 2.4 V VIN instead of LMR10510 (3.0 V)")
    ap.add_argument("--radar-1v8-buck", action="store_true",
                    help="what-if: radar 1.8 V from a buck instead of the LDL112 LDO")
    ap.add_argument("--comp-boost", default="tps61175", choices=["tps61175", "A", "B"],
                    help="what-if COMP_5V boost: A = 2.7 V/6 A, B = 1.8 V/8 A sync")
    ap.add_argument("--radar-off-in-ready", action="store_true",
                    help="radar fully off in Ready, boots at the drop")
    ap.add_argument("--mag-wake-min", type=float, default=None,
                    help="magnetic wake straight from shelf: no standby, Ready = this many minutes")
    ap.add_argument("--storage-temp", type=float, default=22.0)
    ap.add_argument("--temp", type=float, default=22.0, help="mission temperature, C")
    ap.add_argument("--temps", default="22,0,-20", help="sweep mission temps")
    ap.add_argument("--ages", default="0,5,10,15,20", help="sweep shelf ages, years")
    ap.add_argument("--cold-alpha", type=float, default=0.6)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--no-sweep", action="store_true")
    args = ap.parse_args()
    if args.mag_wake_min is not None:
        args.standby_days, args.ready_h = 0.0, args.mag_wake_min / 60

    if args.validate:
        print(f"{'cell':<14}{'I':>8}{'cutoff':>8}{'DS mAh':>8}{'sim':>8}{'err':>8}")
        for name, a, v, ds, sim, src in validate_rows():
            print(f"{name:<14}{a:>7.3f}A{v:>7.1f}V{ds:>8.0f}{sim:>8.1f}"
                  f"{(sim - ds) / ds * 100:>7.1f}%  {src}")
        return
    r = run_mission(PACKS[args.pack], _profile(args, args.shelf_years),
                    args.storage_temp, args.temp, args.cold_alpha, _tree(args))
    print_run(r)
    if not args.no_sweep:
        sweep(args)


if __name__ == "__main__":
    main()
