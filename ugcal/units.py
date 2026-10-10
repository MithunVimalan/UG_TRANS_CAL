"""Dimension-checked physical quantities (SI), dependency-free.

A ``Quantity`` carries a float value in SI base units and a dimension vector
over (m, kg, s, A, K).  Arithmetic checks dimensions: adding a capacitance to
an energy raises ``DimensionError``; ``exp``/``log`` require dimensionless
arguments.  Values are always stored in SI; ``q(1.8, "V")``, ``q(2.3, "fF")``
and ``x.to("pJ")`` handle prefixes.

Temperatures: ``K`` is used for both absolute temperatures and differences.
Celsius is not a unit here because it is affine; use ``celsius(25)`` to get an
absolute temperature and ``.to_celsius()`` to read one back.
"""
from __future__ import annotations

import math
import re
from typing import Dict, Tuple, Union

Dims = Tuple[int, int, int, int, int]  # m, kg, s, A, K
_BASE = ("m", "kg", "s", "A", "K")
_ZERO: Dims = (0, 0, 0, 0, 0)


class DimensionError(TypeError):
    pass


def _add(a: Dims, b: Dims) -> Dims:
    return tuple(x + y for x, y in zip(a, b))  # type: ignore[return-value]


def _sub(a: Dims, b: Dims) -> Dims:
    return tuple(x - y for x, y in zip(a, b))  # type: ignore[return-value]


def _mul(a: Dims, k) -> Dims:
    r = tuple(x * k for x in a)
    for v in r:
        if abs(v - round(v)) > 1e-12:
            raise DimensionError(f"non-integer dimension exponent {r}")
    return tuple(int(round(v)) for v in r)  # type: ignore[return-value]


Number = Union[int, float]


class Quantity:
    __slots__ = ("value", "dims")

    def __init__(self, value: Number, dims: Dims = _ZERO):
        self.value = float(value)
        self.dims = tuple(dims)  # type: ignore[assignment]

    # ---- arithmetic --------------------------------------------------
    def _coerce(self, other) -> "Quantity":
        if isinstance(other, Quantity):
            return other
        if isinstance(other, (int, float)):
            return Quantity(other)
        return NotImplemented  # type: ignore[return-value]

    def __add__(self, other):
        o = self._coerce(other)
        if o is NotImplemented:
            return NotImplemented
        if o.dims != self.dims:
            raise DimensionError(f"cannot add {fmt_dims(self.dims)} and {fmt_dims(o.dims)}")
        return Quantity(self.value + o.value, self.dims)

    __radd__ = __add__

    def __sub__(self, other):
        o = self._coerce(other)
        if o is NotImplemented:
            return NotImplemented
        if o.dims != self.dims:
            raise DimensionError(f"cannot subtract {fmt_dims(o.dims)} from {fmt_dims(self.dims)}")
        return Quantity(self.value - o.value, self.dims)

    def __rsub__(self, other):
        return (-self) + other

    def __neg__(self):
        return Quantity(-self.value, self.dims)

    def __abs__(self):
        return Quantity(abs(self.value), self.dims)

    def __mul__(self, other):
        o = self._coerce(other)
        if o is NotImplemented:
            return NotImplemented
        return Quantity(self.value * o.value, _add(self.dims, o.dims))

    __rmul__ = __mul__

    def __truediv__(self, other):
        o = self._coerce(other)
        if o is NotImplemented:
            return NotImplemented
        return Quantity(self.value / o.value, _sub(self.dims, o.dims))

    def __rtruediv__(self, other):
        o = self._coerce(other)
        return Quantity(o.value / self.value, _sub(o.dims, self.dims))

    def __pow__(self, k: Number):
        return Quantity(self.value ** k, _mul(self.dims, k))

    def sqrt(self) -> "Quantity":
        return self ** 0.5

    # ---- comparison --------------------------------------------------
    def _cmp(self, other) -> Tuple[float, float]:
        o = self._coerce(other)
        if o.dims != self.dims:
            raise DimensionError(f"cannot compare {fmt_dims(self.dims)} with {fmt_dims(o.dims)}")
        return self.value, o.value

    def __lt__(self, o):
        a, b = self._cmp(o)
        return a < b

    def __le__(self, o):
        a, b = self._cmp(o)
        return a <= b

    def __gt__(self, o):
        a, b = self._cmp(o)
        return a > b

    def __ge__(self, o):
        a, b = self._cmp(o)
        return a >= b

    def __eq__(self, o):
        if not isinstance(o, (Quantity, int, float)):
            return NotImplemented
        o = self._coerce(o)
        return self.dims == o.dims and self.value == o.value

    def __hash__(self):
        return hash((self.value, self.dims))

    # ---- conversion --------------------------------------------------
    @property
    def dimensionless(self) -> bool:
        return self.dims == _ZERO

    def __float__(self):
        if not self.dimensionless:
            raise DimensionError(f"cannot convert {fmt_dims(self.dims)} quantity to float; use .to(unit)")
        return self.value

    def to(self, unit: Union[str, "Quantity"]) -> float:
        u = parse_unit(unit) if isinstance(unit, str) else unit
        if u.dims != self.dims:
            raise DimensionError(f"cannot express {fmt_dims(self.dims)} in {unit!r} ({fmt_dims(u.dims)})")
        return self.value / u.value

    def check(self, unit: Union[str, "Quantity"], name: str = "quantity") -> "Quantity":
        u = parse_unit(unit) if isinstance(unit, str) else unit
        if u.dims != self.dims:
            raise DimensionError(f"{name}: expected {unit!r} ({fmt_dims(u.dims)}), got {fmt_dims(self.dims)}")
        return self

    def to_celsius(self) -> float:
        self.check("K", "temperature")
        return self.value - 273.15

    def __repr__(self):
        return f"Quantity({self.value:.6g} {fmt_dims(self.dims)})"

    def __format__(self, spec):
        return format(self.value, spec) + " " + fmt_dims(self.dims)


def fmt_dims(d: Dims) -> str:
    if tuple(d) == _ZERO:
        return "1"
    parts = []
    for name, e in zip(_BASE, d):
        if e == 1:
            parts.append(name)
        elif e != 0:
            parts.append(f"{name}^{e}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# unit table
# ---------------------------------------------------------------------------
_E_CHARGE = 1.602176634e-19  # C, exact (SI 2019)

_UNITS: Dict[str, Quantity] = {
    "1": Quantity(1.0),
    "m": Quantity(1.0, (1, 0, 0, 0, 0)),
    "g": Quantity(1e-3, (0, 1, 0, 0, 0)),
    "s": Quantity(1.0, (0, 0, 1, 0, 0)),
    "A": Quantity(1.0, (0, 0, 0, 1, 0)),
    "K": Quantity(1.0, (0, 0, 0, 0, 1)),
}
_UNITS["Hz"] = Quantity(1.0, (0, 0, -1, 0, 0))
_UNITS["N"] = Quantity(1.0, (1, 1, -2, 0, 0))
_UNITS["J"] = Quantity(1.0, (2, 1, -2, 0, 0))
_UNITS["W"] = Quantity(1.0, (2, 1, -3, 0, 0))
_UNITS["C"] = Quantity(1.0, (0, 0, 1, 1, 0))
_UNITS["V"] = Quantity(1.0, (2, 1, -3, -1, 0))
_UNITS["F"] = Quantity(1.0, (-2, -1, 4, 2, 0))
_UNITS["Ohm"] = Quantity(1.0, (2, 1, -3, -2, 0))
_UNITS["ohm"] = _UNITS["Ohm"]
_UNITS["S"] = Quantity(1.0, (-2, -1, 3, 2, 0))
_UNITS["eV"] = Quantity(_E_CHARGE, (2, 1, -2, 0, 0))
_UNITS["Pa"] = Quantity(1.0, (-1, 1, -2, 0, 0))
_UNITS["dec"] = Quantity(1.0)          # decade (dimensionless marker)
_UNITS["bit"] = Quantity(1.0)          # information unit (dimensionless marker)
_UNITS["op"] = Quantity(1.0)           # operation count (dimensionless marker)

_PREFIXES = {"y": 1e-24, "z": 1e-21, "a": 1e-18, "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6,
             "µ": 1e-6, "m": 1e-3, "c": 1e-2, "k": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}


def _lookup(sym: str) -> Quantity:
    if sym in _UNITS:
        return _UNITS[sym]
    if len(sym) > 1 and sym[0] in _PREFIXES and sym[1:] in _UNITS and sym[1:] != "1":
        u = _UNITS[sym[1:]]
        return Quantity(u.value * _PREFIXES[sym[0]], u.dims)
    raise ValueError(f"unknown unit symbol {sym!r}")


_TOKEN = re.compile(r"\s*([*/])?\s*([A-Za-zµ]+|1)(?:\^(-?\d+(?:\.\d+)?))?")


def parse_unit(s: str) -> Quantity:
    """Parse e.g. 'fF', 'W/m/K', 'K/W', 'um^2', 'J/bit', 'mV/dec'."""
    s = s.strip()
    if s in ("", "1"):
        return Quantity(1.0)
    pos = 0
    result = Quantity(1.0)
    first = True
    while pos < len(s):
        m = _TOKEN.match(s, pos)
        if not m or m.end() == pos:
            raise ValueError(f"cannot parse unit {s!r} at {s[pos:]!r}")
        op, sym, exp = m.groups()
        if op is None and not first:
            op = "*"
        u = _lookup(sym)
        e = float(exp) if exp else 1.0
        u = Quantity(u.value ** e, _mul(u.dims, e))
        result = result / u if op == "/" else result * u
        pos = m.end()
        first = False
    return result


def q(value: Number, unit: str = "1") -> Quantity:
    """Create a quantity: q(2.3, 'fF')."""
    u = parse_unit(unit)
    return Quantity(float(value) * u.value, u.dims)


def celsius(t: Number) -> Quantity:
    return Quantity(float(t) + 273.15, (0, 0, 0, 0, 1))


def exp(x: Quantity) -> float:
    return math.exp(float(_dimless(x, "exp")))


def log(x: Quantity) -> float:
    return math.log(float(_dimless(x, "log")))


def _dimless(x, what):
    if isinstance(x, Quantity):
        if not x.dimensionless:
            raise DimensionError(f"{what}() of a dimensional quantity ({fmt_dims(x.dims)})")
        return x.value
    return float(x)
