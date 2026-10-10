"""Structural generators for integer multipliers.

The algorithm (how partial products are formed and summed) is separated from
the circuit (which cells implement it):

  partial-product generation        reduction                  final addition
  -------------------------         ---------                  --------------
  'and'   unsigned AND array         'array_rc'  ripple rows    'ripple'
  'bw'    Baugh-Wooley (signed)      'array_cs'  carry-save     'kogge_stone'
  'booth4' radix-4 modified Booth     rows (Braun)               'brent_kung'
          (signed or unsigned)       'wallace'                  'sklansky'
                                     'dadda'

All builders work on *columns*: column j holds the nets of weight 2^j.  The
product is taken modulo 2^(na+nb) (the full product width), so constants
introduced by Baugh-Wooley and Booth sign handling are exact.

References for the algorithms (see data/sources.yaml): Wallace 1964, Dadda
1965, Booth 1951, MacSorley 1961 (radix-4), Baugh & Wooley 1973, Kogge &
Stone 1973, Brent & Kung 1982, Sklansky 1960.  Every generated netlist is
verified against Python integer multiplication (exhaustively up to 8x8).
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from .netlist import CONST0, CONST1, Netlist

Columns = List[List[int]]


# ---------------------------------------------------------------------------
# partial products
# ---------------------------------------------------------------------------

def _add_const(cols: Columns, value: int, width: int) -> None:
    value %= 1 << width
    for j in range(width):
        if (value >> j) & 1:
            cols[j].append(CONST1)


def pp_and(nl: Netlist, a: Sequence[int], b: Sequence[int], width: int) -> Columns:
    cols: Columns = [[] for _ in range(width)]
    for j, bj in enumerate(b):
        for i, ai in enumerate(a):
            if i + j < width:
                cols[i + j].append(nl.AND2(ai, bj, "pp"))
    return cols


def pp_rows_and(nl: Netlist, a, b, width) -> List[List[Tuple[int, int]]]:
    """Rows of (weight, net) for array multipliers (row j = a * b_j << j)."""
    rows = []
    for j, bj in enumerate(b):
        rows.append([(i + j, nl.AND2(ai, bj, "pp")) for i, ai in enumerate(a) if i + j < width])
    return rows


def pp_baugh_wooley(nl: Netlist, a, b, width) -> Columns:
    """Modified Baugh-Wooley for two's-complement a (n bits) and b (m bits).

    P = sum_{i<n-1,j<m-1} a_i b_j 2^(i+j) + a_{n-1} b_{m-1} 2^(n+m-2)
        + sum_{j<m-1} NAND(a_{n-1}, b_j) 2^(n-1+j) + sum_{i<n-1} NAND(a_i, b_{m-1}) 2^(i+m-1)
        + 2^(n-1) + 2^(m-1) - 2^(n+m-1)
    The identity is exact over the integers, so the columns are correct modulo
    2^width for any width >= n+m (for width = n+m the constant is the usual
    +2^(n+m-1)).
    """
    n, m = len(a), len(b)
    cols: Columns = [[] for _ in range(width)]
    for j in range(m):
        for i in range(n):
            w = i + j
            if w >= width:
                continue
            sa, sb = i == n - 1, j == m - 1
            if sa ^ sb:
                cols[w].append(nl.NAND2(a[i], b[j], "pp"))
            else:
                cols[w].append(nl.AND2(a[i], b[j], "pp"))
    _add_const(cols, (1 << (n - 1)) + (1 << (m - 1)) - (1 << (n + m - 1)), width)
    return cols


def pp_booth4(nl: Netlist, a, b, width, signed: bool) -> Columns:
    """Radix-4 modified Booth recoding of b; partial products d_k * a, d_k in {-2..2}.

    Unsigned operands are zero-extended by one bit (and b to an even length)
    so that the same signed recoding applies.  Each partial product is an
    (len(a)+1)-bit two's-complement number pp_k; its sign is handled by
    inverting the sign bit and adding the constant -2^(len(a)) * 4^k, and the
    two's-complement negation by adding neg_k at weight 4^k.
    """
    a = list(a)
    b = list(b)
    if not signed:
        a = a + [CONST0]
        b = b + [CONST0]
    if len(b) % 2:
        b = b + [b[-1]]           # sign-extend to even length
    na = len(a)
    cols: Columns = [[] for _ in range(width)]
    const = 0
    groups = len(b) // 2
    for k in range(groups):
        b_m1 = b[2 * k - 1] if k > 0 else CONST0
        b0, b1 = b[2 * k], b[2 * k + 1]
        # encoder
        one = nl.XOR2(b0, b_m1, "enc")
        x01 = nl.XOR2(b1, b0, "enc")
        two = nl.AND2(x01, nl.INV(one, "enc"), "enc")
        neg = b1
        base = 2 * k
        # selector bits j = 0..na  (a_{-1} = 0, a_na = a_{na-1} sign extension)
        sel = []
        for j in range(na + 1):
            aj = a[j] if j < na else a[na - 1]
            ajm1 = a[j - 1] if j >= 1 else CONST0
            t1 = nl.AND2(one, aj, "pp")
            t = nl.AO21(two, ajm1, t1, "pp")       # (two & a_{j-1}) | (one & a_j)
            sel.append(nl.XOR2(t, neg, "pp"))
        # bits 0..na-1 positive weight, bit na is the sign (negative weight)
        for j in range(na):
            w = base + j
            if w < width:
                cols[w].append(sel[j])
        w = base + na
        if w < width:
            cols[w].append(nl.INV(sel[na], "pp"))
        const -= 1 << (base + na)
        if base < width:
            cols[base].append(neg)
    _add_const(cols, const, width)
    return cols


# ---------------------------------------------------------------------------
# column reduction (trees)
# ---------------------------------------------------------------------------

def _compress_constants(nl: Netlist, cols: Columns) -> Columns:
    """Replace multiple CONST1 bits in a column by their binary sum (keeps exactness)."""
    width = len(cols)
    carry_const = 0
    for j in range(width):
        n1 = sum(1 for x in cols[j] if x == CONST1) + carry_const
        cols[j] = [x for x in cols[j] if x not in (CONST0, CONST1)]
        if n1 & 1:
            cols[j].append(CONST1)
        carry_const = n1 >> 1
    return cols


def reduce_wallace(nl: Netlist, cols: Columns) -> Columns:
    """Wallace (1964): in every stage, every complete group of 3 bits -> FA, a
    remaining pair -> HA, until every column has at most 2 bits."""
    cols = _compress_constants(nl, [list(c) for c in cols])
    width = len(cols)
    stage = 0
    while max(len(c) for c in cols) > 2:
        new: Columns = [[] for _ in range(width)]
        for j in range(width):
            c = cols[j]
            i = 0
            while len(c) - i >= 3:
                s, co = nl.FA(c[i], c[i + 1], c[i + 2], "red")
                new[j].append(s)
                if j + 1 < width:
                    new[j + 1].append(co)
                i += 3
            if len(c) - i == 2:
                s, co = nl.HA(c[i], c[i + 1], "red")
                new[j].append(s)
                if j + 1 < width:
                    new[j + 1].append(co)
                i += 2
            new[j].extend(c[i:])
        cols = new
        stage += 1
    nl.meta["reduction_stages"] = stage
    return cols


def dadda_heights(max_h: int) -> List[int]:
    d = [2]
    while d[-1] < max_h:
        d.append(int(d[-1] * 1.5))
    return d


def reduce_dadda(nl: Netlist, cols: Columns) -> Columns:
    """Dadda (1965): reduce column heights to the sequence 2, 3, 4, 6, 9, 13, ...
    using as few counters as possible in each stage, working LSB to MSB."""
    cols = _compress_constants(nl, [list(c) for c in cols])
    width = len(cols)
    heights = dadda_heights(max(len(c) for c in cols))
    targets = [h for h in reversed(heights) if h < max(len(c) for c in cols)]
    stage = 0
    for d in targets:
        new: Columns = [[] for _ in range(width)]
        carries_in: List[int] = []
        for j in range(width):
            c = list(cols[j])
            avail = c
            h = len(avail) + len(carries_in)
            out_bits = list(carries_in)
            carries_out: List[int] = []
            i = 0
            while h > d:
                if h - d >= 2 and len(avail) - i >= 3:
                    s, co = nl.FA(avail[i], avail[i + 1], avail[i + 2], "red")
                    i += 3
                    h -= 2
                elif len(avail) - i >= 2:
                    s, co = nl.HA(avail[i], avail[i + 1], "red")
                    i += 2
                    h -= 1
                else:
                    raise RuntimeError("Dadda reduction failed")
                out_bits.append(s)
                carries_out.append(co)
            out_bits.extend(avail[i:])
            new[j] = out_bits
            carries_in = carries_out if j + 1 < width else []
        cols = new
        stage += 1
    nl.meta["reduction_stages"] = stage
    return cols


# ---------------------------------------------------------------------------
# final carry-propagate adders on two rows
# ---------------------------------------------------------------------------

def _two_rows(cols: Columns) -> Tuple[List[int], List[int]]:
    x, y = [], []
    for c in cols:
        if len(c) > 2:
            raise ValueError("column with more than two bits")
        x.append(c[0] if len(c) > 0 else CONST0)
        y.append(c[1] if len(c) > 1 else CONST0)
    return x, y


def cpa_ripple(nl: Netlist, cols: Columns, group: str = "cpa") -> List[int]:
    x, y = _two_rows(cols)
    out = []
    c = CONST0
    for xi, yi in zip(x, y):
        s, c = nl.FA(xi, yi, c, group)
        out.append(s)
    return out


def _prefix(nl: Netlist, x, y, network: str, group: str = "cpa") -> List[int]:
    """Parallel-prefix adder.  (g, p) combine: g = g_hi | p_hi & g_lo, p = p_hi & p_lo."""
    n = len(x)
    g = []
    p = []
    for xi, yi in zip(x, y):
        s_, c_ = nl.HA(xi, yi, group)   # p = x^y, g = x&y
        p.append(s_)
        g.append(c_)
    P0 = list(p)
    G = list(g)
    P = list(p)

    def combine(i, j):  # combine span ending at i with span ending at j (j < i)
        gi = nl.AO21(P[i], G[j], G[i], group)
        pi = nl.AND2(P[i], P[j], group)
        return gi, pi

    if network == "kogge_stone":
        d = 1
        while d < n:
            newG, newP = list(G), list(P)
            for i in range(d, n):
                newG[i], newP[i] = combine(i, i - d)
            G, P = newG, newP
            d *= 2
    elif network == "sklansky":
        d = 1
        while d < n:
            newG, newP = list(G), list(P)
            for i in range(n):
                if (i // d) % 2 == 1:
                    j = (i // d) * d - 1
                    newG[i], newP[i] = combine(i, j)
            G, P = newG, newP
            d *= 2
    elif network == "brent_kung":
        # up-sweep
        d = 1
        while d < n:
            for i in range(2 * d - 1, n, 2 * d):
                G[i], P[i] = combine(i, i - d)
            d *= 2
        # down-sweep
        d //= 2
        while d >= 1:
            for i in range(3 * d - 1, n, 2 * d):
                G[i], P[i] = combine(i, i - d)
            d //= 2
    else:
        raise ValueError(network)
    out = [P0[0]]
    for i in range(1, n):
        out.append(nl.XOR2(P0[i], G[i - 1], group))
    return out


def cpa(nl: Netlist, cols: Columns, kind: str, group: str = "cpa") -> List[int]:
    if kind == "ripple":
        return cpa_ripple(nl, cols, group)
    x, y = _two_rows(cols)
    return _prefix(nl, x, y, kind, group)


# ---------------------------------------------------------------------------
# array multipliers (row-by-row accumulation)
# ---------------------------------------------------------------------------

def array_ripple_rows(nl: Netlist, rows, width: int) -> List[int]:
    """Each partial-product row is added to the running sum by a ripple-carry adder."""
    acc = [CONST0] * width
    for j, row in enumerate(rows):
        add = [CONST0] * width
        for w, net in row:
            add[w] = net
        out = []
        c = CONST0
        for i in range(width):
            s, c = nl.FA(acc[i], add[i], c, "red")
            out.append(s)
        acc = out
    nl.meta["reduction_stages"] = len(rows)
    return acc


def array_carry_save(nl: Netlist, rows, width: int, final: str) -> List[int]:
    """Braun-style carry-save array: rows of FAs pass carries diagonally to the
    next row (no carry propagation inside a row); a final adder merges the
    last sum and carry vectors."""
    s = [CONST0] * width
    c = [CONST0] * width   # carry vector (already shifted to its weight)
    for row in rows:
        add = [CONST0] * width
        for w, net in row:
            add[w] = net
        ns = [CONST0] * width
        nc = [CONST0] * width
        for i in range(width):
            si, ci = nl.FA(s[i], c[i], add[i], "red")
            ns[i] = si
            if i + 1 < width:
                nc[i + 1] = ci
        s, c = ns, nc
    nl.meta["reduction_stages"] = len(rows)
    cols = [[x for x in (s[i], c[i]) if x != CONST0] for i in range(width)]
    return cpa(nl, cols, final)


# ---------------------------------------------------------------------------
# top level
# ---------------------------------------------------------------------------

ARCHS = {
    # name: (pp, reduction, final adder)
    "array_rc": ("and", "array_rc", "ripple"),
    "braun": ("and", "array_cs", "ripple"),
    "wallace_rca": ("and", "wallace", "ripple"),
    "wallace_ks": ("and", "wallace", "kogge_stone"),
    "dadda_rca": ("and", "dadda", "ripple"),
    "dadda_ks": ("and", "dadda", "kogge_stone"),
    "dadda_bk": ("and", "dadda", "brent_kung"),
    "dadda_sk": ("and", "dadda", "sklansky"),
    "booth4_wallace_ks": ("booth4", "wallace", "kogge_stone"),
    "booth4_dadda_rca": ("booth4", "dadda", "ripple"),
    "booth4_dadda_ks": ("booth4", "dadda", "kogge_stone"),
    "bw_array_cs": ("bw", "array_cs", "ripple"),
    "bw_dadda_ks": ("bw", "dadda", "kogge_stone"),
    "bw_wallace_rca": ("bw", "wallace", "ripple"),
}


def build_multiplier(n: int, m: int, pp: str, red: str, final: str, signed: bool,
                     name: str = "") -> Netlist:
    width = n + m
    nl = Netlist(name or f"mul{n}x{m}_{pp}_{red}_{final}_{'s' if signed else 'u'}")
    a = nl.add_input("a", n)
    b = nl.add_input("b", m)
    nl.meta.update(dict(n=n, m=m, pp=pp, red=red, final=final, signed=signed, width=width))
    if pp == "bw" and not signed:
        raise ValueError("Baugh-Wooley is for signed operands")
    if pp == "and" and signed:
        raise ValueError("plain AND partial products are unsigned; use 'bw' or 'booth4'")
    if red.startswith("array"):
        if pp == "and":
            rows = pp_rows_and(nl, a, b, width)
        elif pp == "bw":
            cols = pp_baugh_wooley(nl, a, b, width)
            # convert columns into rows by bit index (row j holds the j-th entry of each column)
            depth = max(len(c) for c in cols)
            rows = [[(w, cols[w][k]) for w in range(width) if k < len(cols[w])] for k in range(depth)]
            # constants: merge into rows as ordinary bits (folded by FA constant logic)
        else:
            raise ValueError("array reductions implemented for 'and' and 'bw' partial products")
        if red == "array_rc":
            out = array_ripple_rows(nl, rows, width)
        else:
            out = array_carry_save(nl, rows, width, final)
    else:
        if pp == "and":
            cols = pp_and(nl, a, b, width)
        elif pp == "bw":
            cols = pp_baugh_wooley(nl, a, b, width)
        elif pp == "booth4":
            cols = pp_booth4(nl, a, b, width, signed)
        else:
            raise ValueError(pp)
        nl.meta["pp_bits"] = sum(len([x for x in c if x not in (CONST0, CONST1)]) for c in cols)
        nl.meta["max_column_height"] = max(len(c) for c in cols)
        if red == "wallace":
            cols = reduce_wallace(nl, cols)
        elif red == "dadda":
            cols = reduce_dadda(nl, cols)
        else:
            raise ValueError(red)
        out = cpa(nl, cols, final)
    nl.set_output("p", out[:width])
    # remove logic whose outputs are unused (carries beyond the product width,
    # prefix-tree terms that no sum bit needs); synthesis would remove it too
    nl.meta["pruned_gates"] = nl.prune()
    return nl


def build(arch: str, n: int, signed: bool = None) -> Netlist:
    pp, red, final = ARCHS[arch]
    if signed is None:
        signed = pp in ("bw",)
    return build_multiplier(n, n, pp, red, final, signed, name=f"mul{n}_{arch}_{'s' if signed else 'u'}")
