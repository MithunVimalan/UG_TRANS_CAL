"""Import a flat structural Verilog netlist (as written by Yosys) into a ugcal Netlist.

Supported subset: one module, vector or scalar ports, wires, named-port
instances of Liberty cells, ``assign`` of single bits (net aliases or
constants 1'b0/1'b1/1'h0/1'h1).  Cell pin directions and output functions are
taken from the Liberty library, so any combinational cell can be simulated.
Instances are grouped under ``group`` (default 'syn') for power accounting.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from ..gatesim import liberty_to_python
from ..liberty import Library
from .netlist import CONST0, CONST1, Netlist

_PREFIX = "sky130_fd_sc_hd__"


def _strip_comments(t: str) -> str:
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    return re.sub(r"//[^\n]*", "", t)


def import_verilog(text: str, lib: Library, group: str = "syn") -> Netlist:
    t = _strip_comments(text)
    m = re.search(r"module\s+(\w+)\s*\((.*?)\)\s*;(.*?)endmodule", t, re.S)
    if not m:
        raise ValueError("no module found")
    name, _, body = m.groups()
    nl = Netlist(name)
    nets: Dict[str, int] = {}
    widths: Dict[str, Tuple[int, int]] = {}
    outputs: Dict[str, List[str]] = {}

    def bitname(base, i):
        return f"{base}[{i}]"

    for kind, rng, names in re.findall(r"\b(input|output|wire)\s*(\[\s*\d+\s*:\s*\d+\s*\])?\s*([^;]+);", body):
        for nm in [x.strip() for x in names.split(",") if x.strip()]:
            if rng:
                hi, lo = [int(x) for x in re.findall(r"\d+", rng)]
                lo_, hi_ = min(lo, hi), max(lo, hi)
                bits = [bitname(nm, i) for i in range(lo_, hi_ + 1)]
                widths[nm] = (lo_, hi_)
            else:
                bits = [nm]
            if kind == "input":
                ids = nl.add_input(nm, len(bits))
                for b, i in zip(bits, ids):
                    nets[b] = i
            elif kind == "output":
                outputs[nm] = bits
            else:
                for b in bits:
                    if b not in nets:
                        nets[b] = nl.new_net(b)

    def ref(tok: str) -> int:
        tok = tok.strip()
        if re.fullmatch(r"1'[bh]0", tok):
            return CONST0
        if re.fullmatch(r"1'[bh]1", tok):
            return CONST1
        tok = tok.replace(" ", "")
        if tok.startswith("\\"):
            tok = tok[1:]
        if tok not in nets:
            nets[tok] = nl.new_net(tok)
        return nets[tok]

    # assigns (aliases): resolve after instances by union
    aliases: List[Tuple[str, str]] = []
    for lhs, rhs in re.findall(r"assign\s+([^=]+?)\s*=\s*([^;]+);", body):
        aliases.append((lhs.strip(), rhs.strip()))

    fcache: Dict[str, Tuple] = {}
    for cell, inst, conns in re.findall(r"\b(" + _PREFIX + r"\w+)\s+(\\?[\w\[\]\.$]+)\s*\((.*?)\)\s*;", body, re.S):
        short = cell[len(_PREFIX):]
        if short not in fcache:
            c = lib.cell(cell)
            ip = tuple(p for p, v in c.pins.items() if v.direction == "input")
            op = tuple(p for p, v in c.pins.items() if v.direction == "output")
            fx = []
            for p in op:
                f = c.pins[p].function
                if f is None or c.is_sequential:
                    raise ValueError(f"{cell}: sequential or function-less cells are not supported by the importer")
                fx.append(liberty_to_python(f))
            fcache[short] = (ip, op, tuple(fx))
        ip, op, fx = fcache[short]
        pinmap = dict((p, v) for p, v in re.findall(r"\.(\w+)\s*\(\s*([^)]*?)\s*\)", conns))
        ins = [ref(pinmap[p]) for p in ip]
        outs = [ref(pinmap[p]) for p in op]
        nl.cell_gate(short, ip, op, fx, ins, outs, group, inst.lstrip("\\"))
    # outputs: through assigns or direct nets
    alias = {}
    for lhs, rhs in aliases:
        alias[lhs.replace(" ", "")] = rhs
    for o, bits in outputs.items():
        ids = []
        for b in bits:
            src = alias.get(b, b)
            seen = 0
            while src in alias and seen < 10:
                src = alias[src]
                seen += 1
            ids.append(ref(src))
        nl.set_output(o, ids)
    nl.meta["imported"] = True
    return nl
