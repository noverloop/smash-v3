"""Subprocess wrapper for the CalculiX `ccx_2.23` solver.

CalculiX is an external C/FORTRAN binary; the smash pipeline talks to
it by writing a `.inp` deck (`ccx_writer`), invoking the solver in a
clean working directory, and parsing the `.frd` result file
(`frd_parser`). This module is the subprocess shim.

The Homebrew tap `costerwi/calculix/calculix-ccx` installs the binary
at `/opt/homebrew/Cellar/calculix-ccx/<version>/bin/ccx_2.<version>`;
we look there first, then fall back to `which ccx_2.23` / `which ccx`.
A custom path can be passed via the `CCX_BIN` env var or the `binary=`
kwarg on `run_ccx()`.
"""
from __future__ import annotations

import dataclasses
import os
import pathlib
import shutil
import subprocess
import time


# Canonical install location for the costerwi/calculix homebrew tap.
# `find_ccx_binary()` scans these in order and returns the first hit.
_BREW_PATTERN = "/opt/homebrew/Cellar/calculix-ccx/*/bin/ccx_*"
_LINUX_FALLBACKS = (
    "/usr/local/bin/ccx_2.23",
    "/usr/local/bin/ccx",
    "/usr/bin/ccx_2.23",
    "/usr/bin/ccx",
)


def find_ccx_binary(env_override: str | None = None) -> str | None:
    """Locate the CalculiX solver binary.

    Search order:
      1. `env_override` (typically `os.environ["CCX_BIN"]`)
      2. Homebrew Cellar path (costerwi/calculix tap, macOS)
      3. `shutil.which("ccx_2.23")`, `shutil.which("ccx")`
      4. Standard /usr/local/bin / /usr/bin fallbacks

    Returns the path string, or None if no binary is found.
    """
    if env_override and pathlib.Path(env_override).exists():
        return env_override
    env = os.environ.get("CCX_BIN")
    if env and pathlib.Path(env).exists():
        return env
    # Homebrew on macOS.
    import glob
    matches = sorted(glob.glob(_BREW_PATTERN), reverse=True)
    if matches:
        return matches[0]
    # PATH lookup.
    for name in ("ccx_2.23", "ccx_2.22", "ccx_2.21", "ccx"):
        p = shutil.which(name)
        if p:
            return p
    # Hard-coded Linux fallbacks.
    for p in _LINUX_FALLBACKS:
        if pathlib.Path(p).exists():
            return p
    return None


# Resolved at import time; lazy so test rigs can run on machines
# without CalculiX installed.
CCX_BINARY_DEFAULT = find_ccx_binary()


@dataclasses.dataclass
class CCXRunResult:
    """Outcome of a single `ccx` solver run."""
    inp_path: str                     # the .inp deck driving the run
    output_dir: str                   # working directory (.dat, .frd, .sta land here)
    return_code: int                  # subprocess exit code (0 = success)
    elapsed_s: float                  # wall-clock solve time
    stdout: str                       # captured solver stdout
    stderr: str                       # captured solver stderr
    frd_path: str | None              # `.frd` result file (None if solver crashed)
    dat_path: str | None              # `.dat` text summary file


def run_ccx(inp_path: str | pathlib.Path,
            *, binary: str | None = None,
            cwd: str | pathlib.Path | None = None,
            timeout_s: float | None = None,
            check: bool = True) -> CCXRunResult:
    """Invoke `ccx_2.23` on the given input deck.

    `inp_path` is the `.inp` file. `ccx_2.23` takes the job NAME as its
    sole argument (no `.inp` suffix), and writes `<name>.frd`, `<name>.dat`
    and `<name>.sta` in the current directory. We chdir to `cwd` (or the
    inp's parent) before invoking so the output lands next to the input.

    Args:
      inp_path:   path to the `.inp` deck. Suffix optional.
      binary:     explicit ccx binary path. Defaults to `find_ccx_binary()`.
      cwd:        working directory for the solver. Defaults to inp's parent.
      timeout_s:  hard kill after this many seconds; None = no limit.
      check:      raise CalledProcessError if the solver returns non-zero.

    Returns a `CCXRunResult` with all the artefacts the result parser
    needs (`.frd` for nodal fields, `.dat` for the printed summaries).
    """
    inp = pathlib.Path(inp_path).resolve()
    if inp.suffix.lower() != ".inp":
        inp = inp.with_suffix(".inp")
    if not inp.exists():
        raise FileNotFoundError(f"CCX input deck not found: {inp}")
    work = pathlib.Path(cwd).resolve() if cwd is not None else inp.parent

    ccx_bin = binary or CCX_BINARY_DEFAULT
    if ccx_bin is None:
        raise RuntimeError(
            "CalculiX binary not found. Install via the homebrew tap "
            "(`brew tap costerwi/calculix && brew install calculix-ccx`), "
            "set CCX_BIN=/path/to/ccx_2.23, or pass `binary=` explicitly."
        )

    # ccx takes the job name (no extension) as its sole argument.
    job_name = inp.stem
    t0 = time.time()
    proc = subprocess.run(
        [ccx_bin, job_name],
        cwd=str(work), capture_output=True, text=True,
        timeout=timeout_s, check=False,
    )
    elapsed = time.time() - t0

    frd = work / f"{job_name}.frd"
    dat = work / f"{job_name}.dat"
    result = CCXRunResult(
        inp_path=str(inp), output_dir=str(work),
        return_code=proc.returncode, elapsed_s=elapsed,
        stdout=proc.stdout, stderr=proc.stderr,
        frd_path=str(frd) if frd.exists() else None,
        dat_path=str(dat) if dat.exists() else None,
    )
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode, [ccx_bin, job_name],
            output=proc.stdout, stderr=proc.stderr,
        )
    return result
