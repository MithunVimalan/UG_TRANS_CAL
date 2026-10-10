#!/usr/bin/env python3
"""Worked example: from sourced parameters to a MAC performance envelope.

Every input is a Param with an evidence class and a source; every output is a
Result that carries its equation, inputs and assumptions.  Run:

    python3 examples/mac_envelope_example.py

The numbers are those of the carry-save int8 MAC of D8 (gate level, SKY130
tt 25 C 1.8 V); replace the Params to evaluate another design or corner.
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ugcal import fundamental as F  # noqa: E402
from ugcal import switching as S  # noqa: E402
from ugcal import thermal as TH  # noqa: E402
from ugcal.mac import mac_metrics  # noqa: E402
from ugcal.provenance import Cls, MissingParameter, Param, Result, spec, unavailable, val  # noqa: E402
from ugcal.uncertainty import Normal, interval, monte_carlo  # noqa: E402
from ugcal.units import celsius, q  # noqa: E402


def build_inputs():
    P = {}
    P["V_DD"] = Param("V_DD", q(1.8, "V"), Cls.C, source="sky130_fd_sc_hd__tt_025C_1v80.lib nom_voltage", unit="V",
                      valid=(q(1.28, "V"), q(1.95, "V")), note="library characterised 1.28-1.95 V")
    P["E_MAC"] = Param("E_MAC", q(5.603, "pJ"), Cls.E, source="results/power/mac_study.csv (csa_acc_bw_kogge_stone)",
                       unit="J", u_rel=0.20,
                       note="gate level, inertial; SPICE/inertial = 1.19 for the 8x8 array (D7) -> 20 % taken as 1-sigma")
    P["f_clk"] = spec("f_clk", q(145, "MHz"), "Hz", note="sign-off f_max at ss/100 C (D8)")
    P["area"] = Param("A_PE", q(4761 / 0.7, "um^2"), Cls.E, source="Liberty cell area / 0.7 utilisation", unit="m^2")
    P["P_leak_25"] = Param("P_leak,PE(25C)", q(2.24, "nW"), Cls.C, source="Liberty tt_025C_1v80 cell_leakage_power sum",
                           unit="W")
    P["P_leak_100"] = Param("P_leak,PE(100C,ff)", q(5680, "nW"), Cls.C, source="Liberty ff_100C_1v95 sum (upper bound)",
                            unit="W")
    P["P_budget"] = spec("P_budget", q(0.5, "W"), "W", note="example supply/power budget")
    P["theta"] = spec("theta_JA", q(30, "K/W"), "K/W", note="package not chosen: design specification")
    P["T_a"] = spec("T_amb", celsius(25), "K")
    P["T_max"] = Param("T_j,max", celsius(100), Cls.C, source="hottest Liberty characterisation corner", unit="K",
                       note="model-validity limit, not a reliability limit")
    P["E_M_tree"] = unavailable("E_clock_tree", "J", "no clock-tree synthesis performed",
                                authority="CTS + parasitic extraction of the placed array", access="design-specific")
    return P


def envelope(P, n_pe: int = 1000):
    out = {}
    E = P["E_MAC"]
    f = P["f_clk"]
    thr = Param("throughput", val(f) * n_pe, Cls.S, source="design-spec", unit="1/s",
                note=f"{n_pe} PEs x f_clk x II=1")
    P_dyn = Result("P_dyn", val(E) * val(thr), Cls.E, "E_MAC x MAC/s", [E, thr], unit="W")
    P_leak = Result("P_leak", val(P["P_leak_100"]) * n_pe, Cls.E, "n_PE x P_leak,PE(T_max)", [P["P_leak_100"]], unit="W",
                    assumptions=["leakage evaluated at T_j,max (upper bound)"])
    P_tot = Result("P_total", P_dyn.value + P_leak.value, Cls.E, "P_dyn + P_leak", [P_dyn, P_leak], unit="W")
    out["P_total"] = P_tot
    out["E_op"] = S.energy_per_operation(P_tot, thr)
    t_op = Param("t_MAC", 1 / val(f), Cls.E, source="1/f_clk", unit="s")
    out["EDP"] = S.edp(E, t_op)
    area_tot = Result("A_array", val(P["area"]) * n_pe, Cls.E, "n_PE x A_PE", [P["area"]], unit="m^2")
    out["power_density"] = Result("power density", P_tot.value / area_tot.value, Cls.E, "P / A", [P_tot, area_tot],
                                  unit="W/m^2")
    out["T_j"] = TH.junction_temperature(P["T_a"], P_tot, P["theta"])
    out["P_max"] = TH.max_power(P["T_max"], P["T_a"], P["theta"])
    # sustainable throughput under the thermal budget (per PE leakage at T_max)
    budget = out["P_max"].value - P_leak.value
    out["MAC_per_s_thermal"] = Result("MAC/s (thermal)", budget / val(E), Cls.E, "(P_max - P_leak) / E_MAC",
                                      [out["P_max"], P_leak, E], unit="1/s")
    # sustainable throughput under the power budget (same leakage bound)
    out["MAC_per_s_power"] = Result("MAC/s (power budget)", (val(P["P_budget"]) - P_leak.value) / val(E), Cls.E,
                                    "(P_budget - P_leak) / E_MAC", [P["P_budget"], P_leak, E], unit="1/s")
    metrics = mac_metrics(val(E).to("J"), val(f).to("Hz"), n_pe)
    return out, metrics


def sensitivities(P):
    """Local sensitivities d ln(P_total) / d ln(x) by finite differences, and a Monte Carlo."""
    E0 = val(P["E_MAC"]).to("J")
    f0 = val(P["f_clk"]).to("Hz")
    V0 = val(P["V_DD"]).to("V")

    def p_total(E=E0, f=f0, V=V0, act=1.0, C=1.0, T_c=100.0):
        # dynamic energy scales with activity * C * V^2 relative to the reference point;
        # leakage per PE interpolated log-linearly between the 25 C and 100 C Liberty values
        e = E * act * C * (V / V0) ** 2
        pl = TH.leakage_vs_T_from_points([(298.15, 2.24e-9), (373.15, 5680e-9)])(T_c + 273.15)
        return 1000 * (e * f + pl)

    base = p_total()
    sens = {}
    for k, x0 in (("V", V0), ("f", f0), ("act", 1.0), ("C", 1.0), ("T_c", 100.0)):
        h = 1e-3 * x0
        sens[k] = (math.log(p_total(**{k: x0 + h})) - math.log(base)) / (math.log(x0 + h) - math.log(x0)) \
            if k != "T_c" else (p_total(T_c=x0 + 1) - base) / base
    mc = monte_carlo(lambda E: p_total(E=E), {"E": Normal(E0, 0.2 * E0)}, n=20000)
    iv = interval(lambda act, V: p_total(act=act, V=V), {"act": (0.6, 1.0), "V": (1.71, 1.89)})
    return base, sens, mc, iv


def main():
    P = build_inputs()
    out, metrics = envelope(P)
    for k, r in out.items():
        print(r.describe())
        print("   input evidence classes:", ", ".join(r.input_classes()))
    print("\nmetrics (1000 PEs at f_clk):", {k: f"{v:.4g}" for k, v in metrics.items()})
    try:
        P["E_M_tree"].require("clock-tree energy")
    except MissingParameter as e:
        print("\nas expected, a class-I input cannot be used silently:", e)
    base, sens, mc, iv = sensitivities(P)
    print(f"\nP_total(1000 PEs) = {base:.4g} W")
    print("elasticities d ln P / d ln x:", {k: round(v, 3) for k, v in sens.items() if k != "T_c"},
          f"; dP/P per +1 K at 100 C: {sens['T_c']:.2e}")
    print(f"Monte Carlo (E_MAC 1-sigma 20 %): mean {mc['mean']:.4g} W, 5-95 % [{mc['p05']:.4g}, {mc['p95']:.4g}] W")
    print(f"interval (activity 0.6..1.0, V 1.71..1.89 V): [{iv[0]:.4g}, {iv[1]:.4g}] W")
    # fundamental floor for comparison
    T = spec("T", q(300, "K"), "K")
    floor = F.landauer(T, bits=16)
    print(f"\nLandauer floor per MAC (16 bits erased) at 300 K: {floor.value.to('J'):.3g} J;"
          f" ratio E_MAC / floor = {val(P['E_MAC']).to('J') / floor.value.to('J'):.3g}")
    return out


if __name__ == "__main__":
    main()
