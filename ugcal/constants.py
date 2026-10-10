"""Physical constants with provenance.

k_B, e, h, c and N_A are exact by definition since the SI revision of
20 May 2019 (class A).  The vacuum permittivity is no longer exact; its
CODATA 2022 value and relative standard uncertainty are used.
"""
import math

from .provenance import Cls, Param
from .units import Quantity, q

k_B = Param("k_B", q(1.380649e-23, "J/K"), Cls.A, source="si2019", unit="J/K", symbol="k_B",
            note="Boltzmann constant, exact (SI 2019)")
q_e = Param("q", q(1.602176634e-19, "C"), Cls.A, source="si2019", unit="C", symbol="q",
            note="elementary charge, exact (SI 2019)")
h = Param("h", q(6.62607015e-34, "J s"), Cls.A, source="si2019", unit="J s", symbol="h",
          note="Planck constant, exact (SI 2019)")
hbar = Param("hbar", q(6.62607015e-34 / (2 * math.pi), "J s"), Cls.A, source="si2019", unit="J s",
             symbol="hbar", note="h / 2 pi")
eps0 = Param("eps0", q(8.8541878188e-12, "F/m"), Cls.A, source="codata2022", unit="F/m", symbol="epsilon_0",
             u_rel=1.6e-10, note="CODATA 2022; measured, not exact")
LN2 = math.log(2.0)
LN10 = math.log(10.0)

ALL = (k_B, q_e, h, hbar, eps0)
