#!/usr/bin/env python3
"""Controlled comparison of multiplier architectures on sky130_fd_sc_hd.

Same library corner, supply, temperature, output load (5 fF per product
bit), input transition (50 ps ideal ramps), operand width, arithmetic
semantics and stimulus for every design.  Designs: the structural generators
of ugcal.arith (each gate = one drive-1 cell, no sizing/buffering) and the
Yosys/ABC netlists of a behavioural ``a*b`` (results/synth).

Per design and operand distribution:
  cells, transistors (schematic device count per cell), area (Liberty),
  critical path (ugcal.gatesim STA, worst over edges and when-conditions),
  leakage (state-weighted), energy per multiplication in zero-delay
  (functional), inertial and transport modes, glitch factor, EDP.

Energy boundary: VPWR of the multiplier cells; switching of the primary-input
nets is excluded (it belongs to whatever drives the operands).

Output: results/power/arch_study_<corner>.csv
"""
import argparse
import csv
import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from ugcal.arith.multipliers import build  # noqa: E402
from ugcal.arith.verilog import cellinfo  # noqa: E402
from ugcal.arith.vimport import import_verilog  # noqa: E402
from ugcal.gatesim import GateLevel  # noqa: E402
from ugcal.liberty import Library  # noqa: E402
from ugcal.sim.ngspice import pdk_root, repo_root  # noqa: E402

UNSIGNED = ["array_rc", "braun", "wallace_rca", "wallace_ks", "dadda_rca", "dadda_ks", "dadda_bk", "dadda_sk",
            "booth4_dadda_ks", "yosys"]
SIGNED = ["bw_array_cs", "bw_wallace_rca", "bw_dadda_ks", "booth4_wallace_ks", "booth4_dadda_rca",
          "booth4_dadda_ks", "yosys"]


def transistor_count(cell: str, _cache={}) -> int:
    if cell not in _cache:
        base = cell.rsplit("_", 1)[0]
        p = os.path.join(pdk_root(), "sc_hd", "cells", base, f"sky130_fd_sc_hd__{cell}.spice")
        _cache[cell] = sum(1 for l in open(p) if l.startswith("X"))
    return _cache[cell]


def draw(dist: str, n: int, signed: bool, rnd: random.Random) -> int:
    lo, hi = (-(1 << (n - 1)), (1 << (n - 1)) - 1) if signed else (0, (1 << n) - 1)
    if dist == "uniform":
        x = rnd.randint(lo, hi)
    elif dist == "sparse50":
        x = 0 if rnd.random() < 0.5 else rnd.randint(lo, hi)
    elif dist == "small":   # |x| < 2^(n/2)
        r = 1 << (n // 2)
        x = rnd.randint(-r + 1, r - 1) if signed else rnd.randint(0, r - 1)
    elif dist == "gauss":   # NN-weight-like, sigma = range/16
        s = (hi - lo) / 16
        x = int(round(rnd.gauss(0 if signed else (hi - lo) / 8, s)))
    else:
        raise ValueError(dist)
    x = max(lo, min(hi, x))
    return x & ((1 << n) - 1)


def designs(n: int, signed: bool, lib: Library):
    for d in (SIGNED if signed else UNSIGNED):
        if d == "yosys":
            path = os.path.join(repo_root(), "results", "synth", f"mul{n}{'s' if signed else 'u'}_abcarea.v")
            if not os.path.exists(path):
                continue
            nl = import_verilog(open(path).read(), lib, group="syn")
            yield "yosys_abc", nl
        else:
            if d.startswith("bw") and not signed:
                continue
            yield d, build(d, n, signed=signed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corner", default="tt_025C_1v80")
    ap.add_argument("--widths", default="8,16")
    ap.add_argument("--nvec", type=int, default=2001)
    ap.add_argument("--dists", default="uniform,sparse50,small,gauss")
    ap.add_argument("--modes", default="zero,inertial,transport")
    a = ap.parse_args()
    lib = Library(os.path.join(pdk_root(), "sc_hd", "timing", f"sky130_fd_sc_hd__{a.corner}.lib"))
    out = os.path.join(repo_root(), "results", "power", f"arch_study_{a.corner}.csv")
    rows = []
    period = 40e-9
    for n in [int(x) for x in a.widths.split(",")]:
        for signed in (False, True):
            if n == 16 and signed:
                continue
            for name, nl in designs(n, signed, lib):
                t0 = time.time()
                gl = GateLevel(nl, lib, out_load_F=5e-15, in_slew_s=50e-12)
                sta = gl.sta()
                cells = [cellinfo(g)[0] for g in nl.gates]
                area = sum(lib.cell("sky130_fd_sc_hd__" + c).area for c in cells)
                ntr = sum(transistor_count(c) for c in cells)
                leak = sum(gl.bound[i].leak_avg for i in range(len(nl.gates)))
                for dist in a.dists.split(","):
                    rnd = random.Random(1000 + n)
                    vecs = [{"a": draw(dist, n, signed, rnd), "b": draw(dist, n, signed, rnd)}
                            for _ in range(a.nvec)]
                    res = {}
                    for mode in a.modes.split(","):
                        r = gl.simulate(vecs, period, mode)
                        p = r.power()
                        e = (p["total_J"] - p["switching_inputs_J"]) / p["cycles"]
                        res[mode] = (e, (p["toggles_total"]) / p["cycles"], p)
                    row = dict(corner=a.corner, n=n, signed=signed, design=name, dist=dist, cells=len(nl.gates),
                               transistors=ntr, area_um2=area, crit_path_ns=sta["delay_s"] * 1e9,
                               leak_avg_nW=leak * 1e9)
                    for mode, (e, tog, p) in res.items():
                        row[f"E_{mode}_fJ"] = e * 1e15
                        row[f"toggles_{mode}"] = tog
                    if "zero" in res and "inertial" in res:
                        row["glitch_factor_inertial"] = res["inertial"][0] / res["zero"][0]
                    if "zero" in res and "transport" in res:
                        row["glitch_factor_transport"] = res["transport"][0] / res["zero"][0]
                    if "inertial" in res:
                        row["EDP_inertial_fJns"] = res["inertial"][0] * 1e15 * sta["delay_s"] * 1e9
                        grp = res["inertial"][2]["by_group"]
                        tot = sum(sum(v.values()) for k, v in grp.items() if k != "inputs")
                        for g_, v in grp.items():
                            if g_ != "inputs":
                                row[f"share_{g_}"] = sum(v.values()) / tot
                    rows.append(row)
                    print(f"n={n} {'s' if signed else 'u'} {name:18s} {dist:8s} cells={len(nl.gates):4d} "
                          f"area={area:7.0f} crit={sta['delay_s']*1e9:6.3f}ns "
                          + " ".join(f"E_{m}={row[f'E_{m}_fJ']:7.1f}" for m in res)
                          + f" ({time.time()-t0:.0f}s)", flush=True)
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
