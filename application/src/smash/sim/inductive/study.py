"""Two-way inductive link through a steel body: wall-thickness × frequency sweep.

DOWNLINK  clamp → round: |B| at the wake sensors per clamp ampere-turn →
          clamp ampere-turns / current / power to trip the DRV5032FC Hall
          (2 × B_OP max = 9.6 mT) and the RR123 TMR (2 × 0.7 mT). Bits are slow
          coded pulses (Hall 20 Hz sampling → ≥ 100 ms bits ≈ 2–5 Hz content;
          TMR 1 Hz → ≥ 3 s bits ≈ 0.1–0.3 Hz), so the relevant f is low.
UPLINK    round → clamp: tower coil pulsed at I_TOWER; signal as clamp-coil
          EMF and as |B| at a magnetometer on the clamp bore, against thermal,
          sensor and AMBIENT magnetic noise in the bit bandwidth.
Also reported: mutual inductance, peak |B| in the steel (saturation check).
"""
from __future__ import annotations

import dataclasses
import json
import math
import pathlib

import numpy as np

from smash.sim.inductive.model import LinkParams, build, MM

KB_T = 1.380649e-23 * 300.0
HALL_TRIP_T = 2 * 4.8e-3          # DRV5032FC B_OP max × 2 margin
TMR_TRIP_T = 2 * 0.7e-3           # RR123-1H02 B_OP × 2 margin
STEEL_SAT_T = 1.2                 # linear model invalid above ~this
I_TOWER_A = 0.19                  # uplink pulse: BAT_PROT / (4×47 Ω ∥ + coil + BSS138)
TOWER_R_OHM = 2.7                 # 8-turn In2.Cu spiral, 0.25 mm, ½ oz (smash.parts.coils)
CLAMP_WIRE_D_MM = 0.5
CLAMP_FILL = 0.6
AMP_NOISE_V = 5e-9                # V/√Hz, low-noise preamp
FLUXGATE_NOISE_T = 20e-12         # T/√Hz (commercial fluxgate, ~1 Hz)
AMBIENT_NOISE_T = 1e-9            # T/√Hz practical floor (urban / industrial; worse at 50/60 Hz harmonics)
BIT_BW_HZ = 1.0                   # ≈ 1 bit/s OOK
FREQS = (0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0)
WALLS = (1.0, 2.0, 3.0, 5.0, 7.0, 10.0)


def clamp_resistance(p: LinkParams) -> float:
    r_mid = (p.body_r_out + (p.clamp_gap_mm + p.clamp_radial_mm / 2) * MM)
    a_wire = math.pi * (CLAMP_WIRE_D_MM * MM / 2) ** 2
    return 1.7e-8 * p.clamp_turns * 2 * math.pi * r_mid / a_wire


def run_case(p: LinkParams, freqs=FREQS) -> list:
    import dataclasses as _dc
    mesh_dl, info_dl = build(_dc.replace(p, clamp_on="sensor"), f_max_hz=max(freqs))
    mesh, info = build(_dc.replace(p, clamp_on="tower"), f_max_hz=max(freqs))
    rs, zs = info_dl["r_sensor"], info_dl["z_sensor"]
    r_mag = p.body_r_out + 0.5 * MM
    z_t = info["z_tower_coil"]
    R_clamp = clamp_resistance(p)
    out = []
    for f in freqs:
        w = 2 * math.pi * f
        psi_d = mesh_dl.solve(w, {"clamp": 1.0})            # 1 A in the clamp (over the sensors)
        Br, Bz = mesh_dl.B_at(psi_d, rs, zs)
        b_sensor = math.hypot(abs(Br), abs(Bz)) / p.clamp_turns      # T per clamp AT
        b_steel_dl = mesh_dl.max_B_in(psi_d, "steel") / p.clamp_turns   # T per clamp AT
        psi_u = mesh.solve(w, {"tower_coil": 1.0})          # 1 A in the tower coil
        M = mesh.linkage(psi_u, "clamp")                    # Wb-turns per amp = H
        Brm, Bzm = mesh.B_at(psi_u, r_mag, z_t)
        b_mag = math.hypot(abs(Brm), abs(Bzm))             # T per tower amp at the clamp bore
        emf = w * abs(M) * I_TOWER_A
        n_coil = math.sqrt(4 * KB_T * R_clamp + AMP_NOISE_V ** 2) * math.sqrt(BIT_BW_HZ)
        # ambient field noise picked up by the clamp coil (flux through its area)
        a_clamp = math.pi * (p.body_r_out + (p.clamp_gap_mm + p.clamp_radial_mm / 2) * MM) ** 2
        n_amb_emf = w * p.clamp_turns * a_clamp * AMBIENT_NOISE_T * math.sqrt(BIT_BW_HZ)
        sig_mag = b_mag * I_TOWER_A
        n_mag = math.hypot(FLUXGATE_NOISE_T, AMBIENT_NOISE_T) * math.sqrt(BIT_BW_HZ)
        need_hall = HALL_TRIP_T / b_sensor if b_sensor > 0 else math.inf
        need_tmr = TMR_TRIP_T / b_sensor if b_sensor > 0 else math.inf
        out.append({
            "wall_mm": p.wall_mm, "mu_r": p.mu_r, "f_hz": f,
            "dl_B_sensor_uT_per_AT": b_sensor * 1e6,
            "dl_AT_hall": need_hall, "dl_AT_tmr": need_tmr,
            "dl_I_hall_A": need_hall / p.clamp_turns,
            "dl_P_hall_W": (need_hall / p.clamp_turns) ** 2 * R_clamp,
            "dl_B_steel_at_hall_T": b_steel_dl * need_hall,
            "ul_M_nH": abs(M) * 1e9,
            "ul_emf_uV": emf * 1e6,
            "ul_snr_coil_dB": 20 * math.log10(emf / math.hypot(n_coil, n_amb_emf)) if emf > 0 else -math.inf,
            "ul_B_mag_nT": sig_mag * 1e9,
            "ul_snr_mag_dB": 20 * math.log10(sig_mag / n_mag) if sig_mag > 0 else -math.inf,
            "clamp_R_ohm": R_clamp,
        })
    return out


def run(walls=WALLS, freqs=FREQS, mu_rs=(100.0,), mu_sens_wall=3.0, mu_sens=(50.0, 300.0)):
    rows = []
    for mu in mu_rs:
        for t in walls:
            rows += run_case(LinkParams(wall_mm=t, mu_r=mu), freqs)
    for mu in mu_sens:
        rows += run_case(LinkParams(wall_mm=mu_sens_wall, mu_r=mu), freqs)
    # reference: no steel body at all (free air) at the reference wall geometry
    ref = run_case(LinkParams(wall_mm=mu_sens_wall, mu_r=1.0, sigma_steel=0.0), freqs)
    for r in ref:
        r["wall_mm"], r["mu_r"] = 0.0, 1.0
    return rows + ref


def best_rows(rows, mu=100.0):
    """Per wall (µ_r = mu): best uplink frequency (fluxgate SNR) + downlink at 3 Hz."""
    out = []
    for t in sorted({r["wall_mm"] for r in rows if r["mu_r"] == mu and r["wall_mm"] > 0}):
        rr = [r for r in rows if r["wall_mm"] == t and r["mu_r"] == mu]
        ul = max(rr, key=lambda r: r["ul_snr_mag_dB"])
        ulc = max(rr, key=lambda r: r["ul_snr_coil_dB"])
        dl = min(rr, key=lambda r: abs(r["f_hz"] - 3.0))
        out.append({"wall_mm": t, "ul_best_f_mag": ul["f_hz"], "ul_snr_mag_dB": ul["ul_snr_mag_dB"],
                    "ul_B_mag_nT": ul["ul_B_mag_nT"],
                    "ul_best_f_coil": ulc["f_hz"], "ul_snr_coil_dB": ulc["ul_snr_coil_dB"],
                    "dl_AT_hall_3Hz": dl["dl_AT_hall"], "dl_I_hall_3Hz": dl["dl_I_hall_A"],
                    "dl_P_hall_3Hz": dl["dl_P_hall_W"], "dl_B_steel_3Hz": dl["dl_B_steel_at_hall_T"],
                    "dl_AT_tmr_3Hz": dl["dl_AT_tmr"]})
    return out


def write(rows, out_dir) -> dict:
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(rows, indent=1))
    keys = list(rows[0])
    (out / "results.csv").write_text("\n".join([",".join(keys)] + [
        ",".join(f"{r[k]:.6g}" if isinstance(r[k], float) else str(r[k]) for k in keys)
        for r in rows]))
    best = best_rows(rows)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 3, figsize=(15, 4.5))
        for t in sorted({r["wall_mm"] for r in rows if r["mu_r"] in (100.0, 1.0)}):
            rr = [r for r in rows if r["wall_mm"] == t and r["mu_r"] in ((1.0,) if t == 0 else (100.0,))]
            fs = [r["f_hz"] for r in rr]
            lab = "no steel" if t == 0 else f"{t:g} mm"
            ax[0].loglog(fs, [r["dl_AT_hall"] for r in rr], marker="o", label=lab)
            ax[1].semilogx(fs, [r["ul_snr_mag_dB"] for r in rr], marker="o", label=lab)
            ax[2].semilogx(fs, [r["ul_snr_coil_dB"] for r in rr], marker="o", label=lab)
        ax[0].set(title="Downlink: clamp AT to trip the Hall (2×4.8 mT)", xlabel="f (Hz)", ylabel="ampere-turns")
        ax[1].set(title=f"Uplink SNR, magnetometer on clamp ({I_TOWER_A*1e3:g} mA × tower coil, {BIT_BW_HZ:g} Hz BW)",
                  xlabel="f (Hz)", ylabel="dB")
        ax[2].set(title="Uplink SNR, clamp pickup coil", xlabel="f (Hz)", ylabel="dB")
        for a in ax:
            a.grid(True, which="both", alpha=0.3)
        ax[1].axhline(15, color="k", ls="--", lw=0.8)
        ax[2].axhline(15, color="k", ls="--", lw=0.8)
        ax[0].legend(title="steel wall", fontsize=8)
        fig.tight_layout()
        fig.savefig(out / "link_sweep.png", dpi=130)
    except ImportError:
        pass
    lines = ["# Inductive link through a steel body (generated)", "",
             "Axisymmetric magneto-quasistatic FV model (smash.sim.inductive). Ring clamp "
             "coaxial with the tower; µ_r 100, σ 5 MS/m steel, open-ended 250 mm tube.", "",
             "| wall mm | DL clamp AT @3 Hz (Hall / TMR) | DL clamp I (200 t) | DL clamp P | "
             "B steel at DL | UL best f (magnetometer) | UL SNR mag | UL |B| at clamp | "
             "UL best f (coil) | UL SNR coil |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for b in best:
        lines.append(f"| {b['wall_mm']:g} | {b['dl_AT_hall_3Hz']:.0f} / {b['dl_AT_tmr_3Hz']:.0f} | "
                     f"{b['dl_I_hall_3Hz']:.2f} A | {b['dl_P_hall_3Hz']:.1f} W | "
                     f"{b['dl_B_steel_3Hz']:.2f} T | {b['ul_best_f_mag']:g} Hz | "
                     f"{b['ul_snr_mag_dB']:.0f} dB | {b['ul_B_mag_nT']:.2f} nT | "
                     f"{b['ul_best_f_coil']:g} Hz | {b['ul_snr_coil_dB']:.0f} dB |")
    (out / "report.md").write_text("\n".join(lines) + "\n")
    return {"best": best, "dir": out}
