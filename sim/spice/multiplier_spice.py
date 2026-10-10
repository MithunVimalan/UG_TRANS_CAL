#!/usr/bin/env python3
"""Transistor-level energy per multiplication vs gate-level estimates.

For each selected 8x8 multiplier the same random operand sequence is
simulated (a) in ngspice on the full transistor netlist built from the
sky130_fd_sc_hd cell subcircuits (default: layout-extracted cells with LOD
distances, the view that reproduces the Liberty data best, see
results/spice/calibration_inv_1_*), and (b) with ugcal.gatesim from the
Liberty corner in zero-delay, inertial and transport modes.

The comparison boundary is the energy drawn from VPWR+VPB; switching energy of
the primary-input nets (supplied by the stimulus sources in SPICE) is
excluded from the gate-level numbers.  The functional result of every SPICE
cycle is checked against integer multiplication.

Output: results/spice/multiplier_spice_<design>.csv and a summary CSV.
"""
import argparse
import csv
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from ugcal.arith.multipliers import build  # noqa: E402
from ugcal.gatesim import GateLevel  # noqa: E402
from ugcal.liberty import Library  # noqa: E402
from ugcal.sim import netlist_spice as NS  # noqa: E402
from ugcal.sim import ngspice as ng  # noqa: E402

DESIGNS = {"array_rc": False, "braun": False, "dadda_rca": False, "wallace_rca": False, "dadda_ks": False,
           "booth4_dadda_ks": True}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--designs", default=",".join(DESIGNS))
    ap.add_argument("--nvec", type=int, default=41)
    ap.add_argument("--period", type=float, default=12e-9)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--view", default="extracted_lod")
    a = ap.parse_args()
    ng.CELL_VIEW = a.view
    lib = Library(os.path.join(ng.pdk_root(), "sc_hd", "timing", "sky130_fd_sc_hd__tt_025C_1v80.lib"))
    outdir = os.path.join(ng.repo_root(), "results", "spice")
    summary = []
    for d in a.designs.split(","):
        signed = DESIGNS[d]
        nl = build(d, 8, signed=signed)
        rnd = random.Random(a.seed)
        vecs = [{"a": rnd.randrange(256), "b": rnd.randrange(256)} for _ in range(a.nvec)]
        t0 = time.time()
        r = NS.run(nl, vecs, a.period, 1.8, 25, "tt")
        wall = time.time() - t0
        outs = nl.outputs["p"]
        bad = 0
        for k, (v, s) in enumerate(zip(vecs, r["samples"])):
            got = sum(s[n] << i for i, n in enumerate(outs) if n in s)
            aa, bb = v["a"], v["b"]
            if signed:
                aa = aa - 256 if aa > 127 else aa
                bb = bb - 256 if bb > 127 else bb
            if got != (aa * bb) % 65536:
                bad += 1
        gl = GateLevel(nl, lib, out_load_F=5e-15, in_slew_s=50e-12)
        gate = {}
        for mode in ("zero", "inertial", "transport"):
            res = gl.simulate(vecs, a.period, mode)
            p = res.power()
            gate[mode] = [None]  # per-cycle not tracked; use mean
            gate[mode] = (p["total_J"] - p["switching_inputs_J"]) / p["cycles"]
        E = r["E_cycle"]
        e_spice = sum(E) / len(E)
        row = dict(design=d, signed=signed, cells=len(nl.gates), view=a.view, nvec=a.nvec, period_ns=a.period * 1e9,
                   spice_E_fJ=e_spice * 1e15, gate_zero_fJ=gate["zero"] * 1e15, gate_inertial_fJ=gate["inertial"] * 1e15,
                   gate_transport_fJ=gate["transport"] * 1e15,
                   spice_over_inertial=e_spice / gate["inertial"], functional_errors=bad, wall_s=wall,
                   ngspice=r["ngspice"])
        summary.append(row)
        print(", ".join(f"{k}={v:.4g}" if isinstance(v, float) else f"{k}={v}" for k, v in row.items()), flush=True)
        with open(os.path.join(outdir, f"multiplier_spice_{d}_{a.view}.csv"), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["cycle", "a", "b", "E_supply_fJ", "E_input_sources_fJ"])
            for k, (e, ei) in enumerate(zip(E, r["E_in_cycle"]), start=1):
                w.writerow([k, vecs[k]["a"], vecs[k]["b"], f"{e * 1e15:.4f}", f"{ei * 1e15:.4f}"])
    path = os.path.join(outdir, f"multiplier_spice_summary_{a.view}.csv")
    exists = os.path.exists(path)
    with open(path, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary[0].keys()))
        if not exists:
            w.writeheader()
        w.writerows(summary)


if __name__ == "__main__":
    main()
