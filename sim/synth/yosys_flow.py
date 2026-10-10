#!/usr/bin/env python3
"""Synthesise behavioural multipliers with Yosys/ABC onto sky130_fd_sc_hd.

The hand-built architectures in ugcal.arith fix the algorithm and the cells.
A synthesis tool given ``p = a * b`` chooses its own structure (Yosys maps
$mul to a shift-and-add array and ABC re-optimises it for the target).  This
script produces those netlists so the two can be compared on the same
library, corner, load and stimulus.

Flow (Yosys 0.33, as installed): read_verilog; synth -flatten; abc -liberty
<filtered lib> [-D target_ps]; opt_clean -purge; setundef -zero; stat;
write_verilog.  The Liberty file is filtered with LibreLane's
sky130_fd_sc_hd synth_excluded.cells list (clock/delay buffers, lpflow,
scan, probe, physical-only cells) because Yosys 0.33 abc has no dont_use.

Output: results/synth/<name>.v, results/synth/<name>_stat.txt
"""
import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from ugcal.liberty import write_filtered  # noqa: E402
from ugcal.sim.ngspice import pdk_root, repo_root  # noqa: E402

EXCLUDE = ["sky130_fd_sc_hd__clkbuf*", "sky130_fd_sc_hd__clkinv*", "sky130_fd_sc_hd__clkinvlp*",
           "sky130_fd_sc_hd__clkdlybuf*", "sky130_fd_sc_hd__dlygate*", "sky130_fd_sc_hd__dlymetal*",
           "sky130_fd_sc_hd__tap*", "sky130_fd_sc_hd__decap*", "sky130_fd_sc_hd__fill*",
           "sky130_fd_sc_hd__diode*", "sky130_fd_sc_hd__lpflow_*", "sky130_fd_sc_hd__macro_sparecell",
           "sky130_fd_sc_hd__probe*", "sky130_fd_sc_hd__s*"]

RTL = {
    "mul8u": "module mul8u (input [7:0] a, input [7:0] b, output [15:0] p);\n  assign p = a * b;\nendmodule\n",
    "mul8s": "module mul8s (input signed [7:0] a, input signed [7:0] b, output signed [15:0] p);\n"
             "  assign p = a * b;\nendmodule\n",
    "mul16u": "module mul16u (input [15:0] a, input [15:0] b, output [31:0] p);\n  assign p = a * b;\nendmodule\n",
}


def filtered_lib(corner: str = "tt_025C_1v80") -> str:
    src = os.path.join(pdk_root(), "sc_hd", "timing", f"sky130_fd_sc_hd__{corner}.lib")
    dst = os.path.join(repo_root(), "build", f"sky130_fd_sc_hd__{corner}.synth.lib")
    if not os.path.exists(dst):
        n = write_filtered(src, dst, EXCLUDE)
        print(f"filtered {n} cells -> {dst}")
    return dst


def synth(top: str, rtl: str, target_ps: int = None, tag: str = "") -> str:
    lib = filtered_lib()
    outdir = os.path.join(repo_root(), "results", "synth")
    os.makedirs(outdir, exist_ok=True)
    name = f"{top}_abc{'D' + str(target_ps) if target_ps else 'area'}{tag}"
    src = os.path.join(outdir, f"{top}_rtl.v")
    with open(src, "w") as fh:
        fh.write(rtl)
    abc = f"abc -liberty {lib}" + (f" -D {target_ps}" if target_ps else "")
    script = (f"read_verilog {src}; synth -top {top} -flatten; {abc}; opt_clean -purge; setundef -zero; "
              f"opt_clean; tee -o {os.path.join(outdir, name + '_stat.txt')} stat -liberty {lib}; "
              f"write_verilog -noattr -noexpr -nohex -nodec {os.path.join(outdir, name + '.v')}")
    r = subprocess.run(["yosys", "-q", "-p", script], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(r.stdout[-3000:] + r.stderr[-3000:])
    ver = subprocess.run(["yosys", "-V"], capture_output=True, text=True).stdout.strip()
    with open(os.path.join(outdir, name + "_stat.txt"), "a") as fh:
        fh.write(f"\n# {ver}\n# script: {script}\n")
    return os.path.join(outdir, name + ".v")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", default="none,1000,3000")
    a = ap.parse_args()
    for top, rtl in RTL.items():
        for t in a.targets.split(","):
            path = synth(top, rtl, None if t == "none" else int(t))
            stat = open(path.replace(".v", "_stat.txt")).read()
            area = re.search(r"Chip area for module .*?: ([0-9.]+)", stat)
            ncell = re.search(r"Number of cells:\s+(\d+)", stat)
            print(f"{os.path.basename(path)}: cells {ncell.group(1) if ncell else '?'}, "
                  f"area {area.group(1) if area else '?'} um^2")


if __name__ == "__main__":
    main()
