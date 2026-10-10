# D1 — Executive summary

## 1. Objective

The question is how close a given multiplier or MAC, in a given process, at a given voltage and temperature, in a given thermal environment, comes to the physically and technologically achievable limits of energy per operation, throughput and power density. The aim is to establish the strongest defensible reference limits before circuit development, then to say how the gap to them should be measured once a circuit exists.

The project was carried out on SkyWater SKY130. It is the only manufacturable process whose full chain (compact models → cell library → layouts → extraction rules) could be read and simulated without an NDA. All PDK files were read at pinned commits. All simulations use open tools (ngspice 42, Magic, Yosys, OpenSTA) and this repository's Python framework, `ugcal`, which enforces units, evidence classes and the refusal to substitute missing data.

## 2. The answer in brief

There is no single "maximum TOPS per watt" that physics fixes for a CMOS MAC. What can be defended is a **chain of conditional bounds**, each valid under stated assumptions, and each far above the one beneath it.

| Level | Per int8 MAC (SKY130 HD, 25 °C, 1.8 V unless stated) | Kind | Class |
|---|---|---|---|
| Thermodynamic floor (16 operand bits erased, 300 K) | 4.6 × 10⁻²⁰ J | hard law, for irreversible erasure only | A/D |
| Information-theoretic floor for an 8×8 signed product kept, operands kept | 3.1 bits → 9.0 × 10⁻²¹ J | hard law | D |
| Reliability scale per node transition (kT/C, error probability 10⁻¹⁵) | 5.2 × 10⁻¹⁹ J | model; a scale, not a proof | E |
| One SKY130 FO4 inverter transition | 18.6 fJ (1.8 V); 3.0 fJ (0.8 V, 45× slower) | technology | F |
| Best pre-layout MAC built here (gate level, glitch-aware, no wires) | 4.97 pJ at ≤ 104 MHz; 5.60 pJ at ≤ 307 MHz (tt) / 145 MHz (ss, 100 °C) | circuit, conditional | E |
| Post-route MAC array in the same process (third party, zero-delay activity) | 15.9 pJ | implementation, one data point | G |
| Thermally limited throughput (carry-save PEs, array sized to the budget) | P_max = (100 °C − T_a)/θ_JA = 0.5–7.5 W, i.e. 0.18–2.7 TOPS for θ_JA = 10–60 K/W and T_a = 25–70 °C | package-dependent | E/S |

The circuit sits about **10⁸ above the thermodynamic floor**. The floor is real but irrelevant to design at this node: no known theory gives a tight, technology-independent lower bound for irreversible CMOS logic at a specified speed and error rate (D13 §4). The levels that actually constrain a design are technology (charge per transition at the supply), circuit (glitches, registers, adders) and implementation (wires, clock tree, timing repair). In SKY130 throughput is limited by the package and cooling before power density or transistors become binding.

## 3. Principal findings

**Fundamental (D3).** k_BT ln2 applies to erased information, not to transistor switching. An inverter is logically reversible; its ½CV² dissipation is a property of charging a capacitor from a rail. Exact information content: an 8×8 product loses 2.3 bits (unsigned) or 3.1 bits (signed); an int8 MAC that discards its operands erases 16 bits. SKY130's subthreshold swing (85–90 mV/dec at 25 °C) is 1.4–1.5× the thermionic limit. Its library is characterised only from 1.28 V. Neither the 36 mV ideal nor the 207 mV practical minimum supply is close to binding.

**Transistor and cell level (D4, D6).**
* The foundry's schematic cell netlists are not adequate for energy or delay: −39 % energy and −67 % fall delay against the library at the worst points. Layout extraction with stress (LOD) parameters reproduces the Liberty energy within −1.6 … +5.6 %.
* At 100 °C the Liberty leakage is 16× (tt) to ≈560× (ss) above SPICE with the same-named model corner. It matches a separate, unreferenced "leak" model set. Leakage at high temperature is uncertain by one to three decades. For the active arrays studied it is ≤ 1.3 % of power, so the conclusions do not depend on it.

**Multipliers (D7; 8×8, tt 25 °C 1.8 V, pre-layout).**
* Energy spans 1.58–4.81 pJ and delay 3.47–8.86 ns across architectures for identical arithmetic.
* **Glitches are the dominant architecture-dependent term.** Functional energy is nearly identical for all AND-array designs (1.21–1.24 pJ with ripple adders). Inertial glitches add 31–102 % to the AND-array designs and 111 % to Booth + Dadda + KS.
* Transistor-level SPICE of whole multipliers lands inside the gate-level [inertial, transport] bracket, at 1.19–1.30× the inertial estimate.
* Dadda + ripple has the lowest energy; Kogge–Stone final adders are fastest and costliest.
* Radix-4 Booth does *not* save energy in this library (signed 8×8: 4.43 vs 3.12 pJ for Baugh–Wooley).
* Hand-structured netlists beat Yosys/ABC by 13–37 % in energy.
* Operand statistics move energy as much as architecture: 4.7–6.5× less for small unsigned operands. Two's complement nearly erases that saving for small signed values.

**MAC (D8).**
* The lowest-energy MACs spend about half or more of their energy in registers and their clock pins (49 % and 64 %). A multiplier-only figure understates a MAC by 2.8–3.3×.
* A carry-save accumulator gives the best energy–delay point: 5.6 pJ at 2.95× the clock of the ripple variant, for +13 % energy.
* Against a same-process post-route array (zero-delay activity), our pre-layout PEs are lower by a factor of **2.6–3.9**. That factor is the measured price of wires, clock tree, pipeline registers, control and timing repair.

**Heat (D9).**
* With T_j ≤ 100 °C (the characterisation limit, not a reliability limit), sustainable throughput is set by θ_JA.
* The power density of a fully used SKY130 array (6–12 W/cm²) is far below air-cooling capability.
* Electro-thermal loop gain is 0.02–0.10, so runaway is impossible below 100 °C for these arrays.

## 4. What can and cannot be established before circuit design

| Can be established from public data and simulation (this report) | Cannot be established without implementation, foundry data or silicon |
|---|---|
| exact thermodynamic and information floors | reliability-based temperature and lifetime limits (EM, BTI/HCI/TDDB data not public) |
| device and cell characteristics at every foundry corner (SPICE ≈ Liberty) | absolute post-layout energy and f_max (wires, clock tree; factor ≈3 in one external data point) |
| relative ranking of architectures, with a glitch bracket arbitrated by SPICE | which leakage data set represents silicon at high temperature |
| energy accounting of a MAC by functional group, without double counting | clock-tree energy and skew (class I) |
| conditional thermal envelope as a function of package θ | the package's actual θ (design choice and datasheet) |
| supply-voltage trends below the characterised range (FO4 level) | variation-aware low-voltage behaviour of full designs (Monte Carlo not run on multipliers) |
| a benchmarking procedure and record format (D11) | any measured number (no silicon) |

## 5. Evidence position

Nothing in this report is experimentally established for SKY130. The strongest evidence is foundry-supplied data (C) and SPICE on foundry models (F). The quantitative architecture results are model-derived at gate level (E), cross-checked against OpenSTA (0.2–4 %) and against transistor-level SPICE. The array and thermal envelopes rest on design specifications (S) and on class-H inputs (SRAM energy) that are flagged. One external post-layout reference (G) calibrates the implementation overhead. D12 classifies every conclusion. D13 lists every missing parameter with its authority and access route.

The network policy of the container blocked publisher sites, arXiv and most documentation hosts. Bibliographic facts were confirmed through a search service, and no paper's full text was opened (D15).

## 6. Recommended next steps (D14)

1. Place and route the 8×8 candidates and the two MAC variants; extract parasitics; repeat OpenSTA power with glitch-aware activity; re-arbitrate with SPICE of the extracted netlist.
2. Characterise the 22 cells below 1.28 V and with Monte Carlo mismatch, and locate the minimum-energy supply of a real MAC.
3. Choose a package and obtain θ; close the electro-thermal loop at the slow corner.
4. Tape out a test structure with separate supplies per block and on-chip operand generators, and compare silicon with post-layout predictions by the E_n criterion.

## 7. Reading guide

[Research map](00_research_map.md) · [D2 hierarchy](D02_physical_hierarchy.md) · [D3 limits](D03_fundamental_limits.md) · [D4 parameters](D04_transistor_parameters.md) · [D5 PDKs](D05_foundry_pdk_catalogue.md) · [D6 derivations](D06_derivations.md) · [D7 multipliers](D07_multiplier_comparison.md) · [D8 MAC](D08_mac_model.md) · [D9 thermal](D09_thermal_model.md) · [D10 framework](D10_calculation_framework.md) · [D11 benchmarking](D11_benchmarking_procedure.md) · [D12 evidence audit](D12_evidence_audit.md) · [D13 gaps](D13_research_gaps.md) · [D14 roadmap](D14_roadmap.md) · [D15 bibliography](D15_bibliography.md)
