#!/usr/bin/env python3
"""Adders on sky130_fd_sc_hd: ripple-carry vs parallel-prefix (Part IX of the brief).

Two n-bit operands -> n+1-bit sum (carry out kept), unsigned, exhaustively or
randomly verified.  Same conditions as the multiplier study (tt_025C_1v80,
drive-1 cells, 50 ps input ramps, 5 fF output loads, no wires).

Output: results/power/adder_study.csv
"""
import csv
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from ugcal.arith.multipliers import cpa  # noqa: E402
from ugcal.arith.netlist import Netlist, pack_inputs  # noqa: E402
from ugcal.arith.verilog import cellinfo  # noqa: E402
from ugcal.gatesim import GateLevel  # noqa: E402
from ugcal.liberty import Library  # noqa: E402
from ugcal.sim.ngspice import pdk_root, repo_root  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from arch_study import transistor_count  # noqa: E402


def build_adder(n, kind):
    nl = Netlist(f"add{n}_{kind}")
    a = nl.add_input("a", n)
    b = nl.add_input("b", n)
    cols = [[a[i], b[i]] for i in range(n)] + [[]]
    out = cpa(nl, cols, kind)
    nl.set_output("s", out[:n + 1])
    nl.meta["pruned_gates"] = nl.prune()
    return nl


def main():
    lib = Library(os.path.join(pdk_root(), "sc_hd", "timing", "sky130_fd_sc_hd__tt_025C_1v80.lib"))
    rows = []
    for n in (8, 16, 22, 32):
        for kind in ("ripple", "kogge_stone", "brent_kung", "sklansky"):
            nl = build_adder(n, kind)
            rnd = random.Random(5)
            vecs = [{"a": rnd.randrange(1 << n), "b": rnd.randrange(1 << n)} for _ in range(1001)]
            # functional check on the same vectors
            v = nl.simulate(pack_inputs({"a": n, "b": n}, vecs), len(vecs))
            bad = sum(1 for k, x in enumerate(vecs)
                      if sum(((v[net] >> k) & 1) << i for i, net in enumerate(nl.outputs["s"])) != x["a"] + x["b"])
            gl = GateLevel(nl, lib, out_load_F=5e-15, in_slew_s=50e-12)
            sta = gl.sta()
            cells = [cellinfo(g)[0] for g in nl.gates]
            e = {}
            for mode in ("zero", "inertial", "transport"):
                p = gl.simulate(vecs, 20e-9, mode).power()
                e[mode] = (p["total_J"] - p["switching_inputs_J"]) / p["cycles"]
            rows.append(dict(n=n, adder=kind, cells=len(nl.gates), transistors=sum(transistor_count(c) for c in cells),
                             area_um2=sum(lib.cell("sky130_fd_sc_hd__" + c).area for c in cells),
                             crit_ns=sta["delay_s"] * 1e9, E_zero_fJ=e["zero"] * 1e15, E_inertial_fJ=e["inertial"] * 1e15,
                             E_transport_fJ=e["transport"] * 1e15, functional_errors=bad))
            r = rows[-1]
            print(f"{n:2d} {kind:12s} cells={r['cells']:4d} area={r['area_um2']:7.0f} crit={r['crit_ns']:6.3f} ns "
                  f"E zero/inert/trans = {r['E_zero_fJ']:7.1f}/{r['E_inertial_fJ']:7.1f}/{r['E_transport_fJ']:7.1f} fJ "
                  f"errors={bad}", flush=True)
    with open(os.path.join(repo_root(), "results", "power", "adder_study.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
