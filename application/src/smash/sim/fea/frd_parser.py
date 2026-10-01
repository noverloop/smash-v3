"""CalculiX `.frd` result-file parser.

The `.frd` file is CCX's native nodal-result format — fixed-width text
with a small set of card kinds we need:

  1C  — header (job + cgx version)
  2C  — node block (NSE = node coordinates)
  3C  — element block (we skip; the deck already carries connectivity)
  100C — result block header (one per requested field per step):
             label, step_number, total_time, n_nodes, ...
         followed by component descriptors (-4 lines) and one nodal
         result row per node (-1 + node_id + N components).
  9999 — end-of-file

For the smash launch FEA we read:
  - U  (3 components Ux, Uy, Uz) — displacement
  - S  (6 components Sxx, Syy, Szz, Sxy, Syz, Szx) — Cauchy stress
  - E  (6 components) — strain (optional)

A `.frd` from a static step has ONE result block per field;
a `.frd` from an explicit dynamic step has ONE block PER OUTPUT
INCREMENT per field (CCX writes every increment unless *OUTPUT, FREQUENCY=
is set).
"""
from __future__ import annotations

import dataclasses
import pathlib


@dataclasses.dataclass
class FRDField:
    """One result field at one step / time instant."""
    label: str                       # "U", "S", "E", "PE", "DISP", ...
    step_number: int
    total_time: float                # solver time (s for dynamic, 1.0 for static)
    component_names: list            # e.g. ["D1", "D2", "D3"] or stress comps
    values_by_node: dict             # node_id (int) → tuple[float, ...]


@dataclasses.dataclass
class FRDResult:
    """Parsed contents of one `.frd` file."""
    fields: list                     # list[FRDField]
    nodes: dict                      # node_id → (x, y, z) coordinates
    job_name: str | None = None

    def field(self, label: str, *, step: int | None = None,
              time: float | None = None) -> FRDField | None:
        """First field matching `label` (and step/time if given)."""
        for f in self.fields:
            if f.label != label:
                continue
            if step is not None and f.step_number != step:
                continue
            if time is not None and abs(f.total_time - time) > 1e-9:
                continue
            return f
        return None

    def displacements(self, **kw) -> FRDField | None:
        return self.field("DISP", **kw) or self.field("U", **kw)

    def stresses(self, **kw) -> FRDField | None:
        return self.field("STRESS", **kw) or self.field("S", **kw)


# ── parsing primitives ──────────────────────────────────────────────────


def _parse_node_block(lines, i: int) -> tuple[dict, int]:
    """Walk a `2C` node block from line index `i`. Returns
    `(node_id → (x,y,z), next_index)`."""
    nodes: dict = {}
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.startswith(" -3"):           # block terminator
            return nodes, i + 1
        # Node row: " -1 <id> <x> <y> <z>" — but fields are fixed-width.
        # CCX uses 12-char numeric fields after the 3-char tag.
        if line.startswith(" -1"):
            try:
                nid = int(line[3:13].strip())
                x = float(line[13:25])
                y = float(line[25:37])
                z = float(line[37:49])
                nodes[nid] = (x, y, z)
            except (ValueError, IndexError):
                pass
        i += 1
    return nodes, i


def _parse_results_block(lines, i: int) -> tuple[FRDField, int]:
    """Walk a `100C` result block starting at index `i`. The header
    line carries the step + time; the next few `-5` lines name the
    components; then per-node `-1` rows hold the values, terminated by
    `-3`."""
    header = lines[i]
    # The standard header layout (FRD short format) packs to fixed
    # columns. Excerpt: " 100CL  101 <something> <step> ...". We pull
    # the step number + time via a tolerant tokenization.
    tokens = header.split()
    step_number = 1
    total_time = 0.0
    if len(tokens) >= 3:
        try:
            total_time = float(tokens[2])
        except ValueError:
            pass
    if len(tokens) >= 8:
        try:
            step_number = int(tokens[7])
        except ValueError:
            pass

    i += 1
    label = ""
    components: list = []
    values: dict = {}
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.startswith(" -4"):
            # " -4 <label> <ncomp> ..."  the label gives the field name
            parts = line.split()
            if len(parts) >= 2:
                label = parts[1]
            i += 1
            continue
        if line.startswith(" -5"):
            # " -5 <comp_name> <type> <kind> <i1> <i2> [<mag_link>]"
            # CCX emits an extra "ALL" descriptor after the real vector
            # / tensor components — it's the field-magnitude metadata,
            # not a data column. Skip it so the value column count
            # matches the actual data width.
            parts = line.split()
            if len(parts) >= 2 and parts[1] != "ALL":
                components.append(parts[1])
            i += 1
            continue
        if line.startswith(" -1"):
            try:
                nid = int(line[3:13].strip())
                # Each component is a 12-wide column starting at col 13.
                ncomp = max(len(components), 1)
                vals = tuple(
                    float(line[13 + k * 12: 13 + (k + 1) * 12])
                    for k in range(ncomp)
                )
                values[nid] = vals
            except (ValueError, IndexError):
                pass
            i += 1
            continue
        if line.startswith(" -3"):
            i += 1
            return FRDField(
                label=label, step_number=step_number,
                total_time=total_time,
                component_names=components, values_by_node=values,
            ), i
        i += 1
    return FRDField(
        label=label, step_number=step_number, total_time=total_time,
        component_names=components, values_by_node=values,
    ), i


def parse_frd(frd_path: str | pathlib.Path) -> FRDResult:
    """Parse a `.frd` file into nodal coordinates + a list of result
    fields (one per (label, step, time) tuple).

    Tolerates the small format variations between CCX versions — the
    line tags (`-1`, `-3`, `-4`, `-5`, `1C`, `2C`, `100C`) are stable
    across 2.16 → 2.23. The fixed-column layout is FRD-standard
    (Sennott / CCX manual §8.2).
    """
    path = pathlib.Path(frd_path)
    if not path.exists():
        raise FileNotFoundError(f".frd file not found: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    job_name = None
    nodes: dict = {}
    fields: list = []

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        # Header — "    1C ... <jobname>"
        if line.startswith("    1C"):
            tokens = line.split()
            if len(tokens) >= 2:
                job_name = tokens[-1]
            i += 1
            continue
        # Node block.
        if line.startswith("    2C"):
            nodes, i = _parse_node_block(lines, i + 1)
            continue
        # Element block — skip (the .inp already has connectivity).
        if line.startswith("    3C"):
            # Walk to the matching -3.
            i += 1
            while i < n and not lines[i].startswith(" -3"):
                i += 1
            i += 1
            continue
        # Result block.
        if line.startswith("  100C") or line.startswith(" 100C"):
            field, i = _parse_results_block(lines, i)
            fields.append(field)
            continue
        # EOF / unknown — just step.
        i += 1

    return FRDResult(fields=fields, nodes=nodes, job_name=job_name)
