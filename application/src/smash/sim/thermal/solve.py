"""Steady-state thermal nodal-analysis solver.

Lifted verbatim from the legacy (now-removed) `thermal_sim/solve.py`
— the math is just Kirchhoff's current law applied to thermal nodes,
no smash-side concepts touch it. The graph it consumes comes from
`smash.sim.thermal.topology.build_graph()`.

  electrical current   ↔  heat flow      (W)
  electrical voltage   ↔  temperature    (K)
  electrical resistance↔  thermal resist (K/W)
  conductance G        ↔  thermal conductance 1/R  (W/K)

G is the symmetric N×N nodal conductance matrix:
  G[i][i] = sum of conductances connected to node i
  G[i][j] = -g_ij for i≠j (negative of the conductance between nodes)

Q is the N-vector of heat injection (W) per node.

Boundary nodes (housing at T_amb) are eliminated by substitution:
  for each edge i ↔ boundary j with conductance g:
    G[i][i] += g
    Q[i]    += g · T_amb_j

Solve:  T = G⁻¹ · Q   (Kelvin/Celsius — same difference for our use).
"""
from __future__ import annotations

import numpy as np


def solve(g) -> dict:
    """Solve steady-state node temperatures (°C). Returns
    `{node_name: temperature}`."""
    unknown_nodes = [n for n in g.nodes.values() if n.t_fixed_c is None]
    fixed_nodes = {n.name: n.t_fixed_c for n in g.nodes.values()
                   if n.t_fixed_c is not None}
    if not unknown_nodes:
        return {n: t for n, t in fixed_nodes.items()}

    idx = {n.name: i for i, n in enumerate(unknown_nodes)}
    N = len(unknown_nodes)

    G = np.zeros((N, N), dtype=float)
    Q = np.zeros(N, dtype=float)

    # Inject heat sources at unknown nodes.
    for node in unknown_nodes:
        Q[idx[node.name]] += node.p_input_w

    for edge in g.edges:
        if edge.r_k_per_w <= 0 or not np.isfinite(edge.r_k_per_w):
            continue
        gij = 1.0 / edge.r_k_per_w
        a, b = edge.a, edge.b
        a_known = a in fixed_nodes
        b_known = b in fixed_nodes
        if a_known and b_known:
            continue
        if not a_known and not b_known:
            ia, ib = idx[a], idx[b]
            G[ia, ia] += gij
            G[ib, ib] += gij
            G[ia, ib] -= gij
            G[ib, ia] -= gij
        else:
            if a_known:
                ib = idx[b]
                G[ib, ib] += gij
                Q[ib] += gij * fixed_nodes[a]
            else:
                ia = idx[a]
                G[ia, ia] += gij
                Q[ia] += gij * fixed_nodes[b]

    try:
        T = np.linalg.solve(G, Q)
    except np.linalg.LinAlgError as exc:
        raise RuntimeError(
            "thermal solver failed — likely a node with no path to housing.\n"
            f"  numpy: {exc}"
        ) from exc

    out = {n.name: float(T[idx[n.name]]) for n in unknown_nodes}
    out.update(fixed_nodes)
    return out
