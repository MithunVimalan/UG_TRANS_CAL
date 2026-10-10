"""Provenance, evidence classification and missing-data handling.

Every number that enters a calculation is a ``Param``; every number a
calculation produces is a ``Result`` that remembers the equation used, the
inputs (with their own provenance), the assumptions and the validity
conditions.  Raw floats or Quantities are rejected as inputs to the
calculation functions (``strict`` mode), so a value cannot enter a result
without a declared source and evidence class.

Evidence classes follow the project specification (section 3.3):

  A  fundamental constant           F  circuit-simulated
  B  experimentally measured        G  post-layout
  C  foundry-supplied               H  estimated (not independently validated)
  D  peer-reviewed theoretical      I  unknown / unavailable
  E  model-derived

plus one class that is not evidence at all:

  S  design specification - a choice made by the designer (target clock,
     operand width, ambient temperature of the use case, ...).  It has no
     uncertainty in the evidential sense; it defines the question.
"""
from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from .units import Quantity, parse_unit, fmt_dims


class Cls(enum.Enum):
    A = "fundamental constant"
    B = "experimentally measured"
    C = "foundry-supplied"
    D = "peer-reviewed theoretical"
    E = "model-derived"
    F = "circuit-simulated"
    G = "post-layout"
    H = "estimated"
    I = "unknown or unavailable"
    S = "design specification"

    def __str__(self):
        return f"{self.name} ({self.value})"


class MissingParameter(LookupError):
    """Raised when a calculation needs a parameter that is unavailable (class I)."""

    def __init__(self, param: "Param", needed_for: str = ""):
        self.param = param
        msg = f"parameter '{param.name}' is unavailable"
        if param.note:
            msg += f" ({param.note})"
        if needed_for:
            msg += f"; required for {needed_for}"
        if param.authority:
            msg += f"; authoritative source: {param.authority}"
        super().__init__(msg)


class ProvenanceError(TypeError):
    pass


@dataclass(frozen=True)
class Param:
    """A sourced input value.

    ``u_rel``  relative standard uncertainty (1 sigma) when known.
    ``bounds`` (low, high) interval when only bounds are known (e.g. corners);
               this is *not* a probability distribution.
    ``valid``  (low, high) applicability range of the value (e.g. a model is
               valid only for 0..1.95 V).
    """
    name: str
    value: Optional[Quantity]
    cls: Cls
    source: Optional[str] = None
    location: str = ""
    conditions: Mapping[str, str] = field(default_factory=dict)
    symbol: str = ""
    unit: str = ""
    u_rel: Optional[float] = None
    bounds: Optional[Tuple[Quantity, Quantity]] = None
    valid: Optional[Tuple[Quantity, Quantity]] = None
    note: str = ""
    authority: str = ""          # who would normally supply it (for class I)
    access: str = ""             # public / registration / licence / NDA

    def __post_init__(self):
        if self.cls is Cls.I:
            if self.value is not None:
                raise ProvenanceError(f"{self.name}: class I parameter must not carry a value")
        else:
            if self.value is None:
                raise ProvenanceError(f"{self.name}: value is None but class is {self.cls.name}")
            if self.cls not in (Cls.A, Cls.S) and not self.source:
                raise ProvenanceError(f"{self.name}: class {self.cls.name} requires a source id")
            if self.unit:
                u = parse_unit(self.unit)
                if u.dims != self.value.dims:
                    raise ProvenanceError(
                        f"{self.name}: value has dimensions {fmt_dims(self.value.dims)}, declared unit {self.unit}")
        if self.u_rel is not None and not (0 <= self.u_rel < 10):
            raise ProvenanceError(f"{self.name}: implausible relative uncertainty {self.u_rel}")

    @property
    def available(self) -> bool:
        return self.cls is not Cls.I

    def require(self, needed_for: str = "") -> Quantity:
        if not self.available:
            raise MissingParameter(self, needed_for)
        return self.value  # type: ignore[return-value]

    def check_valid(self, x: Quantity, what: str = "") -> None:
        if self.valid is None:
            return
        lo, hi = self.valid
        if not (lo <= x <= hi):
            raise ValueError(f"{what or self.name}: {x} outside validity range [{lo}, {hi}]")

    def describe(self) -> str:
        if not self.available:
            return f"{self.name}: UNAVAILABLE - {self.note}"
        unit = self.unit or ""
        v = self.value.to(unit) if unit else self.value.value
        unc = f" +/-{100 * self.u_rel:.3g}%" if self.u_rel is not None else ""
        cond = ", ".join(f"{k}={v}" for k, v in self.conditions.items())
        return (f"{self.name} = {v:.6g} {unit}{unc} [{self.cls.name}; {self.source or '-'}"
                f"{'; ' + self.location if self.location else ''}{'; ' + cond if cond else ''}]")


def spec(name: str, value: Quantity, unit: str = "", note: str = "") -> Param:
    """A design specification (class S)."""
    return Param(name=name, value=value, cls=Cls.S, unit=unit, note=note, source="design-spec")


def unavailable(name: str, unit: str, note: str, authority: str = "", access: str = "") -> Param:
    return Param(name=name, value=None, cls=Cls.I, unit=unit, note=note, authority=authority, access=access)


Input = Union[Param, "Result"]


@dataclass
class Result:
    name: str
    value: Quantity
    cls: Cls
    equation: str
    inputs: List[Input] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    valid_if: List[str] = field(default_factory=list)
    unit: str = ""
    u_rel: Optional[float] = None
    note: str = ""

    # A Result can be used wherever a Param is accepted.
    @property
    def available(self) -> bool:
        return True

    def require(self, needed_for: str = "") -> Quantity:
        return self.value

    @property
    def source(self) -> str:
        return f"derived:{self.name}"

    def leaves(self) -> List[Param]:
        """All Param leaves in the lineage (deduplicated by name)."""
        seen: Dict[str, Param] = {}
        stack: List[Input] = list(self.inputs)
        while stack:
            x = stack.pop()
            if isinstance(x, Result):
                stack.extend(x.inputs)
            elif x.name not in seen:
                seen[x.name] = x
        return list(seen.values())

    def input_classes(self) -> List[str]:
        return sorted({p.cls.name for p in self.leaves()})

    def all_assumptions(self) -> List[str]:
        out: List[str] = []
        stack: List[Input] = [self]
        while stack:
            x = stack.pop()
            if isinstance(x, Result):
                for a in x.assumptions:
                    if a not in out:
                        out.append(a)
                stack.extend(x.inputs)
        return out

    def describe(self, depth: int = 0) -> str:
        unit = self.unit or ""
        v = self.value.to(unit) if unit else self.value.value
        unc = f" +/-{100 * self.u_rel:.2g}%" if self.u_rel is not None else ""
        pad = "  " * depth
        lines = [f"{pad}{self.name} = {v:.6g} {unit}{unc}  [{self.cls.name}: {self.equation}]"]
        for a in self.assumptions:
            lines.append(f"{pad}  assumes: {a}")
        for inp in self.inputs:
            if isinstance(inp, Result):
                lines.append(inp.describe(depth + 1))
            else:
                lines.append(f"{pad}  <- {inp.describe()}")
        return "\n".join(lines)


def val(x: Input, needed_for: str = "", strict: bool = True) -> Quantity:
    """Extract the Quantity of a Param/Result; reject unlabelled numbers."""
    if isinstance(x, (Param, Result)):
        return x.require(needed_for)
    if strict:
        raise ProvenanceError(
            f"unlabelled input {x!r}: wrap it in a Param with an evidence class and source "
            f"(use provenance.spec() for a design choice)")
    if isinstance(x, Quantity):
        return x
    raise ProvenanceError(f"cannot use {x!r} as an input")


def combine_u_rel(*terms: Tuple[Optional[float], float]) -> Optional[float]:
    """First-order relative uncertainty of a product of powers.

    ``terms`` are (u_rel_i, exponent_i); returns sqrt(sum (e_i u_i)^2) assuming
    uncorrelated inputs, or None if any input uncertainty is unknown.
    """
    s = 0.0
    for u, e in terms:
        if u is None:
            return None
        s += (e * u) ** 2
    return math.sqrt(s)


class ParamSet:
    """A named collection of Params with dependency reporting."""

    def __init__(self, params: Iterable[Param] = ()):
        self._p: Dict[str, Param] = {}
        for p in params:
            self.add(p)

    def add(self, p: Param) -> None:
        if p.name in self._p:
            raise KeyError(f"duplicate parameter {p.name}")
        self._p[p.name] = p

    def __getitem__(self, name: str) -> Param:
        return self._p[name]

    def __contains__(self, name: str) -> bool:
        return name in self._p

    def __iter__(self):
        return iter(self._p.values())

    def missing(self) -> List[Param]:
        return [p for p in self._p.values() if not p.available]

    def by_class(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        for p in self._p.values():
            out.setdefault(p.cls.name, []).append(p.name)
        return out
