"""Validation tests for the dependency-free core (no PDK needed)."""
import math
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ugcal import constants as K  # noqa: E402
from ugcal import fundamental as F  # noqa: E402
from ugcal import switching as S  # noqa: E402
from ugcal import thermal as TH  # noqa: E402
from ugcal.infotheory import mac_entropy_loss, multiplication_entropy_loss  # noqa: E402
from ugcal.mac import MACSpec, accumulator_width, mac_metrics, product_range  # noqa: E402
from ugcal.provenance import Cls, MissingParameter, Param, ProvenanceError, spec, unavailable  # noqa: E402
from ugcal.uncertainty import Normal, interval, monte_carlo  # noqa: E402
from ugcal.units import DimensionError, celsius, parse_unit, q  # noqa: E402


# --------------------------------------------------------------------- units
def test_unit_conversion_and_prefixes():
    assert q(2.302, "fF").to("pF") == pytest.approx(0.002302)
    assert q(1, "pJ").to("fJ") == pytest.approx(1000)
    assert parse_unit("mV/dec").value == pytest.approx(1e-3)
    assert parse_unit("um^2").value == pytest.approx(1e-12)
    assert (q(1, "V") * q(1, "A")).to("W") == pytest.approx(1.0)
    assert (q(1, "F") * q(1, "V") ** 2).to("J") == pytest.approx(1.0)
    assert celsius(25).to("K") == pytest.approx(298.15)


def test_dimension_errors():
    with pytest.raises(DimensionError):
        q(1, "J") + q(1, "W")
    with pytest.raises(DimensionError):
        q(1, "fF").to("pJ")
    with pytest.raises(DimensionError):
        float(q(1, "V"))


# ---------------------------------------------------------------- provenance
def test_unavailable_parameter_raises_and_is_not_substituted():
    p = unavailable("I_gate", "A", "igcmod=0 in the SKY130 cards", authority="foundry gate-leakage data")
    assert not p.available
    with pytest.raises(MissingParameter):
        p.require("gate leakage power")


def test_unlabelled_inputs_rejected():
    with pytest.raises(ProvenanceError):
        F.landauer(q(300, "K"))           # raw quantity, no provenance


def test_param_needs_source_and_matching_unit():
    with pytest.raises(ProvenanceError):
        Param("x", q(1, "fF"), Cls.C)                        # foundry value without source
    with pytest.raises(ProvenanceError):
        Param("x", q(1, "fF"), Cls.C, source="s", unit="V")  # unit mismatch
    Param("x", q(1, "fF"), Cls.C, source="s", unit="fF")


# --------------------------------------------------------------- fundamentals
def test_constants_exact():
    assert K.k_B.value.to("J/K") == 1.380649e-23
    assert K.q_e.value.to("C") == 1.602176634e-19


def test_landauer_and_thermal_voltage_at_300K():
    T = spec("T", q(300, "K"), "K")
    assert F.landauer(T).value.to("J") == pytest.approx(2.870979e-21, rel=1e-6)
    assert F.thermal_voltage(T).value.to("mV") == pytest.approx(25.852, rel=1e-4)
    assert F.subthreshold_swing_limit(T).value.to("mV") == pytest.approx(59.526, rel=1e-4)
    assert F.min_supply_swanson_meindl(T).value.to("mV") == pytest.approx(206.816, rel=1e-4)


def test_noise_error_probability_roundtrip():
    T = spec("T", q(300, "K"), "K")
    E = F.energy_for_error_probability(1e-15, T).value
    # choose C, V with C V^2 / 2 = E
    C = spec("C", q(1, "fF"), "F")
    V = spec("V", (2 * E / q(1, "fF")) ** 0.5, "V")
    p = F.static_node_error_probability(C, V, T).value.value
    assert p == pytest.approx(1e-15, rel=1e-6)


# ------------------------------------------------------------------ switching
def test_activity_conventions_agree():
    C = spec("C", q(10, "fF"), "F")
    V = spec("V", q(1.8, "V"), "V")
    f = 100e6
    a = S.Activity.from_alpha01(0.25, f)
    p1 = S.dynamic_power(C, V, a).value.to("W")
    p_textbook = 0.25 * 10e-15 * 1.8 ** 2 * f
    assert p1 == pytest.approx(p_textbook)
    assert a.tpc == pytest.approx(0.5)


def test_switching_energy_bookkeeping():
    C = spec("C", q(1, "pF"), "F")
    V = spec("V", q(1, "V"), "V")
    assert S.energy_from_supply_per_rise(C, V).value.to("pJ") == pytest.approx(1.0)
    assert S.energy_dissipated_per_transition(C, V).value.to("pJ") == pytest.approx(0.5)


# ---------------------------------------------------------------- arithmetic
def test_accumulator_width_bruteforce():
    for n in (2, 3, 4):
        for K_ in (1, 2, 3, 5, 8):
            for signed in (False, True):
                W = accumulator_width(n, n, K_, signed)
                lo, hi = product_range(n, n, signed)
                smin, smax = K_ * lo, K_ * hi
                if signed:
                    assert -(1 << (W - 1)) <= smin and smax <= (1 << (W - 1)) - 1
                    assert not (-(1 << (W - 2)) <= smin and smax <= (1 << (W - 2)) - 1)
                else:
                    assert smax <= (1 << W) - 1 and smax > (1 << (W - 1)) - 1
    assert accumulator_width(8, 8, 64, True) == 22
    with pytest.raises(ValueError):
        MACSpec(K=64, acc_width=20)


def test_metric_conversions():
    m = mac_metrics(1e-12, 100e6)
    assert m["TOPS_per_W"] == pytest.approx(2.0)
    assert m["MAC_per_s_per_W"] == pytest.approx(1e12)
    assert m["P_W"] == pytest.approx(1e-4)


@pytest.mark.parametrize("n", [4, 6])
def test_all_multiplier_architectures_exhaustive(n):
    from ugcal.arith.multipliers import ARCHS, build_multiplier
    from ugcal.arith.netlist import exhaustive_inputs
    for arch, (pp, red, fin) in ARCHS.items():
        for signed in ([False, True] if pp == "booth4" else [pp == "bw"]):
            nl = build_multiplier(n, n, pp, red, fin, signed)
            ins, nv = exhaustive_inputs({"a": n, "b": n})
            v = nl.simulate(ins, nv)
            for k in range(nv):
                a, b = k & ((1 << n) - 1), k >> n
                if signed:
                    a -= (a >> (n - 1)) << n
                    b -= (b >> (n - 1)) << n
                got = sum(((v[x] >> k) & 1) << i for i, x in enumerate(nl.outputs["p"]))
                assert got == (a * b) % (1 << (2 * n)), (arch, signed, a, b)


def test_mac_variants_random():
    from ugcal.arith.mac import build_mac, simulate_mac
    rnd = random.Random(5)
    n, W = 4, 12
    for variant in ("separate", "fused", "csa_acc"):
        nl = build_mac(n, W, variant, pp="booth4", signed=True)
        seq = [(rnd.randrange(16), rnd.randrange(16), 1 if t % 9 == 0 else 0) for t in range(80)]
        out = simulate_mac(nl, seq, True)
        acc = 0
        ar = br = cr = 0
        for (a, b, c), got in zip(seq, out):
            sa = ar - 16 if ar > 7 else ar
            sb = br - 16 if br > 7 else br
            acc = ((0 if cr else acc) + sa * sb) % (1 << W)
            ar, br, cr = a, b, c
            exp = acc - (1 << W) if acc >> (W - 1) else acc
            assert got == exp, variant


# ---------------------------------------------------------------- info theory
def test_multiplication_entropy_small():
    r = multiplication_entropy_loss(1, False)     # 1x1: products 0 (3/4), 1 (1/4)
    h = -(0.75 * math.log2(0.75) + 0.25 * math.log2(0.25))
    assert r["erased_bits"] == pytest.approx(2 - h)
    assert mac_entropy_loss(8, 22)["erased_bits"] == 16


# -------------------------------------------------------------------- thermal
def test_electrothermal_linear_leakage_analytic():
    # P_leak = a + b (T - T0) -> T = T0 + R (Pd + a + b (T - T0)) => T - T0 = R (Pd + a) / (1 - R b)
    R, Pd, a, b, T0 = 50.0, 0.5, 0.1, 0.004, 300.0
    et = TH.ElectroThermal(T0, R, Pd, lambda T: a + b * (T - T0))
    sol = et.solve()
    assert sol["T_j"] - T0 == pytest.approx(R * (Pd + a) / (1 - R * b), rel=1e-6)
    assert sol["stable"]
    runaway = TH.ElectroThermal(T0, R, Pd, lambda T: a * math.exp((T - T0) / 5.0)).solve(T_hi=2000)
    assert runaway["runaway"]


def test_foster_step_matches_closed_form():
    f = TH.Foster([10.0, 5.0], [1e-3, 1e-1])
    out = f.response([1.0] * 2000, 1e-4)
    assert out[-1] == pytest.approx(f.step(0.2), rel=1e-6)


def test_spreading_formulas():
    k = Param("k_Si", q(148, "W/m/K"), Cls.B, source="test", unit="W/m/K")
    a = spec("a", q(50, "um"), "m")
    iso = TH.spreading_disk_isothermal(a, k).value.to("K/W")
    mean = TH.spreading_disk_uniform_flux_mean(a, k).value.to("K/W")
    mx = TH.spreading_disk_uniform_flux_max(a, k).value.to("K/W")
    assert iso == pytest.approx(1 / (4 * 148 * 50e-6))
    assert iso < mean < mx


# ---------------------------------------------------------------- uncertainty
def test_monte_carlo_linear():
    r = monte_carlo(lambda x, y: 2 * x + y, {"x": Normal(1, 0.1), "y": Normal(0, 0.2)}, n=40000)
    assert r["mean"] == pytest.approx(2.0, abs=0.01)
    assert r["sd"] == pytest.approx(math.sqrt(0.04 + 0.04), rel=0.03)
    assert interval(lambda x: x * x, {"x": (1, 3)}) == (1, 9)


def test_uniform_flux_disk_spreading_by_quadrature():
    """Check R_centre = 1/(pi k a) and R_mean = 8/(3 pi^2 k a) by integrating the
    half-space surface Green's function T = P/(2 pi k r) over a uniform-flux disk."""
    import numpy as np
    k, a, P = 148.0, 50e-6, 1.0
    q_ = P / (math.pi * a * a)
    # centre: T = q/(2 pi k) * int_0^a int_0^2pi (1/r) r dr dphi = q a / k
    T_c = q_ * a / k
    assert T_c / P == pytest.approx(1 / (math.pi * k * a), rel=1e-12)
    # mean: average of the potential phi(r) = int dA'/|r-r'| over the disk (polar quadrature)
    nr, nphi = 400, 400
    rs = (np.arange(nr) + 0.5) / nr * a
    phis = (np.arange(nphi) + 0.5) / nphi * 2 * math.pi
    # potential of a uniform disk at radius r0 (closed form via elliptic integral avoided:
    # integrate in polar coordinates centred on the field point)
    def phi_at(r0):
        th = phis
        # distance from field point to disk edge along direction th
        s = -r0 * np.cos(th) + np.sqrt(a * a - (r0 * np.sin(th)) ** 2)
        return float(np.sum(s) * (2 * math.pi / nphi))   # int_0^2pi s(th) dth
    mean_phi = sum(phi_at(r) * 2 * math.pi * r * (a / nr) for r in rs) / (math.pi * a * a)
    T_m = q_ / (2 * math.pi * k) * mean_phi
    assert T_m / P == pytest.approx(8 / (3 * math.pi ** 2 * k * a), rel=2e-3)


# ------------------------------------------------------------ worked example
def test_worked_example_runs():
    """examples/mac_envelope_example.py: lineage, class-I refusal and the stored headline numbers."""
    import importlib.util
    path = os.path.join(os.path.dirname(__file__), "..", "examples", "mac_envelope_example.py")
    spec_ = importlib.util.spec_from_file_location("mac_envelope_example", path)
    mod = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(mod)
    P = mod.build_inputs()
    out, metrics = mod.envelope(P)
    assert out["P_total"].value.to("W") == pytest.approx(5.603e-12 * 145e6 * 1000 + 5680e-9 * 1000, rel=1e-9)
    assert out["T_j"].value.to("K") == pytest.approx(298.15 + 30 * out["P_total"].value.to("W"), rel=1e-12)
    assert metrics["TOPS_per_W"] == pytest.approx(2 / 5.603, rel=1e-9)
    assert set(out["T_j"].input_classes()) == {"C", "E", "S"}
    with pytest.raises(MissingParameter):
        P["E_M_tree"].require("clock-tree energy")
