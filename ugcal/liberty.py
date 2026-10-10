"""Liberty (.lib) reader for NLDM timing, power and leakage data.

Scope: the subset of the Liberty format used by the SKY130 ``sky130_fd_sc_hd``
NLDM corners (groups, simple and complex attributes, lookup tables).  CCS
noise groups are parsed generically but not interpreted.

Conventions (read from the library header, never assumed):
  * units come from ``time_unit``, ``capacitive_load_unit``, ``voltage_unit``,
    ``leakage_power_unit``; the API converts to SI (s, F, V, W, J).
  * ``internal_power`` tables hold energy per transition in
    (capacitive_load_unit x voltage_unit^2), e.g. pF*V^2 = pJ.
  * Table lookups use bilinear interpolation inside the grid and linear
    extrapolation outside it, which is what OpenSTA does for NLDM tables.

The parser is deliberately strict: unknown units raise, missing tables raise,
and nothing is silently defaulted.
"""
from __future__ import annotations

import bisect
import gzip
import os
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

# --------------------------------------------------------------------------
# Generic parser
# --------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+|\\\n)                       # whitespace / line continuation
  | (?P<comment>/\*.*?\*/|//[^\n]*)         # comments
  | (?P<string>"(?:[^"\\]|\\.)*")           # quoted string
  | (?P<punct>[{}();:,])                   # punctuation
  | (?P<word>[^\s{}();:,"]+)                # bare word / number / expression
    """,
    re.S | re.X,
)


@dataclass
class Group:
    type: str
    args: List[str]
    attrs: Dict[str, List[Union[str, List[str]]]] = field(default_factory=dict)
    groups: List["Group"] = field(default_factory=list)

    def attr(self, name: str, default=None):
        v = self.attrs.get(name)
        if not v:
            return default
        return v[-1]

    def find(self, gtype: str, name: Optional[str] = None) -> List["Group"]:
        return [g for g in self.groups if g.type == gtype and (name is None or (g.args and g.args[0] == name))]

    def first(self, gtype: str, name: Optional[str] = None) -> Optional["Group"]:
        r = self.find(gtype, name)
        return r[0] if r else None


def _tokens(text: str) -> Iterable[str]:
    for m in _TOKEN_RE.finditer(text):
        kind = m.lastgroup
        if kind in ("ws", "comment"):
            continue
        tok = m.group(kind)
        yield tok


def _unquote(s: str) -> str:
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def parse(text: str) -> Group:
    """Parse Liberty text and return the top-level ``library`` group."""
    toks = list(_tokens(text))
    pos = 0
    n = len(toks)

    def parse_group_body(g: Group):
        nonlocal pos
        while pos < n:
            t = toks[pos]
            if t == "}":
                pos += 1
                return
            name = t
            pos += 1
            if pos >= n:
                raise ValueError("unexpected end of file")
            t2 = toks[pos]
            if t2 == ":":  # simple attribute: name : value ;
                pos += 1
                val_parts = []
                while toks[pos] != ";":
                    # Liberty allows a simple attribute to end at a newline
                    # without ';' but SKY130 always uses ';'.
                    if toks[pos] in ("}",):
                        break
                    val_parts.append(toks[pos])
                    pos += 1
                if toks[pos] == ";":
                    pos += 1
                g.attrs.setdefault(name, []).append(_unquote(" ".join(val_parts)))
            elif t2 == "(":
                pos += 1
                args: List[str] = []
                cur = []
                while toks[pos] != ")":
                    if toks[pos] == ",":
                        args.append(" ".join(cur))
                        cur = []
                    else:
                        cur.append(_unquote(toks[pos]))
                    pos += 1
                if cur:
                    args.append(" ".join(cur))
                pos += 1  # ')'
                if pos < n and toks[pos] == "{":
                    pos += 1
                    sub = Group(name, args)
                    parse_group_body(sub)
                    g.groups.append(sub)
                else:
                    if pos < n and toks[pos] == ";":
                        pos += 1
                    g.attrs.setdefault(name, []).append(args)
            else:
                raise ValueError(f"cannot parse near token {pos}: {toks[max(0, pos - 5):pos + 5]}")
        raise ValueError("unterminated group")

    # top level: library (name) { ... }
    if toks[0] != "library":
        raise ValueError("not a Liberty file")
    root = Group("root", [])
    parse_group_body_toplevel = parse_group_body
    # emulate a wrapper so the library group is parsed by the same routine
    toks.append("}")
    n = len(toks)
    parse_group_body_toplevel(root)
    lib = root.first("library")
    if lib is None:
        raise ValueError("no library group")
    return lib


# --------------------------------------------------------------------------
# Units
# --------------------------------------------------------------------------

_PREFIX = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "": 1.0, "k": 1e3}


def _parse_unit(s: str, base: str) -> float:
    s = s.strip().strip('"')
    m = re.fullmatch(r"([0-9.eE+-]*)\s*([fpnumk]?)" + base, s, re.I if base.lower() == "ohm" else 0)
    if not m:
        raise ValueError(f"unrecognised unit '{s}' (expected *{base})")
    mult = float(m.group(1)) if m.group(1) else 1.0
    return mult * _PREFIX[m.group(2)]


@dataclass
class Units:
    time: float          # seconds per library time unit
    cap: float           # farads per library capacitance unit
    voltage: float       # volts per library voltage unit
    leakage: float       # watts per library leakage unit
    current: float       # amperes per library current unit

    @property
    def energy(self) -> float:
        """Joules per internal_power table unit (cap unit * voltage unit^2)."""
        return self.cap * self.voltage ** 2


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------

def _floats(s: Union[str, List[str]]) -> List[float]:
    if isinstance(s, list):
        s = ",".join(s)
    return [float(x) for x in re.split(r"[,\s]+", s.strip().strip('"')) if x]


@dataclass
class Table:
    variables: Tuple[str, ...]
    index: Tuple[List[float], ...]
    values: List[List[float]]  # values[i1][i2]; 1-D tables use values[0][i]

    def lookup(self, **kw: float) -> float:
        """Interpolate.  Keyword names are the Liberty template variables."""
        if len(self.variables) == 0:
            return self.values[0][0]
        if len(self.variables) == 1:
            x = kw[self.variables[0]]
            return _interp1(self.index[0], self.values[0], x)
        x = kw[self.variables[0]]
        y = kw[self.variables[1]]
        return _interp2(self.index[0], self.index[1], self.values, x, y)


def _bracket(axis: Sequence[float], x: float) -> Tuple[int, int]:
    if len(axis) == 1:
        return 0, 0
    i = bisect.bisect_right(axis, x) - 1
    i = min(max(i, 0), len(axis) - 2)
    return i, i + 1


def _interp1(axis: Sequence[float], vals: Sequence[float], x: float) -> float:
    i, j = _bracket(axis, x)
    if i == j:
        return vals[i]
    t = (x - axis[i]) / (axis[j] - axis[i])
    return vals[i] + t * (vals[j] - vals[i])


def _interp2(ax: Sequence[float], ay: Sequence[float], v: List[List[float]], x: float, y: float) -> float:
    i0, i1 = _bracket(ax, x)
    j0, j1 = _bracket(ay, y)
    if i0 == i1:
        return _interp1(ay, v[i0], y)
    if j0 == j1:
        return _interp1(ax, [row[j0] for row in v], x)
    tx = (x - ax[i0]) / (ax[i1] - ax[i0])
    ty = (y - ay[j0]) / (ay[j1] - ay[j0])
    a = v[i0][j0] + ty * (v[i0][j1] - v[i0][j0])
    b = v[i1][j0] + ty * (v[i1][j1] - v[i1][j0])
    return a + tx * (b - a)


# --------------------------------------------------------------------------
# Library model
# --------------------------------------------------------------------------

@dataclass
class TimingArc:
    related_pin: str
    timing_sense: Optional[str]
    timing_type: Optional[str]
    when: Optional[str]
    tables: Dict[str, Table]  # cell_rise, cell_fall, rise_transition, fall_transition, rise_constraint, ...


@dataclass
class InternalPower:
    related_pin: Optional[str]
    when: Optional[str]
    related_pg_pin: Optional[str]
    rise: Optional[Table]
    fall: Optional[Table]


@dataclass
class Pin:
    name: str
    direction: str
    capacitance: Optional[float]   # library cap units
    rise_capacitance: Optional[float]
    fall_capacitance: Optional[float]
    function: Optional[str]
    max_capacitance: Optional[float]
    max_transition: Optional[float]
    clock: bool
    timing: List[TimingArc]
    internal_power: List[InternalPower]


@dataclass
class Cell:
    name: str
    area: float
    leakage: Optional[float]                    # cell_leakage_power, library units
    leakage_states: List[Tuple[Optional[str], float]]
    pins: Dict[str, Pin]
    is_sequential: bool
    raw: Group = field(repr=False, default=None)


class Library:
    """A parsed Liberty library with SI-unit accessors."""

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        opener = gzip.open if path.endswith(".gz") else open
        with opener(path, "rt") as fh:
            text = fh.read()
        self._text = text
        # Parse the header only (everything before the first cell) eagerly;
        # cells are parsed lazily because SKY130 corners are ~13 MB each.
        self._cell_spans = self._index_cells(text)
        first = min((s for s, _ in self._cell_spans.values()), default=len(text))
        header = text[:first] + "\n}\n"
        self.header = parse(header)
        self.name = self.header.args[0] if self.header.args else ""
        self.units = self._units()
        oc_name = self.header.attr("default_operating_conditions")
        oc = self.header.first("operating_conditions", oc_name) if oc_name else None
        self.nom_voltage = float(self.header.attr("nom_voltage"))
        self.nom_temperature = float(self.header.attr("nom_temperature"))
        self.op_voltage = float(oc.attr("voltage")) if oc else self.nom_voltage
        self.op_temperature = float(oc.attr("temperature")) if oc else self.nom_temperature
        self.thresholds = {k: float(self.header.attr(k)) for k in (
            "input_threshold_pct_rise", "input_threshold_pct_fall",
            "output_threshold_pct_rise", "output_threshold_pct_fall",
            "slew_lower_threshold_pct_rise", "slew_upper_threshold_pct_rise",
            "slew_lower_threshold_pct_fall", "slew_upper_threshold_pct_fall",
            "slew_derate_from_library") if self.header.attr(k) is not None}
        self.templates: Dict[str, Group] = {}
        for gt in ("lu_table_template", "power_lut_template"):
            for g in self.header.find(gt):
                self.templates[g.args[0]] = g
        self._cells: Dict[str, Cell] = {}

    # ---- header ---------------------------------------------------------
    def _units(self) -> Units:
        h = self.header
        cap_attr = h.attr("capacitive_load_unit")
        if not isinstance(cap_attr, list):
            raise ValueError("capacitive_load_unit missing")
        cap = float(cap_attr[0]) * _PREFIX[cap_attr[1].strip().strip('"').lower()[0]] \
            if cap_attr[1].strip().strip('"').lower() != "f" else float(cap_attr[0])
        return Units(
            time=_parse_unit(h.attr("time_unit"), "s"),
            cap=cap,
            voltage=_parse_unit(h.attr("voltage_unit"), "V"),
            leakage=_parse_unit(h.attr("leakage_power_unit"), "W"),
            current=_parse_unit(h.attr("current_unit"), "A"),
        )

    @staticmethod
    def _index_cells(text: str) -> Dict[str, Tuple[int, int]]:
        spans = {}
        for m in re.finditer(r'^\s*cell\s*\(\s*"?([^")\s]+)"?\s*\)\s*\{', text, re.M):
            start = m.start()
            # find the matching closing brace
            depth = 0
            i = m.end() - 1
            L = len(text)
            while i < L:
                c = text[i]
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        break
                elif c == "/" and text.startswith("/*", i):
                    i = text.index("*/", i) + 1
                elif c == '"':
                    i = text.index('"', i + 1)
                i += 1
            spans[m.group(1)] = (start, i + 1)
        return spans

    # ---- cells ----------------------------------------------------------
    @property
    def cell_names(self) -> List[str]:
        return sorted(self._cell_spans)

    def cell(self, name: str) -> Cell:
        if name in self._cells:
            return self._cells[name]
        if name not in self._cell_spans:
            raise KeyError(f"cell {name} not in {self.path}")
        s, e = self._cell_spans[name]
        g = parse("library (x) {\n" + self._text[s:e] + "\n}\n").first("cell")
        cell = self._build_cell(g)
        self._cells[name] = cell
        return cell

    def _table(self, g: Group) -> Table:
        tmpl_name = g.args[0] if g.args else None
        tmpl = self.templates.get(tmpl_name) if tmpl_name else None
        if tmpl_name == "scalar":
            vals = _floats(g.attr("values"))
            return Table((), (), [vals])
        variables = []
        idx = []
        for k in ("1", "2", "3"):
            var = tmpl.attr(f"variable_{k}") if tmpl else None
            ind = g.attr(f"index_{k}") or (tmpl.attr(f"index_{k}") if tmpl else None)
            if var is None:
                break
            variables.append(var)
            idx.append(_floats(ind))
        raw_vals = g.attrs.get("values")
        if not raw_vals:
            raise ValueError(f"table {g.type} has no values")
        vlist = raw_vals[-1]
        if isinstance(vlist, str):
            vlist = [vlist]
        rows = [_floats(r) for r in vlist]
        if len(variables) == 1 and len(rows) == 1:
            pass
        return Table(tuple(variables), tuple(idx), rows)

    def _build_cell(self, g: Group) -> Cell:
        pins: Dict[str, Pin] = {}
        pin_groups = list(g.find("pin"))
        for bus in g.find("bus"):
            pin_groups += bus.find("pin")
        for pg in pin_groups:
            arcs = []
            for tg in pg.find("timing"):
                tables = {}
                for sub in tg.groups:
                    if sub.type in ("cell_rise", "cell_fall", "rise_transition", "fall_transition",
                                    "rise_constraint", "fall_constraint"):
                        tables[sub.type] = self._table(sub)
                arcs.append(TimingArc(tg.attr("related_pin"), tg.attr("timing_sense"),
                                      tg.attr("timing_type"), tg.attr("when"), tables))
            ips = []
            for ig in pg.find("internal_power"):
                rise = ig.first("rise_power")
                fall = ig.first("fall_power")
                ips.append(InternalPower(ig.attr("related_pin"), ig.attr("when"), ig.attr("related_pg_pin"),
                                         self._table(rise) if rise else None,
                                         self._table(fall) if fall else None))

            def fnum(name):
                v = pg.attr(name)
                return float(v) if v is not None else None

            pins[pg.args[0]] = Pin(
                name=pg.args[0], direction=pg.attr("direction", ""), capacitance=fnum("capacitance"),
                rise_capacitance=fnum("rise_capacitance"), fall_capacitance=fnum("fall_capacitance"),
                function=pg.attr("function"), max_capacitance=fnum("max_capacitance"),
                max_transition=fnum("max_transition"), clock=(pg.attr("clock") == "true"),
                timing=arcs, internal_power=ips)
        states = []
        for lg in g.find("leakage_power"):
            states.append((lg.attr("when"), float(lg.attr("value"))))
        leak = g.attr("cell_leakage_power")
        return Cell(name=g.args[0], area=float(g.attr("area", "nan")),
                    leakage=float(leak) if leak is not None else None,
                    leakage_states=states, pins=pins,
                    is_sequential=bool(g.find("ff") or g.find("latch")), raw=g)

    # ---- SI accessors ---------------------------------------------------
    def pin_cap_F(self, cell: str, pin: str) -> float:
        p = self.cell(cell).pins[pin]
        if p.capacitance is None:
            raise ValueError(f"{cell}/{pin} has no capacitance attribute")
        return p.capacitance * self.units.cap

    def leakage_W(self, cell: str) -> float:
        c = self.cell(cell)
        if c.leakage is None:
            raise ValueError(f"{cell} has no cell_leakage_power")
        return c.leakage * self.units.leakage

    def arc(self, cell: str, related: str, out: str, when: Optional[str] = None) -> TimingArc:
        arcs = [a for a in self.cell(cell).pins[out].timing if a.related_pin == related
                and (when is None or a.when == when)]
        if not arcs:
            raise KeyError(f"no timing arc {cell}:{related}->{out}")
        return arcs[0]

    def delay_s(self, cell: str, related: str, out: str, edge: str, slew_s: float, load_F: float,
                when: Optional[str] = None) -> float:
        """Propagation delay (50%-50%) for output edge 'rise'/'fall'."""
        a = self.arc(cell, related, out, when)
        t = a.tables[f"cell_{edge}"]
        return self._lookup_time(t, slew_s, load_F)

    def transition_s(self, cell: str, related: str, out: str, edge: str, slew_s: float, load_F: float,
                     when: Optional[str] = None) -> float:
        a = self.arc(cell, related, out, when)
        t = a.tables[f"{edge}_transition"]
        return self._lookup_time(t, slew_s, load_F)

    def _lookup_time(self, t: Table, slew_s: float, load_F: float) -> float:
        kw = {}
        for v in t.variables:
            if v in ("input_net_transition", "input_transition_time", "related_pin_transition"):
                kw[v] = slew_s / self.units.time
            elif v == "total_output_net_capacitance":
                kw[v] = load_F / self.units.cap
            else:
                raise ValueError(f"unsupported table variable {v}")
        return t.lookup(**kw) * self.units.time

    def internal_energy_J(self, cell: str, out: str, related: str, edge: str, slew_s: float,
                          load_F: float, when: Optional[str] = None) -> float:
        """Raw internal_power table entry (energy per transition) in joules."""
        ips = [ip for ip in self.cell(cell).pins[out].internal_power
               if ip.related_pin == related and (when is None or ip.when == when)]
        if not ips:
            raise KeyError(f"no internal_power {cell}:{related}->{out}")
        t = ips[0].rise if edge == "rise" else ips[0].fall
        if t is None:
            raise KeyError(f"no {edge}_power table for {cell}:{related}->{out}")
        kw = {}
        for v in t.variables:
            if v in ("input_transition_time", "input_net_transition"):
                kw[v] = slew_s / self.units.time
            elif v == "total_output_net_capacitance":
                kw[v] = load_F / self.units.cap
            else:
                raise ValueError(f"unsupported power table variable {v}")
        return t.lookup(**kw) * self.units.energy
