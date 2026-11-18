"""Axisymmetric magneto-quasistatic finite-volume solver (r, z), complex phasors.

Unknown: the flux function ψ = r·A_φ (Wb/rad). Fields: B_r = −(1/r) ∂ψ/∂z,
B_z = (1/r) ∂ψ/∂r; flux through a coaxial loop at (r, z) = 2π ψ. Governing
equation (Ampère + eddy currents, E_φ = −jω A_φ):

    ∂/∂r( ν/r ∂ψ/∂r ) + ∂/∂z( ν/r ∂ψ/∂z ) − jωσ ψ / r = −J_s,   ν = 1/µ

Materials (µ_r, σ) and source current densities are piecewise constant per
cell; ψ = 0 on the axis (exact) and on the outer box (truncation — keep it
far). Linear materials only: the caller checks steel saturation from the
returned |B|. Validated against the free-space loop and the long-tube DC
limit in tests/test_sim_inductive.py.
"""
from __future__ import annotations

import dataclasses
import math

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

MU0 = 4e-7 * math.pi
MIN_CELL = 1e-6                # m — coincident region edges closer than this are merged


@dataclasses.dataclass
class Region:
    """Axisymmetric rectangle r0 ≤ r ≤ r1, z0 ≤ z ≤ z1 (metres). Later regions
    override earlier ones. A coil carries `turns` (current set per solve)."""
    name: str
    r0: float
    r1: float
    z0: float
    z1: float
    mu_r: float = 1.0
    sigma: float = 0.0
    turns: int = 0
    h: float | None = None        # requested local mesh size (m)


def graded_axis(lo: float, hi: float, marks: list, h_of, h_far: float, growth: float = 1.18):
    """Node coordinates on [lo, hi]: every mark is a node; each interval between
    marks is split at its local size h_of(a, b) (falls back to geometric growth
    from the nearest fine interval when h_of returns None)."""
    pts = []
    for m in sorted({lo, hi, *[m for m in marks if lo <= m <= hi]}):
        if not pts or m - pts[-1] > MIN_CELL:      # merge coincident region edges
            pts.append(m)
    pts[-1] = hi
    nodes = [pts[0]]
    hs = [h_of(a, b) for a, b in zip(pts, pts[1:])]
    # intervals with no requested size grow geometrically away from fine ones
    for k, (a, b) in enumerate(zip(pts, pts[1:])):
        h = hs[k]
        if h is not None:
            n = max(1, math.ceil((b - a) / h - 1e-9))
            nodes += list(np.linspace(a, b, n + 1)[1:])
            continue
        hl = hs[k - 1] if k > 0 else None
        hr = hs[k + 1] if k + 1 < len(hs) else None
        h0l = hl if hl is not None else h_far
        h0r = hr if hr is not None else h_far
        seg = _grow(a, b, h0l, h0r, h_far, growth)
        nodes += seg[1:]
    out = [nodes[0]]
    for x in nodes[1:]:
        if x - out[-1] > MIN_CELL:
            out.append(x)
    out[-1] = nodes[-1]
    return np.array(out)


def _grow(a, b, h0l, h0r, h_max, g):
    """Nodes from a to b, sizes growing from h0l (left) and h0r (right)."""
    left, right = [a], [b]
    hl, hr = h0l, h0r
    while right[-1] - left[-1] > hl + hr:
        if hl <= hr:
            left.append(left[-1] + hl)
            hl = min(hl * g, h_max)
        else:
            right.append(right[-1] - hr)
            hr = min(hr * g, h_max)
    return left + right[::-1]


class Mesh:
    def __init__(self, r: np.ndarray, z: np.ndarray, regions: list):
        self.r, self.z = r, z
        self.dr, self.dz = np.diff(r), np.diff(z)
        self.rc = 0.5 * (r[:-1] + r[1:])
        self.zc = 0.5 * (z[:-1] + z[1:])
        nr, nz = len(self.rc), len(self.zc)
        self.nu = np.full((nr, nz), 1.0 / MU0)
        self.sigma = np.zeros((nr, nz))
        self.coil = {}                     # name → (mask, turns, area)
        self.region_mask = {}
        R, Z = np.meshgrid(self.rc, self.zc, indexing="ij")
        for reg in regions:
            m = (R >= reg.r0) & (R <= reg.r1) & (Z >= reg.z0) & (Z <= reg.z1)
            self.region_mask[reg.name] = m
            self.nu[m] = 1.0 / (MU0 * reg.mu_r)
            self.sigma[m] = reg.sigma
            if reg.turns:
                area = float((np.outer(self.dr, self.dz) * m).sum())
                self.coil[reg.name] = (m, reg.turns, area)

    # ── assembly ──────────────────────────────────────────────────────
    def solve(self, omega: float, currents: dict) -> np.ndarray:
        """ψ at the nodes (nr+1, nz+1) for coil currents {name: amps (complex)}."""
        r, dr, dz, rc = self.r, self.dr, self.dz, self.rc
        Nr, Nz = len(r), len(self.z)
        ii, jj = np.meshgrid(np.arange(1, Nr - 1), np.arange(1, Nz - 1), indexing="ij")
        nu, sg = self.nu, self.sigma
        J = np.zeros_like(sg)
        for name, amps in currents.items():
            m, turns, area = self.coil[name]
            J = J + m * (turns * amps / area)
        drw, dre = dr[ii - 1], dr[ii]
        dzs, dzn = dz[jj - 1], dz[jj]
        ri = r[ii]
        cSW, cSE = (ii - 1, jj - 1), (ii, jj - 1)
        cNW, cNE = (ii - 1, jj), (ii, jj)
        aE = (nu[cSE] * dzs / 2 + nu[cNE] * dzn / 2) / (rc[ii] * dre)
        aW = (nu[cSW] * dzs / 2 + nu[cNW] * dzn / 2) / (rc[ii - 1] * drw)
        rqw, rqe = ri - drw / 4, ri + dre / 4
        aN = (nu[cNW] * drw / 2 / rqw + nu[cNE] * dre / 2 / rqe) / dzn
        aS = (nu[cSW] * drw / 2 / rqw + nu[cSE] * dre / 2 / rqe) / dzs
        q = [(cSW, drw, dzs, rqw), (cSE, dre, dzs, rqe), (cNW, drw, dzn, rqw), (cNE, dre, dzn, rqe)]
        eddy = sum(sg[c] * (a / 2) * (b / 2) / rq for c, a, b, rq in q)
        src = sum(J[c] * (a / 2) * (b / 2) for c, a, b, _rq in q)
        diag = -(aE + aW + aN + aS) - 1j * omega * eddy
        n_r, n_z = Nr - 2, Nz - 2
        idx = lambda i, j: (i - 1) * n_z + (j - 1)
        k = idx(ii, jj).ravel()
        rows, cols, vals = [k], [k], [diag.ravel()]
        for a, di, dj in ((aE, 1, 0), (aW, -1, 0), (aN, 0, 1), (aS, 0, -1)):
            ni, nj = ii + di, jj + dj
            ok = ((ni >= 1) & (ni <= Nr - 2) & (nj >= 1) & (nj <= Nz - 2)).ravel()
            rows.append(k[ok]); cols.append(idx(ni, nj).ravel()[ok]); vals.append(a.ravel()[ok])
        A = sp.csr_matrix((np.concatenate(vals).astype(complex),
                           (np.concatenate(rows), np.concatenate(cols))), shape=(n_r * n_z,) * 2)
        x = spla.spsolve(A.tocsc(), (-src).ravel().astype(complex))
        psi = np.zeros((Nr, Nz), dtype=complex)
        psi[1:-1, 1:-1] = x.reshape(n_r, n_z)
        return psi

    # ── post-processing ───────────────────────────────────────────────
    def linkage(self, psi: np.ndarray, coil: str) -> complex:
        """Flux linkage (Wb-turns) of a coil: N/A ∫ 2π ψ dA (cell-averaged ψ)."""
        m, turns, area = self.coil[coil]
        pc = 0.25 * (psi[:-1, :-1] + psi[1:, :-1] + psi[:-1, 1:] + psi[1:, 1:])
        return complex(turns / area * (2 * math.pi * pc * np.outer(self.dr, self.dz) * m).sum())

    def cell_B(self, psi: np.ndarray):
        """(B_r, B_z) at cell centres."""
        dpdr = 0.5 * ((psi[1:, :-1] - psi[:-1, :-1]) + (psi[1:, 1:] - psi[:-1, 1:])) / self.dr[:, None]
        dpdz = 0.5 * ((psi[:-1, 1:] - psi[:-1, :-1]) + (psi[1:, 1:] - psi[1:, :-1])) / self.dz[None, :]
        rc = self.rc[:, None]
        return -dpdz / rc, dpdr / rc

    def B_at(self, psi: np.ndarray, r: float, z: float):
        """(B_r, B_z) at a point (bilinear on cell centres)."""
        Br, Bz = self.cell_B(psi)
        i = int(np.clip(np.searchsorted(self.rc, r) - 1, 0, len(self.rc) - 2))
        j = int(np.clip(np.searchsorted(self.zc, z) - 1, 0, len(self.zc) - 2))
        tr = (r - self.rc[i]) / (self.rc[i + 1] - self.rc[i])
        tz = (z - self.zc[j]) / (self.zc[j + 1] - self.zc[j])
        tr, tz = min(max(tr, 0.0), 1.0), min(max(tz, 0.0), 1.0)

        def bil(F):
            return ((1 - tr) * (1 - tz) * F[i, j] + tr * (1 - tz) * F[i + 1, j]
                    + (1 - tr) * tz * F[i, j + 1] + tr * tz * F[i + 1, j + 1])
        quad = self.nu[i:i + 2, j:j + 2]
        if np.ptp(quad) > 1e-9 * quad.max():
            # straddles a material boundary (B_tangential jumps by µ_r):
            # use the cell that contains the point, never a mix
            ic = int(np.clip(np.searchsorted(self.r, r) - 1, 0, len(self.rc) - 1))
            jc = int(np.clip(np.searchsorted(self.z, z) - 1, 0, len(self.zc) - 1))
            return Br[ic, jc], Bz[ic, jc]
        return bil(Br), bil(Bz)

    def max_B_in(self, psi: np.ndarray, region: str) -> float:
        Br, Bz = self.cell_B(psi)
        m = self.region_mask[region]
        return float(np.sqrt(np.abs(Br) ** 2 + np.abs(Bz) ** 2)[m].max()) if m.any() else 0.0
