#!/usr/bin/env python3
"""Calibrate the SPICE set-up against the SKY130 HD Liberty data.

For a single-input cell (default inv_1, also buf_1) and a set of Liberty
(slew, load) grid points, this script simulates one output-falling and one
output-rising transition with ngspice and compares

  * 50 %-50 % propagation delay      vs  cell_rise / cell_fall
  * 20 %-80 % output transition       vs  rise_transition / fall_transition
  * supply energy per edge            vs  rise_power / fall_power
    under two decompositions:
      H1: table = E_supply(edge) - 1/2 C_L V^2  (split model, OpenSTA adds 1/2 C V^2)
      H0: table = E_supply(edge) - C_L V^2 on rising, E_supply on falling
  * effective input capacitance       vs  pin capacitance
  * leakage per input state           vs  leakage_power(when)

Liberty corners are paired with SPICE corners by name (tt_025C_1v80 -> tt,
25 C, 1.80 V).  Which SPICE corner the foundry actually used for each Liberty
corner is not documented; agreement or disagreement here is the evidence.

Output: results/spice/calibration_<cell>_<libcorner>.csv
"""
import argparse
import csv
import math
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from ugcal.liberty import Library  # noqa: E402
from ugcal.sim import cellchar as cc  # noqa: E402
from ugcal.sim import ngspice as ng  # noqa: E402

SLEW_IDX = [0, 2, 4, 6]   # indices into the 7-point Liberty axis
LOAD_IDX = [0, 2, 4, 6]


def lib_path(corner: str) -> str:
    return os.path.join(ng.pdk_root(), "sc_hd", "timing", f"sky130_fd_sc_hd__{corner}.lib")


def decode(corner: str):
    m = re.fullmatch(r"(tt|ss|ff|sf|fs)_(n?)(\d+)C_(\d)v(\d+)", corner)
    proc, neg, t, vi, vf = m.groups()
    return proc, (-1 if neg else 1) * float(t), float(f"{vi}.{vf}")


def characterise(cell: str, inpin: str, outpin: str, libcorner: str, inverting: bool):
    lib = Library(lib_path(libcorner))
    proc, temp, vdd = decode(libcorner)
    assert abs(vdd - lib.op_voltage) < 1e-9 and abs(temp - lib.op_temperature) < 1e-9
    name = f"sky130_fd_sc_hd__{cell}"
    arc = lib.arc(name, inpin, outpin)
    slews = arc.tables["cell_rise"].index[0]
    loads = arc.tables["cell_rise"].index[1]
    rows = []
    for si in SLEW_IDX:
        for li in LOAD_IDX:
            slew = slews[si] * 1e-9
            load = loads[li] * 1e-12
            full = slew / 0.6
            # generous settling windows
            w = 4 * full + 3e-9 + 60e-9 * (load / 0.18e-12)
            t1 = 0.2e-9
            t2 = t1 + w
            tstop = t2 + w
            e1 = cc.Edge(inpin, t1, True, slew)
            e2 = cc.Edge(inpin, t2, False, slew)
            bench = cc.Bench(cell, vdd, temp, proc, inputs={inpin: cc.pwl(0.0, vdd, [e1, e2])},
                             loads={outpin: load}, tstop=tstop, tstep=min(1e-12, full / 50))
            v = bench.run(["v(%s)" % inpin.lower(), "v(%s)" % outpin.lower(), "i(Vvdd)", "i(Vvpb)",
                           "i(Vin_%s)" % inpin.lower()])
            t = v["time"]
            vin = v["v(%s)" % inpin.lower()]
            vout = v["v(%s)" % outpin.lower()]
            p_sup = [-vdd * (a + b) for a, b in zip(v["i(vvdd)"], v["i(vvpb)"])]
            i_in = v["i(vin_%s)" % inpin.lower()]
            half = 0.5 * vdd
            # edge 1: input rises
            tin1 = cc.crossing(t, vin, half, True, t1)
            tout1 = cc.crossing(t, vout, half, not inverting, t1)
            # edge 2: input falls
            tin2 = cc.crossing(t, vin, half, False, t2)
            tout2 = cc.crossing(t, vout, half, inverting, t2)
            lo, hi = 0.2 * vdd, 0.8 * vdd

            def trans(t_after, rising):
                a = cc.crossing(t, vout, lo if rising else hi, rising, t_after)
                b = cc.crossing(t, vout, hi if rising else lo, rising, t_after)
                return b - a

            out1_rising = not inverting
            tr1 = trans(t1, out1_rising)
            tr2 = trans(t2, not out1_rising)
            e_sup1 = cc.integrate(t, p_sup, t1 - 0.05e-9, t2 - 0.05e-9)
            e_sup2 = cc.integrate(t, p_sup, t2 - 0.05e-9, tstop - 0.05e-9)
            # leakage background over the windows (static current at end of each window)
            q_in1 = -cc.integrate(t, i_in, t1 - 0.05e-9, t2 - 0.05e-9)  # charge delivered into the input on rise
            # map to output edges
            if inverting:
                d_fall, d_rise = tout1 - tin1, tout2 - tin2
                tr_fall, tr_rise = tr1, tr2
                e_fall, e_rise = e_sup1, e_sup2
            else:
                d_rise, d_fall = tout1 - tin1, tout2 - tin2
                tr_rise, tr_fall = tr1, tr2
                e_rise, e_fall = e_sup1, e_sup2
            half_cv2 = 0.5 * load * vdd ** 2
            lib_vals = dict(
                lib_cell_rise=lib.delay_s(name, inpin, outpin, "rise", slew, load),
                lib_cell_fall=lib.delay_s(name, inpin, outpin, "fall", slew, load),
                lib_rise_tr=lib.transition_s(name, inpin, outpin, "rise", slew, load),
                lib_fall_tr=lib.transition_s(name, inpin, outpin, "fall", slew, load),
                lib_rise_power=lib.internal_energy_J(name, outpin, inpin, "rise", slew, load),
                lib_fall_power=lib.internal_energy_J(name, outpin, inpin, "fall", slew, load),
            )
            rows.append(dict(
                cell=cell, libcorner=libcorner, slew_ns=slews[si], load_pF=loads[li],
                spice_cell_rise_ps=d_rise * 1e12, lib_cell_rise_ps=lib_vals["lib_cell_rise"] * 1e12,
                spice_cell_fall_ps=d_fall * 1e12, lib_cell_fall_ps=lib_vals["lib_cell_fall"] * 1e12,
                spice_rise_tr_ps=tr_rise * 1e12, lib_rise_tr_ps=lib_vals["lib_rise_tr"] * 1e12,
                spice_fall_tr_ps=tr_fall * 1e12, lib_fall_tr_ps=lib_vals["lib_fall_tr"] * 1e12,
                spice_E_supply_rise_fJ=e_rise * 1e15, spice_E_supply_fall_fJ=e_fall * 1e15,
                half_CV2_fJ=half_cv2 * 1e15,
                H1_rise_fJ=(e_rise - half_cv2) * 1e15, H1_fall_fJ=(e_fall - half_cv2) * 1e15,
                lib_rise_power_fJ=lib_vals["lib_rise_power"] * 1e15,
                lib_fall_power_fJ=lib_vals["lib_fall_power"] * 1e15,
                spice_avg_E_per_transition_fJ=0.5 * (e_rise + e_fall) * 1e15,
                opensta_avg_E_per_transition_fJ=(0.5 * (lib_vals["lib_rise_power"] + lib_vals["lib_fall_power"]) + half_cv2) * 1e15,
                spice_Cin_eff_fF=q_in1 / vdd * 1e15,
                lib_Cin_fF=lib.pin_cap_F(name, inpin) * 1e15,
            ))
            r = rows[-1]
            print(f"{cell} {libcorner} slew {slews[si]:.4g} ns load {loads[li]:.4g} pF: "
                  f"rise {r['spice_cell_rise_ps']:.2f}/{r['lib_cell_rise_ps']:.2f} ps, "
                  f"fall {r['spice_cell_fall_ps']:.2f}/{r['lib_cell_fall_ps']:.2f} ps, "
                  f"E/trans {r['spice_avg_E_per_transition_fJ']:.3f}/{r['opensta_avg_E_per_transition_fJ']:.3f} fJ",
                  flush=True)
    # leakage per state
    leak_rows = []
    c = lib.cell(name)
    for when, val in c.leakage_states:
        state = {inpin: (0.0 if when.startswith("!") else vdd)}
        p = cc.static_power(cell, vdd, temp, proc, state)
        leak_rows.append(dict(cell=cell, libcorner=libcorner, when=when, lib_leak_nW=val * lib.units.leakage * 1e9,
                              spice_leak_nW=p * 1e9))
        print(f"  leakage when {when}: lib {val * lib.units.leakage * 1e9:.5g} nW, spice {p * 1e9:.5g} nW")
    return rows, leak_rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", default="inv_1")
    ap.add_argument("--inpin", default="A")
    ap.add_argument("--outpin", default="Y")
    ap.add_argument("--noninverting", action="store_true")
    ap.add_argument("--corners", default="tt_025C_1v80,tt_100C_1v80,ss_100C_1v60,ff_n40C_1v95")
    a = ap.parse_args()
    outdir = os.path.join(ng.repo_root(), "results", "spice")
    os.makedirs(outdir, exist_ok=True)
    for corner in a.corners.split(","):
        rows, leak = characterise(a.cell, a.inpin, a.outpin, corner, not a.noninverting)
        with open(os.path.join(outdir, f"calibration_{a.cell}_{corner}.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        with open(os.path.join(outdir, f"calibration_{a.cell}_{corner}_leakage.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(leak[0].keys()))
            w.writeheader()
            w.writerows(leak)


if __name__ == "__main__":
    main()
