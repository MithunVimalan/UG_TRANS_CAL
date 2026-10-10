"""Transistor-level (ngspice) simulation of a whole gate-level netlist.

Every gate of a ugcal Netlist is instantiated as its sky130_fd_sc_hd cell
subcircuit (schematic or layout-extracted view, see ngspice.CELL_VIEW) on the
SKY130 BSIM4 model cards.  Primary inputs are ideal PWL sources with linear
ramps (20-80 % time = in_slew); outputs drive ideal capacitors.  Energy per
cycle is the integral of V_DD * I over each clock period of the current drawn
from VPWR and VPB (the n-well), i.e. the energy delivered by the supply.

Energy supplied by the ideal input sources (charging the input-pin
capacitance of the first gates) is not drawn from VPWR; it is reported
separately so that comparisons with gate-level power use the same boundary.
"""
from __future__ import annotations

import os
from typing import Dict, List, Sequence

from ..arith.netlist import CONST0, CONST1, Netlist
from ..arith.verilog import CELLMAP, PREFIX, cellinfo
from . import ngspice as ng
from .cellchar import SIM_OPTIONS, crossing, integrate


def _pins_of(cell: str) -> List[str]:
    with open(ng.cell_netlist(cell)) as fh:
        for line in fh:
            if line.lower().startswith(".subckt"):
                return line.split()[2:]
    raise ValueError(cell)


def deck(nl: Netlist, vectors: Sequence[Dict[str, int]], period: float, vdd: float, temp_c: float,
         corner: str = "tt", out_load: float = 5e-15, in_slew: float = 50e-12, tstep: float = 10e-12,
         options: str = ".options reltol=5e-4 abstol=1e-13 vntol=1e-6") -> str:
    cells = sorted({cellinfo(g)[0] for g in nl.gates})
    if any(g.kind == "DFF" for g in nl.gates):
        raise NotImplementedError("sequential netlists: use the registered testbench (not implemented)")
    lines = [f"* {nl.name} transistor-level", ng.lib_line(corner), f".temp {temp_c}", options]
    for c in cells:
        lines.append(f'.include "{ng.cell_netlist(c)}"')
    lines += [f"Vvdd vpwr 0 {vdd}", f"Vvpb vpb 0 {vdd}", "Vhi hi 0 {vdd}".format(vdd=vdd)]

    def node(n: int) -> str:
        if n == CONST0:
            return "0"
        if n == CONST1:
            return "hi"
        return f"n{n}"

    for g in nl.gates:
        cell, ip, op = cellinfo(g)
        pins = _pins_of(cell)
        conn = {"VPWR": "vpwr", "VPB": "vpb", "VGND": "0", "VNB": "0"}
        for p, n in zip(ip, g.ins):
            conn[p] = node(n)
        for p, n in zip(op, g.outs):
            conn[p] = node(n)
        lines.append(f"X{g.name} " + " ".join(conn[p] for p in pins) + f" {PREFIX}{cell}")
    full = in_slew / 0.6
    for bus, nets in nl.inputs.items():
        for i, n in enumerate(nets):
            pts = []
            prev = (vectors[0][bus] >> i) & 1
            pts.append((0.0, prev * vdd))
            for k in range(1, len(vectors)):
                cur = (vectors[k][bus] >> i) & 1
                if cur != prev:
                    t0 = k * period
                    pts.append((t0, prev * vdd))
                    pts.append((t0 + full, cur * vdd))
                prev = cur
            pwl = " ".join(f"{t:.6e} {v:.4g}" for t, v in pts)
            lines.append(f"Vin_{bus}_{i} {node(n)} 0 PWL({pwl})")
    for nets in nl.outputs.values():
        for n in nets:
            if n not in (CONST0, CONST1):
                lines.append(f"Cload_{n} {node(n)} 0 {out_load:.4e}")
    tstop = len(vectors) * period
    in_srcs = " ".join(f"i(Vin_{bus}_{i})" for bus, nets in nl.inputs.items() for i in range(len(nets)))
    outs = " ".join(f"v({node(n)})" for nets in nl.outputs.values() for n in nets if n not in (CONST0, CONST1))
    # save only what is post-processed (all-node storage costs GBs of memory)
    lines.append(f".save i(Vvdd) i(Vvpb) {in_srcs} {outs}")
    lines += [f".tran {tstep:.3e} {tstop:.6e}", ".control", "set wr_vecnames", "set wr_singlescale", "run",
              f"wrdata sup.txt i(Vvdd) i(Vvpb)", f"wrdata inp.txt {in_srcs}", f"wrdata out.txt {outs}",
              ".endc", ".end"]
    return "\n".join(lines) + "\n"


def run(nl: Netlist, vectors: Sequence[Dict[str, int]], period: float, vdd: float, temp_c: float,
        corner: str = "tt", out_load: float = 5e-15, in_slew: float = 50e-12, keep_dir: str = None,
        **kw) -> Dict[str, object]:
    d = deck(nl, vectors, period, vdd, temp_c, corner, out_load, in_slew, **kw)
    r = ng.run(d, ["sup.txt", "inp.txt", "out.txt"], timeout=24 * 3600, keep_dir=keep_dir)
    v = r.vectors
    t = v["sup.txt:time"]
    p = [-vdd * (a + b) for a, b in zip(v["sup.txt:i(vvdd)"], v["sup.txt:i(vvpb)"])]
    ti = v["inp.txt:time"]
    pin = [0.0] * len(ti)
    for k, val in v.items():
        if k.startswith("inp.txt:i("):
            for j, x in enumerate(val):
                pin[j] += -vdd * x  # power delivered by input sources (approx: source at vdd level)
    per_cycle = []
    per_cycle_in = []
    for k in range(1, len(vectors)):
        t0 = k * period
        per_cycle.append(integrate(t, p, t0, t0 + period))
        per_cycle_in.append(integrate(ti, pin, t0, t0 + period))
    # functional check: sample outputs at end of each cycle
    to = v["out.txt:time"]
    outs = [n for nets in nl.outputs.values() for n in nets if n not in (CONST0, CONST1)]
    samples = []
    for k in range(len(vectors)):
        tk = (k + 1) * period - 0.02 * period
        idx = min(range(len(to)), key=lambda j: abs(to[j] - tk))
        bits = {n: 1 if v[f"out.txt:v(n{n})"][idx] > vdd / 2 else 0 for n in outs}
        samples.append(bits)
    return dict(E_cycle=per_cycle, E_in_cycle=per_cycle_in, wall_s=r.wall_s, ngspice=r.version,
                samples=samples, n_transistors=None)
