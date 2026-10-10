# D2 — Physical hierarchy: from physics to an AI accelerator

Each level of the stack inherits constraints from the level below and adds its own. The table names, for every level, the governing physics or engineering, the quantities that cross into the next level, where this project obtains them, and the evidence class of what is known for SKY130.

```
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │ L7  AI accelerator  GEMM/conv mapping, dataflow, SRAM/register files, NoC, I/O│  energy/inference, TOPS/W
 │        ▲ MACs/s, bytes moved per MAC, utilisation                            │
 │ L6  MAC array       systolic/SIMD tiling, operand reuse, clock tree, PDN     │  pJ/MAC incl. movement
 │        ▲ E_MAC, f_max, area per MAC, power density                           │
 │ L5  MAC unit        multiplier + accumulator + registers + clock + control   │  pJ/MAC, MAC/s
 │        ▲ E_mult, t_mult, area                                                │
 │ L4  Multiplier      PP generation, reduction tree, final adder               │  pJ/mult, ns
 │        ▲ per-arc delay, energy tables, pin C, leakage per state              │
 │ L3  Logic cells     static CMOS gates (inv, nand, xor, fa, dff) + layout     │  Liberty NLDM
 │        ▲ I(V), C(V), leakage, mismatch, temperature                          │
 │ L2  Transistors     BSIM4 compact model of nfet_01v8 / pfet_01v8_hvt         │  model cards
 │        ▲ mobility, v_sat, oxide, junctions, stress, doping                   │
 │ L1  Materials       Si, SiO2, silicide, Al/Cu interconnect, dielectrics      │  ρ, κ, ε, μ
 │        ▲ kT, q, h, Boltzmann/Fermi statistics                                │
 │ L0  Fundamental     thermodynamics, statistical mechanics, quantum mechanics │  kT ln2, kT/q ln10
 └──────────────────────────────────────────────────────────────────────────────┘
          heat flows up and out through die → package → board/heat sink (D9)
```

| Level | Governing physics / engineering | Quantities passed upward | Where they come from here | SKY130 evidence status |
|---|---|---|---|---|
| L0 Fundamental | 2nd law, Landauer, Boltzmann statistics, equipartition, energy–time bounds | $k_BT$, $k_BT/q$, SS ≥ 59.5 mV/dec, erasure cost | `ugcal.fundamental`, `ugcal.infotheory` (D3) | A (constants), D (bounds), exact information content (E) |
| L1 Materials | band structure, phonon transport, dielectrics | ε_ox (3.9 in cards), κ_Si, sheet resistances | model cards; SkyWater RCX docs; bulk literature | C (cards, docs); B (bulk κ_Si from literature). Thin-film and interface values are not separated in public data (I) |
| L2 Transistors | MOS electrostatics, drift–diffusion with velocity saturation, subthreshold conduction, junction leakage, STI stress (LOD) | $I_D(V_{GS},V_{DS},T)$, $C_{gg}$, $C_j$, mismatch $A_{VT}$ | BSIM4 cards (`sky130_fd_pr`), ngspice (`sim/spice/device_char.py`) | C (cards), F (extracted Vth, SS, Ion, Ioff, Cgg). Gate leakage, self-heating and ageing are not modelled (I) |
| L3 Cells | static CMOS topology, layout parasitics, short-circuit current | NLDM delay, slew, internal energy, pin C, state leakage | Liberty corners; cell netlists; Magic-extracted cells; SPICE calibration (D6 §6) | C (Liberty); F (SPICE reproduction within −1.6…+5.6 % energy) |
| L4 Multiplier | algorithm (Booth/BW/AND), reduction (array/Wallace/Dadda), CPA (ripple/prefix); glitch generation | E/multiplication, critical path, area | `ugcal.arith` generators; `ugcal.gatesim`; OpenSTA; Yosys/ABC; full-chip SPICE | E/F (gate-level from Liberty, cross-checked with OpenSTA to 0.2–4 %); F (transistor-level SPICE) |
| L5 MAC | accumulator width, register and clock energy, pipelining | E/MAC, f_max, latency, II, area | `ugcal.arith.mac`, `sim/gatelevel/mac_study.py` (D8) | E/F pre-layout; no post-layout (G) or silicon (B) data |
| L6 Array | data reuse, operand broadcast/forwarding, clock tree, power grid | E/MAC incl. movement, power density | `ugcal.mac`, D8 §5 (model with explicit unknowns) | E with class-I inputs (SRAM and wire energies need a memory compiler and layout) |
| L7 Accelerator | algorithm → GEMM/conv mapping (im2col, implicit GEMM, Winograd), memory hierarchy, utilisation | energy per inference | literature (Eyeriss, TPU), not modelled numerically | D/B from literature, other technologies only |
| Heat path | conduction (Fourier), spreading, package and convection | T_j, max sustainable power | `ugcal.thermal` (D9) | E; package R_th is design-specific (I until the package is chosen) |

## Why the same mathematics costs different energy

$Y = A\cdot B + C$ fixes the *information* that must be processed (D3 §1.5). It fixes neither the circuit nor the data movement. The same dot product can be computed:

* by **different arithmetic transformations**: direct convolution, im2col + GEMM, implicit GEMM, or Winograd minimal filtering. The last reduces multiplications by up to 4× for 3×3 filters at the cost of more additions and transforms (Lavin & Gray 2016). The number of MACs per inference changes; the mathematical result does not, or does only within rounding for transforms in finite precision;
* by **different multiplier circuits**: measured here in SKY130, energy per 8×8 multiplication spans 1.58 to 4.81 pJ across architectures and delay 3.4 to 8.9 ns, for identical arithmetic (D7);
* with **different data statistics**: the same circuit spends 3–7× less energy on sparse or small-magnitude unsigned operands than on uniform random ones. For two's-complement small values the saving nearly disappears, because sign extension toggles the upper bits (D7);
* with **different storage and movement**: the operands of every MAC must reach the multiplier. Register-file, SRAM and DRAM accesses cost far more than the arithmetic in published accelerators (Horowitz 2014 via secondary sources; Eyeriss, Chen et al. 2017). In SKY130 the in-MAC operand and accumulator registers, with their clock pins, already account for 23–64 % of MAC energy across the seven variants, and about half or more for the two lowest-energy ones (D8).

The performance envelope (D9/D12) is therefore built bottom-up as a chain of conditional bounds, one per level. Each level states the assumptions it imports from the level below.
