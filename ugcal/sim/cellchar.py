"""Transistor-level characterisation of sky130_fd_sc_hd cells with ngspice.

The functions here build test benches around the foundry cell netlists
(``cells/<cell>/sky130_fd_sc_hd__<cell>.spice``) and the SKY130 BSIM4 model
cards, run them, and post-process the waveforms in Python:

  * propagation delay at the 50 % points (Liberty ``input/output_threshold_pct``)
  * output transition between the 20 % and 80 % points (Liberty slew thresholds,
    ``slew_derate_from_library`` = 1)
  * energy drawn from each supply/input source, by trapezoidal integration of
    V * I over a window
  * static (leakage) power per input state from a DC operating point

Input ramps are linear with a 20-80 % time equal to the requested slew, i.e.
a 0-100 % time of slew / 0.6, which corresponds to the ``driver_model: "ramp"``
declared in the SKY130 Liberty header.

All results are class F (circuit-simulated) evidence: they depend on the model
cards, the test bench, the simulator and its tolerances, which are recorded.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import ngspice as ng

SIM_OPTIONS = ".options reltol=1e-4 abstol=1e-15 vntol=1e-7"
# DC leakage needs a much smaller GMIN than ngspice's default 1e-12 S: the
# default conductance across every pn junction alone injects ~1.8 pA at 1.8 V,
# more than the real off-current of a minimum-size SKY130 device at 25 C.
LEAK_OPTIONS = ".options reltol=1e-6 abstol=1e-20 vntol=1e-9 gmin=1e-20"


@dataclass
class Edge:
    pin: str
    t0: float          # start of 0-100 % ramp (s)
    rising: bool
    slew: float        # 20-80 % time (s)

    @property
    def full(self) -> float:
        return self.slew / 0.6


def pwl(v_init: float, vdd: float, edges: Sequence[Edge]) -> str:
    pts = [(0.0, v_init)]
    v = v_init
    for e in sorted(edges, key=lambda e: e.t0):
        v_new = vdd if e.rising else 0.0
        pts.append((e.t0, v))
        pts.append((e.t0 + e.full, v_new))
        v = v_new
    return "PWL(" + " ".join(f"{t:.6e} {vv:.6g}" for t, vv in pts) + ")"


def cell_pins(cell: str) -> List[str]:
    with open(ng.cell_netlist(cell)) as fh:
        for line in fh:
            if line.lower().startswith(".subckt"):
                return line.split()[2:]
    raise ValueError(cell)


@dataclass
class Bench:
    cell: str
    vdd: float
    temp_c: float
    corner: str = "tt"
    inputs: Dict[str, str] = field(default_factory=dict)       # pin -> source spec (DC value or PWL(...))
    loads: Dict[str, float] = field(default_factory=dict)      # output pin -> load cap (F)
    tstop: float = 0.0
    tstep: float = 1e-12
    full_lib: bool = False

    def deck(self, save: Sequence[str]) -> str:
        pins = cell_pins(self.cell)
        nodes = []
        for p in pins:
            if p in ("VPWR", "VPB"):
                nodes.append("vpwr" if p == "VPWR" else "vpb")
            elif p in ("VGND", "VNB"):
                nodes.append("0" if p == "VNB" else "vgnd")
            else:
                nodes.append(p.lower())
        lines = [f"* {self.cell} bench", ng.lib_line(self.corner, self.full_lib),
                 f'.include "{ng.cell_netlist(self.cell)}"', f".temp {self.temp_c}", SIM_OPTIONS,
                 f"Vvdd vpwr 0 {self.vdd}", f"Vvpb vpb 0 {self.vdd}", "Vvgnd vgnd 0 0",
                 f"X1 {' '.join(nodes)} sky130_fd_sc_hd__{self.cell}"]
        for pin, spec in self.inputs.items():
            lines.append(f"Vin_{pin.lower()} {pin.lower()} 0 {spec}")
        for pin, c in self.loads.items():
            lines.append(f"Cload_{pin.lower()} {pin.lower()} 0 {c:.6e}")
        lines += [f".tran {self.tstep:.3e} {self.tstop:.6e}", ".control", "set wr_vecnames",
                  "set wr_singlescale", "run", f"wrdata out.txt {' '.join(save)}", ".endc", ".end"]
        return "\n".join(lines) + "\n"

    def run(self, save: Sequence[str]) -> Dict[str, List[float]]:
        return ng.run(self.deck(save), ["out.txt"]).vectors


# ---------------------------------------------------------------------------
# waveform post-processing
# ---------------------------------------------------------------------------

def crossing(t: Sequence[float], v: Sequence[float], level: float, rising: bool,
             after: float = 0.0) -> float:
    """Time of the first crossing of `level` in the given direction after `after`."""
    for i in range(1, len(t)):
        if t[i] < after:
            continue
        a, b = v[i - 1], v[i]
        if rising and a < level <= b or (not rising) and a > level >= b:
            return t[i - 1] + (level - a) * (t[i] - t[i - 1]) / (b - a)
    return math.nan


def integrate(t: Sequence[float], y: Sequence[float], t0: float, t1: float) -> float:
    """Trapezoidal integral of y dt over [t0, t1] with linear interpolation at the ends."""
    def at(tt):
        for i in range(1, len(t)):
            if t[i] >= tt:
                f = (tt - t[i - 1]) / (t[i] - t[i - 1]) if t[i] > t[i - 1] else 0.0
                return y[i - 1] + f * (y[i] - y[i - 1])
        return y[-1]
    pts = [(t0, at(t0))] + [(ti, yi) for ti, yi in zip(t, y) if t0 < ti < t1] + [(t1, at(t1))]
    s = 0.0
    for (ta, ya), (tb, yb) in zip(pts, pts[1:]):
        s += 0.5 * (ya + yb) * (tb - ta)
    return s


def static_power(cell: str, vdd: float, temp_c: float, corner: str, state: Dict[str, float],
                 full_lib: bool = False) -> float:
    """Total DC power drawn from VPWR and VPB (W) for a fixed input state.

    Gate leakage of the driven inputs is not included because the BSIM4 cards
    of nfet_01v8/pfet_01v8_hvt have igcmod = igbmod = 0 (no gate tunnelling
    model), so it would be zero anyway; junction leakage to the wells is
    included through VPB / VGND.
    """
    pins = cell_pins(cell)
    nodes = []
    for p in pins:
        nodes.append({"VPWR": "vpwr", "VPB": "vpb", "VGND": "0", "VNB": "0"}.get(p, p.lower()))
    lines = [f"* {cell} leakage", ng.lib_line(corner, full_lib), f'.include "{ng.cell_netlist(cell)}"',
             f".temp {temp_c}", LEAK_OPTIONS, f"Vvdd vpwr 0 {vdd}", f"Vvpb vpb 0 {vdd}",
             f"X1 {' '.join(nodes)} sky130_fd_sc_hd__{cell}"]
    for pin, v in state.items():
        lines.append(f"Vin_{pin.lower()} {pin.lower()} 0 {v}")
    lines += [".op", ".control", "run", "print i(Vvdd) i(Vvpb)", ".endc", ".end"]
    r = ng.run("\n".join(lines) + "\n")
    i_vdd = r.measures.get("i(vvdd)")
    i_vpb = r.measures.get("i(vvpb)")
    if i_vdd is None or i_vpb is None:
        raise ng.NgspiceError("operating point currents not found:\n" + r.stdout[-2000:])
    return -vdd * (i_vdd + i_vpb)
