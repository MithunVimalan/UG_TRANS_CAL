"""Read SKY130 BSIM4 model cards (``*.pm3.spice``): bins and parameters.

The cards are binned: each ``.model <name>.<k>`` covers a range of drawn L
and W (lmin..lmax, wmin..wmax, in metres).  Many parameters are regression
coefficients that become physical only after the simulator applies the
binning (P = P0 + PL/Leff + PW/Weff + PP/(Leff Weff)); expressions in braces
contain the mismatch terms (zero unless mc_mm_switch = 1).  This reader
returns the nominal literal value of each parameter of the bin that covers a
given geometry; use it for documentation and for parameters that are not
binned (oxide thickness, overlap and junction capacitances, model switches),
never to hand-compute Vth or currents (simulate instead).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

_PARAM = re.compile(r"(\w+)\s*=\s*(\{[^}]*\}|[-+]?[0-9.]+(?:[eE][-+]?\d+)?)")


def read_bins(path: str) -> List[Tuple[str, Dict[str, str]]]:
    txt = open(path).read()
    out = []
    for m in re.finditer(r"^\.model\s+(\S+)\s+\w+\s*$(.*?)(?=^\.model|^\.ends|\Z)", txt, re.M | re.S):
        name, body = m.group(1), m.group(2)
        params: Dict[str, str] = {}
        for line in body.splitlines():
            if not line.startswith("+"):
                continue
            for k, v in _PARAM.findall(line):
                params[k.lower()] = v
        out.append((name, params))
    return out


def nominal(v: str) -> float:
    """Literal value, or the first number of a brace expression (the nominal term)."""
    if v.startswith("{"):
        m = re.match(r"\{\s*([-+]?[0-9.]+(?:[eE][-+]?\d+)?)", v)
        if not m:
            raise ValueError(v)
        return float(m.group(1))
    return float(v)


def bin_for(path: str, W_um: float, L_um: float) -> Tuple[str, Dict[str, str]]:
    W, L = W_um * 1e-6, L_um * 1e-6
    for name, p in read_bins(path):
        lmin, lmax, wmin, wmax = (float(p[k]) for k in ("lmin", "lmax", "wmin", "wmax"))
        if lmin <= L * (1 + 1e-9) and L <= lmax * (1 + 1e-9) and wmin <= W * (1 + 1e-9) and W <= wmax * (1 + 1e-9):
            return name, p
    raise KeyError(f"no bin for W={W_um} L={L_um} in {path}")
