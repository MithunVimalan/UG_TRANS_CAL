#!/usr/bin/env python3
"""Generate the numeric tables quoted in docs/report from the ugcal code.

Every number in the fundamental-limit, information-content and
accumulator-sizing tables of the report is produced here, so the report and
the framework cannot drift apart.  Output: results/tables/*.csv and *.md
"""
import csv
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ugcal import constants as K  # noqa: E402
from ugcal import fundamental as F  # noqa: E402
from ugcal.infotheory import mac_entropy_loss, multiplication_entropy_loss  # noqa: E402
from ugcal.mac import accumulator_width  # noqa: E402
from ugcal.provenance import spec  # noqa: E402
from ugcal.units import celsius, q  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results", "tables")


def write(name, header, rows, fmt=None):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name + ".csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    with open(os.path.join(OUT, name + ".md"), "w") as fh:
        fh.write("| " + " | ".join(header) + " |\n|" + "---|" * len(header) + "\n")
        for r in rows:
            fh.write("| " + " | ".join(str(x) for x in r) + " |\n")


def g(x, d=4):
    return f"{x:.{d}g}"


def fundamental():
    temps = [("300 K", q(300, "K")), ("25 C", celsius(25)), ("100 C", celsius(100))]
    rows = []
    for label, T in temps:
        t = spec("T", T, "K")
        kT = (K.k_B.value * T).to("J")
        rows.append([label, g(kT), g(F.thermal_voltage(t).value.to("mV")), g(F.landauer(t).value.to("J")),
                     g(F.subthreshold_swing_limit(t).value.to("mV")), g(F.min_supply_ideal_inverter(t).value.to("mV")),
                     g(F.min_supply_swanson_meindl(t).value.to("mV")),
                     g(F.energy_for_error_probability(1e-15, t).value.to("J")),
                     g(F.barrier_for_retention(1e-15, t).value.to("J"))])
    write("fundamental_limits",
          ["T", "kT (J)", "kT/q (mV)", "kT ln2 (J)", "SS_min (mV/dec)", "2 ln2 kT/q (mV)", "8 kT/q (mV)",
           "E_s for p=1e-15, kT/C model (J)", "E_b for p=1e-15, barrier (J)"], rows)
    # error-probability ladder at 300 K
    t = spec("T", q(300, "K"), "K")
    kT = (K.k_B.value * q(300, "K")).to("J")
    rows = []
    for p in (1e-3, 1e-6, 1e-9, 1e-12, 1e-15, 1e-18, 1e-24):
        es = F.energy_for_error_probability(p, t).value.to("J")
        eb = F.barrier_for_retention(p, t).value.to("J")
        rows.append([f"{p:g}", g(es), g(es / kT), g(eb), g(eb / kT)])
    write("error_probability_energy_300K",
          ["p", "E_s = 2kT[Q^-1(p)]^2 (J)", "E_s/kT", "E_b = kT ln(1/p) (J)", "E_b/kT"], rows)
    # quantum speed limit at representative energies
    rows = []
    for e in ("1 aJ", "1 fJ", "10 fJ", "1 pJ"):
        val, unit = e.split()
        E = spec("E", q(float(val), unit), "J")
        rows.append([e, g(F.margolus_levitin_time(E).value.to("s"))])
    write("margolus_levitin", ["mean energy above ground state", "t_min = h/(4E) (s)"], rows)


def information():
    kT = (K.k_B.value * q(300, "K")).to("J")
    rows = []
    for n in (4, 8, 12):
        for s in (False, True):
            r = multiplication_entropy_loss(n, s)
            rows.append([n, "signed" if s else "unsigned", g(r["H_out_bits"], 5), g(r["erased_bits"], 4),
                         r["distinct_products"], g(r["erased_bits"] * kT * math.log(2))])
    write("multiplication_information",
          ["n", "operands", "H(product) bits", "erased bits H(A,B)-H(AB)", "distinct products",
           "Landauer floor at 300 K (J)"], rows)
    rows = []
    for n, W in ((8, 22), (16, 38)):
        r = mac_entropy_loss(n, W)
        rows.append([n, W, r["erased_bits"], g(r["erased_bits"] * kT * math.log(2))])
    write("mac_information", ["n", "W", "erased bits (operands discarded)", "Landauer floor at 300 K (J)"], rows)


def accumulators():
    rows = []
    for n in (4, 8, 16):
        for K_ in (1, 9, 64, 256, 1024, 4096):
            rows.append([n, K_, accumulator_width(n, n, K_, True), accumulator_width(n, n, K_, False)])
    write("accumulator_width", ["n", "K (terms)", "W signed", "W unsigned"], rows)


if __name__ == "__main__":
    fundamental()
    information()
    accumulators()
    print("tables written to", os.path.abspath(OUT))
