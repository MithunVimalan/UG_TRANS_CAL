#!/usr/bin/env python3
"""Assemble the performance envelope of an int8 MAC in SKY130 (Deliverable 9/12 inputs).

Reads the simulation results produced by the other scripts and combines them
with the models of ugcal into a chain of bounds, each with its evidence class:

  1. fundamental floors (Landauer, output-only and gate-level model)
  2. technology floor: minimum-energy point of SKY130 HD logic (SPICE FO4 sweep)
     applied to the MAC's switched capacitance and leakage
  3. circuit level: gate-level E/MAC (zero-delay, inertial) and f_max per variant
  4. array level: + operand forwarding wires + SRAM traffic vs reuse
  5. thermal level: maximum sustainable power/throughput vs package theta_JA,
     with the electro-thermal fixed point using Liberty and SPICE leakage

Output: results/envelope/*.csv
"""
import csv
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from ugcal import array as AR  # noqa: E402
from ugcal import constants as K  # noqa: E402
from ugcal import thermal as TH  # noqa: E402
from ugcal.arith.mac import build_mac  # noqa: E402
from ugcal.arith.verilog import cellinfo  # noqa: E402
from ugcal.liberty import Library  # noqa: E402
from ugcal.mac import accumulator_width  # noqa: E402
from ugcal.provenance import Cls, Param, spec  # noqa: E402
from ugcal.sim.ngspice import pdk_root, repo_root  # noqa: E402
from ugcal.units import q  # noqa: E402

OUT = os.path.join(repo_root(), "results", "envelope")
LIBDIR = os.path.join(pdk_root(), "sc_hd", "timing")


def write(name, rows):
    os.makedirs(OUT, exist_ok=True)
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(os.path.join(OUT, name + ".csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def mac_rows():
    rows = list(csv.DictReader(open(os.path.join(repo_root(), "results", "power", "mac_study.csv"))))
    return rows


def pe_leakage(variant, pp, final, acc_adder):
    """Liberty cell_leakage_power sum of the MAC netlist at several corners (W)."""
    W = accumulator_width(8, 8, 64, True)
    nl = build_mac(8, W, variant, pp=pp, red="dadda", final=final, acc_adder=acc_adder, signed=True)
    cells = [cellinfo(g)[0] for g in nl.gates]
    out = {}
    for corner in ("tt_025C_1v80", "tt_100C_1v80", "ss_100C_1v60", "ff_100C_1v95"):
        lib = Library(os.path.join(LIBDIR, f"sky130_fd_sc_hd__{corner}.lib"))
        out[corner] = sum(lib.leakage_W("sky130_fd_sc_hd__" + c) for c in cells)
    return out, len(cells)


def main():
    macs = mac_rows()
    # ------------------------------------------------------------- level 3
    best = {}
    for r in macs:
        if r["dist"] == "uniform" and r["mode"] == "inertial":
            best[r["variant"]] = r
    # ------------------------------------------------------------- level 1
    T = spec("T", q(300, "K"), "K")
    kT = (K.k_B.value * q(300, "K")).to("J")
    floors = [dict(level="1 fundamental", item="Landauer, MAC operands discarded (16 bits)", E_J=16 * kT * math.log(2),
                   cls="D (exact information content x kT ln2)", applies="absolute floor for irreversible MAC"),
              dict(level="1 fundamental", item="Landauer, signed 8x8 multiply output-only (3.144 bits)",
                   E_J=3.144 * kT * math.log(2), cls="D", applies="absolute floor for irreversible multiply"),
              dict(level="1 model", item="gate-level irreversible model, 8x8 multipliers (111-265 bits)",
                   E_J=111 * kT * math.log(2), E_hi_J=265 * kT * math.log(2), cls="E", applies="if every gate erases its inputs")]
    write("fundamental_floors", floors)
    # ------------------------------------------------------------- level 4: array
    C_lo = Param("C_wire,met2,isolated", q(0.14 * 16.9423e-6 + 2 * 37.759e-6, "pF/um"), Cls.C,
                 source="sky130_fd_sc_hd tech LEF met2 CPERSQDIST/EDGECAPACITANCE", unit="pF/um",
                 note="0.14 um wire to substrate, no lateral coupling (lower bound)")
    C_hi = Param("C_wire,met2,dense", q(0.2, "fF/um"), Cls.H, source="engineering bracket",
                 unit="fF/um", note="upper bracket incl. coupling; not a foundry number")
    V = Param("V_DD", q(1.8, "V"), Cls.C, source="tt_025C_1v80 nom_voltage", unit="V")
    E_word = Param("E_sram_access_32b", q(2 * 9.589466, "pJ"), Cls.H,
                   source="sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.lib clk0 internal_power (OpenRAM)",
                   unit="J", note="2 clock edges x 9.59 pJ; same value for read/write/deselect: analytical estimate")
    arr_rows = []
    for name, r in best.items():
        area = float(r["area_um2"])
        pitch = Param("PE pitch", q(math.sqrt(area / 0.7), "um"), Cls.E, source="derived from cell area / 0.7 utilisation",
                      unit="um")
        E_PE = Param("E_PE", q(float(r["E_MAC_fJ"]), "fJ"), Cls.E, source="results/power/mac_study.csv", unit="J")
        for N in (1, 4, 16, 64, 256):
            for Cw, tag in ((C_lo, "lo"), (C_hi, "hi")):
                f = AR.forwarding_energy(8, 0.5, Cw, pitch, V)
                s = AR.sram_energy_per_mac(8, int(r["W"]), 32, N, 64, E_word)
                tot = AR.array_energy(E_PE, f, s)
                arr_rows.append(dict(variant=name, reuse_N=N, wire=tag, E_PE_fJ=float(r["E_MAC_fJ"]),
                                     E_fwd_fJ=f.value.to("fJ"), E_sram_fJ=s.value.to("fJ"),
                                     E_total_fJ=tot.value.to("fJ"), sram_share=s.value.value / tot.value.value,
                                     TOPS_per_W=2 / tot.value.to("pJ")))
    write("array_model", arr_rows)
    # ------------------------------------------------------------- level 5: thermal
    th_rows = []
    variants = {"csa_acc_bw_kogge_stone": ("csa_acc", "bw", "kogge_stone", "kogge_stone"),
                "separate_bw_ripple_accripple": ("separate", "bw", "ripple", "ripple")}
    for name, (variant, pp, final, accadd) in variants.items():
        r = best[name]
        leak, ncell = pe_leakage(variant, pp, final, accadd)
        E = float(r["E_MAC_fJ"]) * 1e-15
        area_mm2 = float(r["area_um2"]) * 1e-6 / 0.7
        f_ss = float(r["fmax_ss100_MHz"]) * 1e6
        f_tt = float(r["fmax_tt_MHz"]) * 1e6
        for theta in (10, 20, 30, 40, 60):
            for Ta in (25.0, 70.0):
                Tmax = 100.0
                # Liberty leakage vs T from tt 25 C and tt 100 C (per PE)
                pl = TH.leakage_vs_T_from_points([(298.15, leak["tt_025C_1v80"]), (373.15, leak["tt_100C_1v80"])])
                pl_pess = TH.leakage_vs_T_from_points([(298.15, leak["tt_025C_1v80"]), (373.15, leak["ff_100C_1v95"])])
                Pmax = (Tmax - Ta) / theta
                # number of PEs at f_ss that the package can sustain, with pessimistic leakage at Tmax
                per_pe = E * f_ss + pl_pess(Tmax + 273.15)
                n_pe = Pmax / per_pe
                mac_s = n_pe * f_ss
                # die area needed for that many PEs and resulting power density
                die_mm2 = n_pe * area_mm2
                # electro-thermal check of runaway: all PEs active at f_ss
                et = TH.ElectroThermal(Ta + 273.15, theta, n_pe * E * f_ss, lambda Tk: n_pe * pl_pess(Tk))
                sol = et.solve()
                th_rows.append(dict(variant=name, theta_JA_K_W=theta, T_amb_C=Ta, T_max_C=Tmax, P_max_W=Pmax,
                                    E_MAC_fJ=E * 1e15, f_ss100_MHz=f_ss / 1e6, PE_leak_tt25_nW=leak["tt_025C_1v80"] * 1e9,
                                    PE_leak_tt100_nW=leak["tt_100C_1v80"] * 1e9, PE_leak_ss100_nW=leak["ss_100C_1v60"] * 1e9,
                                    PE_leak_ff100_nW=leak["ff_100C_1v95"] * 1e9, cells=ncell,
                                    n_PE_sustainable=n_pe, MAC_per_s=mac_s, TOPS=2 * mac_s / 1e12,
                                    die_area_mm2=die_mm2, power_density_W_cm2=Pmax / (die_mm2 / 100),
                                    Tj_solved_C=sol["T_j"] - 273.15, loop_gain=sol["loop_gain"], runaway=sol["runaway"]))
    write("thermal_envelope", th_rows)
    print("envelope tables written to", OUT)


if __name__ == "__main__":
    main()
