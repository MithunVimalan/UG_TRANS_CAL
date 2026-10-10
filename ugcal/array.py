"""MAC-array energy model: processing element + operand forwarding + SRAM traffic.

Model of an N x N output-stationary systolic array computing C = A * B
(Kung 1982 style): every processing element (PE) is the verified MAC of
ugcal.arith.mac with operand registers that also forward A to the right and
B downwards.  Per MAC:

  E_MAC,array = E_PE                                   (gate level, D8)
              + E_fwd = 2 n tpc (1/2) C_w L_pitch V^2   (A and B forwarding wires)
              + E_sram,in  = (2 n / (w_word N)) E_word  (operands read once per N reuses)
              + E_sram,out = (W / w_word) E_word / K    (one result written per K MACs)
              + E_clk,tree (unknown wiring of the clock tree; class I unless implemented)

Inputs are Params (with evidence class); unknowns stay explicit.  The model
deliberately omits DRAM/off-chip I/O (no SKY130 system data) and global
interconnect beyond the array edge.
"""
from __future__ import annotations

import math
from typing import Dict, Optional

from .provenance import Cls, Input, Param, Result, val
from .units import q


def forwarding_energy(n_bits: int, tpc: float, C_per_um: Input, pitch: Input, V: Input) -> Result:
    e = 2 * n_bits * tpc * 0.5 * val(C_per_um) * val(pitch) * val(V) ** 2
    return Result("E_fwd", e, Cls.E, "2 n tpc (1/2) C_w L V^2", [C_per_um, pitch, V],
                  assumptions=[f"{n_bits}-bit A and B links, {tpc} transitions per bit per cycle",
                               "point-to-point wire of one PE pitch; driver/receiver pin energy is already in E_PE"],
                  unit="J")


def sram_energy_per_mac(n_bits: int, W_acc: int, w_word: int, reuse_N: int, K: int, E_word: Input) -> Result:
    reads = 2 * n_bits / (w_word * reuse_N)
    writes = (W_acc / w_word) / K
    e = (reads + writes) * val(E_word)
    return Result("E_sram/MAC", e, Cls.E, "(2n/(w N) + (W/w)/K) E_word", [E_word],
                  assumptions=[f"operands read once and reused N={reuse_N} times", f"one {W_acc}-bit result per K={K} MACs",
                               f"{w_word}-bit words, energy per access E_word independent of read/write"],
                  unit="J")


def array_energy(E_PE: Input, E_fwd: Result, E_sram: Result, E_clk_tree: Optional[Input] = None) -> Result:
    e = val(E_PE) + E_fwd.value + E_sram.value
    inputs = [E_PE, E_fwd, E_sram]
    assumptions = []
    if E_clk_tree is not None and getattr(E_clk_tree, "available", True):
        e = e + val(E_clk_tree)
        inputs.append(E_clk_tree)
    else:
        assumptions.append("clock-tree wiring and buffers not included (unknown before CTS)")
    return Result("E_MAC,array", e, Cls.E, "E_PE + E_fwd + E_sram (+ E_clk,tree)", inputs,
                  assumptions=assumptions, unit="J")


def pe_density(area_um2: float, utilisation: float) -> float:
    """PEs per mm^2 for a given placement utilisation (cell area / core area)."""
    return 1e6 * utilisation / area_um2
