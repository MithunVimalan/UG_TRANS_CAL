"""Information-theoretic (logical irreversibility) content of arithmetic operations.

Landauer's bound applies to *erased* information.  How much information an
operation erases depends on what is kept:

  * algorithm level, output-only:  an operation f that keeps only its output
    erases at least H(X) - H(f(X)) bits per evaluation (X = the input random
    variable).  For multiplication of independent uniform n-bit operands this
    is computed here exactly by enumeration.
  * reversible embedding (Bennett 1973): keep the inputs (or uncompute), erase
    nothing -> no Landauer floor, at a cost in time and storage.
  * gate level: if every gate's inputs are discarded after evaluation, each
    gate erases H(inputs of that gate) - H(outputs of that gate) given the
    actual joint input statistics.  This is a *model* of irreversible logic,
    not a law; CMOS dissipation is unrelated to it in practice (CV^2 >> kT).

Entropies are in bits.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Dict, Iterable, List, Tuple

from .arith.netlist import Netlist


def entropy(counts: Iterable[int]) -> float:
    counts = [c for c in counts if c]
    n = sum(counts)
    return -sum(c / n * math.log2(c / n) for c in counts)


def multiplication_entropy_loss(n: int, signed: bool = False) -> Dict[str, float]:
    """Exact H(A,B) - H(A*B) for independent uniform n-bit operands."""
    import numpy as np
    vals = np.arange(1 << n, dtype=np.int64)
    if signed:
        vals = np.where(vals >= (1 << (n - 1)), vals - (1 << n), vals)
    prod = np.multiply.outer(vals, vals).ravel()
    _, counts = np.unique(prod, return_counts=True)
    h_out = entropy(counts.tolist())
    h_in = 2.0 * n
    return dict(n=n, signed=signed, H_in_bits=h_in, H_out_bits=h_out, erased_bits=h_in - h_out,
                distinct_products=int(len(counts)))


def mac_entropy_loss(n: int, W: int) -> Dict[str, float]:
    """ACC' = ACC + A*B mod 2^W with uniform independent ACC (W bits), A, B (n bits):
    for fixed (A,B) the map ACC -> ACC' is a bijection, so H(ACC') = W and the
    erased information when A, B are discarded is exactly 2n bits."""
    return dict(n=n, W=W, H_in_bits=W + 2 * n, H_out_bits=float(W), erased_bits=2.0 * n)


def gate_level_erasure(nl: Netlist, values: Dict[int, int], nvec: int) -> Dict[str, float]:
    """Sum over gates of H(inputs) - H(outputs) from bit-sliced simulation values.

    ``values`` maps net -> bit-sliced integer over nvec samples (from
    Netlist.simulate).  Joint statistics per gate are estimated empirically.
    """
    total = 0.0
    by_kind: Dict[str, float] = {}
    for g in nl.gates:
        if g.kind == "DFF":
            continue
        cin: Counter = Counter()
        cout: Counter = Counter()
        ins = [values[x] for x in g.ins]
        outs = [values[x] for x in g.outs]
        # enumerate joint patterns by masking: iterate over all 2^k input patterns
        k = len(ins)
        for pat in range(1 << k):
            m = (1 << nvec) - 1
            for i in range(k):
                m &= ins[i] if (pat >> i) & 1 else ~ins[i]
            c = bin(m & ((1 << nvec) - 1)).count("1")
            if c:
                cin[pat] = c
        ko = len(outs)
        for pat in range(1 << ko):
            m = (1 << nvec) - 1
            for i in range(ko):
                m &= outs[i] if (pat >> i) & 1 else ~outs[i]
            c = bin(m & ((1 << nvec) - 1)).count("1")
            if c:
                cout[pat] = c
        e = entropy(cin.values()) - entropy(cout.values())
        total += e
        by_kind[g.kind] = by_kind.get(g.kind, 0.0) + e
    return dict(total_bits=total, by_kind=by_kind)
