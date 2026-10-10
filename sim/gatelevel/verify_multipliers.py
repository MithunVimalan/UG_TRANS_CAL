#!/usr/bin/env python3
"""Functional verification of every multiplier netlist used in the report (evidence level 0, D11).

* Generated architectures: exhaustive at 4, 6 and 8 bits (2^(2n) operand pairs,
  bit-sliced simulation); 16x16 with 100 000 random pairs.
* Yosys/ABC netlists (results/synth/mul*_abcarea.v): exhaustive at 8 bits,
  random at 16 bits (needs the PDK Liberty for the cell functions).

Output: results/power/verification.csv
"""
import csv
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from ugcal.arith.multipliers import ARCHS, build_multiplier  # noqa: E402
from ugcal.arith.netlist import exhaustive_inputs, pack_inputs  # noqa: E402
from ugcal.sim.ngspice import pdk_root, repo_root  # noqa: E402


def check(nl, n, signed, pairs=None):
    """Return (errors, vectors). pairs=None -> exhaustive."""
    if pairs is None:
        ins, nvec = exhaustive_inputs({"a": n, "b": n})
        pairs = [(k & ((1 << n) - 1), k >> n) for k in range(nvec)]
    else:
        ins, nvec = pack_inputs({"a": n, "b": n}, [{"a": a, "b": b} for a, b in pairs]), len(pairs)
    v = nl.simulate(ins, nvec)
    outs = nl.outputs["p"]
    bad = 0
    for k, (a, b) in enumerate(pairs):
        if signed:
            a -= (a >> (n - 1)) << n
            b -= (b >> (n - 1)) << n
        got = 0
        for i, net in enumerate(outs):
            got |= ((v[net] >> k) & 1) << i
        bad += got != (a * b) % (1 << (2 * n))
    return bad, nvec


def main():
    rows = []
    rnd = random.Random(16)
    rand16 = [(rnd.randrange(1 << 16), rnd.randrange(1 << 16)) for _ in range(100000)]
    for n in (4, 6, 8, 16):
        for arch, (pp, red, fin) in ARCHS.items():
            for signed in ([False, True] if pp == "booth4" else [pp == "bw"]):
                nl = build_multiplier(n, n, pp, red, fin, signed)
                bad, nv = check(nl, n, signed, rand16 if n == 16 else None)
                rows.append(dict(design=arch, n=n, signed=signed, method="random" if n == 16 else "exhaustive",
                                 vectors=nv, errors=bad))
                print(rows[-1], flush=True)
    lib_path = os.path.join(pdk_root(), "sc_hd", "timing", "sky130_fd_sc_hd__tt_025C_1v80.lib")
    if os.path.exists(lib_path):
        from ugcal.arith.vimport import import_verilog
        from ugcal.liberty import Library
        lib = Library(lib_path)
        for name, n, signed in (("mul8u", 8, False), ("mul8s", 8, True), ("mul16u", 16, False)):
            path = os.path.join(repo_root(), "results", "synth", f"{name}_abcarea.v")
            if not os.path.exists(path):
                continue
            nl = import_verilog(open(path).read(), lib, group="syn")
            bad, nv = check(nl, n, signed, rand16 if n == 16 else None)
            rows.append(dict(design=f"yosys_abc ({name})", n=n, signed=signed,
                             method="random" if n == 16 else "exhaustive", vectors=nv, errors=bad))
            print(rows[-1], flush=True)
    with open(os.path.join(repo_root(), "results", "power", "verification.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    total_bad = sum(r["errors"] for r in rows)
    print(f"{len(rows)} netlists, {sum(r['vectors'] for r in rows)} vectors, {total_bad} errors")
    return 1 if total_bad else 0


if __name__ == "__main__":
    sys.exit(main())
