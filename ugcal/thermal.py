"""Thermal models: steady state, spreading, transient networks, electro-thermal coupling.

Every function states its model.  Thermal resistances and capacitances of a
real package/die/heat-sink are *not* supplied by this module (they are
package- and board-specific, class B/C data from datasheets or measurements,
or class I when unknown); the functions take them as Params.

Conventions: temperatures in K (absolute) or K (differences); power in W;
thermal resistance in K/W; thermal capacitance in J/K.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

from .provenance import Cls, Input, Param, Result, val
from .units import Quantity, q

# ---------------------------------------------------------------------------
# steady state
# ---------------------------------------------------------------------------

def junction_temperature(T_ref: Input, P: Input, R_th: Input, name: str = "T_j") -> Result:
    """T_j = T_ref + P * R_th (lumped, steady state, single path)."""
    T = val(T_ref) + val(P) * val(R_th)
    return Result(name, T, Cls.E, "T_ref + P R_th", [T_ref, P, R_th], unit="K",
                  assumptions=["steady state", "all dissipated power flows through R_th",
                               "R_th measured/defined for the same boundary conditions (e.g. JEDEC board, still air)"],
                  valid_if=["theta_JA is a package-comparison metric (JESD51-2); for a real board use "
                            "theta_JC/psi_JT with measured case/board temperatures"])


def series(*Rs: Input, name: str = "R_series") -> Result:
    tot = val(Rs[0])
    for r in Rs[1:]:
        tot = tot + val(r)
    return Result(name, tot, Cls.E, " + ".join(getattr(r, "name", "?") for r in Rs), list(Rs), unit="K/W")


def max_power(T_max: Input, T_ref: Input, R_th: Input) -> Result:
    p = (val(T_max) - val(T_ref)) / val(R_th)
    return Result("P_max,thermal", p, Cls.E, "(T_j,max - T_ref) / R_th", [T_max, T_ref, R_th], unit="W",
                  assumptions=["steady state", "leakage evaluated at T_j,max must be subtracted to obtain the dynamic budget"])


# ---------------------------------------------------------------------------
# conduction / spreading in silicon
# ---------------------------------------------------------------------------

def slab_resistance(thickness: Input, k: Input, area: Input) -> Result:
    r = val(thickness) / (val(k) * val(area))
    return Result("R_slab", r, Cls.E, "t / (k A)", [thickness, k, area], unit="K/W",
                  assumptions=["1-D conduction (heat source covers the whole area)", "constant k"])


def spreading_disk_isothermal(radius: Input, k: Input) -> Result:
    """Isothermal circular contact of radius a on a half-space: R = 1/(4 k a)."""
    r = 1.0 / (4 * val(k) * val(radius))
    return Result("R_spread,disk,iso", r, Cls.D, "1 / (4 k a)", [radius, k], unit="K/W",
                  assumptions=["semi-infinite homogeneous medium", "isothermal source", "other boundaries adiabatic"])


def spreading_disk_uniform_flux_mean(radius: Input, k: Input) -> Result:
    """Uniform-flux disk on a half-space, mean source temperature: R = 8/(3 pi^2 k a)."""
    r = 8.0 / (3 * math.pi ** 2 * val(k) * val(radius))
    return Result("R_spread,disk,flux,mean", r, Cls.D, "8 / (3 pi^2 k a)", [radius, k], unit="K/W",
                  assumptions=["semi-infinite homogeneous medium", "uniform heat flux over the disk"])


def spreading_disk_uniform_flux_max(radius: Input, k: Input) -> Result:
    """Uniform-flux disk on a half-space, centre (maximum) temperature: R = 1/(pi k a)."""
    r = 1.0 / (math.pi * val(k) * val(radius))
    return Result("R_spread,disk,flux,max", r, Cls.D, "1 / (pi k a)", [radius, k], unit="K/W",
                  assumptions=["semi-infinite homogeneous medium", "uniform heat flux over the disk"])


def diffusion_time(L: Input, k: Input, rho: Input, cp: Input) -> Result:
    """Characteristic conduction time L^2 / alpha, alpha = k / (rho c_p)."""
    alpha = val(k) / (val(rho) * val(cp))
    t = val(L) ** 2 / alpha
    return Result("tau_diff", t, Cls.E, "L^2 rho c_p / k", [L, k, rho, cp], unit="s",
                  assumptions=["order-of-magnitude; exact prefactor depends on geometry and boundary conditions"])


def adiabatic_rise(E: Input, volume: Input, rho: Input, cp: Input) -> Result:
    """Temperature rise if energy E is deposited in a volume with no heat loss."""
    dT = val(E) / (val(volume) * val(rho) * val(cp))
    return Result("dT_adiabatic", dT, Cls.E, "E / (V rho c_p)", [E, volume, rho, cp], unit="K",
                  assumptions=["no conduction during the deposition (upper bound on the local rise)"])


# ---------------------------------------------------------------------------
# transient networks
# ---------------------------------------------------------------------------

@dataclass
class Foster:
    """Foster network Z(t) = sum R_i (1 - exp(-t/tau_i)) (fitted, non-physical nodes)."""
    R: Sequence[float]      # K/W
    tau: Sequence[float]    # s

    def step(self, t: float) -> float:
        return sum(r * (1 - math.exp(-t / ta)) for r, ta in zip(self.R, self.tau))

    def response(self, P: Sequence[float], dt: float) -> List[float]:
        """Temperature rise for piecewise-constant power samples P[k] over steps dt (exact ZOH)."""
        state = [0.0] * len(self.R)
        out = []
        decay = [math.exp(-dt / ta) for ta in self.tau]
        for p in P:
            for i, (r, d) in enumerate(zip(self.R, decay)):
                state[i] = state[i] * d + p * r * (1 - d)
            out.append(sum(state))
        return out


def rc_network_transient(G: List[List[float]], C: Sequence[float], P_of_t: Callable[[float], Sequence[float]],
                         T0: Sequence[float], t_end: float, dt: float, G_amb: Sequence[float],
                         T_amb: float) -> Tuple[List[float], List[List[float]]]:
    """Implicit-Euler solution of C dT/dt = -G T - G_amb (T - T_amb) + P(t).

    G: node-to-node conductance matrix (W/K, symmetric, off-diagonal = -g_ij,
    diagonal = sum of g_ij); G_amb: conductance of each node to ambient.
    Physically based (Cauer-type) networks such as HotSpot grids fit here.
    """
    import numpy as np
    n = len(C)
    Gm = np.array(G, dtype=float) + np.diag(G_amb)
    Cm = np.diag(C)
    A = Cm / dt + Gm
    T = np.array(T0, dtype=float)
    ts, Ts = [0.0], [T.tolist()]
    t = 0.0
    while t < t_end - 1e-15:
        t += dt
        rhs = Cm @ T / dt + np.array(P_of_t(t)) + np.array(G_amb) * T_amb
        T = np.linalg.solve(A, rhs)
        ts.append(t)
        Ts.append(T.tolist())
    return ts, Ts


# ---------------------------------------------------------------------------
# electro-thermal coupling
# ---------------------------------------------------------------------------

def leakage_vs_T_from_points(points: Sequence[Tuple[float, float]]) -> Callable[[float], float]:
    """Log-linear interpolation/extrapolation of leakage power P(T) through (T_K, P_W) points.

    Equivalent to an exponential P = P0 exp((T - T0)/T_char) between points.
    Extrapolation beyond the outermost points uses the nearest segment and
    must be flagged by the caller.
    """
    pts = sorted(points)
    if len(pts) < 2:
        raise ValueError("need at least two (T, P) points")

    def f(T: float) -> float:
        i = 0
        while i < len(pts) - 2 and T > pts[i + 1][0]:
            i += 1
        (T0, P0), (T1, P1) = pts[i], pts[i + 1]
        s = (math.log(P1) - math.log(P0)) / (T1 - T0)
        return math.exp(math.log(P0) + s * (T - T0))

    return f


@dataclass
class ElectroThermal:
    T_amb: float                            # K
    R_th: float                             # K/W
    P_dyn: float                            # W (temperature-independent part)
    P_leak: Callable[[float], float]        # W as a function of T (K)

    def g(self, T: float) -> float:
        return self.T_amb + self.R_th * (self.P_dyn + self.P_leak(T)) - T

    def solve(self, T_hi: float = 600.0, n: int = 4000) -> dict:
        """Find the lowest stable fixed point T = T_amb + R (P_dyn + P_leak(T)).

        Returns dict(T_j, P_total, stable, runaway).  Runaway: no fixed point
        below T_hi (the self-consistent temperature does not exist within the
        modelled range).  Stability: R dP_leak/dT < 1 at the fixed point.
        """
        lo = self.T_amb
        prev_T, prev_g = lo, self.g(lo)
        for k in range(1, n + 1):
            T = lo + (T_hi - lo) * k / n
            gv = self.g(T)
            if prev_g >= 0 and gv < 0:
                a, b = prev_T, T
                for _ in range(80):
                    m = 0.5 * (a + b)
                    if self.g(m) >= 0:
                        a = m
                    else:
                        b = m
                Tj = 0.5 * (a + b)
                h = 1e-3
                slope = self.R_th * (self.P_leak(Tj + h) - self.P_leak(Tj - h)) / (2 * h)
                return dict(T_j=Tj, P_total=self.P_dyn + self.P_leak(Tj), loop_gain=slope,
                            stable=slope < 1, runaway=False)
            prev_T, prev_g = T, gv
        return dict(T_j=math.inf, P_total=math.inf, loop_gain=math.inf, stable=False, runaway=True)


def max_dynamic_power(T_max: float, T_amb: float, R_th: float, P_leak: Callable[[float], float]) -> float:
    """Largest temperature-independent power such that T_j <= T_max in steady state."""
    return (T_max - T_amb) / R_th - P_leak(T_max)
