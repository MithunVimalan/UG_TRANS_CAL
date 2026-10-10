"""Benchmarking a candidate multiplier/MAC against its predicted limits.

Evidence ladder (a result is reported with the highest level actually reached):

  0 FUNCTIONAL          arithmetic verified (exhaustive or randomised) in RTL/gate model
  1 CIRCUIT_SIMULATED   transistor-level SPICE with foundry models (cells as used)
  2 SYNTHESIZED         mapped to a characterised library; STA/power with wire-load or no wires
  3 IMPLEMENTED         placed and routed
  4 POST_LAYOUT         extracted parasitics (SPEF) back-annotated; STA/power re-run
  5 THERMALLY_VALIDATED temperature computed/measured with the stated boundary conditions
  6 SILICON_MEASURED    measured on fabricated silicon with stated instruments/uncertainty

Consistency criterion between a measurement (or higher-level result) x_m
with expanded uncertainty U_m and a prediction x_p with expanded uncertainty
U_p: the normalised error E_n = (x_m - x_p) / sqrt(U_m^2 + U_p^2); |E_n| <= 1
means consistent (the E_n statistic used in interlaboratory comparisons, ISO
13528).  When the prediction is an interval [lo, hi] (bounded uncertainty), a
result is consistent if it lies inside the interval widened by U_m.
"""
from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


class Level(enum.IntEnum):
    FUNCTIONAL = 0
    CIRCUIT_SIMULATED = 1
    SYNTHESIZED = 2
    IMPLEMENTED = 3
    POST_LAYOUT = 4
    THERMALLY_VALIDATED = 5
    SILICON_MEASURED = 6


def en_number(x_m: float, U_m: float, x_p: float, U_p: float) -> float:
    return (x_m - x_p) / math.sqrt(U_m ** 2 + U_p ** 2)


def consistent(x_m: float, U_m: float, x_p: float = None, U_p: float = None,
               interval: Tuple[float, float] = None) -> Dict[str, object]:
    if interval is not None:
        lo, hi = interval
        ok = (lo - U_m) <= x_m <= (hi + U_m)
        return dict(consistent=ok, method="interval", lo=lo, hi=hi)
    en = en_number(x_m, U_m, x_p, U_p)
    return dict(consistent=abs(en) <= 1, method="E_n", E_n=en)


@dataclass
class Candidate:
    name: str
    level: Level
    metrics: Dict[str, float]                         # e.g. E_op_J, f_max_Hz, area_m2, P_leak_W
    conditions: Dict[str, str]                        # corner, V, T, activity source, loads
    uncertainty: Dict[str, float] = field(default_factory=dict)   # relative expanded uncertainty per metric

    def gap_to(self, bound_name: str, bound_value: float, metric: str) -> Dict[str, float]:
        v = self.metrics[metric]
        return dict(candidate=self.name, metric=metric, value=v, bound=bound_name, bound_value=bound_value,
                    ratio=v / bound_value, decades=math.log10(v / bound_value))


REQUIRED_FIELDS = ["operand_width", "arithmetic", "functional_check", "cells", "transistors", "area_um2",
                   "critical_path_s", "latency_cycles", "initiation_interval", "throughput_ops_s",
                   "P_dynamic_W", "P_leakage_W", "P_total_W", "E_op_J", "EDP_Js", "T_junction_K",
                   "power_density_W_m2", "VDD_V", "f_clk_Hz", "corner", "activity_source", "output_load_F",
                   "interconnect"]


def missing_fields(record: Dict[str, object]) -> List[str]:
    """Fields of the benchmark record that are absent (must be reported as 'not established')."""
    return [k for k in REQUIRED_FIELDS if k not in record or record[k] is None]
