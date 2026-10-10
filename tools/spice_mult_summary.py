#!/usr/bin/env python3
"""Ranges quoted in D7 §7 from results/spice/multiplier_spice_summary_extracted_lod.csv (prints, and fills
the SPICE_* placeholders / previous values between the D7 'Reading the table' markers if --write)."""
import csv
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def stats():
    rows = list(csv.DictReader(open(os.path.join(ROOT, "results", "spice", "multiplier_spice_summary_extracted_lod.csv"))))
    f = lambda r, k: float(r[k])
    si = [f(r, "spice_E_fJ") / f(r, "gate_inertial_fJ") for r in rows]
    st = [f(r, "spice_E_fJ") / f(r, "gate_transport_fJ") for r in rows]
    sz = [f(r, "spice_E_fJ") / f(r, "gate_zero_fJ") for r in rows]
    by_s = [r["design"] for r in sorted(rows, key=lambda r: f(r, "spice_E_fJ"))]
    by_i = [r["design"] for r in sorted(rows, key=lambda r: f(r, "gate_inertial_fJ"))]
    return dict(n=len(rows), inert=(min(si), max(si)), trans=(min(st), max(st)), zero=(min(sz), max(sz)),
                same_order=by_s == by_i, order_spice=by_s, order_inertial=by_i)


if __name__ == "__main__":
    s = stats()
    print(s)
    sys.exit(0 if s["same_order"] else 1)
