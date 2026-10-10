"""Minimal, dependency-free driver for batch ngspice runs.

A deck is written to a work directory together with the PDK ``.spiceinit``
(``ngbehavior=hsa`` is required to read the SKY130 model cards), ngspice is
run in batch mode, and vectors written with ``wrdata`` are parsed back.

Every run records the ngspice version, the deck text and the wall time so
that a result file can quote exactly how it was produced.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

SPICEINIT = """* written by ugcal.sim.ngspice (copied from the SKY130 fd_pr models/.spiceinit)
set ngbehavior=hsa
set skywaterpdk
set ng_nomodcheck
set num_threads=1
option noinit
option klu
"""


def pdk_root() -> str:
    return os.path.expanduser(os.environ.get("PDK_ROOT", "~/pdk"))


def repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def slim_lib_path() -> str:
    """Path of the reduced model library (see sim/pdk/make_slim_lib.py)."""
    p = os.environ.get("SKY130_SLIM_LIB") or os.path.join(repo_root(), "build", "sky130_slim.lib.spice")
    if not os.path.exists(p):
        raise FileNotFoundError(
            f"{p} not found: run `PDK_ROOT=... python3 sim/pdk/make_slim_lib.py` first")
    return p


def full_lib_path() -> str:
    return os.path.join(pdk_root(), "fd_pr", "models", "sky130.lib.spice")


def cell_netlist(cell: str) -> str:
    """Path of a sky130_fd_sc_hd cell transistor netlist, e.g. 'inv_1'."""
    base = cell.rsplit("_", 1)[0]
    p = os.path.join(pdk_root(), "sc_hd", "cells", base, f"sky130_fd_sc_hd__{cell}.spice")
    if not os.path.exists(p):
        raise FileNotFoundError(p)
    return p


_VERSION_CACHE: Optional[str] = None


def ngspice_version() -> str:
    global _VERSION_CACHE
    if _VERSION_CACHE is None:
        out = subprocess.run(["ngspice", "--version"], capture_output=True, text=True).stdout
        m = re.search(r"ngspice-(\S+)", out)
        _VERSION_CACHE = m.group(1) if m else "unknown"
    return _VERSION_CACHE


@dataclass
class RunResult:
    deck: str
    stdout: str
    vectors: Dict[str, List[float]] = field(default_factory=dict)
    measures: Dict[str, float] = field(default_factory=dict)
    wall_s: float = 0.0
    version: str = ""


class NgspiceError(RuntimeError):
    pass


def parse_wrdata(path: str) -> Dict[str, List[float]]:
    """Parse a file written with `set wr_vecnames` + `set wr_singlescale`."""
    with open(path) as fh:
        header = fh.readline().split()
        cols: List[List[float]] = [[] for _ in header]
        for line in fh:
            parts = line.split()
            if len(parts) != len(header):
                continue
            for i, tok in enumerate(parts):
                cols[i].append(float(tok))
    return {_norm(name): col for name, col in zip(header, cols)}


def _norm(name: str) -> str:
    """Normalise vector names: lower case, 'vx#branch' -> 'i(vx)'."""
    n = name.lower()
    if n.endswith("#branch"):
        n = f"i({n[:-7]})"
    return n


_MEAS_RE = re.compile(r"^\s*([A-Za-z_][\w()\[\].:#]*)\s*=\s*([-+0-9.eE]+)\s*$", re.M)


def run(deck: str, wrdata_files: Optional[List[str]] = None, timeout: float = 1200,
        keep_dir: Optional[str] = None) -> RunResult:
    """Run a deck in batch mode.

    ``wrdata_files`` lists file names (relative to the work directory) that the
    deck's control block writes with ``wrdata``; they are parsed and merged
    into ``RunResult.vectors`` (prefixed with ``<file>:`` when several).
    ``.meas`` results and ``print`` scalars of the form ``name = value`` are
    parsed into ``RunResult.measures``.
    """
    work = keep_dir or tempfile.mkdtemp(prefix="ugcal_ngspice_")
    os.makedirs(work, exist_ok=True)
    with open(os.path.join(work, ".spiceinit"), "w") as fh:
        fh.write(SPICEINIT)
    deck_path = os.path.join(work, "deck.sp")
    with open(deck_path, "w") as fh:
        fh.write(deck)
    t0 = time.time()
    proc = subprocess.run(["ngspice", "-b", "deck.sp"], cwd=work, capture_output=True,
                          text=True, timeout=timeout)
    wall = time.time() - t0
    out = proc.stdout + proc.stderr
    if proc.returncode != 0 or re.search(r"(?i)\berror\b(?! *\(ignored\))", out) and "fatal" in out.lower():
        raise NgspiceError(f"ngspice failed (rc={proc.returncode}) in {work}:\n{out[-4000:]}")
    res = RunResult(deck=deck, stdout=out, wall_s=wall, version=ngspice_version())
    for m in _MEAS_RE.finditer(out):
        try:
            res.measures[m.group(1).lower()] = float(m.group(2))
        except ValueError:
            pass
    for fname in wrdata_files or []:
        p = os.path.join(work, fname)
        if not os.path.exists(p):
            raise NgspiceError(f"expected output {fname} not written; log tail:\n{out[-4000:]}")
        vecs = parse_wrdata(p)
        if len(wrdata_files) == 1:
            res.vectors.update(vecs)
        else:
            res.vectors.update({f"{fname}:{k}": v for k, v in vecs.items()})
    if keep_dir is None:
        shutil.rmtree(work, ignore_errors=True)
    return res


def lib_line(corner: str = "tt", full: bool = False) -> str:
    path = full_lib_path() if full else slim_lib_path()
    return f'.lib "{path}" {corner}'
