#!/usr/bin/env python3
"""State-by-state cell leakage: Liberty vs ngspice on the foundry model corners.

For each cell and each Liberty ``leakage_power(when)`` state, the static
supply power (VPWR + n-well) is computed by a DC operating point on the
layout-extracted cell (junction areas matter for junction leakage) with a
GMIN of 1e-20 S (ngspice's default 1e-12 S injects ~1.8 pA per junction at
1.8 V, comparable to the real off-current at 25 C).

Liberty corners are compared with the SPICE corner of the same name and with
the PDK's 'leak' and 'tt_leak' model sets (present in models/corners but not
exposed by sky130.lib.spice).  Which model set produced the Liberty leakage
is not documented.

Output: results/spice/leakage_study.csv
"""
import csv
import itertools
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from ugcal.liberty import Library  # noqa: E402
from ugcal.gatesim import compile_expr  # noqa: E402
from ugcal.sim import cellchar as cc  # noqa: E402
from ugcal.sim import ngspice as ng  # noqa: E402

CELLS = {"inv_1": ["A"], "nand2_1": ["A", "B"], "nor2_1": ["A", "B"], "and2_1": ["A", "B"],
         "xor2_1": ["A", "B"], "a21o_1": ["A1", "A2", "B1"], "ha_1": ["A", "B"], "fa_1": ["A", "B", "CIN"],
         "mux2_1": ["A0", "A1", "S"]}
CORNERS = [("tt_025C_1v80", ["tt", "tt_leak", "leak"]),
           ("tt_100C_1v80", ["tt", "leak"]),
           ("ss_100C_1v60", ["ss", "tt", "leak"]),
           ("ff_100C_1v95", ["ff", "leak"]),
           ("ff_n40C_1v95", ["ff"]),
           ("ss_n40C_1v60", ["ss"])]


def decode(c):
    m = re.fullmatch(r"(tt|ss|ff)_(n?)(\d+)C_(\d)v(\d+)", c)
    return m.group(1), (-1 if m.group(2) else 1) * float(m.group(3)), float(f"{m.group(4)}.{m.group(5)}")


def main():
    ng.CELL_VIEW = os.environ.get("UGCAL_CELL_VIEW", "extracted")
    rows = []
    for libc, spice_corners in CORNERS:
        lib = Library(os.path.join(ng.pdk_root(), "sc_hd", "timing", f"sky130_fd_sc_hd__{libc}.lib"))
        proc, T, V = decode(libc)
        for cell, pins in CELLS.items():
            c = lib.cell(f"sky130_fd_sc_hd__{cell}")
            for when, val in c.leakage_states:
                f = compile_expr(when)
                # find the input assignment that satisfies 'when'
                assign = None
                for bits in itertools.product((0, 1), repeat=len(pins)):
                    env = dict(zip(pins, bits))
                    try:
                        if f(env):
                            assign = env
                            break
                    except KeyError:
                        continue
                if assign is None:
                    continue
                row = dict(libcorner=libc, cell=cell, when=when, lib_nW=val * lib.units.leakage * 1e9)
                for sc in spice_corners:
                    p = cc.static_power(cell, V, T, sc, {k: V * b for k, b in assign.items()})
                    row[f"spice_{sc}_nW"] = p * 1e9
                rows.append(row)
                print(", ".join(f"{k}={v:.4g}" if isinstance(v, float) else f"{k}={v}" for k, v in row.items()),
                      flush=True)
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    out = os.path.join(ng.repo_root(), "results", "spice", "leakage_study.csv")
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
        fh.write(f"# cell view: {ng.CELL_VIEW}; ngspice {ng.ngspice_version()}; GMIN 1e-20 S\n")


if __name__ == "__main__":
    main()
