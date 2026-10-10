"""Switching energy, dynamic/leakage power and activity conventions.

Activity conventions (the most common source of factor-of-two errors):

  alpha01   probability that a node makes a 0->1 transition in a clock cycle.
            Textbook form: P_dyn = alpha01 * C * V^2 * f.
  tpc       transitions per cycle, counting both edges (0->1 and 1->0).
            For a stationary signal tpc = 2 * alpha01.
  density   transitions per second, both edges (OpenSTA/Synopsys 'toggle
            rate'/'density'): density = tpc * f.  P_dyn = 1/2 * C * V^2 * density.

All three describe the same physics; ``Activity`` stores density and converts.

Energy bookkeeping for one node of capacitance C charged from a DC rail V
through any (possibly nonlinear) resistive pull-up and discharged to ground:
  energy drawn from the supply on a 0->1 transition:     C V^2
  energy stored on C after the 0->1 transition:          C V^2 / 2
  energy dissipated in the pull-up during 0->1:          C V^2 / 2
  energy dissipated in the pull-down during 1->0:        C V^2 / 2 (the stored energy)
  average dissipated per transition (either edge):       C V^2 / 2
These hold for step-like charging from a constant voltage source regardless
of the switch resistance; they do NOT hold for adiabatic (ramped-supply)
charging, charge recycling, or nonlinear C(V) (use the charge integral).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .provenance import Cls, Input, Param, Result, val
from .units import Quantity, q


@dataclass(frozen=True)
class Activity:
    density_per_s: float          # transitions per second, both edges
    f_clk_hz: Optional[float] = None
    duty: Optional[float] = None  # probability of logic 1

    @classmethod
    def from_alpha01(cls, alpha01: float, f_clk_hz: float, duty: Optional[float] = None) -> "Activity":
        if not 0 <= alpha01 <= 0.5:
            raise ValueError("alpha01 must be in [0, 0.5] for a stationary signal")
        return cls(2 * alpha01 * f_clk_hz, f_clk_hz, duty)

    @classmethod
    def from_tpc(cls, tpc: float, f_clk_hz: float, duty: Optional[float] = None) -> "Activity":
        return cls(tpc * f_clk_hz, f_clk_hz, duty)

    @property
    def tpc(self) -> float:
        if not self.f_clk_hz:
            raise ValueError("clock frequency unknown; tpc undefined")
        return self.density_per_s / self.f_clk_hz

    @property
    def alpha01(self) -> float:
        return self.tpc / 2


def energy_from_supply_per_rise(C: Input, V: Input) -> Result:
    e = val(C) * val(V) ** 2
    return Result("E_supply,0->1", e, Cls.E, "C V^2", [C, V],
                  assumptions=["step charging from a constant-voltage rail", "linear C"], unit="J")


def energy_dissipated_per_transition(C: Input, V: Input) -> Result:
    e = 0.5 * val(C) * val(V) ** 2
    return Result("E_diss,transition", e, Cls.E, "C V^2 / 2", [C, V],
                  assumptions=["step charging/discharging from constant-voltage rails", "linear C",
                               "full-swing transition"], unit="J")


def dynamic_power(C: Input, V: Input, act: Activity) -> Result:
    p = 0.5 * val(C) * val(V) ** 2 * act.density_per_s
    a = Param("activity density", q(act.density_per_s, "1/s"), Cls.S, source="design-spec", unit="1/s",
              note="transitions per second, both edges")
    return Result("P_dyn", p, Cls.E, "1/2 C V^2 density  (= alpha01 C V^2 f)", [C, V, a],
                  assumptions=["full-swing transitions", "C is the total switched capacitance of the node"],
                  unit="W")


def leakage_power(V: Input, I_leak: Input) -> Result:
    p = val(V) * val(I_leak)
    return Result("P_leak", p, Cls.E, "V_DD I_leak", [V, I_leak], unit="W",
                  assumptions=["I_leak is the total static supply current in the stated input state and temperature"])


def short_circuit_power_veendrick(beta: Input, V: Input, Vt: Input, tau: Input, f: Input) -> Result:
    """Veendrick (1984) estimate for an unloaded symmetric inverter.

    P_sc = (beta/12) (V - 2 Vt)^3 tau f.  Approximate; the formula was not
    re-checked against the original paper in this project (paywalled).  Prefer
    characterised internal power (Liberty) which already includes short-circuit
    current; adding this on top of Liberty internal power double counts.
    """
    vov = val(V) - 2 * val(Vt)
    if vov.value <= 0:
        p = Quantity(0.0, (2, 1, -3, 0, 0))
    else:
        p = val(beta) / 12 * vov ** 3 * val(tau) * val(f)
    return Result("P_sc", p, Cls.E, "(beta/12)(V_DD - 2V_T)^3 tau f", [beta, V, Vt, tau, f],
                  assumptions=["symmetric inverter, no load", "linear input ramp of duration tau",
                               "square-law devices"], note="formula not verified against primary source",
                  unit="W")


def energy_per_operation(P_avg: Input, throughput: Input) -> Result:
    e = val(P_avg) / val(throughput)
    return Result("E_op", e, Cls.E, "P_avg / throughput", [P_avg, throughput],
                  assumptions=["P_avg averaged over a window containing an integer number of operations",
                               "steady-state operation at the stated throughput"], unit="J")


def edp(E: Input, t: Input) -> Result:
    return Result("EDP", val(E) * val(t), Cls.E, "E * t", [E, t], unit="J s")


def alpha_power_delay(V, Vt, alpha, k):
    """Sakurai-Newton alpha-power-law delay model t = k V / (V - Vt)^alpha (model only)."""
    if V <= Vt:
        return math.inf
    return k * V / (V - Vt) ** alpha


def fit_alpha_power(Vs, ts):
    """Least-squares fit of (Vt, alpha, k) to delay-vs-supply data (log-domain grid search + refine)."""
    import itertools
    best = None
    vmin = min(Vs)
    for vt in [i * 0.005 for i in range(0, int(vmin / 0.005))]:
        for a in [1.0 + 0.01 * j for j in range(0, 101)]:
            # k by closed form in log domain
            logs = [math.log(t) - math.log(V / (V - vt) ** a) for V, t in zip(Vs, ts)]
            lk = sum(logs) / len(logs)
            err = sum((l - lk) ** 2 for l in logs)
            if best is None or err < best[0]:
                best = (err, vt, a, math.exp(lk))
    err, vt, a, k = best
    return dict(Vt=vt, alpha=a, k=k, rms_log_err=math.sqrt(err / len(Vs)))
