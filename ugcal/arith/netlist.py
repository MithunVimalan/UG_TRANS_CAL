"""Gate-level netlists for arithmetic circuits.

A ``Netlist`` is a directed acyclic graph of primitive gates (plus D
flip-flops for sequential designs).  It supports

  * bit-parallel ("bit-sliced") simulation: every net holds a Python integer
    whose bit k is the net's value in test vector k, so all 65 536 input pairs
    of an 8x8 multiplier are simulated in one pass;
  * zero-delay toggle counting for a vector sequence (functional activity);
  * structural statistics per gate kind and per functional group
    ('pp', 'enc', 'red', 'cpa', 'acc', 'reg', ...);
  * logic depth (unit delay) and weighted depth (per-kind delays);
  * emission of structural Verilog mapped onto sky130_fd_sc_hd cells.

Net 0 is constant 0 and net 1 is constant 1.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

CONST0 = 0
CONST1 = 1

# kind -> (number of inputs, number of outputs)
KINDS: Dict[str, Tuple[int, int]] = {
    "INV": (1, 1), "BUF": (1, 1),
    "AND2": (2, 1), "NAND2": (2, 1), "OR2": (2, 1), "NOR2": (2, 1),
    "XOR2": (2, 1), "XNOR2": (2, 1),
    "AND3": (3, 1), "AO21": (3, 1), "AOI21": (3, 1), "OAI21": (3, 1), "MAJ3": (3, 1), "XOR3": (3, 1),
    "MUX2": (3, 1),   # (A0, A1, S) -> S ? A1 : A0
    "HA": (2, 2),     # (A, B) -> (SUM, COUT)
    "FA": (3, 2),     # (A, B, CIN) -> (SUM, COUT)
    "DFF": (1, 1),    # D -> Q, clocked by the netlist clock
}


@dataclass
class Gate:
    kind: str
    ins: Tuple[int, ...]
    outs: Tuple[int, ...]
    group: str
    name: str
    # for kind == "CELL" (any Liberty cell, e.g. imported from a synthesised
    # netlist): library cell name without prefix, pin names and the output
    # functions as Python expressions over the input pin names (see
    # ugcal.gatesim.liberty_to_python); M is the all-ones mask
    cell: Optional[str] = None
    ip: Tuple[str, ...] = ()
    op: Tuple[str, ...] = ()
    fexpr: Tuple[str, ...] = ()
    seq: bool = False


@dataclass
class Netlist:
    name: str
    nets: List[str] = field(default_factory=lambda: ["const0", "const1"])
    gates: List[Gate] = field(default_factory=list)
    inputs: Dict[str, List[int]] = field(default_factory=dict)
    outputs: Dict[str, List[int]] = field(default_factory=dict)
    meta: Dict[str, object] = field(default_factory=dict)
    _driver: Dict[int, int] = field(default_factory=dict)

    # ---- construction --------------------------------------------------
    def new_net(self, hint: str = "n") -> int:
        self.nets.append(f"{hint}_{len(self.nets)}")
        return len(self.nets) - 1

    def add_input(self, bus: str, width: int) -> List[int]:
        ids = []
        for i in range(width):
            self.nets.append(f"{bus}[{i}]")
            ids.append(len(self.nets) - 1)
        self.inputs[bus] = ids
        return ids

    def set_output(self, bus: str, nets: Sequence[int]) -> None:
        self.outputs[bus] = list(nets)

    def cell_gate(self, cell: str, ip: Sequence[str], op: Sequence[str], fexpr: Sequence[str],
                  ins: Sequence[int], outs: Sequence[int], group: str, name: str, seq: bool = False) -> int:
        """Add a generic Liberty cell with pre-allocated output nets."""
        g = Gate("CELL", tuple(ins), tuple(outs), group, name, cell=cell, ip=tuple(ip), op=tuple(op),
                 fexpr=tuple(fexpr), seq=seq)
        for o in outs:
            self._driver[o] = len(self.gates)
        self.gates.append(g)
        return len(self.gates) - 1

    def gate(self, kind: str, ins: Sequence[int], group: str) -> Tuple[int, ...]:
        nin, nout = KINDS[kind]
        if len(ins) != nin:
            raise ValueError(f"{kind} expects {nin} inputs, got {len(ins)}")
        outs = tuple(self.new_net(f"{group}") for _ in range(nout))
        g = Gate(kind, tuple(ins), outs, group, f"{group}_{kind.lower()}_{len(self.gates)}")
        for o in outs:
            self._driver[o] = len(self.gates)
        self.gates.append(g)
        return outs

    # convenience wrappers with constant folding --------------------------
    def INV(self, a, g):
        if a in (CONST0, CONST1):
            return CONST1 - a
        return self.gate("INV", [a], g)[0]

    def AND2(self, a, b, g):
        if CONST0 in (a, b):
            return CONST0
        if a == CONST1:
            return b
        if b == CONST1:
            return a
        return self.gate("AND2", [a, b], g)[0]

    def NAND2(self, a, b, g):
        if CONST0 in (a, b):
            return CONST1
        if a == CONST1:
            return self.INV(b, g)
        if b == CONST1:
            return self.INV(a, g)
        return self.gate("NAND2", [a, b], g)[0]

    def OR2(self, a, b, g):
        if CONST1 in (a, b):
            return CONST1
        if a == CONST0:
            return b
        if b == CONST0:
            return a
        return self.gate("OR2", [a, b], g)[0]

    def NOR2(self, a, b, g):
        return self.INV(self.OR2(a, b, g), g) if CONST0 in (a, b) or CONST1 in (a, b) else \
            self.gate("NOR2", [a, b], g)[0]

    def XOR2(self, a, b, g):
        if a == CONST0:
            return b
        if b == CONST0:
            return a
        if a == CONST1:
            return self.INV(b, g)
        if b == CONST1:
            return self.INV(a, g)
        return self.gate("XOR2", [a, b], g)[0]

    def XNOR2(self, a, b, g):
        if CONST0 in (a, b) or CONST1 in (a, b):
            return self.INV(self.XOR2(a, b, g), g)
        return self.gate("XNOR2", [a, b], g)[0]

    def AO21(self, a1, a2, b1, g):
        """(a1 & a2) | b1"""
        if b1 == CONST1:
            return CONST1
        if b1 == CONST0:
            return self.AND2(a1, a2, g)
        if CONST0 in (a1, a2):
            return b1
        if a1 == CONST1:
            return self.OR2(a2, b1, g)
        if a2 == CONST1:
            return self.OR2(a1, b1, g)
        return self.gate("AO21", [a1, a2, b1], g)[0]

    def MUX2(self, a0, a1, s, g):
        if s == CONST0:
            return a0
        if s == CONST1:
            return a1
        return self.gate("MUX2", [a0, a1, s], g)[0]

    def HA(self, a, b, g) -> Tuple[int, int]:
        """returns (sum, carry)"""
        if CONST0 in (a, b):
            return (b if a == CONST0 else a), CONST0
        if a == CONST1 and b == CONST1:
            return CONST0, CONST1
        if a == CONST1:
            return self.INV(b, g), b
        if b == CONST1:
            return self.INV(a, g), a
        s, c = self.gate("HA", [a, b], g)
        return s, c

    def FA(self, a, b, c, g) -> Tuple[int, int]:
        """returns (sum, carry)"""
        consts = [x for x in (a, b, c) if x in (CONST0, CONST1)]
        if not consts:
            s, co = self.gate("FA", [a, b, c], g)
            return s, co
        vars_ = [x for x in (a, b, c) if x not in (CONST0, CONST1)]
        n1 = sum(1 for x in consts if x == CONST1)
        if len(vars_) == 2:
            x, y = vars_
            if n1 == 0:
                return self.HA(x, y, g)
            # x + y + 1: sum = XNOR(x, y), carry = OR(x, y)
            return self.XNOR2(x, y, g), self.OR2(x, y, g)
        if len(vars_) == 1:
            x = vars_[0]
            if n1 == 0:
                return x, CONST0
            if n1 == 1:
                return self.INV(x, g), x
            return x, CONST1
        tot = n1
        return (CONST1 if tot & 1 else CONST0), (CONST1 if tot >= 2 else CONST0)

    def DFF(self, d, g) -> int:
        return self.gate("DFF", [d], g)[0]

    def prune(self) -> int:
        """Remove gates none of whose outputs is used (iteratively); return count."""
        removed = 0
        while True:
            used = set()
            for g in self.gates:
                used.update(g.ins)
            for nets in self.outputs.values():
                used.update(nets)
            keep = [g for g in self.gates if any(o in used for o in g.outs)]
            if len(keep) == len(self.gates):
                break
            removed += len(self.gates) - len(keep)
            self.gates = keep
            self._driver = {o: i for i, g in enumerate(self.gates) for o in g.outs}
        return removed

    # ---- analysis -----------------------------------------------------
    def topo(self) -> List[int]:
        """Gate indices in topological order (DFF outputs treated as sources)."""
        indeg = [0] * len(self.gates)
        fanout: Dict[int, List[int]] = defaultdict(list)
        for gi, g in enumerate(self.gates):
            if g.kind == "DFF" or g.seq:
                continue
            for n in g.ins:
                d = self._driver.get(n)
                if d is not None and not (self.gates[d].kind == "DFF" or self.gates[d].seq):
                    indeg[gi] += 1
                    fanout[d].append(gi)
        order = [gi for gi in range(len(self.gates)) if indeg[gi] == 0]
        k = 0
        while k < len(order):
            for f in fanout[order[k]]:
                indeg[f] -= 1
                if indeg[f] == 0:
                    order.append(f)
            k += 1
        if len(order) != len(self.gates):
            raise ValueError("combinational loop")
        return order

    def stats(self) -> Dict[str, object]:
        by_kind = Counter(g.kind for g in self.gates)
        by_group: Dict[str, Counter] = defaultdict(Counter)
        for g in self.gates:
            by_group[g.group][g.kind] += 1
        return dict(gates=len(self.gates), by_kind=dict(by_kind),
                    by_group={k: dict(v) for k, v in by_group.items()})

    def depth(self, delay: Optional[Dict[str, float]] = None) -> Tuple[float, List[int]]:
        """Longest input-to-output (or register-to-register) path.

        ``delay`` maps kind -> delay (default 1 per gate).  Returns (depth, gate path).
        """
        delay = delay or {}
        arr: Dict[int, float] = {}
        prev: Dict[int, Optional[int]] = {}
        best_gate: Dict[int, Optional[int]] = {}
        order = self.topo()
        for gi in order:
            g = self.gates[gi]
            if g.kind == "DFF":
                t_in = 0.0
                src = None
            else:
                t_in = 0.0
                src = None
                for n in g.ins:
                    d = self._driver.get(n)
                    if d is None or self.gates[d].kind == "DFF":
                        continue
                    if arr[d] > t_in:
                        t_in = arr[d]
                        src = d
            arr[gi] = t_in + delay.get(g.kind, 1.0) if g.kind != "DFF" else delay.get("DFF", 0.0)
            prev[gi] = src
        if not arr:
            return 0.0, []
        # endpoints: gates driving outputs or DFF inputs
        ends = set()
        for nets in self.outputs.values():
            for n in nets:
                if n in self._driver:
                    ends.add(self._driver[n])
        for g in self.gates:
            if g.kind == "DFF":
                d = self._driver.get(g.ins[0])
                if d is not None:
                    ends.add(d)
        end = max(ends, key=lambda gi: arr[gi]) if ends else max(arr, key=arr.get)
        path = []
        x: Optional[int] = end
        while x is not None:
            path.append(x)
            x = prev.get(x)
        return arr[end], list(reversed(path))

    # ---- simulation ---------------------------------------------------
    def simulate(self, values: Dict[str, Sequence[int]], nvec: int,
                 state: Optional[Dict[int, int]] = None) -> Dict[int, int]:
        """Bit-sliced combinational evaluation.

        ``values`` maps each input bus to a list of per-bit integers (bit k of
        element i = value of input bit i in vector k).  ``state`` gives DFF
        output values (same encoding).  Returns net -> integer.
        """
        mask = (1 << nvec) - 1
        v: Dict[int, int] = {CONST0: 0, CONST1: mask}
        for bus, nets in self.inputs.items():
            bits = values[bus]
            if len(bits) != len(nets):
                raise ValueError(f"bus {bus}: {len(bits)} bits given, {len(nets)} expected")
            for n, b in zip(nets, bits):
                v[n] = b & mask
        for gi, g in enumerate(self.gates):
            if g.kind == "DFF":
                v[g.outs[0]] = (state or {}).get(g.outs[0], 0) & mask
        for gi in self.topo():
            g = self.gates[gi]
            if g.kind == "DFF":
                continue
            x = [v[n] for n in g.ins]
            k = g.kind
            if k == "INV":
                r = (~x[0] & mask,)
            elif k == "BUF":
                r = (x[0],)
            elif k == "AND2":
                r = (x[0] & x[1],)
            elif k == "NAND2":
                r = (~(x[0] & x[1]) & mask,)
            elif k == "OR2":
                r = (x[0] | x[1],)
            elif k == "NOR2":
                r = (~(x[0] | x[1]) & mask,)
            elif k == "XOR2":
                r = (x[0] ^ x[1],)
            elif k == "XNOR2":
                r = (~(x[0] ^ x[1]) & mask,)
            elif k == "AND3":
                r = (x[0] & x[1] & x[2],)
            elif k == "AO21":
                r = ((x[0] & x[1]) | x[2],)
            elif k == "AOI21":
                r = (~((x[0] & x[1]) | x[2]) & mask,)
            elif k == "OAI21":
                r = (~((x[0] | x[1]) & x[2]) & mask,)
            elif k == "MAJ3":
                r = ((x[0] & x[1]) | (x[0] & x[2]) | (x[1] & x[2]),)
            elif k == "XOR3":
                r = (x[0] ^ x[1] ^ x[2],)
            elif k == "MUX2":
                r = ((x[0] & ~x[2]) | (x[1] & x[2]),)
            elif k == "HA":
                r = (x[0] ^ x[1], x[0] & x[1])
            elif k == "FA":
                r = (x[0] ^ x[1] ^ x[2], (x[0] & x[1]) | (x[0] & x[2]) | (x[1] & x[2]))
            elif k == "CELL":
                env = dict(zip(g.ip, x))
                env["M"] = mask
                r = tuple(eval(e, {"__builtins__": {}}, env) for e in g.fexpr)
            else:
                raise ValueError(k)
            for o, val in zip(g.outs, r):
                v[o] = val & mask
        return v

    def read_bus(self, v: Dict[int, int], bus: str, k: int, signed: bool = False) -> int:
        nets = self.outputs.get(bus) or self.inputs[bus]
        x = 0
        for i, n in enumerate(nets):
            x |= ((v[n] >> k) & 1) << i
        if signed and x >> (len(nets) - 1):
            x -= 1 << len(nets)
        return x


def pack_inputs(widths: Dict[str, int], vectors: Sequence[Dict[str, int]]) -> Dict[str, List[int]]:
    """Convert a list of {bus: int} vectors to bit-sliced per-bit integers."""
    out = {bus: [0] * w for bus, w in widths.items()}
    for k, vec in enumerate(vectors):
        for bus, w in widths.items():
            x = vec[bus] & ((1 << w) - 1)
            bits = out[bus]
            i = 0
            while x:
                if x & 1:
                    bits[i] |= 1 << k
                x >>= 1
                i += 1
    return out


def exhaustive_inputs(widths: Dict[str, int]) -> Tuple[Dict[str, List[int]], int]:
    """Bit-sliced patterns enumerating all input combinations (bus order = dict order)."""
    total = sum(widths.values())
    nvec = 1 << total
    out: Dict[str, List[int]] = {}
    shift = 0
    for bus, w in widths.items():
        bits = []
        for i in range(w):
            pos = shift + i
            # pattern where bit k is ((k >> pos) & 1)
            block = ((1 << (1 << pos)) - 1) << (1 << pos)   # 2^pos zeros then 2^pos ones
            period = 1 << (pos + 1)
            pat = 0
            # replicate the period over nvec bits by doubling
            pat = block
            length = period
            while length < nvec:
                pat |= pat << length
                length *= 2
            bits.append(pat & ((1 << nvec) - 1))
        out[bus] = bits
        shift += w
    return out, nvec
