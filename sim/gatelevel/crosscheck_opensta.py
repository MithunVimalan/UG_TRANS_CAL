#!/usr/bin/env python3
"""Cross-check ugcal.gatesim (timing and power) against OpenSTA.

For each design: the structural netlist is emitted as sky130 Verilog, the
Python event-driven simulator produces a value-change trace, the trace is
written as a VCD, and OpenSTA (pinned build) reads the same netlist, Liberty
corner and VCD and reports power and the worst path.  Agreement checks:

  * power: same activity, same Liberty data -> totals should agree closely;
    differences come from OpenSTA's averaging of rise/fall internal energy
    and its sensitisation weighting vs. per-event attribution here, and from
    input-port nets (OpenSTA does not charge switching power on nets driven
    by top-level inputs; ugcal reports that separately).
  * timing: worst combinational path vs report_checks.

Output: results/power/crosscheck_opensta.csv
"""
import csv
import json
import os
import random
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from ugcal.arith.multipliers import build  # noqa: E402
from ugcal.arith.mac import build_mac  # noqa: E402
from ugcal.arith.verilog import emit  # noqa: E402
from ugcal.gatesim import GateLevel  # noqa: E402
from ugcal.liberty import Library  # noqa: E402
from ugcal.sim.ngspice import pdk_root, repo_root  # noqa: E402

LIB = os.path.join(pdk_root(), "sc_hd", "timing", "sky130_fd_sc_hd__tt_025C_1v80.lib")


def run_sta(verilog, top, vcd, period_ns, begin_ps, has_clk, out_load_pf=0.005, in_tr_ns=0.05):
    work = tempfile.mkdtemp(prefix="ugcal_sta_")
    vpath = os.path.join(work, "d.v")
    with open(vpath, "w") as fh:
        fh.write(verilog)
    clk = f"create_clock -name clk -period {period_ns} [get_ports clk]" if has_clk else \
        f"create_clock -name vclk -period {period_ns}"
    io = "" if has_clk else ("set_input_delay 0 -clock vclk [all_inputs]\n"
                             "set_output_delay 0 -clock vclk [all_outputs]")
    tcl = f"""
read_liberty {LIB}
read_verilog {vpath}
link_design {top}
{clk}
{io}
set_load {out_load_pf} [all_outputs]
set_input_transition {in_tr_ns} [all_inputs]
read_vcd -scope tb/dut -begin_time {begin_ps} {vcd}
report_power -digits 8 -format json
report_checks -path_delay max -digits 4 -format end
report_checks -path_delay max -digits 4
"""
    tpath = os.path.join(work, "run.tcl")
    with open(tpath, "w") as fh:
        fh.write(tcl)
    out = subprocess.run(["sta", "-no_init", "-exit", tpath], capture_output=True, text=True).stdout
    m = re.search(r"\{.*?\"total\".*?\}\s*\}", out, re.S)
    js = None
    jm = re.search(r"(\{\s*\"Sequential\".*?\n\})", out, re.S)
    if jm:
        js = json.loads(jm.group(1))
    arr = re.findall(r"^\s*([-0-9.]+)\s+data arrival time", out, re.M)
    return out, js, (float(arr[0]) if arr else None)


def main():
    lib = Library(LIB)
    random.seed(2026)
    nvec = 401
    period = 20e-9
    designs = [("mul8_array_rc", lambda: build("array_rc", 8, signed=False)),
               ("mul8_braun", lambda: build("braun", 8, signed=False)),
               ("mul8_dadda_rca", lambda: build("dadda_rca", 8, signed=False)),
               ("mul8_wallace_rca", lambda: build("wallace_rca", 8, signed=False)),
               ("mul8_dadda_ks", lambda: build("dadda_ks", 8, signed=False)),
               ("mul8_booth4_dadda_ks", lambda: build("booth4_dadda_ks", 8, signed=True)),
               ("mac8_w22_separate", lambda: build_mac(8, 22, "separate")),
               ("mac8_w22_csa_acc", lambda: build_mac(8, 22, "csa_acc"))]
    rows = []
    outdir = os.path.join(repo_root(), "results", "power")
    os.makedirs(outdir, exist_ok=True)
    for name, fn in designs:
        nl = fn()
        has_clk = any(g.kind == "DFF" for g in nl.gates)
        vecs = []
        for i in range(nvec):
            v = {"a": random.randrange(256), "b": random.randrange(256)}
            if "clr" in nl.inputs:
                v["clr"] = 1 if i % 64 == 0 else 0
            vecs.append(v)
        gl = GateLevel(nl, lib, out_load_F=5e-15, in_slew_s=50e-12)
        sta_py = gl.sta()
        for mode in ("zero", "inertial"):
            r = gl.simulate(vecs, period, mode, trace=True)
            p = r.power()
            work = tempfile.mkdtemp(prefix="ugcal_vcd_")
            vcd = os.path.join(work, "d.vcd")
            r.write_vcd(vcd)
            out, js, arrival = run_sta(emit(nl, "dut_top"), "dut_top", vcd, period * 1e9,
                                       int(round(period * 1e12)), has_clk)
            if js is None:
                print(out[-3000:])
                raise SystemExit(f"OpenSTA power JSON not found for {name}")
            tot = js["Total"]
            T = r.T
            py_int = p["totals"]["internal_J"] / T
            py_sw = (p["totals"]["switching_J"] - p["switching_inputs_J"]) / T
            py_leak = p["totals"]["leakage_J"] / T
            row = dict(design=name, mode=mode, cycles=r.cycles,
                       py_internal_W=py_int, sta_internal_W=tot["internal"],
                       py_switching_W=py_sw, sta_switching_W=tot["switching"],
                       py_switching_input_nets_W=p["switching_inputs_J"] / T,
                       py_leakage_W=py_leak, sta_leakage_W=tot["leakage"],
                       py_total_W=py_int + py_sw + py_leak, sta_total_W=tot["total"],
                       ratio_total=(py_int + py_sw + py_leak) / tot["total"],
                       py_worst_path_ns=sta_py["delay_s"] * 1e9, sta_worst_arrival_ns=arrival)
            rows.append(row)
            print(f"{name:22s} {mode:8s} total py {row['py_total_W']*1e6:9.3f} uW  sta {tot['total']*1e6:9.3f} uW"
                  f"  ratio {row['ratio_total']:.4f} | int {py_int*1e6:.3f}/{tot['internal']*1e6:.3f}"
                  f" sw {py_sw*1e6:.3f}/{tot['switching']*1e6:.3f} leak {py_leak*1e9:.3f}/{tot['leakage']*1e9:.3f} nW"
                  f" | path py {row['py_worst_path_ns']:.3f} sta {arrival}", flush=True)
    with open(os.path.join(outdir, "crosscheck_opensta.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
