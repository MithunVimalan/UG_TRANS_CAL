"""Uncertainty propagation (Monte Carlo) and corner/interval evaluation.

Two different things are kept apart:

  * statistical uncertainty: inputs with a documented distribution (e.g. the
    Gaussian mismatch terms in the SKY130 model cards, or a measurement with a
    standard uncertainty) are sampled and propagated by Monte Carlo;
  * bounded (epistemic) uncertainty: inputs known only to lie between corners
    or between two sources (e.g. inertial vs transport glitch models) are
    propagated as intervals by evaluating the model at the bounds.  No
    distribution is invented for them; the result is an interval, not a
    confidence interval.
"""
from __future__ import annotations

import itertools
import math
import random
import statistics
from dataclasses import dataclass
from typing import Callable, Dict, List, Sequence, Tuple


@dataclass
class Normal:
    mean: float
    sd: float

    def sample(self, rng: random.Random) -> float:
        return rng.gauss(self.mean, self.sd)


@dataclass
class LogNormal:
    median: float
    sigma_ln: float

    def sample(self, rng: random.Random) -> float:
        return self.median * math.exp(rng.gauss(0.0, self.sigma_ln))


def monte_carlo(f: Callable[..., float], dists: Dict[str, object], n: int = 20000, seed: int = 1,
                fixed: Dict[str, float] = None) -> Dict[str, float]:
    rng = random.Random(seed)
    fixed = fixed or {}
    out = []
    for _ in range(n):
        kw = {k: d.sample(rng) for k, d in dists.items()}
        kw.update(fixed)
        out.append(f(**kw))
    out.sort()
    return dict(mean=statistics.fmean(out), sd=statistics.pstdev(out), p05=out[int(0.05 * n)],
                p50=out[int(0.5 * n)], p95=out[int(0.95 * n)], n=n)


def interval(f: Callable[..., float], bounds: Dict[str, Tuple[float, float]],
             fixed: Dict[str, float] = None) -> Tuple[float, float]:
    """Evaluate f at every combination of bound values (exact for monotonic f)."""
    fixed = fixed or {}
    keys = list(bounds)
    vals = []
    for combo in itertools.product(*[bounds[k] for k in keys]):
        kw = dict(zip(keys, combo))
        kw.update(fixed)
        vals.append(f(**kw))
    return min(vals), max(vals)
