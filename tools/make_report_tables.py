#!/usr/bin/env python3
"""Fill the generated tables in docs/report/*.md from the result CSVs.

Report files contain markers
    <!-- BEGIN:name -->  ...  <!-- END:name -->
and everything between them is replaced by the table `name` generated here.
Re-run after any simulation to keep the report consistent with the data.
"""
import csv
import glob
import math
import os
import re
import statistics
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
RES = os.path.join(ROOT, "results")

from ugcal.switching import fit_alpha_power  # noqa: E402


def rd(path):
    p = os.path.join(RES, path)
    if not os.path.exists(p):
        return None
    return list(csv.DictReader(l for l in open(p) if not l.startswith("#")))


def md(header, rows):
    out = "| " + " | ".join(header) + " |\n|" + "---|" * len(header) + "\n"
    for r in rows:
        out += "| " + " | ".join(str(x) for x in r) + " |\n"
    return out


def g(x, d=3):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return str(x)
    if x == 0:
        return "0"
    if abs(x) >= 1000 or abs(x) < 0.01:
        return f"{x:.{d}g}"
    return f"{x:.{d}g}"


# ---------------------------------------------------------------- devices
def t_device_conditions():
    rows = rd("spice/device_params.csv")
    if not rows:
        return None
    sel = [("tt", "-40", "1.8"), ("tt", "25", "1.8"), ("tt", "100", "1.8"), ("ss", "100", "1.6"), ("ff", "-40", "1.95"),
           ("ff", "100", "1.95"), ("sf", "25", "1.8"), ("fs", "25", "1.8"), ("tt", "25", "1.2"), ("tt", "25", "0.9")]
    out = []
    for dev in ("nfet_01v8", "pfet_01v8_hvt"):
        for c, T, V in sel:
            for r in rows:
                if r["device"] == dev and r["W_um"] in ("1", "1.0") and r["L_um"] == "0.15" and r["corner"] == c \
                        and r["T_C"] == T and float(r["VDD_V"]) == float(V):
                    out.append([dev, c, T, V, g(r["Vth_cc_lin_V"]), g(r["Vth_cc_sat_V"]), g(r["SS_min_mV_dec"]),
                                g(r["DIBL_mV_V"]), g(r["Ion_uA_um"]), g(r["Ioff_pA_um"]), g(r["Ion_Ioff"]),
                                g(r["Cgg_on_fF_um"]), g(r["intrinsic_CV_over_I_ps"])])
    return md(["device", "corner", "T (°C)", "V_DD (V)", "V_th,cc lin (V)", "V_th,cc sat (V)", "SS (mV/dec)",
               "DIBL (mV/V)", "I_on (µA/µm)", "I_off (pA/µm)", "I_on/I_off", "C_gg,on (fF/µm)", "CV/I (ps)"], out)


def t_device_flavours():
    rows = rd("spice/device_params.csv")
    if not rows:
        return None
    out = []
    for dev in ("nfet_01v8", "nfet_01v8_lvt", "pfet_01v8_hvt", "pfet_01v8"):
        for r in rows:
            if r["device"] == dev and r["W_um"] in ("1", "1.0") and r["L_um"] == "0.15" and r["corner"] == "tt" \
                    and r["T_C"] == "25" and float(r["VDD_V"]) == 1.8:
                out.append([dev, g(r["Vth_cc_lin_V"]), g(r["SS_min_mV_dec"]), g(r["DIBL_mV_V"]), g(r["Ion_uA_um"]),
                            g(r["Ioff_pA_um"]), g(r["Ion_Ioff"])])
    return md(["device (W/L = 1/0.15 µm)", "V_th,cc lin (V)", "SS (mV/dec)", "DIBL (mV/V)", "I_on (µA/µm)",
               "I_off (pA/µm)", "I_on/I_off"], out)


# ------------------------------------------------------------ vdd sweep / MEP
def mep_model(rows, Ld_fo4, act_tpc, n_nodes_equiv, n_leak_inv):
    """Minimum-energy point of a logic block from the FO4 sweep (see D6 §8).

    E_op(V) = act_tpc * n_nodes_equiv * E_FO4_transition(V)
              + n_leak_inv * P_leak,inv(V) * Ld_fo4 * t_FO4(V)
    """
    pts = []
    for r in rows:
        V = float(r["VDD_V"])
        e_dyn = act_tpc * n_nodes_equiv * float(r["E_per_transition_fJ"]) * 1e-15
        t = Ld_fo4 * float(r["fo4_ps"]) * 1e-12
        e_leak = n_leak_inv * float(r["leak_inv_pW"]) * 1e-12 * t
        pts.append((V, e_dyn + e_leak, e_dyn, e_leak, t))
    return sorted(pts)


def t_vdd_sweep():
    out = []
    for T in ("25", "100"):
        rows = rd(f"spice/vdd_sweep_tt_{T}C.csv")
        if not rows:
            continue
        for r in sorted(rows, key=lambda r: -float(r["VDD_V"])):
            out.append([T, g(r["VDD_V"]), g(r["fo4_ps"], 4), g(r["E_per_transition_fJ"]), g(r["leak_inv_pW"]),
                        g(float(r["E_per_transition_fJ"]) * float(r["fo4_ps"]) * 1e-3)])
    if not out:
        return None
    text = md(["T (°C)", "V_DD (V)", "FO4 delay (ps)", "E per FO4 transition (fJ)", "inv_1 leakage (pW)",
               "E·t (fJ·ns)"], out)
    # alpha-power-law fit (Sakurai-Newton) on the strong-inversion part only, used for interpolation
    fits = []
    for T in ("25", "100"):
        rows = [r for r in (rd(f"spice/vdd_sweep_tt_{T}C.csv") or []) if float(r["VDD_V"]) >= 1.0 - 1e-9]
        if len(rows) >= 4:
            fit = fit_alpha_power([float(r["VDD_V"]) for r in rows], [float(r["fo4_ps"]) * 1e-12 for r in rows])
            fits.append(f"{T} °C: V_t = {fit['Vt']:.3f} V, α = {fit['alpha']:.2f}, "
                        f"rms log error {fit['rms_log_err']:.3f} ({len(rows)} points, {min(float(r['VDD_V']) for r in rows):g}–"
                        f"{max(float(r['VDD_V']) for r in rows):g} V)")
    if fits:
        text += ("\n\nAlpha-power-law fit $t_{FO4} = kV/(V-V_t)^\\alpha$ to the FO4 delay for V_DD ≥ 1.0 V "
                 "(`ugcal.switching.fit_alpha_power`, class E; for interpolation only): " + "; ".join(fits) + ".")
    return text


def t_mep():
    out = []
    mac = rd("power/mac_study.csv")
    if not mac:
        return None
    for T in ("25", "100"):
        rows = rd(f"spice/vdd_sweep_tt_{T}C.csv")
        if not rows:
            continue
        r18 = [r for r in rows if abs(float(r["VDD_V"]) - 1.8) < 1e-6][0]
        for vname in ("csa_acc_bw_kogge_stone", "separate_bw_ripple_accripple"):
            m = [r for r in mac if r["variant"] == vname and r["dist"] == "uniform" and r["mode"] == "inertial"][0]
            E18 = float(m["E_MAC_fJ"]) * 1e-15
            Ld = float(m["crit_tt_ns"]) * 1e3 / float(r18["fo4_ps"])  # logic depth in FO4 at 1.8 V
            # express the MAC as an equivalent number of FO4 transitions at 1.8 V
            n_eq = E18 / (float(r18["E_per_transition_fJ"]) * 1e-15)
            # PE leakage at 1.8 V from Liberty (tt corner at this temperature), scaled with V
            # like the SPICE inverter leakage: n_leak_inv = P_PE(1.8 V) / P_inv(1.8 V)
            th = rd("envelope/thermal_envelope.csv") or []
            pe = [x for x in th if x["variant"] == vname]
            if not pe:
                continue
            p_pe = float(pe[0]["PE_leak_tt25_nW" if T == "25" else "PE_leak_tt100_nW"]) * 1e-9
            n_leak = p_pe / (float(r18["leak_inv_pW"]) * 1e-12)
            pts = mep_model(rows, Ld, 1.0, n_eq, n_leak)
            best = min(pts, key=lambda p: p[1])
            e18 = [p for p in pts if abs(p[0] - 1.8) < 1e-6][0]
            # a minimum at the lowest simulated supply is a bound, not an optimum
            vopt = ("≤ " if best[0] == min(p[0] for p in pts) else "") + g(best[0])
            out.append([T, vname, g(Ld), g(n_eq), g(e18[1] * 1e15, 4), vopt, g(best[1] * 1e15, 4),
                        g(e18[1] / best[1]), g(best[4] * 1e9, 4)])
    return md(["T (°C)", "MAC variant", "logic depth (FO4 at 1.8 V)", "equivalent FO4 transitions/MAC",
               "model E/MAC at 1.8 V (fJ)", "V_opt (V)", "E/MAC at V_opt (fJ)", "gain vs 1.8 V", "cycle time at V_opt (ns)"],
              out)


# ------------------------------------------------------------- calibration
def t_calibration():
    out = []
    for view, label in (("", "schematic"), ("_extracted", "extracted"), ("_extracted_lod", "extracted + LOD")):
        rows = rd(f"spice/calibration_inv_1_tt_025C_1v80{view}.csv")
        if not rows:
            continue

        def rng(a, b, filt=lambda r: True):
            xs = [100 * (float(r[a]) / float(r[b]) - 1) for r in rows if filt(r)]
            return f"{min(xs):+.1f} … {max(xs):+.1f} %"
        fs = lambda r: float(r["slew_ns"]) <= 0.3
        cin = statistics.fmean(float(r["spice_Cin_eff_fF"]) for r in rows)
        out.append([label, rng("spice_avg_E_per_transition_fJ", "opensta_avg_E_per_transition_fJ"),
                    rng("spice_cell_rise_ps", "lib_cell_rise_ps", fs), rng("spice_cell_fall_ps", "lib_cell_fall_ps", fs),
                    f"{cin:.3f} vs {float(rows[0]['lib_Cin_fF']):.3f}"])
    return md(["cell view", "energy/transition vs Liberty (16 pts)", "rise delay (slew ≤ 0.28 ns)",
               "fall delay (slew ≤ 0.28 ns)", "C_in SPICE vs Liberty (fF)"], out)


def t_leakage():
    rows = rd("spice/leakage_study.csv")
    if not rows:
        return None
    agg = {}
    for r in rows:
        lib = float(r["lib_nW"])
        for k, v in r.items():
            if k.startswith("spice_") and v and float(v) > 0 and lib > 0:
                agg.setdefault((r["libcorner"], k), []).append(math.log10(float(v) / lib))
    out = []
    order = ["tt_025C_1v80", "tt_100C_1v80", "ss_100C_1v60", "ff_100C_1v95", "ff_n40C_1v95", "ss_n40C_1v60"]
    for c in order:
        for (cc, k), v in sorted(agg.items()):
            if cc == c:
                model = k.replace("spice_", "").replace("_nW", "")
                note = "below DC resolution for stacked cells" if "n40" in c else ""
                out.append([c, model, g(10 ** statistics.fmean(v)), f"{g(10 ** min(v))} … {g(10 ** max(v))}", len(v), note])
    return md(["Liberty corner", "SPICE model set", "geo. mean SPICE/Liberty", "range over states", "states", "note"], out)


# --------------------------------------------------------------- multipliers
def t_arch(n, signed, dist="uniform"):
    rows = rd("power/arch_study_tt_025C_1v80.csv")
    if not rows:
        return None
    out = []
    for r in rows:
        if r["n"] == str(n) and r["signed"] == str(signed) and r["dist"] == dist:
            out.append([r["design"], r["cells"], r["transistors"], g(r["area_um2"], 4), g(r["crit_path_ns"]),
                        g(r["E_zero_fJ"], 4), g(r["E_inertial_fJ"], 4), g(r["E_transport_fJ"], 4),
                        g(r["glitch_factor_inertial"]), g(r["EDP_inertial_fJns"], 4), g(r["leak_avg_nW"])])
    return md(["design", "cells", "transistors", "area (µm²)", "critical path (ns)", "E zero-delay (fJ)",
               "E inertial (fJ)", "E transport (fJ)", "glitch factor (inertial/zero)", "EDP inertial (fJ·ns)",
               "leakage tt25 (nW)"], out)


def t_arch_data():
    rows = rd("power/arch_study_tt_025C_1v80.csv")
    if not rows:
        return None
    out = []
    for n, s in ((8, False), (8, True), (16, False)):
        designs = []
        for r in rows:
            if r["n"] == str(n) and r["signed"] == str(s) and r["design"] not in designs:
                designs.append(r["design"])
        for d in designs:
            e = {r["dist"]: float(r["E_inertial_fJ"]) for r in rows if r["n"] == str(n) and r["signed"] == str(s)
                 and r["design"] == d}
            out.append([f"{n}{'s' if s else 'u'}", d] + [g(e.get(k), 4) for k in ("uniform", "sparse50", "small", "gauss")]
                       + [g(e["uniform"] / min(e.values()))])
    return md(["width", "design", "uniform", "sparse 50 %", "small |x| < 2^(n/2)", "gaussian", "max/min"], out)


def t_spice_mult():
    rows = []
    for f in sorted(glob.glob(os.path.join(RES, "spice", "multiplier_spice_summary_*.csv"))):
        rows += list(csv.DictReader(open(f)))
    if not rows:
        return None
    out = []
    for r in rows:
        out.append([r["design"], r["view"], r["nvec"], g(r["period_ns"]), g(r["spice_E_fJ"], 4), g(r["gate_zero_fJ"], 4),
                    g(r["gate_inertial_fJ"], 4), g(r["gate_transport_fJ"], 4), g(r["spice_over_inertial"]),
                    g(float(r["spice_E_fJ"]) / float(r["gate_transport_fJ"])), r["functional_errors"], g(float(r["wall_s"]) / 60, 3)])
    return md(["design", "cell view", "vectors", "period (ns)", "SPICE E/mult (fJ)", "gate zero (fJ)", "gate inertial (fJ)",
               "gate transport (fJ)", "SPICE/inertial", "SPICE/transport", "functional errors", "SPICE wall time (min)"], out)


# ---------------------------------------------------------------------- MAC
def t_mac(dist="uniform", mode="inertial"):
    rows = rd("power/mac_study.csv")
    if not rows:
        return None
    cats = ["reg_op", "enc", "pp", "red", "cpa", "acc", "reg_acc", "clk", "outcpa"]
    out = []
    for r in rows:
        if r["dist"] == dist and r["mode"] == mode:
            out.append([r["variant"], r["cells"], g(r["area_um2"], 4), g(r["crit_tt_ns"]), g(r["fmax_tt_MHz"], 4),
                        g(r["fmax_ss100_MHz"], 4), g(r["E_MAC_fJ"], 4), g(r["TOPS_per_W"])] +
                       [g(r.get("E_" + c + "_fJ") or 0, 3) for c in cats])
    return md(["variant", "cells", "area (µm²)", "crit tt (ns)", "f_max tt (MHz)", "f_max ss/100 °C (MHz)", "E/MAC (fJ)",
               "TOPS/W"] + [f"{c} (fJ)" for c in cats], out)


def t_mac_dists():
    rows = rd("power/mac_study.csv")
    if not rows:
        return None
    out = []
    variants = []
    for r in rows:
        if r["variant"] not in variants:
            variants.append(r["variant"])
    for v in variants:
        line = [v]
        for d in ("uniform", "gauss", "relu_gauss"):
            for m in ("zero", "inertial"):
                x = [r for r in rows if r["variant"] == v and r["dist"] == d and r["mode"] == m]
                line.append(g(x[0]["E_MAC_fJ"], 4) if x else "")
        out.append(line)
    return md(["variant", "uniform zero", "uniform inertial", "gauss zero", "gauss inertial", "relu×gauss zero",
               "relu×gauss inertial"], out)


def t_array():
    rows = rd("envelope/array_model.csv")
    if not rows:
        return None
    out = []
    for r in rows:
        if r["variant"] in ("csa_acc_bw_kogge_stone", "separate_bw_ripple_accripple"):
            out.append([r["variant"], r["reuse_N"], r["wire"], g(r["E_PE_fJ"], 4), g(r["E_fwd_fJ"]), g(r["E_sram_fJ"], 4),
                        g(r["E_total_fJ"], 4), g(float(r["sram_share"]) * 100, 3), g(r["TOPS_per_W"])])
    return md(["PE variant", "reuse N", "wire C", "E_PE (fJ)", "E_fwd (fJ)", "E_SRAM (fJ)", "E_MAC,array (fJ)",
               "SRAM share (%)", "TOPS/W"], out)


def t_thermal():
    rows = rd("envelope/thermal_envelope.csv")
    if not rows:
        return None
    out = []
    for r in rows:
        out.append([r["variant"], r["theta_JA_K_W"], g(r["T_amb_C"]), g(r["P_max_W"]), g(r["n_PE_sustainable"], 4),
                    g(r["TOPS"]), g(r["die_area_mm2"]), g(r["power_density_W_cm2"]), g(r["loop_gain"])])
    return md(["PE variant", "θ_JA (K/W)", "T_amb (°C)", "P_max at T_j = 100 °C (W)", "PEs at f_max(ss,100 °C)", "TOPS",
               "PE area (mm²)", "power density (W/cm²)", "electro-thermal loop gain"], out)


def t_pe_leak():
    rows = rd("envelope/thermal_envelope.csv")
    if not rows:
        return None
    seen = set()
    out = []
    for r in rows:
        if r["variant"] in seen:
            continue
        seen.add(r["variant"])
        out.append([r["variant"], r["cells"], g(r["PE_leak_tt25_nW"]), g(r["PE_leak_tt100_nW"]), g(r["PE_leak_ss100_nW"]),
                    g(r["PE_leak_ff100_nW"]), g(float(r["E_MAC_fJ"]) * 1e-15 * float(r["f_ss100_MHz"]) * 1e6 * 1e6, 4)])
    return md(["PE variant", "cells", "Liberty leakage tt 25 °C (nW)", "tt 100 °C (nW)", "ss 100 °C (nW)", "ff 100 °C (nW)",
               "dynamic power at f_max(ss) (µW)"], out)


def t_adders():
    rows = rd("power/adder_study.csv")
    if not rows:
        return None
    out = [[r["n"], r["adder"], r["cells"], r["transistors"], g(r["area_um2"], 4), g(r["crit_ns"]), g(r["E_zero_fJ"], 4),
            g(r["E_inertial_fJ"], 4), g(r["E_transport_fJ"], 4),
            g(float(r["E_inertial_fJ"]) * float(r["crit_ns"]), 4), r["functional_errors"]] for r in rows]
    return md(["n", "adder", "cells", "transistors", "area (µm²)", "critical path (ns)", "E zero (fJ)", "E inertial (fJ)",
               "E transport (fJ)", "EDP inertial (fJ·ns)", "errors (1 001 vectors)"], out)


TABLES = {
    "adders": t_adders,
    "device_conditions": t_device_conditions, "device_flavours": t_device_flavours, "vdd_sweep": t_vdd_sweep,
    "mep": t_mep, "calibration": t_calibration, "leakage": t_leakage,
    "arch8u": lambda: t_arch(8, False), "arch8s": lambda: t_arch(8, True), "arch16u": lambda: t_arch(16, False),
    "arch_data": t_arch_data, "spice_mult": t_spice_mult, "mac_uniform": t_mac, "mac_dists": t_mac_dists,
    "array": t_array, "thermal": t_thermal, "pe_leak": t_pe_leak,
}


def main():
    docs = glob.glob(os.path.join(ROOT, "docs", "report", "*.md")) + [os.path.join(ROOT, "README.md")]
    cache = {}
    for path in docs:
        text = open(path).read()
        changed = False
        for m in re.finditer(r"<!-- BEGIN:(\w+) -->", text):
            name = m.group(1)
            if name not in TABLES:
                print(f"{os.path.basename(path)}: unknown table {name}")
                continue
            if name not in cache:
                cache[name] = TABLES[name]()
            body = cache[name]
            if body is None:
                print(f"{os.path.basename(path)}: no data for {name}")
                continue
            text, n = re.subn(rf"(<!-- BEGIN:{name} -->)(.*?)(<!-- END:{name} -->)",
                              lambda mm: mm.group(1) + "\n" + body + mm.group(3), text, flags=re.S)
            changed |= n > 0
        if changed:
            open(path, "w").write(text)
            print("filled", os.path.relpath(path, ROOT))


if __name__ == "__main__":
    main()
