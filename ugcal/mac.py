"""MAC specification, accumulator sizing, metric conversions and energy accounting.

Operation-counting convention (stated once, used everywhere):
  * 1 MAC = 1 multiplication + 1 addition.
  * Reported "ops" count each MAC as 2 operations (the convention used by most
    accelerator papers for TOPS); MAC/s and ops/s are always reported together.
  * Energy per MAC = average total energy over a window containing an integer
    number of MACs (dynamic + leakage + clock), divided by the number of MACs.
  * TOPS/W = 2 * (MAC/s/W) / 1e12 = 2 / (E_MAC [pJ]).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


def product_range(n: int, m: int, signed: bool):
    if signed:
        amin, amax = -(1 << (n - 1)), (1 << (n - 1)) - 1
        bmin, bmax = -(1 << (m - 1)), (1 << (m - 1)) - 1
    else:
        amin, amax, bmin, bmax = 0, (1 << n) - 1, 0, (1 << m) - 1
    cands = [amin * bmin, amin * bmax, amax * bmin, amax * bmax]
    return min(cands), max(cands)


def accumulator_width(n: int, m: int, K: int, signed: bool) -> int:
    """Minimum two's-complement (signed) or unsigned width that holds any sum of K products exactly.

    Derived from the exact product range: lo = K * min(a*b), hi = K * max(a*b).
    Signed: smallest W with -2^(W-1) <= lo and hi <= 2^(W-1) - 1.
    Unsigned: smallest W with hi <= 2^W - 1.
    """
    pmin, pmax = product_range(n, m, signed)
    lo, hi = K * pmin, K * pmax
    W = 1
    while True:
        if signed:
            if -(1 << (W - 1)) <= lo and hi <= (1 << (W - 1)) - 1:
                return W
        else:
            if hi <= (1 << W) - 1:
                return W
        W += 1


@dataclass
class MACSpec:
    n_a: int = 8
    n_b: int = 8
    signed: bool = True
    K: int = 64                    # accumulations between clears (dot-product length)
    acc_width: Optional[int] = None
    arithmetic: str = "integer"    # 'integer' only here; floating point is out of scope
    overflow: str = "none (W sized for K terms; wrap-around otherwise)"
    rounding: str = "none (exact)"
    latency_cycles: int = 2
    initiation_interval: int = 1

    def __post_init__(self):
        need = accumulator_width(self.n_a, self.n_b, self.K, self.signed)
        if self.acc_width is None:
            self.acc_width = need
        elif self.acc_width < need:
            raise ValueError(f"accumulator width {self.acc_width} < required {need} for K={self.K}")


def mac_metrics(E_mac_J: float, f_clk_hz: float, macs_per_cycle: float = 1.0) -> Dict[str, float]:
    """Consistent set of efficiency/throughput numbers from energy per MAC and clock."""
    mac_s = f_clk_hz * macs_per_cycle
    return dict(E_MAC_pJ=E_mac_J * 1e12, MAC_per_s=mac_s, ops_per_s=2 * mac_s,
                P_W=E_mac_J * mac_s, MAC_per_s_per_W=1.0 / E_mac_J, TOPS_per_W=2.0 / E_mac_J / 1e12)


# Functional groups used by the generators (ugcal.arith) -> MAC energy categories
CATEGORY = {
    "pp": "partial-product generation",
    "enc": "Booth encoding",
    "red": "partial-product reduction",
    "cpa": "final carry-propagate addition",
    "acc": "accumulation (adder + clear gating)",
    "outcpa": "output conversion CPA (once per K MACs)",
    "reg_op": "operand registers",
    "reg_acc": "accumulator registers",
    "clk": "clock net (flip-flop clock pins)",
    "inputs": "primary-input nets (driven from outside the block)",
}


def energy_accounting(power: Dict[str, object], macs: int, exclude_input_nets: bool = True,
                      outcpa_amortise_K: Optional[int] = None) -> Dict[str, object]:
    """Split a ugcal.gatesim power result into per-MAC energy categories.

    Every instance belongs to exactly one group and every net's switching
    energy is charged to the group of its driver (clock net to 'clk'), so the
    categories sum to the total without double counting.  The output CPA of a
    carry-save accumulator runs once per K accumulations; when
    ``outcpa_amortise_K`` is given its simulated per-cycle energy is scaled by
    1/K (it was simulated toggling every cycle).
    """
    rows = {}
    total = 0.0
    for grp, r in power["by_group"].items():
        if exclude_input_nets and grp == "inputs":
            continue
        e = r["switching_J"] + r["internal_J"] + r["leakage_J"]
        if grp == "outcpa" and outcpa_amortise_K:
            e = e / outcpa_amortise_K
        rows[grp] = dict(category=CATEGORY.get(grp, grp), E_per_MAC_J=e / macs,
                         switching=r["switching_J"] / macs, internal=r["internal_J"] / macs,
                         leakage=r["leakage_J"] / macs)
        total += e
    for g in rows.values():
        g["share"] = g["E_per_MAC_J"] / (total / macs) if total else 0.0
    return dict(by_group=rows, E_per_MAC_J=total / macs)
