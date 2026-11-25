"""Mission drawdown for the flight pack: Shelf -> Standby -> Ready hold ->
radar boot -> descent -> parachute cut. The pack only has to last until the
parachute opens (the ground phase runs on a separate pack — user 2026-11-22).

Two questions per run:
  1. ENERGY — does the pack deliver every phase's mWh while staying above the
     system floor (the highest recommended VIN minimum of the live
     converters)? Reported as mWh used vs mWh still deliverable at the
     descent load, plus spare descent seconds.
  2. PULSES — at the most depleted point of each phase, can the pack source
     the worst simultaneous ms-class peak (cell pulse rating, pack voltage vs
     converter UVLOs, every converter's switch / output limits)?
"""
from __future__ import annotations

from dataclasses import dataclass, field

from smash.sim.battery import loads as L
from smash.sim.battery.cells import CellModel, aging_loss_frac
from smash.sim.battery.power_tree import Converter, Load, TreeState, converters, solve_tree

YEAR_S = 365.25 * 24 * 3600
R_WIRING = 0.06       # Q_ISO + QMAIN (2 x PMPB15XP on power_board, ~20 mOhm each at -2.5 V) + 3 cell lanes in parallel + GND return (est 20 mOhm), ohms
V_SOLVE_FLOOR = 1.0


@dataclass(frozen=True)
class Peak:
    name: str
    extra: tuple[Load, ...]


@dataclass(frozen=True)
class Phase:
    name: str
    dur_s: float
    loads: tuple[Load, ...] = ()
    dormant_i_a: float | None = None     # dormant phases: constant current
    peaks: tuple[Peak, ...] = ()


@dataclass
class PhaseResult:
    phase: Phase
    q_end_mah: float
    mwh: float
    v_min: float
    i_max: float
    fail: str = ""


@dataclass
class PeakResult:
    phase: str
    peak: str
    v_pack: float
    i_pack: float
    i_rating: float
    tree: TreeState | None
    fail: list[str] = field(default_factory=list)


@dataclass
class MissionResult:
    cell: CellModel
    phases: list[PhaseResult]
    peaks: list[PeakResult]
    spare_descent_s: float
    spare_mwh: float
    shelf_years: float
    mission_temp: float

    @property
    def ok(self) -> bool:
        return (not any(p.fail for p in self.phases)
                and not any(p.fail for p in self.peaks))

    @property
    def used_mwh(self) -> float:
        return sum(p.mwh for p in self.phases)


def build_profile(shelf_years: float = 10.0, standby_days: float = 0.0,
                  ready_h: float = 1.0, descent_s: float = 90.0,
                  sectors: int = 1, cutter_w: float = L.CUTTER_W_PER_SECTOR,
                  xv_tx: bool = False, radar_in_ready: bool = True,
                  fins: bool = False) -> list[Phase]:
    """Default ladder (user 2026-11-22): shelf -> MAGNETIC WAKE -> Ready while
    the field is present (off again when it goes away) -> drop. No separate
    standby (standby_days=0); Ready is budgeted at 1 h as margin even though
    the real armed window is shorter. The radar boots at the wake and idles
    through Ready (booting at the drop is too slow).

    radar_in_ready=False: the radar stays fully OFF through Ready (it is only
    needed in descent) and boots at the drop — its 1 s image load + cal then
    overlaps the first second of descent instead of the arming.
    fins=False (default): no fin load — fin builds get a larger-scoped pack,
    sized separately (user 2026-11-22).
    xv_tx=False (default): the S4 transverter is off; S1 (LR2021 direct) is
    the default link (user 2026-11-22). xv_tx=True keys it for the whole
    descent (worst case)."""
    descent = tuple(ld for ld in L.DESCENT
                    if (xv_tx or not ld.name.startswith("XV"))
                    and (fins or not ld.name.startswith("fins")))
    fin_step = (L.FIN_STEP_EXTRA,) if fins else ()
    ready_base = tuple(L.READY if radar_in_ready else
                       [ld for ld in L.READY if not ld.rail.startswith("AWR")])
    ready = ready_base + (Load("health coil avg", "BAT",
                               L.HEALTH_COIL.amps * L.HEALTH_COIL_DUTY, "est"),)
    cut = L.cutter(sectors, cutter_w)
    phases = [
        Phase("shelf", shelf_years * YEAR_S, dormant_i_a=L.I_SHELF_A),
        Phase("standby", standby_days * 86400, dormant_i_a=L.I_STANDBY_A),
    ]
    if radar_in_ready:
        phases.append(Phase("radar boot @ arm", 1.0, ready_base + tuple(L.RADAR_BOOT_EXTRA),
                            peaks=(Peak("boot + health coil", (L.HEALTH_COIL,)),)))
    phases.append(Phase("ready hold", ready_h * 3600, ready,
                        peaks=(Peak("health coil pulse", (L.HEALTH_COIL,)),)))
    if not radar_in_ready:
        boot = tuple(ld for ld in descent if not ld.rail.startswith("AWR")) \
            + tuple(L.RADAR_BOOT_EXTRA)
        phases.append(Phase("radar boot @ drop", 1.0, boot,
                            peaks=(Peak("boot pulse", fin_step),)))
    return phases + [
        Phase("descent", descent_s, descent,
              peaks=((Peak("chirp + fin step", (L.RADAR_CHIRP_EXTRA,) + fin_step),
                      Peak("chirp + fin step + cutter", (L.RADAR_CHIRP_EXTRA,) + fin_step + (cut,)))
                     if fins else ())
              + (Peak("chirp + cutter", (L.RADAR_CHIRP_EXTRA, cut)),)),
    ]


class Pack:
    def __init__(self, cell: CellModel, temp_c: float, cold_alpha: float = 0.6,
                 convs: tuple[Converter, ...] | None = None):
        self.cell, self.temp, self.alpha = cell, temp_c, cold_alpha
        self.convs = convs
        self.q = 0.0
        self.dormant_years = 0.0

    def v_term(self, i: float, fast: bool = False) -> float:
        fn = self.cell.voltage_fast if fast else self.cell.voltage
        return fn(self.q, i, self.temp, self.alpha) - i * R_WIRING

    def operating_point(self, loads: list[Load], fast: bool = False
                        ) -> tuple[float, TreeState | None]:
        """Pack voltage where V = v_term(I_tree(V)); None tree = collapse."""
        def g(v: float) -> float:
            return v - self.v_term(solve_tree(loads, v, fast, self.convs).i_bat, fast)
        lo, hi = V_SOLVE_FLOOR, 4.3
        if g(lo) > 0:
            return 0.0, None
        for _ in range(30):
            mid = (lo + hi) / 2
            if g(mid) > 0:
                hi = mid
            else:
                lo = mid
        return lo, solve_tree(loads, lo, fast, self.convs)


def run_phase(pack: Pack, ph: Phase, storage_temp: float) -> PhaseResult:
    if ph.dormant_i_a is not None:
        yrs = ph.dur_s / YEAR_S
        pack.q += ph.dormant_i_a * ph.dur_s / 3.6
        pack.q += pack.cell.capacity_ref_mah * (
            aging_loss_frac(storage_temp, pack.dormant_years + yrs)
            - aging_loss_frac(storage_temp, pack.dormant_years))
        pack.dormant_years += yrs
        v = pack.v_term(ph.dormant_i_a)
        # aging is capacity lost, not energy delivered: count only the load
        mwh = ph.dormant_i_a * ph.dur_s / 3.6 * v
        return PhaseResult(ph, pack.q, mwh, v, ph.dormant_i_a)
    n = max(2, int(ph.dur_s / 0.25) + 1) if ph.dur_s <= 150 else 120
    dt = ph.dur_s / n
    res = PhaseResult(ph, pack.q, 0.0, 99.0, 0.0)
    for k in range(n):
        v, tree = pack.operating_point(list(ph.loads))
        if tree is None:
            res.fail = f"pack collapsed {k*dt:.0f} s into {ph.name}"
            break
        res.v_min, res.i_max = min(res.v_min, v), max(res.i_max, tree.i_bat)
        flags = tree.flags()
        if flags:
            res.fail = f"{k*dt:.0f} s into {ph.name}: " + "; ".join(flags)
            break
        if tree.i_bat > pack.cell.i_cont_max:
            res.fail = f"I {tree.i_bat:.2f} A > {pack.cell.i_cont_max} A continuous"
            break
        pack.q += tree.i_bat * dt / 3.6
        res.mwh += v * tree.i_bat * dt / 3.6
    res.q_end_mah = pack.q
    return res


def run_peak(pack: Pack, ph: Phase, pk: Peak) -> PeakResult:
    loads = list(ph.loads) + list(pk.extra)
    v, tree = pack.operating_point(loads, fast=True)
    res = PeakResult(ph.name, pk.name, v, tree.i_bat if tree else 0.0,
                     pack.cell.i_pulse_1s_max, tree)
    if tree is None:
        res.fail.append("pack collapses (no operating point)")
        return res
    res.fail += tree.flags()
    if tree.i_bat > pack.cell.i_pulse_1s_max:
        res.fail.append(f"I {tree.i_bat:.2f} A > {pack.cell.i_pulse_1s_max} A pulse rating")
    return res


def spare_descent(pack: Pack, descent: Phase, cap_s: float = 3600.0
                  ) -> tuple[float, float]:
    """Seconds and mWh the descent load could still run after the mission."""
    t, mwh, dt = 0.0, 0.0, 1.0
    while t < cap_s:
        v, tree = pack.operating_point(list(descent.loads))
        if tree is None or tree.flags():
            break
        pack.q += tree.i_bat * dt / 3.6
        mwh += v * tree.i_bat * dt / 3.6
        t += dt
    return t, mwh


def run_mission(cell: CellModel, phases: list[Phase], storage_temp: float = 22.0,
                mission_temp: float = 22.0, cold_alpha: float = 0.6,
                tree: dict | None = None) -> MissionResult:
    """tree: kwargs for power_tree.converters() (what-if regulator swaps)."""
    pack = Pack(cell, storage_temp, cold_alpha, converters(**(tree or {})))
    out: list[PhaseResult] = []
    peaks: list[PeakResult] = []
    failed = False
    for ph in phases:
        pack.temp = storage_temp if ph.dormant_i_a is not None else mission_temp
        if failed:
            break
        pr = run_phase(pack, ph, storage_temp)
        out.append(pr)
        failed = bool(pr.fail)
        for pk in ph.peaks:           # at the phase's most depleted point
            peaks.append(run_peak(pack, ph, pk))
    descent = next(p for p in phases if p.name == "descent")
    spare_s, spare_mwh = (0.0, 0.0) if failed else spare_descent(pack, descent)
    shelf = next((p.dur_s / YEAR_S for p in phases if p.name == "shelf"), 0.0)
    return MissionResult(cell, out, peaks, spare_s, spare_mwh, shelf, mission_temp)


def max_descent_s(cell: CellModel, profile_kw: dict, storage_temp: float,
                  mission_temp: float, cold_alpha: float = 0.6,
                  cap_s: float = 1800.0, tree: dict | None = None
                  ) -> tuple[float, MissionResult]:
    """Longest descent (incl. the end-of-descent pulse checks) that still
    passes. Returns (-1, failing run) when even a zero-length descent fails —
    i.e. the pack cannot finish Ready or source the release pulse at all."""
    def run(d: float) -> MissionResult:
        return run_mission(cell, build_profile(**{**profile_kw, "descent_s": d}),
                           storage_temp, mission_temp, cold_alpha, tree)
    r0 = run(0.0)
    if not r0.ok:
        return -1.0, r0
    hi_r = run(cap_s)
    if hi_r.ok:
        return cap_s, hi_r
    lo, hi, best = 0.0, cap_s, r0
    while hi - lo > 1.0:
        mid = (lo + hi) / 2
        r = run(mid)
        if r.ok:
            lo, best = mid, r
        else:
            hi = mid
    return lo, best


def first_failure(r: MissionResult) -> str:
    for p in r.phases:
        if p.fail:
            return f"{p.phase.name}: {p.fail}"
    for pk in r.peaks:
        if pk.fail:
            return f"{pk.phase}/{pk.peak}: {pk.fail[0]}"
    return ""
