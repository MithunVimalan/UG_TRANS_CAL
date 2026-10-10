"""Fundamental (technology-independent) bounds relevant to electronic computation.

Each function returns a ``Result`` that states the governing equation, its
assumptions and the conditions under which it applies.  None of these is the
practical minimum energy of a CMOS gate, multiplier or MAC; see
docs/report/D03_fundamental_limits.md for the applicability discussion.
"""
from __future__ import annotations

import math
from statistics import NormalDist

from . import constants as K
from .provenance import Cls, Input, Param, Result, val
from .units import Quantity, q

_N = NormalDist()


def thermal_energy(T: Input) -> Result:
    kT = val(K.k_B) * val(T, "kT")
    return Result("kT", kT, Cls.A if isinstance(T, Param) and T.cls is Cls.S else Cls.E, "k_B * T",
                  [K.k_B, T], unit="J")


def thermal_voltage(T: Input) -> Result:
    vt = val(K.k_B) * val(T) / val(K.q_e)
    return Result("V_T", vt, Cls.E, "k_B T / q", [K.k_B, T, K.q_e], unit="V")


def landauer(T: Input, bits: float = 1.0) -> Result:
    """Minimum heat released to a bath at T when `bits` of information are erased.

    Bound on the *expected* heat for logically irreversible erasure of `bits`
    bits of Shannon entropy (each erased bit of a uniformly random variable
    = 1 bit), quasi-static limit.  Applies to erasure only: logically
    reversible operations have no such lower bound (Bennett 1973).  Finite-time
    erasure costs more (Proesmans et al. 2020).
    """
    e = val(K.k_B) * val(T) * (K.LN2 * bits)
    return Result(f"E_Landauer({bits:g} bit)", e, Cls.D, "bits * k_B T ln 2", [K.k_B, T],
                  assumptions=["information erased is `bits` bits of Shannon entropy",
                               "heat bath at temperature T; quasi-static (infinitely slow) protocol",
                               "bound on the mean; single realisations can fall below it"],
                  valid_if=["logically irreversible operation", "classical, Markovian bath"],
                  unit="J")


def subthreshold_swing_limit(T: Input) -> Result:
    """Minimum subthreshold swing of a thermionic (Boltzmann-injection) FET, n = 1."""
    ss = val(K.k_B) * val(T) / val(K.q_e) * K.LN10
    return Result("SS_min", ss, Cls.D, "ln(10) k_B T / q (n = 1)", [K.k_B, T, K.q_e],
                  assumptions=["carrier injection over a barrier with a non-degenerate (Boltzmann) tail",
                               "ideal gate coupling (body factor n = 1)"],
                  valid_if=["conventional MOSFET/FinFET/GAA FET; not tunnel FETs or negative-capacitance FETs"],
                  unit="V")


def min_supply_ideal_inverter(T: Input) -> Result:
    """2 ln2 kT/q: minimum supply of an ideal CMOS inverter (Meindl & Davis 2000).

    Not re-derived from the original paper in this project (full text not
    accessible); see source catalogue entry meindl2000.
    """
    v = 2 * K.LN2 * val(K.k_B) * val(T) / val(K.q_e)
    return Result("V_DD,min(ideal)", v, Cls.D, "2 ln2 k_B T / q", [K.k_B, T, K.q_e],
                  assumptions=["ideal MOSFETs with n = 1 subthreshold slope", "unity small-signal gain at the switching point"],
                  valid_if=["static CMOS inverter"], note="via secondary sources; original not inspected",
                  unit="V")


def min_supply_swanson_meindl(T: Input) -> Result:
    """~8 kT/q: smallest supply at which their weak-inversion CMOS inverter model functions."""
    v = 8 * val(K.k_B) * val(T) / val(K.q_e)
    return Result("V_DD,min(Swanson-Meindl)", v, Cls.D, "~8 k_B T / q", [K.k_B, T, K.q_e],
                  assumptions=["weak-inversion (subthreshold) MOS equations", "practical noise-margin requirement"],
                  valid_if=["static CMOS, 1972 device assumptions"], unit="V")


def kTC_noise_rms(C: Input, T: Input) -> Result:
    """Equilibrium RMS voltage noise on a capacitance: sqrt(kT/C) (equipartition).

    Independent of the resistance that sets the bandwidth (Johnson-Nyquist
    noise integrated over the RC bandwidth).
    """
    v = (val(K.k_B) * val(T) / val(C)).sqrt()
    return Result("v_n,rms", v, Cls.D, "sqrt(k_B T / C)", [K.k_B, T, C],
                  assumptions=["node in thermal equilibrium with its resistive environment",
                               "linear capacitance"], unit="V")


def static_node_error_probability(C: Input, V: Input, T: Input) -> Result:
    """Probability that kT/C noise moves a static logic node past mid-rail at one sampling instant.

    p = Q( (V/2) / sqrt(kT/C) ) = Q( sqrt(E_s / (2 kT)) ),  E_s = C V^2 / 2.

    A snapshot bound: it ignores regeneration (a CMOS gate actively restores
    the node), correlation between samples and non-equilibrium noise.  Useful
    to show how far practical node energies are from noise-limited ones.
    """
    sigma = (val(K.k_B) * val(T) / val(C)).sqrt()
    z = float((val(V) / 2) / sigma)
    p = _N.cdf(-z)
    return Result("p_err,node", Quantity(p), Cls.E, "Q((V/2)/sqrt(kT/C))", [K.k_B, T, C, V],
                  assumptions=["Gaussian equilibrium kT/C noise", "decision threshold at V/2",
                               "single independent sample, no regeneration"])


def energy_for_error_probability(p: float, T: Input) -> Result:
    """Stored node energy E_s = C V^2/2 needed so that the snapshot error probability is p.

    Inverse of static_node_error_probability: E_s = 2 kT [Q^-1(p)]^2.
    """
    zq = -_N.inv_cdf(p)
    e = 2 * zq * zq * val(K.k_B) * val(T)
    return Result(f"E_s(p={p:g})", e, Cls.E, "2 k_B T [Q^-1(p)]^2", [K.k_B, T],
                  assumptions=["see static_node_error_probability"], unit="J")


def barrier_for_retention(p: float, T: Input) -> Result:
    """Barrier height E_b such that the Boltzmann factor exp(-E_b/kT) equals p.

    For a bit stored in a double-well with barrier E_b, the per-attempt
    probability of a thermally activated flip scales as exp(-E_b/kT)
    (Arrhenius/Kramers).  The prefactor (attempt frequency x time) is not
    included; this gives the order of magnitude used in switch-scaling
    arguments (e.g. Zhirnov et al. 2003).
    """
    e = math.log(1.0 / p) * val(K.k_B) * val(T)
    return Result(f"E_b(p={p:g})", e, Cls.D, "k_B T ln(1/p)", [K.k_B, T],
                  assumptions=["thermally activated escape over a single barrier",
                               "per-attempt probability; multiply by attempts per lifetime for a reliability budget"],
                  unit="J")


def margolus_levitin_time(E: Input) -> Result:
    """Minimum time for a quantum state to evolve to an orthogonal state: h / (4 E).

    E is the mean energy above the ground state.  Constrains the rate of
    distinguishable state changes per unit of energy, not the delay of a
    dissipative CMOS gate.
    """
    t = val(K.h) / (4 * val(E))
    return Result("t_ML", t, Cls.D, "h / (4 E)", [K.h, E],
                  assumptions=["isolated quantum system", "E = mean energy above ground state"], unit="s")


def mandelstam_tamm_time(dE: Input) -> Result:
    """Minimum orthogonalisation time h / (4 dE) for energy standard deviation dE."""
    t = val(K.h) / (4 * val(dE))
    return Result("t_MT", t, Cls.D, "h / (4 Delta E)", [K.h, dE],
                  assumptions=["isolated quantum system", "Delta E = energy standard deviation"], unit="s")


def ratio(a: Result, b: Result, name: str) -> Result:
    r = a.value / b.value
    return Result(name, r, Cls.E, f"{a.name} / {b.name}", [a, b])
