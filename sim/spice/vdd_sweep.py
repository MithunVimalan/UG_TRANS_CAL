#!/usr/bin/env python3
"""Supply-voltage sweep of SKY130 HD logic: FO4 delay, switching energy, leakage.

Test structures (layout-extracted inv_1 cells, extracted_lod view by default):

  * FO4 chain: a driver inverter, then 4 stages each loaded by four inv_1
    inputs (one in the chain plus three dummies), driven by a ramp.  The FO4
    delay is the mean of rise and fall 50 %-50 % delays of the 3rd stage.
  * Energy per FO4 transition: supply energy of the measured stage (its own
    VPWR/VPB sources) per output transition, averaged over rise and fall.
  * Leakage: static VPWR+VPB power of one inv_1 averaged over its two input
    states (DC operating point, GMIN 1e-20 S).

Below 1.28 V the HD library has no Liberty characterisation; the BSIM4 cards
are nominally valid for 0..1.95 V.  Results at low VDD are model
extrapolations of the foundry cards (class F) without foundry
characterisation of the cells.

Output: results/spice/vdd_sweep_<corner>_<T>C.csv
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from ugcal.sim import cellchar as cc  # noqa: E402
from ugcal.sim import ngspice as ng  # noqa: E402


def fo4_deck(vdd: float, temp: float, corner: str, period: float, tr: float) -> str:
    inv = ng.cell_netlist("inv_1")
    pins = cc.cell_pins("inv_1")

    def X(name, a, y, supply):
        m = {"A": a, "Y": y, "VPWR": supply, "VPB": supply, "VGND": "0", "VNB": "0"}
        return f"X{name} " + " ".join(m[p] for p in pins) + " sky130_fd_sc_hd__inv_1"

    lines = [f"* FO4 chain VDD={vdd}", ng.lib_line(corner), f'.include "{inv}"', f".temp {temp}",
             ".options reltol=1e-4 abstol=1e-15 vntol=1e-7",
             f"Vvdd vdd 0 {vdd}", f"Vmeas vdd vm 0",  # measured stage supply (stage 3)
             f"Vin in 0 PULSE(0 {vdd} {period/4} {tr/0.6} {tr/0.6} {period/2 - tr/0.6} {period})"]
    # driver + 5 stages; every stage drives the next stage + 3 dummy inverters (FO4)
    nodes = ["in", "n1", "n2", "n3", "n4", "n5", "n6"]
    lines.append(X("drv", "in", "n0", "vdd"))
    prev = "n0"
    for k in range(1, 6):
        out = f"n{k}"
        sup = "vm" if k == 3 else "vdd"
        lines.append(X(f"s{k}", prev, out, sup))
        for d in range(3):
            lines.append(X(f"d{k}_{d}", out, f"dummy{k}_{d}", "vdd"))
        prev = out
    lines.append(X("term", prev, "nterm", "vdd"))
    tstop = 3 * period
    lines += [f".tran {min(1e-12, period / 2000):.3e} {tstop:.4e}", ".save v(n2) v(n3) i(Vmeas)", ".control",
              "set wr_vecnames", "set wr_singlescale", "run", "wrdata out.txt v(n2) v(n3) i(Vmeas)", ".endc", ".end"]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corner", default="tt")
    ap.add_argument("--temp", type=float, default=25.0)
    ap.add_argument("--view", default="extracted_lod")
    ap.add_argument("--vdds", default="1.95,1.8,1.6,1.4,1.2,1.0,0.9,0.8,0.7,0.6,0.5,0.45,0.4,0.35,0.3")
    a = ap.parse_args()
    ng.CELL_VIEW = a.view
    rows = []
    for vdd in [float(x) for x in a.vdds.split(",")]:
        # choose a period long enough for the slow low-voltage delays (iterate)
        period = 4e-9
        for _ in range(8):
            r = ng.run(fo4_deck(vdd, a.temp, a.corner, period, 0.2 * period / 20), ["out.txt"]).vectors
            t, v2, v3, i = r["time"], r["v(n2)"], r["v(n3)"], r["i(vmeas)"]
            half = vdd / 2
            # second period: n2 and n3 edges
            t0 = period
            d = []
            for rising_in in (True, False):
                tin = cc.crossing(t, v2, half, rising_in, t0)
                tout = cc.crossing(t, v3, half, not rising_in, tin if tin == tin else t0)
                d.append(tout - tin)
            if all(x == x and x > 0 for x in d) and max(d) < period / 8:
                break
            period *= 4
        # Vmeas is in series between vdd and the stage supply: its branch current
        # is positive when it delivers current to the stage (opposite sign to a
        # supply source from vdd to ground)
        p = [vdd * x for x in i]
        e_cycle = cc.integrate(t, p, period, 2 * period)   # one rise + one fall of n3
        leak = 0.5 * (cc.static_power("inv_1", vdd, a.temp, a.corner, {"A": 0.0}) +
                      cc.static_power("inv_1", vdd, a.temp, a.corner, {"A": vdd}))
        # dynamic energy per transition = (E_cycle - leakage over the period) / 2
        e_dyn = (e_cycle - leak * period) / 2
        row = dict(corner=a.corner, T_C=a.temp, view=a.view, VDD_V=vdd, fo4_ps=0.5 * sum(d) * 1e12,
                   fo4_rise_ps=d[1] * 1e12, fo4_fall_ps=d[0] * 1e12, E_per_transition_fJ=e_dyn * 1e15,
                   leak_inv_pW=leak * 1e12, sim_period_ns=period * 1e9)
        rows.append(row)
        print(", ".join(f"{k}={v:.4g}" if isinstance(v, float) else f"{k}={v}" for k, v in row.items()), flush=True)
    out = os.path.join(ng.repo_root(), "results", "spice", f"vdd_sweep_{a.corner}_{int(a.temp)}C.csv")
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
        fh.write(f"# ngspice {ng.ngspice_version()}; FO4 chain of inv_1 ({a.view} view)\n")


if __name__ == "__main__":
    main()
