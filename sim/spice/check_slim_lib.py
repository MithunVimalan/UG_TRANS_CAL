#!/usr/bin/env python3
"""Check that the reduced model library reproduces the full SKY130 library.

For each corner, drain currents of nfet_01v8 and pfet_01v8_hvt are computed
on a grid of gate voltages and geometries with both libraries.  The script
fails if any relative difference exceeds 1e-9 (i.e. the two must be
numerically identical apart from print rounding).

Output: results/spice/slim_lib_check.csv
"""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from ugcal.sim import ngspice as ng  # noqa: E402

GEOMS = [(0.42, 0.15), (0.65, 0.15), (1.0, 0.15), (7.0, 0.15), (1.0, 1.0)]


def deck(lib_line: str, corner: str) -> str:
    lines = ["* slim vs full", lib_line, ".temp 25", "Vdd dd 0 1.8", "Vg g 0 0"]
    for i, (w, l) in enumerate(GEOMS):
        lines.append(f"Vdn{i} dd dn{i} 0")
        lines.append(f"Xn{i} dn{i} g 0 0 sky130_fd_pr__nfet_01v8 w={w} l={l}")
        lines.append(f"Vdp{i} sp{i} dp{i} 0")
        lines.append(f"Xp{i} 0 gp sp{i} dd sky130_fd_pr__pfet_01v8_hvt w={w} l={l}")
        lines.append(f"Vsp{i} dd sp{i} 0")
    lines.append("Egp gp 0 dd g 1")  # pfet sees Vsg = Vg
    vecs = " ".join([f"i(Vdn{i}) i(Vsp{i})" for i in range(len(GEOMS))])
    lines += [".dc Vg 0 1.8 0.1", ".control", "set wr_vecnames", "set wr_singlescale",
              "run", f"wrdata out.txt {vecs}", ".endc", ".end"]
    return "\n".join(lines) + "\n"


def main() -> int:
    out_rows = []
    worst = 0.0
    for corner in ("tt", "ss", "ff", "sf", "fs"):
        r_full = ng.run(deck(ng.lib_line(corner, full=True), corner), ["out.txt"])
        r_slim = ng.run(deck(ng.lib_line(corner, full=False), corner), ["out.txt"])
        for name, vf in r_full.vectors.items():
            vs = r_slim.vectors[name]
            for a, b in zip(vf, vs):
                denom = max(abs(a), 1e-30)
                rel = abs(a - b) / denom
                worst = max(worst, rel)
        out_rows.append((corner, r_full.wall_s, r_slim.wall_s, worst))
        print(f"{corner}: full {r_full.wall_s:.1f} s, slim {r_slim.wall_s:.1f} s, worst rel diff so far {worst:.3e}")
    os.makedirs(os.path.join(ng.repo_root(), "results", "spice"), exist_ok=True)
    with open(os.path.join(ng.repo_root(), "results", "spice", "slim_lib_check.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["corner", "full_lib_wall_s", "slim_lib_wall_s", "worst_rel_diff_cumulative"])
        w.writerows(out_rows)
        fh.write(f"# ngspice {ng.ngspice_version()}\n")
    if worst > 1e-9:
        print("FAIL: reduced library differs from full library")
        return 1
    print("PASS: reduced library reproduces full library")
    return 0


if __name__ == "__main__":
    sys.exit(main())
