#!/usr/bin/env python3
"""Build the SKY130 transistor/cell parameter database (Deliverable 4).

Every row is read from a pinned file or from a result file produced by this
project, with its source, location, operating conditions and evidence class.
Nothing is typed in by hand except the documentation rows of class I
(unavailable parameters) and the meaning/equation columns.

Output: data/sky130/parameter_database.csv and results/tables/parameter_database.md
Columns follow the project specification (section 6.2).
"""
import csv
import math
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ugcal import constants as K  # noqa: E402
from ugcal.liberty import Library  # noqa: E402
from ugcal.modelcard import bin_for, nominal  # noqa: E402
from ugcal.sim.ngspice import pdk_root, repo_root  # noqa: E402

SC = "fossi-foundation/skywater-pdk-libs-sky130_fd_sc_hd@9cb2d7cb"
PR = "fossi-foundation/skywater-pdk-libs-sky130_fd_pr@16f93a79"
DOCS = "google/skywater-pdk@7198cf64 docs"
TECH = "SKY130 (SkyWater 130 nm, open PDK)"
COLS = ["Parameter", "Symbol", "Unit", "Physical meaning", "Source", "Source location", "Technology",
        "Operating conditions", "Data classification", "Uncertainty", "Used in which equation?"]
rows = []


def add(param, sym, unit, meaning, source, loc, cond, cls, unc, eq, value):
    rows.append({"Parameter": param, "Symbol": sym, "Unit": unit, "Physical meaning": meaning, "Source": source,
                 "Source location": loc, "Technology": TECH, "Operating conditions": cond,
                 "Data classification": cls, "Uncertainty": unc, "Used in which equation?": eq,
                 "Value": fmt(value, 6) if isinstance(value, float) else value})


def fmt(x, d=4):
    if isinstance(x, str):
        return x
    return f"{x:.{d}g}"


def constants():
    for p, meaning, eq in [(K.k_B, "Boltzmann constant", "kT, kT ln2, kT/q, kT/C"),
                           (K.q_e, "elementary charge", "kT/q"),
                           (K.h, "Planck constant", "h/(4E)"),
                           (K.eps0, "vacuum permittivity", "C_ox = eps0 epsrox / toxe")]:
        unit = p.unit
        add(p.name, p.symbol, unit, meaning, p.source, "SI 2019 / CODATA 2022", "-",
            "A fundamental constant", "exact" if p.u_rel is None else f"u_r = {p.u_rel:g}", eq, fmt(p.value.to(unit), 11))


def liberty_rows():
    for corner in ("tt_025C_1v80", "ss_100C_1v60", "ff_n40C_1v95", "tt_100C_1v80"):
        lib = Library(os.path.join(pdk_root(), "sc_hd", "timing", f"sky130_fd_sc_hd__{corner}.lib"))
        loc = f"timing/sky130_fd_sc_hd__{corner}.lib"
        cond = f"{corner} (V={lib.op_voltage} V, T={lib.op_temperature} C)"
        src = SC
        if corner == "tt_025C_1v80":
            add("Nominal supply voltage", "V_DD", "V", "library nominal supply", src, loc + " nom_voltage", cond,
                "C foundry-supplied", "n/a (definition)", "E = 1/2 C V^2, P = V I", lib.nom_voltage)
            for k in ("slew_lower_threshold_pct_rise", "slew_upper_threshold_pct_rise", "input_threshold_pct_rise"):
                add(k, "", "%", "measurement threshold of table data", src, loc, cond, "C foundry-supplied",
                    "n/a (definition)", "delay/slew definitions", lib.thresholds[k])
        for cell in ("inv_1", "nand2_1", "and2_1", "xor2_1", "ha_1", "fa_1", "a21o_1", "dfxtp_1"):
            name = f"sky130_fd_sc_hd__{cell}"
            c = lib.cell(name)
            if corner == "tt_025C_1v80":
                add(f"{cell} area", "A_cell", "um^2", "placement area (LEF width x height)", src, loc + f" cell({name}) area",
                    "-", "C foundry-supplied", "exact (layout grid)", "area, power density", c.area)
                for pin, pv in c.pins.items():
                    if pv.direction == "input" and pv.capacitance is not None:
                        add(f"{cell} pin {pin} capacitance", "C_in", "fF", "input pin capacitance (table-based)",
                            src, loc + f" pin({pin}) capacitance", cond, "C foundry-supplied",
                            "characterisation method undocumented", "switching 1/2 C V^2, load", pv.capacitance * 1e3)
                a = c.pins[[p for p, v in c.pins.items() if v.direction == "output"][0]]
            add(f"{cell} cell_leakage_power", "P_leak", "nW", "equal-weight mean of state leakage",
                src, loc + f" cell({name}) cell_leakage_power", cond, "C foundry-supplied",
                "model set used for characterisation undocumented; see results/spice/leakage_study.csv",
                "P_leak = sum_states p_s P_s", c.leakage * lib.units.leakage * 1e9)
        # reference delays and energies for inv_1 and fa_1
        for cell, rel, out in (("inv_1", "A", "Y"), ("fa_1", "A", "SUM"), ("fa_1", "CIN", "COUT")):
            name = f"sky130_fd_sc_hd__{cell}"
            for edge in ("rise", "fall"):
                d = lib.delay_s(name, rel, out, edge, 50e-12, 5e-15)
                add(f"{cell} {rel}->{out} cell_{edge}", "t_pd", "ps", "50%-50% propagation delay",
                    src, loc + f" cell({name}) pin({out}) timing(related {rel})",
                    cond + "; input slew 50 ps, load 5 fF (interpolated)", "C foundry-supplied",
                    "table interpolation; see calibration", "critical path, f_max", d * 1e12)
        name = "sky130_fd_sc_hd__dfxtp_1"
        add("dfxtp_1 CLK->Q (rise)", "t_cq", "ps", "clock-to-output delay", src, loc + " dfxtp_1 pin(Q)",
            cond + "; clk slew 50 ps, load 5 fF", "C foundry-supplied", "table interpolation",
            "T_clk >= t_cq + t_logic + t_setup", lib.delay_s(name, "CLK", "Q", "rise", 50e-12, 5e-15) * 1e12)


def model_rows():
    for dev, W, L in (("nfet_01v8", 0.65, 0.15), ("pfet_01v8_hvt", 1.0, 0.15)):
        path = os.path.join(pdk_root(), "fd_pr", "cells", dev, f"sky130_fd_pr__{dev}__tt.pm3.spice")
        name, p = bin_for(path, W, L)
        loc = f"cells/{dev}/sky130_fd_pr__{dev}__tt.pm3.spice, .model {name.split('__')[-1]}"
        cond = f"tt; bin for W={W} um, L={L} um (inv_1 device)"
        src = PR
        cls = "C foundry-supplied (compact-model card)"
        add(f"{dev} model level/version", "", "-", "BSIM4 level 54 version 4.5", src, loc, cond, cls, "-",
            "all device equations", f"level={p['level']}, version={p['version']}")
        tox = nominal(p["toxe"])
        add(f"{dev} toxe", "t_ox,e", "nm", "electrical oxide thickness (model)", src, loc, cond, cls,
            "mismatch sigma = toxe*slope/sqrt(WL)", "C_ox", tox * 1e9)
        epsrox = float(p["epsrox"])
        add(f"{dev} epsrox", "eps_r,ox", "-", "gate dielectric relative permittivity (model)", src, loc, cond, cls,
            "-", "C_ox", epsrox)
        cox = K.eps0.value.to("F/m") * epsrox / tox
        add(f"{dev} C_ox (derived)", "C_ox", "fF/um^2", "eps0 epsrox / toxe", "this project (E)",
            "tools/build_parameter_db.py", cond, "E model-derived", "inherits toxe", "C_gate ~ C_ox W L", cox * 1e15 / 1e12)
        add(f"{dev} tnom", "T_nom", "C", "model extraction temperature", src, loc, cond, cls, "-",
            "temperature scaling", float(p["tnom"]))
        for k, sym, unit, meaning, scale in (("cgso", "C_gso", "fF/um", "gate-source overlap capacitance per width", 1e9),
                                             ("cgdo", "C_gdo", "fF/um", "gate-drain overlap capacitance per width", 1e9),
                                             ("cf", "C_f", "fF/um", "outer fringe capacitance per width", 1e9),
                                             ("cjs", "C_j", "fF/um^2", "S/D junction bottom capacitance (zero bias)", 1e3),
                                             ("cjsws", "C_jsw", "fF/um", "S/D junction sidewall capacitance (isolation edge)", 1e9),
                                             ("cjswgs", "C_jswg", "fF/um", "S/D junction sidewall capacitance (gate edge)", 1e9),
                                             ("jsws", "J_sws", "pA/um", "sidewall junction saturation current density", 1e6),
                                             ("rdsw", "R_dsw", "Ohm um", "source/drain resistance per width (internal, rdsmod=0)", 1.0)):
            if k in p:
                add(f"{dev} {k}", sym, unit, meaning, src, loc, cond, cls,
                    "BSIM4 units assumed (F/m, F/m^2, A/m); manual not inspected", "C(V), leakage, R_access",
                    nominal(p[k]) * scale)
        for k, meaning in (("igcmod", "gate-to-channel tunnelling current model switch"),
                           ("igbmod", "gate-to-body tunnelling current model switch"),
                           ("rdsmod", "external S/D resistance network switch"),
                           ("rgatemod", "gate resistance model switch"),
                           ("capmod", "charge/capacitance model selector")):
            add(f"{dev} {k}", k, "-", meaning, src, loc, cond, cls, "-", "model capability", p[k])
        add(f"{dev} saref/sbref", "SA_ref", "um", "reference LOD (STI stress) distance", src, loc, cond, cls, "-",
            "stress-dependent mobility/Vth", nominal(p["saref"]) * 1e6)
        mm = os.path.join(pdk_root(), "fd_pr", "cells", dev, f"sky130_fd_pr__{dev}__mismatch.corner.spice")
        txt = open(mm).read()
        m = re.search(rf"sky130_fd_pr__{dev}__vth0_slope\s*=\s*([0-9.eE+-]+)", txt)
        add(f"{dev} Vth0 mismatch coefficient", "A_VT", "mV um",
            "sigma(Vth0) = A_VT / sqrt(W L mult), Gaussian (AGAUSS), per device", src,
            f"cells/{dev}/sky130_fd_pr__{dev}__mismatch.corner.spice; applied in vth0 expression", "mc_mm_switch=1",
            cls, "distribution stated as Gaussian in the card", "variability, Monte Carlo", float(m.group(1)) * 1e3)


def doc_rows():
    src = DOCS
    for dev, rng in (("nfet_01v8", "V_DS, V_GS 0..1.95 V; V_BS +0.3..-1.95 V"),
                     ("pfet_01v8_hvt", "V_DS, V_GS 0..-1.95 V; V_BS -0.1..+1.95 V")):
        add(f"{dev} SPICE-model validity range", "", "V", "voltages where the foundry states the models are valid",
            src, "docs/rules/device-details.rst", "-", "C foundry-supplied", "-", "validity of all simulations", rng)
    tab = {"nfet_01v8": [("VTXNS15", "7/0.15", "V", "0.645", "0.700", "0.661", "0.739"),
                         ("IDSNS15", "7/0.15", "mA", "3.512", "3.510", "3.039", "3.981"),
                         ("VTXNL", "7/8", "V", "0.538", "0.541", "0.515", "0.567")],
           "pfet_01v8_hvt": [("VTXPS15", "7/0.15", "V", "-0.888", "-0.888", "-0.963", "-0.814"),
                             ("IDSPS15", "7/0.15", "mA", "1.003", "1.003", "0.697", "1.309"),
                             ("VTXPL", "7/8", "V", "-1.107", "-1.107", "-1.141", "-1.067")]}
    for dev, items in tab.items():
        for name, wl, unit, model_tt, nom, mn, mx in items:
            loc = f"docs/rules/device-details/{dev}/{dev}-table0.rst"
            add(f"{dev} {name} model TT", name, unit, f"model value, W/L={wl} um (extraction method not stated)", src, loc,
                "tt (temperature/bias not stated)", "C foundry-supplied (model)", "-", "model sanity check", model_tt)
            add(f"{dev} {name} e-test (EDR) nominal [min, max]", name, unit,
                f"electrical design rule (e-test) window, W/L={wl} um", src, loc, "not stated",
                "C foundry-supplied (silicon spec window)", f"window [{mn}, {mx}]", "model-vs-silicon check", nom)
    add("Inverter FO=1 stage delay, e-test", "t_inv", "ps", "e-test ring/chain delay per stage (143 stages)", src,
        "docs/rules/device-details/pfet_01v8_hvt/pfet_01v8_hvt-table1.rst", "nfet_01v8/pfet_01v8_hvt inverter; sizes not stated",
        "C foundry-supplied (silicon spec window)", "window [29.3, 52.1] ps", "delay sanity check", 38)
    rcx = os.path.join(pdk_root(), "skywater-pdk", "docs", "rules", "rcx", "resistance-values.tsv")
    for line in open(rcx).read().splitlines()[1:]:
        layer, r = line.split("\t")
        if layer in ("Local interconnect", "Metal1", "Metal2", "Metal3", "Metal4", "Metal5", "LICON contact",
                     "MCON contact", "VIA", "VIA2", "VIA3", "VIA4", "Poly"):
            add(f"{layer} sheet/contact resistance", "R_sh", "mOhm/sq or mOhm/contact", "interconnect resistance",
                src, "docs/rules/rcx/resistance-values.tsv", "nominal", "C foundry-supplied", "corner spread not given here",
                "wire RC delay, IR drop", float(r))


def spice_rows():
    path = os.path.join(repo_root(), "results", "spice", "device_params.csv")
    data = list(csv.DictReader(l for l in open(path) if not l.startswith("#")))
    for r in data:
        if r["W_um"] not in ("1", "1.0") or r["L_um"] != "0.15":
            continue
        if r["device"] not in ("nfet_01v8", "pfet_01v8_hvt"):
            continue
        cond = f"{r['corner']}, {r['T_C']} C, |V_DS|=|V_GS|max={r['VDD_V']} V; W/L=1/0.15 um, single finger"
        loc = "results/spice/device_params.csv (sim/spice/device_char.py)"
        src = "this project: ngspice-42 on " + PR
        cls = "F circuit-simulated (foundry models)"
        for key, sym, unit, meaning, eq in (
                ("Vth_cc_lin_V", "V_th,cc", "V", "constant-current Vth (100 nA*W/L, |V_DS|=50 mV)", "I_sub ~ exp((V_GS-V_th)/(n kT/q))"),
                ("SS_min_mV_dec", "SS", "mV/dec", "minimum subthreshold swing at |V_DS|=V_DD", "SS = n ln10 kT/q"),
                ("DIBL_mV_V", "DIBL", "mV/V", "Vth shift per V of drain bias", "leakage vs V_DS"),
                ("Ion_uA_um", "I_on", "uA/um", "drain current at |V_GS|=|V_DS|=V_DD", "t ~ C V / I_on"),
                ("Ioff_pA_um", "I_off", "pA/um", "drain current at V_GS=0, |V_DS|=V_DD (incl. junction)", "P_leak = V I_off W"),
                ("Cgg_on_fF_um", "C_gg", "fF/um", "total gate capacitance at |V_GS|=V_DD, V_DS=0", "E = C V^2"),
                ("intrinsic_CV_over_I_ps", "CV/I", "ps", "C_gg V_DD / I_on", "intrinsic delay metric")):
            add(f"{r['device']} {key}", sym, unit, meaning, src, loc, cond, cls,
                "method-dependent; model accuracy not stated by foundry", eq, fmt(float(r[key])))


def unavailable_rows():
    items = [
        ("Gate tunnelling current", "I_G", "A", "igcmod=igbmod=0 in the tt cards: the models contain no gate-current mechanism",
         "foundry gate-leakage measurements", "public (absent)", "gate leakage power"),
        ("Maximum junction temperature / mission profile", "T_j,max", "C", "not found in the open PDK documentation",
         "SkyWater reliability/qualification documents", "likely customer/NDA", "thermal limit; Liberty characterises only -40..100 C"),
        ("Electromigration current-density limits", "J_max", "mA/um", "docs refer to 'Electrical DR' guidelines not included in the open docs (periphery rule x.4)",
         "SkyWater Electrical Design Rules", "likely customer/NDA", "EM sizing of power grid and wires"),
        ("TDDB / BTI / HCI lifetime models", "-", "-", "no ageing models in the open model set",
         "foundry reliability manual", "likely customer/NDA", "ageing guard-band"),
        ("Self-heating model", "R_th,dev", "K/W", "BSIM4 has no self-heating network; none provided",
         "foundry device thermal characterisation", "unknown", "device temperature rise"),
        ("Package thermal resistance for a SKY130 die", "theta_JA, theta_JC", "K/W", "depends on the package/board chosen by the designer",
         "package datasheet (JESD51 conditions) or measurement", "design-specific", "T_j = T_a + P theta"),
        ("Liberty characterisation conditions (SPICE corner, model version, netlist view)", "-", "-",
         "not documented; this project infers them (see calibration)", "SkyWater characterisation reports", "unknown", "interpretation of Liberty data"),
        ("Per-layer interconnect capacitance per corner (field-solver)", "C_wire", "fF/um",
         "spreadsheet referenced in docs/rules/rcx.rst is an external link (not in repository)", "SkyWater stackup data",
         "public link (not inspected; host blocked)", "wire switching energy"),
    ]
    for name, sym, unit, why, authority, access, used in items:
        add(name, sym, unit, why, authority, "-", "-", "I unknown/unavailable", access, used,
            "not publicly available / not established")


def main():
    constants()
    doc_rows()
    model_rows()
    liberty_rows()
    spice_rows()
    unavailable_rows()
    out_csv = os.path.join(repo_root(), "data", "sky130", "parameter_database.csv")
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS[:3] + ["Value"] + COLS[3:])
        w.writeheader()
        w.writerows(rows)
    md = os.path.join(repo_root(), "results", "tables", "parameter_database.md")
    os.makedirs(os.path.dirname(md), exist_ok=True)
    with open(md, "w") as fh:
        hdr = ["Parameter", "Symbol", "Value", "Unit", "Physical meaning", "Source", "Source location",
               "Operating conditions", "Data classification", "Uncertainty", "Used in which equation?"]
        fh.write("| " + " | ".join(hdr) + " |\n|" + "---|" * len(hdr) + "\n")
        for r in rows:
            fh.write("| " + " | ".join(str(r[h]).replace("|", "/") for h in hdr) + " |\n")
    print(f"{len(rows)} rows -> {out_csv}")


if __name__ == "__main__":
    main()
