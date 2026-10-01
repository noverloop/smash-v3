"""Map parsed `.frd` results to chip pads, write per-chip verdicts.

The bridge between the CalculiX raw output and the same per-chip
pass / warn / fail picture the analytic bend-sim's `ChipVerdict`
already produces. For each chip placement on the board, walk its
`CHIP_PAD_<ref>` node set (the 4 bottom nodes of the chip-or-UF
column, from `smash.sim.fea.mesh`), pull σ(node) from the FRD, and
compute:

  - σ_vm   = von Mises stress = sqrt(0.5·((σxx-σyy)² + (σyy-σzz)² +
              (σzz-σxx)²) + 3·(σxy² + σyz² + σzx²))
  - σ_t    = the maximum positive normal component (tensile pull-off
              along Z — peel mode); for our mesh's z-up orientation
              this is mostly σ_zz at the pad
  - σ_s    = √(σ_xz² + σ_yz²)  — shear at the pad face

Verdict tiers mirror the bend-sim:
  pass < 50 % of limit  (m < 0.5)
  warn < 100 %          (joint stressed but not failing)
  fail ≥ 100 %          (joint fractures)

Comparisons use the per-mode strength from the FabProfile's Solder
(`shear_strength_mpa` for σ_s, `tensile_strength_mpa` for σ_t). The
overall chip verdict is max(σ_t/σ_t_fail, σ_s/σ_s_fail, σ_vm/σ_vm_fail)
where σ_vm_fail = σ_t_fail (conservative).
"""
from __future__ import annotations

import dataclasses
import json
import math
import pathlib

from smash.sim.fea.frd_parser import FRDResult
from smash.sim.fea.mesh import BoardMesh
from smash.state.geometry3d import board_solder


# ── per-chip verdict + report dataclass ────────────────────────────────


@dataclasses.dataclass
class FEAChipVerdict:
    """One chip's worst-pad stress at the parsed FRD's load step.

    For a static run there's only one load step; for a transient
    dynamic run, `time_of_worst_s` is the time at which the worst
    margin occurred (the report walks every stress field in the FRD
    and tracks the worst-across-time per chip)."""
    ref: str
    pad_node_id: int                  # worst node in CHIP_PAD_<ref>
    pad_position_mm: tuple             # (x, y, z) of that node
    sigma_vm_mpa: float                # von Mises at the worst pad node
    sigma_tension_mpa: float           # max +ve normal component (peel mode)
    sigma_shear_mpa: float             # sqrt(σ_xz² + σ_yz²) at the pad
    shear_strength_mpa: float          # solder shear limit (catalog)
    tensile_strength_mpa: float        # solder tensile pull-off limit
    margin: float                       # worst-mode m = σ/σ_fail; ≥1 fails
    binding_mode: str                  # "shear" | "tension" | "vm"
    verdict: str                       # "pass" | "warn" | "fail"
    time_of_worst_s: float | None = None  # solver time of the worst-margin
                                           # snapshot (transient runs only)


@dataclasses.dataclass
class FEABoardResult:
    """Per-board result: every chip's verdict + the load case."""
    board: str
    job_name: str
    load_step_time: float               # solver time (s for dynamic, 1 for static)
    chips: list                          # list[FEAChipVerdict]
    worst: FEAChipVerdict | None
    skipped: list                        # list[(ref, reason)]


# ── helpers ─────────────────────────────────────────────────────────────


def _verdict(margin: float) -> str:
    if margin >= 1.0:  return "fail"
    if margin >= 0.50: return "warn"
    return "pass"


def _von_mises_pa(stress_components: tuple) -> float:
    """σ_vm from CCX Voigt components (Pa). Voigt order: σxx, σyy, σzz,
    σxy, σyz, σzx."""
    sxx, syy, szz, sxy, syz, szx = stress_components
    return math.sqrt(
        0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2)
        + 3.0 * (sxy * sxy + syz * syz + szx * szx)
    )


def _principal_normal_pa(stress_components: tuple) -> float:
    """Max-positive principal normal stress (rough tensile-peel proxy).
    For a corner solder ball, the pull-off direction is largely along
    the plate normal, so σ_zz (component 3) dominates — but the
    eigenvalue path catches general tensile geometry too. Returns the
    maximum eigenvalue of the 3×3 Cauchy tensor."""
    sxx, syy, szz, sxy, syz, szx = stress_components
    # Build the symmetric Cauchy tensor (3×3) and use the standard
    # closed-form eigenvalue formula for symmetric 3×3.
    # Trace + invariants:
    p1 = sxy * sxy + syz * syz + szx * szx
    if p1 == 0.0:
        return max(sxx, syy, szz)
    q = (sxx + syy + szz) / 3.0
    p2 = ((sxx - q) ** 2 + (syy - q) ** 2 + (szz - q) ** 2
          + 2.0 * p1)
    p = math.sqrt(p2 / 6.0)
    if p == 0.0:
        return max(sxx, syy, szz)
    # B = (1/p)·(A - q·I)
    B11 = (sxx - q) / p
    B22 = (syy - q) / p
    B33 = (szz - q) / p
    B12 = sxy / p
    B23 = syz / p
    B13 = szx / p
    detB = (B11 * (B22 * B33 - B23 * B23)
            - B12 * (B12 * B33 - B23 * B13)
            + B13 * (B12 * B23 - B22 * B13))
    r = max(-1.0, min(1.0, detB / 2.0))
    phi = math.acos(r) / 3.0
    eig1 = q + 2.0 * p * math.cos(phi)
    eig3 = q + 2.0 * p * math.cos(phi + 2.0 * math.pi / 3.0)
    eig2 = 3.0 * q - eig1 - eig3
    return max(eig1, eig2, eig3)


def _shear_at_node_pa(stress_components: tuple) -> float:
    """In-plane shear at a pad-bottom node: √(σ_xz² + σ_yz²). The
    pad's normal is z, so the shear acting in the pad plane is the
    magnitude of the (σ_xz, σ_yz) traction vector."""
    _, _, _, _, syz, szx = stress_components
    return math.sqrt(syz * syz + szx * szx)


# ── per-chip walker ────────────────────────────────────────────────────


def evaluate_chip_verdicts(frd: FRDResult, mesh: BoardMesh, board,
                            *, fab=None,
                            field_label: str | None = None,
                            ) -> FEABoardResult:
    """For every chip placement on `board`, find the worst-stress node
    in its CHIP_PAD_<ref> set, classify against the FabProfile's solder
    strengths, and return one `FEAChipVerdict` per chip.

    `field_label` selects which stress field to read from the FRD; the
    default picks the first "STRESS"/"S" field (CCX static runs only
    have one).
    """
    s = (frd.field(field_label) if field_label
         else frd.stresses())
    if s is None:
        raise ValueError("FRD has no stress field — solver didn't "
                         "emit `*EL FILE, S`?")

    solder = board_solder(board, fab=fab)
    if solder is None or solder.shear_strength_mpa is None \
            or solder.tensile_strength_mpa is None:
        raise ValueError(
            f"{board.name}: FabProfile lacks shear / tensile strength for "
            f"the board's solder — populate Solder.shear_strength_mpa + "
            f"tensile_strength_mpa"
        )
    sigma_shear_fail = float(solder.shear_strength_mpa)
    sigma_tens_fail = float(solder.tensile_strength_mpa)
    # vm threshold — use the tensile limit as the conservative
    # equivalent (vm ~ 1.7 × shear, matches tensile order)
    sigma_vm_fail = sigma_tens_fail

    chips_done: list = []
    skipped: list = []
    for pl in (board.chip_placements or []):
        chip = pl.item
        ref = getattr(chip, "ref", None)
        if ref is None:
            continue
        nset_name = f"CHIP_PAD_{ref}"
        nset = mesh.node_sets.get(nset_name)
        if not nset:
            skipped.append((ref, "no CHIP_PAD node set in mesh"))
            continue
        # Worst-σ node in the pad set, by von Mises.
        worst_nid = None
        worst_v = None
        worst_vm = -1.0
        for nid in nset:
            comps = s.values_by_node.get(nid)
            if comps is None:
                continue
            vm = _von_mises_pa(comps)
            if vm > worst_vm:
                worst_vm = vm
                worst_nid = nid
                worst_v = comps
        if worst_nid is None:
            skipped.append((ref, "no stress data at any pad node"))
            continue
        sigma_t = max(0.0, _principal_normal_pa(worst_v)) / 1e6
        sigma_s = _shear_at_node_pa(worst_v) / 1e6
        sigma_vm = worst_vm / 1e6
        # Per-mode margins; the verdict is the binding worst.
        m_s = sigma_s / sigma_shear_fail
        m_t = sigma_t / sigma_tens_fail
        m_v = sigma_vm / sigma_vm_fail
        if m_s >= m_t and m_s >= m_v:
            binding, margin = "shear", m_s
        elif m_t >= m_v:
            binding, margin = "tension", m_t
        else:
            binding, margin = "vm", m_v
        coord = frd.nodes.get(worst_nid, (0.0, 0.0, 0.0))
        chips_done.append(FEAChipVerdict(
            ref=ref, pad_node_id=worst_nid,
            pad_position_mm=(coord[0] * 1e3,
                              coord[1] * 1e3, coord[2] * 1e3),
            sigma_vm_mpa=sigma_vm,
            sigma_tension_mpa=sigma_t,
            sigma_shear_mpa=sigma_s,
            shear_strength_mpa=sigma_shear_fail,
            tensile_strength_mpa=sigma_tens_fail,
            margin=margin, binding_mode=binding,
            verdict=_verdict(margin),
        ))

    worst = max(chips_done, key=lambda c: c.margin) if chips_done else None
    return FEABoardResult(
        board=board.name,
        job_name=frd.job_name or board.name,
        load_step_time=s.total_time,
        chips=chips_done, worst=worst, skipped=skipped,
    )


def _interp_fcu_disp(fcu_top: dict, disp, x_mm: float, y_mm: float):
    """Bilinear-interpolate the F.Cu top-surface displacement at (x, y) mm
    from the structured node grid. Returns (ux, uy, uz) or None if the
    point has no in-board grid support. Re-normalises the weights over
    whichever of the 4 surrounding nodes exist (grid holes at the disc
    edge carry a 0 node id), so a pad near the board rim still resolves."""
    g = fcu_top["grid"]
    nx = len(g)
    ny = len(g[0]) if nx else 0
    if not nx or not ny:
        return None
    fx = (x_mm - fcu_top["x0"]) / fcu_top["xy"]
    fy = (y_mm - fcu_top["y0"]) / fcu_top["xy"]
    ix, iy = int(math.floor(fx)), int(math.floor(fy))
    tx, ty = fx - ix, fy - iy
    acc = [0.0, 0.0, 0.0]
    wsum = 0.0
    for dix, diy, w in ((0, 0, (1 - tx) * (1 - ty)), (1, 0, tx * (1 - ty)),
                        (0, 1, (1 - tx) * ty), (1, 1, tx * ty)):
        jx, jy = ix + dix, iy + diy
        if 0 <= jx < nx and 0 <= jy < ny and g[jx][jy]:
            u = disp.values_by_node.get(g[jx][jy])
            if u is not None:
                acc[0] += w * u[0]; acc[1] += w * u[1]; acc[2] += w * u[2]
                wsum += w
    if wsum < 1e-9:
        return None
    return (acc[0] / wsum, acc[1] / wsum, acc[2] / wsum)


# ── SAC305 solder-joint failure STRAINS (single high-strain-rate event) ──
# The launch pulse is a single ~1-5 ms monotonic event, not fatigue cycling,
# so the joint fails by ductile tear at a limiting shear/peel STRAIN — not by
# a linear-elastic stress (solder yields at ~0.2 % and flows to tens of % of
# strain, so multiplying strain by the elastic modulus grossly over-states the
# "stress"). These are the calibration knobs of the whole launch verdict and
# should be pinned to coupon/shock-test data (the user's empirical range).
# Conservative starting values: SAC305 shear elongation-to-failure is ~30-45 %
# quasi-static but embrittles at high strain rate; ~50 µm/mm class balls with a
# stress concentration at the corner tear earlier. 20 % shear / 12 % peel are
# deliberately conservative placeholders.
GAMMA_FAIL_SHEAR = 0.20
GAMMA_FAIL_PEEL = 0.12


def evaluate_chip_verdicts_joint(frd: FRDResult, mesh: BoardMesh,
                                 board, *, fab=None,
                                 gamma_fail_shear: float = GAMMA_FAIL_SHEAR,
                                 gamma_fail_peel: float = GAMMA_FAIL_PEEL,
                                 ) -> FEABoardResult:
    """Grade each chip on solder-joint STRAIN (γ = Δu / h_joint), not on
    substrate stress and not on a linear-elastic joint *stress*.

    Δu is the relative displacement of the cohesive-spring node pair (chip
    pad ↔ nearest F.Cu node), read from the frd nodal displacement field;
    h_joint is the ball/fillet standoff. γ_shear = |Δu_xy| / h, γ_peel =
    Δu_z⁺ / h. margin = max(γ_shear/γ_fail_shear, γ_peel/γ_fail_peel).

    Two reasons this is the right metric for a single launch pulse:
      • mesh-INSENSITIVE — displacement (the primary FE unknown) converges
        where derived stress does not, so it's immune to the Cu-coin
        material-interface singularity that makes the nodal-von-Mises
        verdict non-convergent under refinement;
      • physically correct for DUCTILE solder under a single monotonic
        event — failure is strain-to-tear, so a linear elastic spring
        force (F = k·Δu → τ = G·γ) over-reads by ~E/σ_yield (≈50×) once
        the joint yields (e.g. a NAND corner at γ=1.2 % reads 210 MPa ≫
        34 MPa strength, but 1.2 % ≪ 20 % tear strain → it survives).

    `sigma_shear_mpa` / `sigma_tension_mpa` carry the equivalent ELASTIC
    stress (G·γ, E·γ) for reference/calibration only — they are NOT the
    verdict. Needs the deck's cohesive springs + `*NODE FILE, U`.
    """
    from smash.sim.fea.build_deck import _solder_constants
    disp = frd.displacements()
    if disp is None:
        raise ValueError("FRD has no displacement field — need *NODE FILE, U")
    E_sol, G_sol, _nu = _solder_constants(fab)

    # pad-node XY (mm) for interpolating the board displacement AT the pad,
    # not at the offset nearest F.Cu grid node (which measures the board's
    # local surface strain over the ~0.3 mm gap, not the joint shear).
    xy_mm = {nid: (xm * 1e3, ym * 1e3)
             for (nid, xm, ym, _zm) in mesh.node_coords}

    by_chip: dict = {}
    for sp in (mesh.spring_pairs or []):
        by_chip.setdefault(sp.chip_ref, []).append(sp)

    chips_done: list = []
    skipped: list = []
    for ref, pairs in by_chip.items():
        h_j = max(pairs[0].h_joint_mm, 0.025) * 1e-3        # m
        w_m = -1.0; w_bind = "shear"; w_gs = 0.0; w_gp = 0.0; w_nid = None
        for sp in pairs:
            up = disp.values_by_node.get(sp.pad_node)
            pxy = xy_mm.get(sp.pad_node)
            uf = (_interp_fcu_disp(mesh.fcu_top, disp, pxy[0], pxy[1])
                  if (mesh.fcu_top and pxy) else None)
            if uf is None:                       # fallback: offset nearest node
                uf = disp.values_by_node.get(sp.fcu_node)
            if up is None or uf is None:
                continue
            dx, dy, dz = up[0] - uf[0], up[1] - uf[1], up[2] - uf[2]
            g_shear = (dx * dx + dy * dy) ** 0.5 / h_j       # shear strain
            g_peel = max(0.0, dz) / h_j                       # peel strain
            m_s, m_p = g_shear / gamma_fail_shear, g_peel / gamma_fail_peel
            m = max(m_s, m_p)
            if m > w_m:
                w_m, w_bind = m, ("shear" if m_s >= m_p else "peel")
                w_gs, w_gp, w_nid = g_shear, g_peel, sp.pad_node
        if w_nid is None:
            skipped.append((ref, "no displacement at spring nodes"))
            continue
        coord = frd.nodes.get(w_nid, (0.0, 0.0, 0.0))
        chips_done.append(FEAChipVerdict(
            ref=ref, pad_node_id=w_nid,
            pad_position_mm=(coord[0] * 1e3, coord[1] * 1e3, coord[2] * 1e3),
            sigma_vm_mpa=w_gs * G_sol / 1e6,             # equiv elastic (ref)
            sigma_tension_mpa=w_gp * E_sol / 1e6,
            sigma_shear_mpa=w_gs * G_sol / 1e6,
            shear_strength_mpa=gamma_fail_shear * 100.0,   # store γ_fail as %
            tensile_strength_mpa=gamma_fail_peel * 100.0,
            margin=w_m, binding_mode=w_bind, verdict=_verdict(w_m),
        ))
    worst = max(chips_done, key=lambda c: c.margin) if chips_done else None
    return FEABoardResult(
        board=board.name, job_name=frd.job_name or board.name,
        load_step_time=(disp.total_time if hasattr(disp, "total_time") else 0.0),
        chips=chips_done, worst=worst, skipped=skipped,
    )


def evaluate_chip_verdicts_transient(frd: FRDResult, mesh: BoardMesh,
                                       board, *, fab=None) -> FEABoardResult:
    """Walk EVERY stress field in the FRD (one per output time step),
    classify per chip, and keep the worst margin per chip across time.
    The returned FEAChipVerdict's `time_of_worst_s` records when each
    chip's worst margin occurred — useful for telling the design where
    the binding instant in the load history lives (e.g., "the worst
    stress on U_AWR happens at t=2.3 ms, just past peak acceleration")."""
    stress_fields = [f for f in frd.fields
                     if f.label in ("STRESS", "S")]
    if not stress_fields:
        raise ValueError(
            "FRD has no STRESS fields — *EL FILE, S not requested?"
        )

    # Run the per-step walker for each field; merge by chip ref keeping
    # the WORST margin so far.
    by_ref: dict = {}            # ref → (FEAChipVerdict, source_field_time)
    last_result: FEABoardResult | None = None
    for field in stress_fields:
        per_step = evaluate_chip_verdicts(
            frd, mesh, board, fab=fab, field_label=field.label,
        ) if False else _evaluate_against_one_field(
            field, frd.nodes, mesh, board, fab,
        )
        last_result = per_step
        for v in per_step.chips:
            cur = by_ref.get(v.ref)
            if cur is None or v.margin > cur.margin:
                v.time_of_worst_s = field.total_time
                by_ref[v.ref] = v

    chips = list(by_ref.values())
    worst = max(chips, key=lambda c: c.margin) if chips else None
    return FEABoardResult(
        board=board.name,
        job_name=frd.job_name or board.name,
        load_step_time=stress_fields[-1].total_time if stress_fields else 0.0,
        chips=chips, worst=worst,
        skipped=last_result.skipped if last_result else [],
    )


def _evaluate_against_one_field(field, nodes, mesh, board, fab):
    """Internal — same logic as evaluate_chip_verdicts but takes a
    specific FRDField instance instead of resolving from `frd.field()`.
    Lets the transient walker iterate per-step without re-resolving."""
    solder = board_solder(board, fab=fab)
    if solder is None or solder.shear_strength_mpa is None \
            or solder.tensile_strength_mpa is None:
        raise ValueError(
            f"{board.name}: FabProfile lacks shear / tensile strength for "
            f"the board's solder"
        )
    sigma_shear_fail = float(solder.shear_strength_mpa)
    sigma_tens_fail = float(solder.tensile_strength_mpa)
    sigma_vm_fail = sigma_tens_fail

    chips_done: list = []
    skipped: list = []
    for pl in (board.chip_placements or []):
        chip = pl.item
        ref = getattr(chip, "ref", None)
        if ref is None:
            continue
        nset = mesh.node_sets.get(f"CHIP_PAD_{ref}")
        if not nset:
            skipped.append((ref, "no CHIP_PAD node set"))
            continue
        worst_nid = None
        worst_v = None
        worst_vm = -1.0
        for nid in nset:
            comps = field.values_by_node.get(nid)
            if comps is None:
                continue
            vm = _von_mises_pa(comps)
            if vm > worst_vm:
                worst_vm = vm
                worst_nid = nid
                worst_v = comps
        if worst_nid is None:
            skipped.append((ref, "no stress data at any pad node"))
            continue
        sigma_t = max(0.0, _principal_normal_pa(worst_v)) / 1e6
        sigma_s = _shear_at_node_pa(worst_v) / 1e6
        sigma_vm = worst_vm / 1e6
        m_s = sigma_s / sigma_shear_fail
        m_t = sigma_t / sigma_tens_fail
        m_v = sigma_vm / sigma_vm_fail
        if m_s >= m_t and m_s >= m_v:
            binding, margin = "shear", m_s
        elif m_t >= m_v:
            binding, margin = "tension", m_t
        else:
            binding, margin = "vm", m_v
        coord = nodes.get(worst_nid, (0.0, 0.0, 0.0))
        chips_done.append(FEAChipVerdict(
            ref=ref, pad_node_id=worst_nid,
            pad_position_mm=(coord[0] * 1e3, coord[1] * 1e3, coord[2] * 1e3),
            sigma_vm_mpa=sigma_vm, sigma_tension_mpa=sigma_t,
            sigma_shear_mpa=sigma_s,
            shear_strength_mpa=sigma_shear_fail,
            tensile_strength_mpa=sigma_tens_fail,
            margin=margin, binding_mode=binding,
            verdict=_verdict(margin),
        ))

    worst = max(chips_done, key=lambda c: c.margin) if chips_done else None
    return FEABoardResult(
        board=board.name,
        job_name="",                  # transient walker fills this in
        load_step_time=field.total_time,
        chips=chips_done, worst=worst, skipped=skipped,
    )


# ── report writers ────────────────────────────────────────────────────


_VERDICT_GLYPH = {"pass": "✓", "warn": "⚠", "fail": "✗"}


def write_report(result: FEABoardResult, out_dir: str | pathlib.Path,
                 *, platform_label: str | None = None) -> dict:
    """Emit `report.md` + `report.json` to `out_dir`. Returns a summary
    dict the platform-sweep harness can roll up."""
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # JSON sidecar — round-trip friendly.
    chips_json = [dataclasses.asdict(c) for c in result.chips]
    json_blob = {
        "board": result.board,
        "job": result.job_name,
        "load_step_time_s": result.load_step_time,
        "platform": platform_label,
        "chips": chips_json,
        "worst": dataclasses.asdict(result.worst) if result.worst else None,
        "skipped": [{"ref": r, "reason": w} for r, w in result.skipped],
    }
    (out / "report.json").write_text(json.dumps(json_blob, indent=2))

    # Markdown.
    lines = [
        f"# FEA stress report — `{result.board}`",
        "",
    ]
    if platform_label:
        lines += [f"Launch platform: **{platform_label}**", ""]
    lines += [
        f"CCX job: `{result.job_name}` · step time = {result.load_step_time}",
        "",
        "## Per-chip pad stress",
        "",
        ("| ref | pad pos (mm) | σ_vm (MPa) | σ_tension (MPa) | "
         "σ_shear (MPa) | binding | margin | verdict |"),
        ("|---|---|---:|---:|---:|---|---:|---|"),
    ]
    for c in sorted(result.chips, key=lambda x: -x.margin):
        x, y, z = c.pad_position_mm
        v = _VERDICT_GLYPH.get(c.verdict, "?")
        lines.append(
            f"| `{c.ref}` | ({x:+.1f}, {y:+.1f}, {z:+.2f}) | "
            f"{c.sigma_vm_mpa:6.2f} | {c.sigma_tension_mpa:6.2f} | "
            f"{c.sigma_shear_mpa:6.2f} | {c.binding_mode} | "
            f"{c.margin:.3f} | {v} {c.verdict} |"
        )
    if result.worst:
        w = result.worst
        lines += [
            "",
            f"**Worst chip: `{w.ref}` — m = {w.margin:.3f} ({w.verdict}) "
            f"on the {w.binding_mode} mode.**",
        ]
    if result.skipped:
        lines += ["", "## Skipped chips", ""]
        for ref, reason in result.skipped:
            lines.append(f"- `{ref}` — {reason}")

    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "output_dir": str(out),
        "n_chips": len(result.chips),
        "n_skipped": len(result.skipped),
        "worst_ref": result.worst.ref if result.worst else None,
        "worst_margin": (result.worst.margin if result.worst else None),
    }
