#!/usr/bin/env python3
"""Extract transistor-level parameters of SKY130 1.8 V FETs with ngspice.

For each device, geometry, model corner, temperature and supply this script
runs DC sweeps and a quasi-static C-V ramp on the foundry BSIM4 model cards
and extracts:

  Vth_cc_lin, Vth_cc_sat  constant-current threshold at |Id| = I0 * W/L,
                          I0 = 100 nA, at |Vds| = 50 mV and |Vds| = VDD
  Vth_elr_lin             max-gm linear extrapolation at |Vds| = 50 mV
                          (Vth = Vgs(gm_max) - Id/gm_max - Vds/2)
  SS_min                  minimum subthreshold swing at |Vds| = VDD (mV/dec)
  DIBL                    (Vth_cc_lin - Vth_cc_sat)/(VDD - 0.05) (mV/V)
  Ion                     |Id| at |Vgs| = |Vds| = VDD, per um of width
  Ioff                    |Id| at Vgs = 0, |Vds| = VDD, per um of width
  gm_max_sat, gds_on      transconductance max at |Vds|=VDD; output conductance at Vgs=Vds=VDD
  Cgg_on, Cgg_off         gate capacitance per um of width at |Vgs| = VDD and 0 (Vds = 0)

The constant-current and ELR definitions are standard extraction methods
(see e.g. Ortiz-Conde et al., Microelectronics Reliability 42 (2002) 583);
the numbers depend on the method and are reported with the method name.

Results are class F (circuit-simulated from foundry-supplied model cards).
Output: results/spice/device_params.csv and raw sweeps in results/spice/device_sweeps/.
"""
import argparse
import csv
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from ugcal.sim import ngspice as ng  # noqa: E402

I0 = 100e-9        # A, constant-current criterion per square (W/L)
VLIN = 0.05        # V


def sweep_deck(dev: str, w: float, l: float, corner: str, temp: float, vdd: float, pmos: bool) -> str:
    # NMOS: S=B=0, gate swept 0..VDD.  PMOS: S=B=VDD, gate swept VDD..0 expressed as |Vgs|.
    lines = [f"* {dev} sweep", ng.lib_line(corner), f".temp {temp}",
             ".options reltol=1e-6 abstol=1e-18 vntol=1e-9 gmin=1e-18",
             f"Vdd dd 0 {vdd}"]
    if not pmos:
        lines += ["Vg g 0 0", f"Vdl dl 0 {VLIN}", "Vds ds dd 0",
                  f"Xlin dl g 0 0 sky130_fd_pr__{dev} w={w} l={l}",
                  f"Xsat ds g 0 0 sky130_fd_pr__{dev} w={w} l={l}"]
        currents = "i(Vdl) i(Vds)"
    else:
        # gate voltage = VDD - Vgsabs ; drains at VDD-0.05 and 0
        lines += ["Vg gabs 0 0", "Eg g 0 dd gabs 1", f"Vdl dl 0 {vdd - VLIN}", "Vds ds 0 0",
                  f"Xlin dl g dd dd sky130_fd_pr__{dev} w={w} l={l}",
                  f"Xsat ds g dd dd sky130_fd_pr__{dev} w={w} l={l}"]
        currents = "i(Vdl) i(Vds)"
    lines += [f".dc Vg 0 {vdd} 0.005", ".control", "set wr_vecnames", "set wr_singlescale", "run",
              f"wrdata out.txt {currents}", ".endc", ".end"]
    return "\n".join(lines) + "\n"


def idvd_deck(dev: str, w: float, l: float, corner: str, temp: float, vdd: float, pmos: bool) -> str:
    """Output conductance at Vgs = Vds = VDD by a small Vds sweep around VDD."""
    if not pmos:
        body = ["Vg g 0 {vdd}".format(vdd=vdd), "Vd d 0 0", f"X1 d g 0 0 sky130_fd_pr__{dev} w={w} l={l}"]
        sweep = f".dc Vd {vdd - 0.1:.4f} {vdd:.4f} 0.01"
    else:
        body = [f"Vdd dd 0 {vdd}", "Vg g 0 0", "Vdabs dabs 0 0", "Ed d 0 dd dabs 1",
                f"X1 d g dd dd sky130_fd_pr__{dev} w={w} l={l}", "Vmeas d dm 0"]
        body = [f"Vdd dd 0 {vdd}", "Vg g 0 0", "Vd d 0 0", f"X1 d g dd dd sky130_fd_pr__{dev} w={w} l={l}"]
        sweep = f".dc Vd 0 0.1 0.01"
    lines = [f"* {dev} idvd", ng.lib_line(corner), f".temp {temp}", ".options reltol=1e-6"] + body + [
        sweep, ".control", "set wr_vecnames", "set wr_singlescale", "run", "wrdata out.txt i(Vd)", ".endc", ".end"]
    return "\n".join(lines) + "\n"


def cv_deck(dev: str, w: float, l: float, corner: str, temp: float, vdd: float, pmos: bool) -> str:
    """Quasi-static gate capacitance: slow gate ramp, Cgg = |Ig| / (dVg/dt), Vds = 0."""
    tr = 1e-6
    if not pmos:
        body = [f"Vg g 0 PWL(0 0 {tr} {vdd})", f"X1 0 g 0 0 sky130_fd_pr__{dev} w={w} l={l}"]
    else:
        body = [f"Vdd dd 0 {vdd}", f"Vg g 0 PWL(0 {vdd} {tr} 0)", f"X1 dd g dd dd sky130_fd_pr__{dev} w={w} l={l}"]
    lines = [f"* {dev} cv", ng.lib_line(corner), f".temp {temp}", ".options reltol=1e-6 abstol=1e-18"] + body + [
        f".tran {tr / 400} {tr}", ".control", "set wr_vecnames", "set wr_singlescale", "run",
        "wrdata out.txt v(g) i(Vg)", ".endc", ".end"]
    return "\n".join(lines) + "\n"


def extract(vg, i_lin, i_sat, w, l, vdd):
    vg = np.asarray(vg)
    il = np.abs(np.asarray(i_lin))
    isat = np.abs(np.asarray(i_sat))
    icrit = I0 * w / l

    def vth_cc(i):
        idx = np.where(i >= icrit)[0]
        if len(idx) == 0 or idx[0] == 0:
            return math.nan
        k = idx[0]
        # log-linear interpolation
        x0, x1 = vg[k - 1], vg[k]
        y0, y1 = math.log10(i[k - 1]), math.log10(i[k])
        return x0 + (math.log10(icrit) - y0) * (x1 - x0) / (y1 - y0)

    vth_lin = vth_cc(il)
    vth_sat = vth_cc(isat)
    gm = np.gradient(il, vg)
    k = int(np.argmax(gm))
    vth_elr = vg[k] - il[k] / gm[k] - VLIN / 2
    # subthreshold swing on the saturation curve, below icrit/10 and above 1e3*floor
    logi = np.log10(np.maximum(isat, 1e-30))
    ss = np.gradient(vg, logi) * 1e3  # mV/dec
    floor = isat[0]
    mask = (isat < icrit / 10) & (isat > max(floor * 10, 1e-15)) & np.isfinite(ss) & (ss > 0)
    ss_min = float(np.min(ss[mask])) if mask.any() else math.nan
    gm_sat = np.gradient(isat, vg)
    return dict(
        Vth_cc_lin_V=vth_lin, Vth_cc_sat_V=vth_sat, Vth_elr_lin_V=float(vth_elr),
        SS_min_mV_dec=ss_min,
        DIBL_mV_V=(vth_lin - vth_sat) / (vdd - VLIN) * 1e3,
        Ion_uA_um=float(isat[-1]) / w * 1e6, Ioff_pA_um=float(isat[0]) / w * 1e12,
        Ion_Ioff=float(isat[-1] / isat[0]),
        gm_max_sat_uS_um=float(np.max(gm_sat)) / w * 1e6,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    devices = [("nfet_01v8", False), ("pfet_01v8_hvt", True), ("nfet_01v8_lvt", False), ("pfet_01v8", True)]
    geoms = [(1.0, 0.15), (0.65, 0.15), (0.42, 0.15), (1.0, 0.5)]
    conds = [("tt", 25, 1.8), ("tt", -40, 1.8), ("tt", 100, 1.8), ("ss", 100, 1.6), ("ff", -40, 1.95),
             ("ss", -40, 1.6), ("ff", 100, 1.95), ("sf", 25, 1.8), ("fs", 25, 1.8),
             ("tt", 25, 1.2), ("tt", 25, 0.9), ("tt_leak", 25, 1.8), ("leak", 25, 1.8)]
    if a.quick:
        devices = devices[:2]
        geoms = geoms[:1]
        conds = conds[:3]
    outdir = os.path.join(ng.repo_root(), "results", "spice")
    rawdir = os.path.join(outdir, "device_sweeps")
    os.makedirs(rawdir, exist_ok=True)
    rows = []
    for dev, pmos in devices:
        for (w, l) in geoms:
            for corner, temp, vdd in conds:
                if corner == "tt_leak" and dev == "pfet_01v8":
                    continue  # not present in corners/tt/leak.spice
                r = ng.run(sweep_deck(dev, w, l, corner, temp, vdd, pmos), ["out.txt"])
                v = r.vectors
                vg = v["v-sweep"] if "v-sweep" in v else v[list(v.keys())[0]]
                il, isat = v["i(vdl)"], v["i(vds)"]
                ex = extract(vg, il, isat, w, l, vdd)
                # output conductance
                rd = ng.run(idvd_deck(dev, w, l, corner, temp, vdd, pmos), ["out.txt"]).vectors
                vd = rd[list(rd.keys())[0]]
                idd = np.abs(rd["i(vd)"])
                gds = abs(float(np.polyfit(vd, idd, 1)[0]))
                # C-V
                rc = ng.run(cv_deck(dev, w, l, corner, temp, vdd, pmos), ["out.txt"]).vectors
                t = np.asarray(rc["time"])
                ig = np.abs(np.asarray(rc["i(vg)"]))
                dvdt = vdd / 1e-6
                cgg = ig / dvdt
                # Cgg at |Vgs| = VDD (end) and 0 (start); avoid ramp corners
                n = len(t)
                c_on = float(np.median(cgg[int(0.97 * n):int(0.995 * n)]))
                c_off = float(np.median(cgg[int(0.005 * n):int(0.03 * n)]))
                row = dict(device=dev, W_um=w, L_um=l, corner=corner, T_C=temp, VDD_V=vdd, **ex,
                           gds_on_uS_um=gds / w * 1e6, Cgg_on_fF_um=c_on / w * 1e15,
                           Cgg_off_fF_um=c_off / w * 1e15,
                           intrinsic_CV_over_I_ps=(c_on * vdd / (ex["Ion_uA_um"] * 1e-6 * w)) * 1e12)
                rows.append(row)
                print(", ".join(f"{k}={v:.4g}" if isinstance(v, float) else f"{k}={v}" for k, v in row.items()),
                      flush=True)
                if (w, l) == (1.0, 0.15) and corner in ("tt",) and vdd == 1.8:
                    with open(os.path.join(rawdir, f"{dev}_W1_L0p15_{corner}_{temp}C_{vdd}V.csv"), "w",
                              newline="") as fh:
                        wr = csv.writer(fh)
                        wr.writerow(["Vgs_abs_V", "Id_lin_abs_A", "Id_sat_abs_A"])
                        for x, y1, y2 in zip(vg, il, isat):
                            wr.writerow([f"{x:.4f}", f"{abs(y1):.6e}", f"{abs(y2):.6e}"])
    with open(os.path.join(outdir, "device_params.csv"), "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
        fh.write(f"# ngspice {ng.ngspice_version()}; I0={I0} A per square; VLIN={VLIN} V\n")


if __name__ == "__main__":
    main()
