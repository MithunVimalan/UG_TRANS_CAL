#!/usr/bin/env python3
"""Complete integer MAC: energy accounting, timing and throughput (gate level).

MAC definition (ugcal.arith.mac): ACC <- (clr ? 0 : ACC) + A*B, A and B
signed 8-bit, operands registered at the input, accumulator W = 22 bits (the
exact width for K = 64 terms, ugcal.mac.accumulator_width), wrap-around
arithmetic (no overflow possible for K <= 64), no rounding, latency 2 cycles,
initiation interval 1.

For every variant: cells, transistors, area, register-to-register critical
path at tt_025C_1v80 and ss_100C_1v60 (f_max = 1 / (clk->Q + logic + setup)),
energy per MAC split by category (operand registers, Booth encoding, partial
products, reduction, CPA, accumulation, accumulator registers, clock net),
in zero-delay and inertial modes, at a common clock period, and derived
MAC/s/W, TOPS/W (2 ops per MAC) and power density.

Output: results/power/mac_study.csv
"""
import argparse
import csv
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from ugcal.arith.mac import build_mac  # noqa: E402
from ugcal.arith.verilog import cellinfo  # noqa: E402
from ugcal.gatesim import GateLevel  # noqa: E402
from ugcal.liberty import Library  # noqa: E402
from ugcal.mac import accumulator_width, energy_accounting, mac_metrics  # noqa: E402
from ugcal.sim.ngspice import pdk_root, repo_root  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from arch_study import transistor_count  # noqa: E402

VARIANTS = [("separate", "booth4", "kogge_stone", "kogge_stone"),
            ("separate", "bw", "kogge_stone", "kogge_stone"),
            ("separate", "bw", "ripple", "ripple"),
            ("fused", "booth4", "kogge_stone", None),
            ("fused", "bw", "kogge_stone", None),
            ("csa_acc", "booth4", "kogge_stone", None),
            ("csa_acc", "bw", "kogge_stone", None)]


def stimulus(dist, ncyc, K, rnd):
    vecs = []
    for t in range(ncyc):
        if dist == "uniform":
            a, b = rnd.randint(-128, 127), rnd.randint(-128, 127)
        elif dist == "gauss":
            a = max(-128, min(127, int(round(rnd.gauss(0, 16)))))
            b = max(-128, min(127, int(round(rnd.gauss(0, 16)))))
        elif dist == "relu_gauss":   # activation >= 0 (half zeros) x weight
            a = max(0, min(127, int(round(rnd.gauss(0, 32)))))
            b = max(-128, min(127, int(round(rnd.gauss(0, 16)))))
        else:
            raise ValueError(dist)
        vecs.append({"a": a & 255, "b": b & 255, "clr": 1 if t % K == 0 else 0})
    return vecs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ncyc", type=int, default=1025)
    ap.add_argument("--K", type=int, default=64)
    ap.add_argument("--period_ns", type=float, default=10.0)
    ap.add_argument("--dists", default="uniform,gauss,relu_gauss")
    a = ap.parse_args()
    lib_tt = Library(os.path.join(pdk_root(), "sc_hd", "timing", "sky130_fd_sc_hd__tt_025C_1v80.lib"))
    lib_ss = Library(os.path.join(pdk_root(), "sc_hd", "timing", "sky130_fd_sc_hd__ss_100C_1v60.lib"))
    W = accumulator_width(8, 8, a.K, True)
    rows = []
    for variant, pp, final, acc_adder in VARIANTS:
        nl = build_mac(8, W, variant, pp=pp, red="dadda", final=final, acc_adder=acc_adder or "kogge_stone",
                       signed=True)
        name = f"{variant}_{pp}_{final}" + (f"_acc{acc_adder}" if acc_adder and variant == "separate" else "")
        gl = GateLevel(nl, lib_tt, out_load_F=5e-15, in_slew_s=50e-12)
        gl_ss = GateLevel(nl, lib_ss, out_load_F=5e-15, in_slew_s=50e-12)
        # register-to-register path: exclude the output conversion CPA (outside the loop)
        sta_tt = gl.sta()
        sta_ss = gl_ss.sta()
        cells = [cellinfo(g)[0] for g in nl.gates]
        area = sum(lib_tt.cell("sky130_fd_sc_hd__" + c).area for c in cells)
        ntr = sum(transistor_count(c) for c in cells)
        for dist in a.dists.split(","):
            rnd = random.Random(77)
            vecs = stimulus(dist, a.ncyc, a.K, rnd)
            for mode in ("zero", "inertial"):
                r = gl.simulate(vecs, a.period_ns * 1e-9, mode)
                p = r.power()
                acc = energy_accounting(p, r.cycles, outcpa_amortise_K=a.K if variant == "csa_acc" else None)
                e = acc["E_per_MAC_J"]
                f_max_tt = 1.0 / sta_tt["delay_s"]
                met = mac_metrics(e, 1.0 / (a.period_ns * 1e-9))
                row = dict(variant=name, pp=pp, final=final, W=W, dist=dist, mode=mode, cells=len(nl.gates),
                           transistors=ntr, area_um2=area, crit_tt_ns=sta_tt["delay_s"] * 1e9,
                           crit_ss100_ns=sta_ss["delay_s"] * 1e9, fmax_tt_MHz=f_max_tt / 1e6,
                           fmax_ss100_MHz=1e3 / (sta_ss["delay_s"] * 1e9), period_ns=a.period_ns,
                           E_MAC_fJ=e * 1e15, TOPS_per_W=met["TOPS_per_W"],
                           P_at_fmax_tt_uW=e * f_max_tt * 1e6,
                           power_density_at_fmax_tt_W_cm2=e * f_max_tt / (area * 1e-8))
                for g, v in acc["by_group"].items():
                    row[f"E_{g}_fJ"] = v["E_per_MAC_J"] * 1e15
                rows.append(row)
                print(f"{name:34s} {dist:10s} {mode:8s} E/MAC={e*1e15:8.1f} fJ  crit tt {sta_tt['delay_s']*1e9:.2f} ns"
                      f" ss {sta_ss['delay_s']*1e9:.2f} ns  area {area:.0f} um2  " +
                      " ".join(f"{g}={v['E_per_MAC_J']*1e15:.0f}" for g, v in acc["by_group"].items()), flush=True)
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    out = os.path.join(repo_root(), "results", "power", "mac_study.csv")
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
