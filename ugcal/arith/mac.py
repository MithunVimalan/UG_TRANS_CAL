"""Structural MAC (multiply-accumulate) generators.

Definition used throughout the project (integer MAC):

    ACC[t+1] = (clr ? 0 : ACC[t]) + A[t-1] * B[t-1]       (mod 2^W)

  * A, B: N-bit two's-complement (signed=True) or unsigned operands,
    registered at the MAC input (operand registers, as in a systolic PE);
  * product: 2N bits, sign-extended (or zero-extended) to W bits;
  * accumulator: W bits, wrap-around (modular) overflow - the width W is
    chosen so that overflow cannot occur for K accumulations (see
    ugcal.mac.accumulator_width), so no saturation logic is needed;
  * no rounding (exact integer arithmetic);
  * latency: 2 clock cycles from operand presentation to the accumulator
    update; initiation interval 1 (one MAC per cycle).

Variants (same arithmetic, different circuits):

  'separate'  multiplier (tree + CPA) -> W-bit adder -> ACC register
  'fused'     ACC bits enter the multiplier's reduction tree as an extra row,
              one W-bit CPA per cycle
  'csa_acc'   accumulator kept in carry-save form (2W register bits); the
              reduction tree absorbs both ACC rows, so no carry-propagate
              adder is in the loop; a CPA converts the result once per K
              accumulations (it is outside the loop and reported separately)
"""
from __future__ import annotations

from typing import List, Tuple

from .multipliers import (CONST0, CONST1, _compress_constants, cpa, pp_and, pp_baugh_wooley,
                          pp_booth4, reduce_dadda, reduce_wallace)
from .netlist import Netlist


def _extend(bits: List[int], width: int, signed: bool) -> List[int]:
    if len(bits) >= width:
        return bits[:width]
    fill = bits[-1] if signed else CONST0
    return bits + [fill] * (width - len(bits))


def _pp(nl, a, b, width, pp, signed):
    if pp == "and":
        return pp_and(nl, a, b, width)
    if pp == "bw":
        return pp_baugh_wooley(nl, a, b, width)
    if pp == "booth4":
        return pp_booth4(nl, a, b, width, signed)
    raise ValueError(pp)


def _reduce(nl, cols, red):
    return reduce_dadda(nl, cols) if red == "dadda" else reduce_wallace(nl, cols)


def build_mac(n: int, acc_width: int, variant: str = "separate", pp: str = "booth4", red: str = "dadda",
              final: str = "kogge_stone", acc_adder: str = "kogge_stone", signed: bool = True,
              name: str = "") -> Netlist:
    W = acc_width
    nl = Netlist(name or f"mac{n}_w{W}_{variant}_{pp}_{red}_{final}")
    nl.meta.update(dict(n=n, W=W, variant=variant, pp=pp, red=red, final=final, acc_adder=acc_adder,
                        signed=signed))
    a_in = nl.add_input("a", n)
    b_in = nl.add_input("b", n)
    clr = nl.add_input("clr", 1)[0]
    # operand registers
    a = [nl.DFF(x, "reg_op") for x in a_in]
    b = [nl.DFF(x, "reg_op") for x in b_in]
    clr_r = nl.DFF(clr, "reg_op")
    keep = nl.INV(clr_r, "acc")
    pw = 2 * n
    if variant == "separate":
        cols = _pp(nl, a, b, pw, pp, signed)
        cols = _reduce(nl, cols, red)
        prod = cpa(nl, cols, final)
        prod = _extend(prod, W, signed)
        acc_q = [nl.new_net("acc_q") for _ in range(W)]
        fb = [nl.AND2(q, keep, "acc") for q in acc_q]
        cols2 = [[x for x in (fb[i], prod[i]) if x != CONST0] for i in range(W)]
        s = cpa(nl, cols2, acc_adder, group="acc")
        d = s
        _close_loop(nl, acc_q, d, "reg_acc")
        nl.set_output("acc", acc_q)
    elif variant == "fused":
        # partial products generated modulo 2^W (exact sign/zero extension)
        cols = _pp_wide(nl, a, b, W, pp, signed) if W > pw else _pp(nl, a, b, pw, pp, signed)
        acc_q = [nl.new_net("acc_q") for _ in range(W)]
        fb = [nl.AND2(q, keep, "acc") for q in acc_q]
        for i in range(W):
            cols[i].append(fb[i])
        cols = _reduce(nl, cols, red)
        s = cpa(nl, cols, final)
        _close_loop(nl, acc_q, s[:W], "reg_acc")
        nl.set_output("acc", acc_q)
    elif variant == "csa_acc":
        cols = _pp_wide(nl, a, b, W, pp, signed) if W > pw else _pp(nl, a, b, pw, pp, signed)
        acc_s = [nl.new_net("acc_s") for _ in range(W)]
        acc_c = [nl.new_net("acc_c") for _ in range(W)]
        fb_s = [nl.AND2(q, keep, "acc") for q in acc_s]
        fb_c = [nl.AND2(q, keep, "acc") for q in acc_c]
        for i in range(W):
            cols[i].append(fb_s[i])
            cols[i].append(fb_c[i])
        cols = _reduce(nl, cols, red)
        # the tree leaves at most two bits per column: register both rows
        # (both rows have weight 2^i at index i); no CPA inside the loop
        row_s = [c[0] if len(c) > 0 else CONST0 for c in cols]
        row_c = [c[1] if len(c) > 1 else CONST0 for c in cols]
        _close_loop(nl, acc_s, row_s[:W], "reg_acc")
        _close_loop(nl, acc_c, row_c[:W], "reg_acc")
        # output CPA (outside the loop; needed once per K accumulations)
        cols_out = [[x for x in (acc_s[i], acc_c[i]) if x != CONST0] for i in range(W)]
        out = cpa(nl, cols_out, final, group="outcpa")
        nl.set_output("acc", out[:W])
    else:
        raise ValueError(variant)
    # remove logic whose outputs are unused (carries beyond the product width,
    # prefix-tree terms that no sum bit needs); synthesis would remove it too
    nl.meta["pruned_gates"] = nl.prune()
    return nl


def _pp_wide(nl, a, b, W, pp, signed):
    """Partial-product columns of a*b modulo 2^W (W > 2n).

    The Booth and Baugh-Wooley generators are exact over the integers (their
    sign-handling constants are taken modulo 2^width), and the AND array of
    unsigned operands is exact by construction, so generating them with
    width W gives the W-bit (sign- or zero-extended) product directly.
    """
    if pp == "booth4":
        return pp_booth4(nl, a, b, W, signed)
    if pp == "bw":
        return pp_baugh_wooley(nl, a, b, W)
    if pp == "and":
        return pp_and(nl, a, b, W)
    raise ValueError(pp)


def _close_loop(nl: Netlist, q_nets: List[int], d_nets: List[int], group: str) -> None:
    """Create DFFs whose outputs are the pre-allocated nets q_nets."""
    for q, d in zip(q_nets, d_nets):
        outs = nl.gate("DFF", [d], group)
        # rewire: replace the new output net by the pre-allocated q net
        g = nl.gates[-1]
        new_q = outs[0]
        g.outs = (q,)
        nl._driver[q] = len(nl.gates) - 1
        del nl._driver[new_q]


def simulate_mac(nl: Netlist, seq: List[Tuple[int, int, int]], signed: bool) -> List[int]:
    """Cycle-accurate simulation (one trajectory).  seq = [(a, b, clr), ...].

    Returns the ACC output (as integer, two's complement interpreted if signed)
    after each clock edge.
    """
    n = nl.meta["n"]
    W = nl.meta["W"]
    dffs = [g for g in nl.gates if g.kind == "DFF"]
    state = {g.outs[0]: 0 for g in dffs}
    out = []
    for a, b, c in seq:
        ins = {"a": [(a >> i) & 1 for i in range(n)], "b": [(b >> i) & 1 for i in range(n)], "clr": [c & 1]}
        v = nl.simulate(ins, 1, state)
        # clock edge
        state = {g.outs[0]: v[g.ins[0]] for g in dffs}
        v2 = nl.simulate(ins, 1, state)
        x = 0
        for i, net in enumerate(nl.outputs["acc"]):
            x |= (v2[net] & 1) << i
        if signed and x >> (W - 1):
            x -= 1 << W
        out.append(x)
    return out
