"""Gate-level static timing, event-driven timing simulation and power.

Why this module exists
----------------------
The usual open-source route to glitch-aware switching activity (Icarus
Verilog + SDF from OpenSTA + the sky130 ``*.timing.v`` cell models) silently
produces zero-delay simulation: the sky130 timing models describe their delay
paths as state-dependent specify paths (``if (!B&CIN) (A +=> COUT) = ...``),
OpenSTA writes unconditional IOPATH entries, and Icarus 12 does not apply them
(verified in this project: outputs switch at the input edge).  This module
therefore computes delays directly from the Liberty NLDM tables and runs its
own event-driven simulation.

Models and approximations (all explicit)
----------------------------------------
* Net load = sum of Liberty input-pin capacitances of the fanout (+ optional
  wire capacitance from the Liberty wire-load model, + explicit output loads).
* Pin slews are propagated statically (worst of rise/fall transition of the
  driver at its actual load and worst input slew), as in a block-based STA
  without slew merging per edge.  Delays per arc and output edge are looked up
  at that slew and load; they do not vary event by event.
* Arcs with several ``when`` conditions: the maximum over conditions is used
  for STA, the mean for simulation.
* Delay semantics:
    'inertial'  a pending output change is cancelled if the gate re-evaluates
                to the opposite value before it matures (pulses shorter than
                the gate delay are filtered) - lower glitch estimate;
    'transport' every evaluation change propagates - upper glitch estimate;
    'zero'      settled values only (functional activity, no glitches).
* Power follows the OpenSTA decomposition (Power.cc at the pinned commit):
    switching = 1/2 C_net V^2 per transition of the net,
    internal  = Liberty internal_power entry of the arc that caused each output
                transition (rise_power or fall_power at the pin slew and load),
                plus input-pin internal_power (flip-flop CLK/D) per transition,
    leakage   = Liberty leakage_power(when) weighted by the time each instance
                spends in each input state (sampled once per cycle).
  Liberty internal_power already includes short-circuit current; nothing is
  added for it.
"""
from __future__ import annotations

import heapq
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .arith.netlist import CONST0, CONST1, Netlist
from .arith.verilog import CELLMAP, PREFIX, cellinfo
from .liberty import Library

# ---------------------------------------------------------------------------
# Boolean expression evaluation for Liberty 'function' / 'when' strings
# ---------------------------------------------------------------------------
_TOK = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_\[\]]*|[!&|^()'*+]|1|0)")


def compile_expr(expr: str) -> Callable[[Dict[str, int]], int]:
    toks = [t for t in _TOK.findall(expr) if t]
    pos = 0

    def peek():
        return toks[pos] if pos < len(toks) else None

    def take():
        nonlocal pos
        t = toks[pos]
        pos += 1
        return t

    def p_or():
        f = p_xor()
        while peek() in ("|", "+"):
            take()
            g = p_xor()
            f = (lambda f, g: lambda e: f(e) | g(e))(f, g)
        return f

    def p_xor():
        f = p_and()
        while peek() == "^":
            take()
            g = p_and()
            f = (lambda f, g: lambda e: f(e) ^ g(e))(f, g)
        return f

    def p_and():
        f = p_not()
        while peek() in ("&", "*") or (peek() is not None and peek() not in ("|", "+", "^", ")")):
            if peek() in ("&", "*"):
                take()
            g = p_not()
            f = (lambda f, g: lambda e: f(e) & g(e))(f, g)
        return f

    def p_not():
        if peek() == "!":
            take()
            f = p_not()
            return lambda e: 1 - f(e)
        f = p_atom()
        while peek() == "'":
            take()
            f = (lambda f: lambda e: 1 - f(e))(f)
        return f

    def p_atom():
        t = take()
        if t == "(":
            f = p_or()
            if take() != ")":
                raise ValueError(expr)
            return f
        if t == "1":
            return lambda e: 1
        if t == "0":
            return lambda e: 0
        return lambda e, t=t: e[t]

    f = p_or()
    if pos != len(toks):
        raise ValueError(f"trailing tokens in {expr!r}")
    return f


# ---------------------------------------------------------------------------
# Netlist + library binding
# ---------------------------------------------------------------------------

def liberty_to_python(expr: str) -> str:
    """Translate a Liberty boolean function into a Python expression over
    pin names using &, |, ^ and (M ^ x) for negation (M = all-ones mask)."""
    toks = [t for t in _TOK.findall(expr) if t]
    out = []
    pos = 0

    def peek():
        return toks[pos] if pos < len(toks) else None

    def take():
        nonlocal pos
        pos += 1
        return toks[pos - 1]

    def p_or():
        a = p_xor()
        while peek() in ("|", "+"):
            take()
            a = f"({a} | {p_xor()})"
        return a

    def p_xor():
        a = p_and()
        while peek() == "^":
            take()
            a = f"({a} ^ {p_and()})"
        return a

    def p_and():
        a = p_not()
        while peek() in ("&", "*") or (peek() is not None and peek() not in ("|", "+", "^", ")")):
            if peek() in ("&", "*"):
                take()
            a = f"({a} & {p_not()})"
        return a

    def p_not():
        if peek() == "!":
            take()
            return f"(M ^ {p_not()})"
        a = p_atom()
        while peek() == "'":
            take()
            a = f"(M ^ {a})"
        return a

    def p_atom():
        t = take()
        if t == "(":
            a = p_or()
            take()
            return a
        if t == "1":
            return "M"
        if t == "0":
            return "0"
        return t

    r = p_or()
    if pos != len(toks):
        raise ValueError(expr)
    return r


def _eval_gate(g, x: Sequence[int]) -> Tuple[int, ...]:
    if g.kind == "CELL":
        env = dict(zip(g.ip, x))
        env["M"] = 1
        return tuple(eval(e, {"__builtins__": {}}, env) for e in g.fexpr)
    return _gate_eval(g.kind, x)


def _gate_eval(kind: str, x: Sequence[int]) -> Tuple[int, ...]:
    if kind == "INV":
        return (1 - x[0],)
    if kind == "BUF":
        return (x[0],)
    if kind == "AND2":
        return (x[0] & x[1],)
    if kind == "NAND2":
        return (1 - (x[0] & x[1]),)
    if kind == "OR2":
        return (x[0] | x[1],)
    if kind == "NOR2":
        return (1 - (x[0] | x[1]),)
    if kind == "XOR2":
        return (x[0] ^ x[1],)
    if kind == "XNOR2":
        return (1 - (x[0] ^ x[1]),)
    if kind == "AND3":
        return (x[0] & x[1] & x[2],)
    if kind == "AO21":
        return ((x[0] & x[1]) | x[2],)
    if kind == "AOI21":
        return (1 - ((x[0] & x[1]) | x[2]),)
    if kind == "OAI21":
        return (1 - ((x[0] | x[1]) & x[2]),)
    if kind == "MAJ3":
        return ((x[0] & x[1]) | (x[0] & x[2]) | (x[1] & x[2]),)
    if kind == "XOR3":
        return (x[0] ^ x[1] ^ x[2],)
    if kind == "MUX2":
        return (x[1] if x[2] else x[0],)
    if kind == "HA":
        return (x[0] ^ x[1], x[0] & x[1])
    if kind == "FA":
        return (x[0] ^ x[1] ^ x[2], (x[0] & x[1]) | (x[0] & x[2]) | (x[1] & x[2]))
    raise ValueError(kind)


@dataclass
class ArcData:
    d_rise: float
    d_fall: float
    tr_rise: float
    tr_fall: float
    e_rise: float     # internal energy (J) per output rise caused by this input
    e_fall: float


@dataclass
class Bound:
    gi: int
    cell: str
    in_pins: Tuple[str, ...]
    out_pins: Tuple[str, ...]
    arcs: Dict[Tuple[int, int], ArcData] = field(default_factory=dict)   # (in idx, out idx)
    leak: List[Tuple[Optional[Callable], float]] = field(default_factory=list)
    leak_avg: float = 0.0
    in_pin_energy: Dict[int, float] = field(default_factory=dict)     # per input transition (J)


class GateLevel:
    """Bind a Netlist to a Liberty corner and compute loads, slews and delays."""

    def __init__(self, nl: Netlist, lib: Library, out_load_F: float = 5e-15, in_slew_s: float = 50e-12,
                 wire_load: Optional[str] = None, clock_slew_s: float = 50e-12, out_loads: Dict[int, float] = None):
        self.nl = nl
        self.lib = lib
        self.V = lib.op_voltage
        self.in_slew = in_slew_s
        self.clock_slew = clock_slew_s
        self.gates = nl.gates
        self.driver = dict(nl._driver)
        self.fanout: Dict[int, List[Tuple[int, int]]] = defaultdict(list)   # net -> [(gate, pin idx)]
        for gi, g in enumerate(self.gates):
            for k, n in enumerate(g.ins):
                self.fanout[n].append((gi, k))
        self.cells = [PREFIX + cellinfo(g)[0] for g in self.gates]
        # --- net capacitance -----------------------------------------
        self.cap: Dict[int, float] = defaultdict(float)
        for gi, g in enumerate(self.gates):
            cell = lib.cell(self.cells[gi])
            ip = cellinfo(g)[1]
            for k, n in enumerate(g.ins):
                self.cap[n] += lib.pin_cap_F(self.cells[gi], ip[k])
        self.wire_cap: Dict[int, float] = defaultdict(float)
        if wire_load:
            wl = lib.header.first("wire_load", wire_load)
            cpl = float(wl.attr("capacitance")) * lib.units.cap
            fl = {}
            for args in wl.attrs.get("fanout_length", []):
                fl[int(float(args[0]))] = float(args[1])
            slope = float(wl.attr("slope"))
            maxk = max(fl)
            for n in set(list(self.cap.keys()) + [o for g in self.gates for o in g.outs]):
                k = len(self.fanout.get(n, []))
                if k == 0:
                    continue
                length = fl[k] if k in fl else fl[maxk] + slope * (k - maxk)
                self.wire_cap[n] = cpl * length
                self.cap[n] += self.wire_cap[n]
        self.out_nets = set(n for nets in nl.outputs.values() for n in nets)
        for n in self.out_nets:
            self.cap[n] += out_load_F
        for n, c in (out_loads or {}).items():
            self.cap[n] += c
        # --- slew propagation + arc tables -----------------------------
        self.slew: Dict[int, float] = defaultdict(lambda: self.in_slew)
        self.bound: List[Bound] = [None] * len(self.gates)  # type: ignore
        order = nl.topo()
        # DFFs first (sources), then combinational in topo order
        for gi in [g for g in range(len(self.gates)) if self.gates[g].kind == "DFF"] + \
                  [g for g in order if self.gates[g].kind != "DFF"]:
            self._bind(gi)

    def _bind(self, gi: int):
        g = self.gates[gi]
        lib = self.lib
        cname = self.cells[gi]
        cell = lib.cell(cname)
        cellname, ip, op = cellinfo(g)
        b = Bound(gi, cname, ip, op)
        for oi, (opin, onet) in enumerate(zip(op, g.outs)):
            load = self.cap[onet]
            worst_tr = 0.0
            if g.kind == "DFF":
                related = [("CLK", -1)]
            else:
                related = [(p, k) for k, p in enumerate(ip)]
            for rpin, k in related:
                arcs = [a for a in cell.pins[opin].timing if a.related_pin == rpin
                        and a.timing_type in (None, "combinational", "rising_edge")]
                if not arcs:
                    continue
                s_in = self.clock_slew if k < 0 else self.slew[g.ins[k]]

                def tab(name, a):
                    t = a.tables.get(name)
                    return lib._lookup_time(t, s_in, load) if t is not None else None

                dr = [tab("cell_rise", a) for a in arcs if "cell_rise" in a.tables]
                df = [tab("cell_fall", a) for a in arcs if "cell_fall" in a.tables]
                trr = [tab("rise_transition", a) for a in arcs if "rise_transition" in a.tables]
                trf = [tab("fall_transition", a) for a in arcs if "fall_transition" in a.tables]
                ips = [x for x in cell.pins[opin].internal_power if x.related_pin == rpin]
                er = [lib.internal_energy_J(cname, opin, rpin, "rise", s_in, load, x.when) for x in ips if x.rise]
                ef = [lib.internal_energy_J(cname, opin, rpin, "fall", s_in, load, x.when) for x in ips if x.fall]
                mean = lambda v: sum(v) / len(v) if v else 0.0
                ad = ArcData(d_rise=mean(dr), d_fall=mean(df), tr_rise=max(trr or [0]), tr_fall=max(trf or [0]),
                             e_rise=mean(er), e_fall=mean(ef))
                ad.d_rise_max = max(dr or [0])
                ad.d_fall_max = max(df or [0])
                b.arcs[(k, oi)] = ad
                worst_tr = max(worst_tr, ad.tr_rise, ad.tr_fall)
            self.slew[onet] = worst_tr if worst_tr > 0 else self.in_slew
        # leakage states
        for when, val in cell.leakage_states:
            b.leak.append((compile_expr(when) if when else None, val * lib.units.leakage))
        b.leak_avg = (cell.leakage or 0.0) * lib.units.leakage
        # input-pin internal power (e.g. DFF CLK and D pins); average of rise/fall
        for k, p in enumerate(("CLK",) + ip if g.kind == "DFF" else ip):
            pin = cell.pins.get(p)
            if pin is None or not pin.internal_power:
                continue
            vals = []
            s_in = self.clock_slew if p == "CLK" else self.slew[g.ins[ip.index(p)]]
            for x in pin.internal_power:
                for t in (x.rise, x.fall):
                    if t is not None:
                        vals.append(t.lookup(**{v: s_in / lib.units.time for v in t.variables}) * lib.units.energy)
            if vals:
                # Liberty input-pin internal power: energy per input transition;
                # 'when' variants averaged
                b.in_pin_energy[-1 if p == "CLK" else ip.index(p)] = sum(vals) / len(vals)
        self.bound[gi] = b

    # ---------------------------------------------------------------- STA
    def sta(self, clk2q: bool = True) -> Dict[str, object]:
        """Longest path (max over when-conditions and edges); returns delay and path."""
        arr: Dict[int, float] = {}
        prev: Dict[int, Tuple[Optional[int], str]] = {}
        for n in [x for nets in self.nl.inputs.values() for x in nets]:
            arr[n] = 0.0
        arr[CONST0] = arr[CONST1] = -math.inf
        order = self.nl.topo()
        for gi in [g for g in range(len(self.gates)) if self.gates[g].kind == "DFF"]:
            g = self.gates[gi]
            ad = self.bound[gi].arcs[(-1, 0)]
            arr[g.outs[0]] = max(ad.d_rise_max, ad.d_fall_max) if clk2q else 0.0
            prev[g.outs[0]] = (None, self.cells[gi])
        for gi in order:
            g = self.gates[gi]
            if g.kind == "DFF":
                continue
            for oi, o in enumerate(g.outs):
                best = -math.inf
                src = None
                for k, n in enumerate(g.ins):
                    ad = self.bound[gi].arcs.get((k, oi))
                    if ad is None:
                        continue
                    t = arr.get(n, 0.0) + max(ad.d_rise_max, ad.d_fall_max)
                    if t > best:
                        best, src = t, n
                arr[o] = best
                prev[o] = (src, self.cells[gi])
        # endpoints
        ends = [(n, 0.0) for nets in self.nl.outputs.values() for n in nets]
        setup = 0.0
        for gi, g in enumerate(self.gates):
            if g.kind == "DFF":
                cell = self.lib.cell(self.cells[gi])
                st = [a for a in cell.pins["D"].timing if a.timing_type == "setup_rising"]
                if st:
                    t = st[0].tables.get("rise_constraint") or st[0].tables.get("fall_constraint")
                    kw = {}
                    for v in t.variables:
                        kw[v] = (self.clock_slew if v == "related_pin_transition" else self.slew[g.ins[0]]) / self.lib.units.time
                    s = max(st[0].tables[x].lookup(**kw) for x in ("rise_constraint", "fall_constraint")
                            if x in st[0].tables) * self.lib.units.time
                    ends.append((g.ins[0], s))
        worst = max(ends, key=lambda e: arr.get(e[0], -math.inf) + e[1])
        n = worst[0]
        path = []
        while n in prev and n not in (CONST0, CONST1):
            src, cell = prev[n]
            path.append((self.nl.nets[n], cell, arr[n]))
            if src is None:
                break
            n = src
        return dict(delay_s=arr.get(worst[0], 0.0) + worst[1], setup_s=worst[1],
                    path=list(reversed(path)))

    # ------------------------------------------------------------ simulate
    def simulate(self, vectors: Sequence[Dict[str, int]], period_s: float, mode: str = "inertial",
                 settle_s: Optional[float] = None, trace: bool = False) -> "SimResult":
        nl = self.nl
        gates = self.gates
        nnet = len(nl.nets)
        val = [0] * nnet
        val[CONST1] = 1
        dffs = [gi for gi, g in enumerate(gates) if g.kind == "DFF"]
        comb_order = [gi for gi in nl.topo() if gates[gi].kind != "DFF"]
        toggles = [0] * nnet
        int_energy = [0.0] * len(gates)
        inpin_energy = [0.0] * len(gates)
        leak_time = [defaultdict(float) for _ in gates]   # state-key -> time
        # initial settle with first vector
        in_nets = nl.inputs

        def apply_inputs(vec, target):
            for bus, nets in in_nets.items():
                x = vec[bus]
                for i, n in enumerate(nets):
                    target[n] = (x >> i) & 1

        def settle(v):
            for gi in comb_order:
                g = gates[gi]
                outs = _eval_gate(g, [v[n] for n in g.ins])
                for o, x in zip(g.outs, outs):
                    v[o] = x

        apply_inputs(vectors[0], val)
        settle(val)
        tr: List[Tuple[float, int, int]] = [] if trace else None
        init_vals = list(val)
        t_now = 0.0
        events: List[Tuple[float, int, int, int, int]] = []   # (time, seq, net, value, cause gate/pin code)
        pending: Dict[int, Tuple[float, int, int]] = {}        # inertial: net -> (time, value, seq)
        seq = 0
        n_cycles = len(vectors)
        ffq = {gates[gi].outs[0]: gi for gi in dffs}

        def schedule_from_gate(gi, k_changed, t):
            nonlocal seq
            g = gates[gi]
            outs = _eval_gate(g, [val[n] for n in g.ins])
            b = self.bound[gi]
            for oi, (o, x) in enumerate(zip(g.outs, outs)):
                ad = b.arcs.get((k_changed, oi))
                if ad is None:
                    continue
                if mode == "inertial":
                    p = pending.get(o)
                    if p is not None:
                        if p[1] == x:
                            continue
                        # cancel the pending (opposite) change: pulse swallowed
                        del pending[o]
                        if x == val[o]:
                            continue
                    elif x == val[o]:
                        continue
                    d = ad.d_rise if x else ad.d_fall
                    seq += 1
                    pending[o] = (t + max(d, 0.0), x, seq)
                    heapq.heappush(events, (t + max(d, 0.0), seq, o, x, gi * 8 + k_changed))
                else:  # transport
                    d = ad.d_rise if x else ad.d_fall
                    seq += 1
                    heapq.heappush(events, (t + max(d, 0.0), seq, o, x, gi * 8 + k_changed))

        has_ff = bool(dffs)
        for cyc in range(1, n_cycles):
            t0 = cyc * period_s
            # leakage state sampling (state just before the next edge)
            for gi, g in enumerate(gates):
                b = self.bound[gi]
                if not b.leak:
                    continue
                key = tuple(val[n] for n in g.ins) + tuple(val[o] for o in g.outs)
                leak_time[gi][key] += period_s
            if mode == "zero":
                old = list(val)
                if has_ff:
                    newq = {gates[gi].outs[0]: val[gates[gi].ins[0]] for gi in dffs}
                    for o, x in newq.items():
                        val[o] = x
                    for gi in dffs:
                        inpin_energy[gi] += 2 * self.bound[gi].in_pin_energy.get(-1, 0.0)  # two clock edges
                apply_inputs(vectors[cyc], val)
                settle(val)
                for n in range(2, nnet):
                    if val[n] != old[n]:
                        toggles[n] += 1
                        if tr is not None:
                            tr.append((t0, n, val[n]))
                        gi = self.driver.get(n)
                        if gi is not None:
                            g = gates[gi]
                            oi = g.outs.index(n)
                            b = self.bound[gi]
                            # attribute to the first input that changed
                            ks = [k for k, x in enumerate(g.ins) if val[x] != old[x]] or [0]
                            k = ks[0] if gates[gi].kind != "DFF" else -1
                            ad = b.arcs.get((k, oi))
                            if ad:
                                int_energy[gi] += ad.e_rise if val[n] else ad.e_fall
                        for (fg, k) in self.fanout.get(n, []):
                            e = self.bound[fg].in_pin_energy.get(k)
                            if e:
                                inpin_energy[fg] += e
                continue
            # event-driven
            # 1) clock edge: DFF outputs change after clk->q
            if has_ff:
                for gi in dffs:
                    g = gates[gi]
                    q = g.outs[0]
                    d = val[g.ins[0]]
                    inpin_energy[gi] += 2 * self.bound[gi].in_pin_energy.get(-1, 0.0)
                    if d != val[q]:
                        ad = self.bound[gi].arcs[(-1, 0)]
                        seq += 1
                        heapq.heappush(events, (t0 + (ad.d_rise if d else ad.d_fall), seq, q, d, gi * 8 + 7))
            # 2) primary inputs change at t0
            for bus, nets in in_nets.items():
                x = vectors[cyc][bus]
                for i, n in enumerate(nets):
                    nv = (x >> i) & 1
                    if nv != val[n]:
                        seq += 1
                        heapq.heappush(events, (t0, seq, n, nv, -1))
            t_end = t0 + period_s
            while events and events[0][0] < t_end:
                t, s, n, x, cause = heapq.heappop(events)
                if mode == "inertial":
                    p = pending.get(n)
                    if cause >= 0 and (cause % 8) != 7:
                        if p is None or p[2] != s:
                            continue          # cancelled
                        del pending[n]
                if val[n] == x:
                    continue
                val[n] = x
                toggles[n] += 1
                if tr is not None:
                    tr.append((t, n, x))
                if cause >= 0:
                    gi, k = divmod(cause, 8)
                    if k == 7:
                        k = -1
                    g = gates[gi]
                    oi = g.outs.index(n)
                    ad = self.bound[gi].arcs.get((k, oi))
                    if ad:
                        int_energy[gi] += ad.e_rise if x else ad.e_fall
                for (fg, k) in self.fanout.get(n, []):
                    e = self.bound[fg].in_pin_energy.get(k)
                    if e:
                        inpin_energy[fg] += e
                    if gates[fg].kind == "DFF":
                        continue
                    schedule_from_gate(fg, k, t)
            if events and events[0][0] < t_end + 1e-15 and mode == "inertial":
                pass
        unsettled = len(events)
        T = (n_cycles - 1) * period_s
        r = SimResult(self, toggles, int_energy, inpin_energy, leak_time, T, n_cycles - 1, mode,
                      unsettled)
        r.trace = tr
        r.init_vals = init_vals
        r.period = period_s
        return r


@dataclass
class SimResult:
    gl: GateLevel
    toggles: List[int]
    int_energy: List[float]
    inpin_energy: List[float]
    leak_time: List[Dict[tuple, float]]
    T: float
    cycles: int
    mode: str
    unsettled_events: int

    def power(self) -> Dict[str, object]:
        gl = self.gl
        V = gl.V
        sw_by_group: Dict[str, float] = defaultdict(float)
        int_by_group: Dict[str, float] = defaultdict(float)
        leak_by_group: Dict[str, float] = defaultdict(float)
        sw_wire = 0.0
        sw_inputs = 0.0
        for n, k in enumerate(self.toggles):
            if k == 0 or n in (CONST0, CONST1):
                continue
            e = 0.5 * gl.cap[n] * V * V * k
            gi = gl.driver.get(n)
            grp = gl.gates[gi].group if gi is not None else "inputs"
            if gi is None:
                sw_inputs += e
            sw_by_group[grp] += e
            sw_wire += 0.5 * gl.wire_cap.get(n, 0.0) * V * V * k
        for gi, g in enumerate(gl.gates):
            int_by_group[g.group] += self.int_energy[gi] + self.inpin_energy[gi]
            b = gl.bound[gi]
            if not b.leak:
                continue
            tot_t = sum(self.leak_time[gi].values())
            if tot_t <= 0:
                leak_by_group[g.group] += b.leak_avg * self.T
                continue
            pins = list(b.in_pins) + list(b.out_pins)
            e = 0.0
            for key, t in self.leak_time[gi].items():
                env = dict(zip(pins, key))
                if g.kind == "DFF":
                    # clock is high half of the time: average both CLK states
                    ps = []
                    for clk in (0, 1):
                        env2 = dict(env, IQ=env.get("Q", 0), CLK=clk)
                        m = [v for f, v in b.leak if f is not None and _safe(f, env2)]
                        ps.append(m[0] if m else b.leak_avg)
                    p = sum(ps) / 2
                else:
                    matched = [v for f, v in b.leak if f is not None and _safe(f, env)]
                    p = matched[0] if matched else b.leak_avg
                e += p * t
            leak_by_group[g.group] += e
        # clock net: the clock port is implicit (no CTS); charge the CLK pin
        # capacitance of every flip-flop twice per cycle (1/2 C V^2 per edge)
        c_clk = sum(gl.lib.pin_cap_F(gl.cells[gi], "CLK") for gi, g in enumerate(gl.gates) if g.kind == "DFF")
        if c_clk:
            sw_by_group["clk"] += c_clk * V * V * self.cycles
        groups = sorted(set(sw_by_group) | set(int_by_group) | set(leak_by_group))
        rows = {}
        for gname in groups:
            rows[gname] = dict(switching_J=sw_by_group.get(gname, 0.0), internal_J=int_by_group.get(gname, 0.0),
                               leakage_J=leak_by_group.get(gname, 0.0))
        tot = {k: sum(r[k] for r in rows.values()) for k in ("switching_J", "internal_J", "leakage_J")}
        total = sum(tot.values())
        return dict(by_group=rows, totals=tot, total_J=total, per_cycle_J=total / self.cycles,
                    avg_power_W=total / self.T, switching_wire_J=sw_wire, switching_inputs_J=sw_inputs,
                    toggles_total=sum(self.toggles[2:]), cycles=self.cycles, mode=self.mode)

    def write_vcd(self, path: str, scope: Tuple[str, ...] = ("tb", "dut"), clock: str = "clk") -> None:
        """Write the simulated value changes as a VCD (1 ps timescale).

        Net names match ugcal.arith.verilog.emit (internal nets 'n<i>', bus
        bits 'bus [i]').  If the design has flip-flops, a clock port toggling
        at the simulation period is added (rising edge at each cycle start).
        """
        if getattr(self, "trace", None) is None:
            raise ValueError("simulate(..., trace=True) is required for VCD output")
        gl = self.gl
        nl = gl.nl
        names = {}
        for i in range(2, len(nl.nets)):
            names[i] = f"n{i}"
        for bus, nets in list(nl.inputs.items()) + list(nl.outputs.items()):
            for k, n in enumerate(nets):
                if bus in nl.inputs:
                    names[n] = f"{bus} [{k}]"
        used = set(n for (_, n, _) in self.trace) | set(names)
        def ident(i):
            chars = "".join(chr(c) for c in range(33, 127))
            s_ = ""
            i += 1
            while i:
                i, r = divmod(i - 1, len(chars))
                s_ = chars[r] + s_
            return s_
        ids = {n: ident(k) for k, n in enumerate(sorted(names))}
        has_ff = any(g.kind == "DFF" for g in nl.gates)
        clk_id = ident(len(ids) + 1)
        with open(path, "w") as fh:
            fh.write("$timescale 1ps $end\n")
            for sc in scope:
                fh.write(f"$scope module {sc} $end\n")
            if has_ff:
                fh.write(f"$var wire 1 {clk_id} {clock} $end\n")
            for n in sorted(names):
                fh.write(f"$var wire 1 {ids[n]} {names[n]} $end\n")
            # instance scopes: OpenSTA annotates pins (inst/PIN), not nets, so
            # every cell pin is declared as an alias of its net's identifier
            for g in nl.gates:
                _, ip, op = cellinfo(g)
                fh.write(f"$scope module {g.name} $end\n")
                if g.kind == "DFF" and has_ff:
                    fh.write(f"$var wire 1 {clk_id} CLK $end\n")
                for pin, n in list(zip(ip, g.ins)) + list(zip(op, g.outs)):
                    if n in ids:
                        fh.write(f"$var wire 1 {ids[n]} {pin} $end\n")
                fh.write("$upscope $end\n")
            for _ in scope:
                fh.write("$upscope $end\n")
            fh.write("$enddefinitions $end\n#0\n$dumpvars\n")
            if has_ff:
                fh.write(f"0{clk_id}\n")
            for n in sorted(names):
                fh.write(f"{self.init_vals[n]}{ids[n]}\n")
            fh.write("$end\n")
            events = sorted(self.trace, key=lambda e: e[0])
            if has_ff:
                ck = []
                for c in range(1, self.cycles + 1):
                    ck.append((c * self.period, -1, 1))
                    ck.append((c * self.period + self.period / 2, -1, 0))
                events = sorted(events + ck, key=lambda e: e[0])
            cur = None
            for t, n, x in events:
                tp = int(round(t * 1e12))
                if tp != cur:
                    fh.write(f"#{tp}\n")
                    cur = tp
                fh.write(f"{x}{clk_id if n == -1 else ids[n]}\n")
            fh.write(f"#{int(round((self.cycles + 1) * self.period * 1e12))}\n")


def _safe(f, env):
    try:
        return f(env)
    except KeyError:
        return 0
