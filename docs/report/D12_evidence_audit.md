# D12 — Evidence and uncertainty audit

## 1. Classes used throughout

Every number in the framework and the report carries one of these classes (`ugcal.provenance.Cls`). The brief's six categories map onto them as shown.

| Class | Meaning | Brief's category | Examples here |
|---|---|---|---|
| A | fundamental constant (exact by SI definition, or CODATA) | theoretically derived (inputs) | k_B, q, h, ε₀ |
| B | experimentally measured, published | experimentally established | Si thermal conductivity; Bérut et al. 2012 erasure measurement |
| C | foundry-supplied (PDK files, foundry documentation) | foundry-supplied | BSIM4 cards, Liberty tables, LEF capacitances |
| D | peer-reviewed theoretical result | theoretically derived | Landauer, Margolus–Levitin, Meindl minimum supply |
| E | model-derived (our equation applied to sourced inputs; includes gate-level simulation on Liberty data) | theoretically derived / estimated | gate-level energies (D7, D8), array and thermal envelopes |
| F | circuit-simulated (SPICE on foundry models) | simulation-derived | device parameters (D4), inv_1 calibration, whole-multiplier SPICE |
| G | post-layout (extracted parasitics of a placed-and-routed design) | simulation-derived | none of this project's own; one external SKY130 array used as a reference (D8 §5.1) |
| H | estimated (engineering judgement or analytical tool without characterisation) | estimated | OpenRAM SRAM energy, 0.2 fF/µm wire bracket, 70 % utilisation |
| I | unknown or unavailable | unresolved | clock-tree energy, EM limits, reliability models, T_j,max qualification |
| S | design specification (a choice, not a fact) | — | θ_JA sweep, f_clk, T_amb, power budget |

A result's class is the weakest class among the inputs it depends on, unless the result is a bound whose validity does not depend on that input. `Result.input_classes()` lists the classes mechanically. For example, the worked example's T_j rests on {C, E, S} (D10 §3).

## 2. Every major conclusion, classified

**Experimentally established (B):** none of this project's conclusions. No silicon was measured, and the published measurements cited (Bérut et al. 2012; Jun et al. 2014) support the Landauer bound itself, not any SKY130 number.

**Foundry-supplied (C), used as given:**

| Conclusion | Source | Inspected? | Caveat |
|---|---|---|---|
| SKY130 HD cell library characterised 1.28–1.95 V and −40…100 °C | Liberty file names and headers | yes (pinned commit) | characterisation conditions undocumented |
| BSIM4 v4.5 binned cards; gate tunnelling off (`igcmod = igbmod = 0`); mismatch A_VT 3.356 mV·µm (nfet), 5.5 mV·µm (pfet_hvt) | `sky130_fd_pr` model files | yes | no documentation of extraction data |
| HD cells use nfet_01v8 + pfet_01v8_hvt only | cell netlists | yes | — |
| met2 area + fringe capacitance 0.078 fF/µm (isolated, to substrate) | tech LEF | yes | lower bound only (no coupling) |
| Cell areas, pin capacitances, leakage, NLDM delays and energies | Liberty | yes | used as class C inputs to class E models |

**Theoretically derived (A/D inputs, exact or proven under stated assumptions):**

| Conclusion | Value | Assumptions | Applies to SKY130 MAC? |
|---|---|---|---|
| Landauer, 16 bits erased per int8 MAC, 300 K | 4.6 × 10⁻²⁰ J | quasi-static, bath at T, operands discarded | as an absolute floor only |
| Output-only entropy loss of 8×8 multiplication | 2.295 bits (unsigned), 3.144 bits (signed) | uniform independent operands; exact enumeration | as an absolute floor only |
| Thermionic SS limit | 59.5 mV/dec at 300 K | Boltzmann injection, ideal electrostatics | yes; SKY130 is 85–90 mV/dec at 25 °C (F) |
| Minimum CMOS supply | 36 mV (2 ln2 kT/q) to 207 mV (8 kT/q) | ideal or 1972-technology subthreshold inverter | no: the library stops at 1.28 V |
| Margolus–Levitin time at 1 fJ | 1.7 × 10⁻¹⁹ s | isolated quantum system, orthogonal states | no (≈10⁸ below FO4) |
| Exact accumulator width | 22 bits for 64 signed int8 products | exact integer arithmetic | yes (brute-force verified) |

**Simulation-derived (F, SPICE on foundry models):**

| Conclusion | Value | Uncertainty and validity |
|---|---|---|
| Extracted + LOD inv_1 reproduces Liberty energy | −1.6 … +5.6 % over 16 points | one cell, tt/25 °C; three other corners checked with the schematic view only |
| Schematic netlists are inadequate | energy −39 %, fall delay −67 % (worst points) | same |
| Device table (V_th, SS, DIBL, I_on, I_off) | D4 §2 | V_th is method-dependent (constant current). It agrees with the foundry documentation within 3–5 mV at two documented geometries and 20–50 mV at others; the documentation does not state the bias conditions |
| Liberty 100 °C leakage ≫ same-corner SPICE | 16× (tt), ≈560× (ss), ≈4× (ff) | the reason (a `leak` model set) is an **inference**; characterisation undocumented |
| FO4 delay and energy vs V_DD | D4 §4 | below 1.28 V no foundry characterisation to compare with; cards nominally valid |
| Whole-multiplier SPICE vs gate-level | six 8×8 designs: SPICE 1.19–1.37× inertial, always inside [inertial, transport]; identical energy ranking | 30–40 transitions, one corner (tt, 25 °C, 1.8 V); no inter-cell wires |

**Model-derived (E): gate-level on Liberty, analytical envelopes.** These are the bulk of the quantitative conclusions. Each is conditional on Liberty data being right, on no wires, on drive-1 cells and on the stated stimulus.

| Conclusion | Value | Robustness |
|---|---|---|
| Dadda + ripple is the lowest-energy 8×8 unsigned multiplier; Kogge–Stone final adder is fastest | 1.58 pJ / 5.90 ns; 2.72 pJ / 3.47 ns | Dadda + ripple and Wallace + ripple are the two lowest at every operand distribution, within 2.5 % of each other. Wallace is lower for small and Gaussian operands. Not checked post-layout |
| Glitches dominate the architecture-dependent energy | inertial/zero 1.31–2.11 (8×8 unsigned), up to 3.4 at 16×16 | bracketed; SPICE inside the bracket |
| Booth radix-4 costs more energy than Baugh–Wooley/AND arrays in this library | signed 8×8 4.43 vs 3.12 pJ | library-specific (heavy XOR cells); not a general claim |
| Hand-structured netlists beat Yosys/ABC | 13–37 % energy, up to 1.7× delay | one Yosys version and script; a timing-driven commercial flow may differ |
| Registers and their clock pins are 23–64 % of MAC energy (49 % and 64 % in the two lowest-energy variants) | D8 | the dfxtp_1 clock energy is from Liberty; no clock tree included |
| Carry-save accumulation gives the best energy–delay trade-off | 5.6 pJ/MAC at 307/145 MHz (tt / ss 100 °C) | f_max without wires or clock skew is optimistic |
| SRAM traffic 2.8–3.0× energy without reuse, ≈6 % at reuse 64 | D8 §5 | rests on OpenRAM energy (H) → the result is effectively H |
| Thermal throughput is package-limited, not transistor-limited | 0.18–2.7 TOPS for θ_JA 10–60 K/W | θ is a specification (S); T_j,max = 100 °C is a characterisation limit, not a reliability limit |
| Electro-thermal loop gain small, no runaway below 100 °C | 0.02–0.10 | with Liberty leakage as upper bound |
| Minimum-energy supply of a MAC | D4 §4 | three approximations: glitch fraction, logic depth in FO4 and leakage mix are taken as independent of V |

**External post-layout reference (G, third party):** a post-route SKY130 int8 MAC array at 15.9 pJ/MAC (zero-delay activity), 2.6–3.9× this project's pre-layout zero-delay MACs (D8 §5.1). It is used only as an empirical implementation factor. It is not peer-reviewed, and its netlist was not re-analysed.

**Estimated (H):** SRAM energy per word (19.2 pJ, OpenRAM Liberty, identical for read/write/idle), coupling-inclusive wire capacitance upper bracket (0.2 fF/µm), placement utilisation (70 %), and the ≈20 % OpenRCX extraction error quoted from the input research file.

**Unresolved (I):** clock-tree energy and skew; wire parasitics of any real layout; gate-tunnelling leakage; electromigration current limits; BTI/HCI/TDDB ageing; qualified maximum junction temperature; device self-heating; package θ values; silicon behaviour of any circuit here. D13 lists each with its authority and access.

## 3. Quality-control questions applied to the key numbers

The ten questions of the brief (§21), answered for the numbers that carry the conclusions. Y = yes, P = partly, N = no.

| Number | 1 Source | 2 Authoritative | 3 Inspected | 4 Units | 5 Conditions | 6 Equation applies | 7 Assumptions explicit | 8 Kind | 9 Uncertainty | 10 Over-claimed? |
|---|---|---|---|---|---|---|---|---|---|---|
| k_BT ln2 = 2.87 × 10⁻²¹ J (300 K) | SI 2019 constants | Y | Y (values; standard text via secondary) | Y (checked) | Y | Y for erasure | Y | theory | exact | no; D3 states it is not a per-switch bound |
| 2.295 / 3.144 bits per 8×8 product | exact enumeration | Y (mathematics) | Y (code) | Y (bits) | uniform operands | Y | Y | theory | exact | no |
| SS 85–90 mV/dec | SPICE on foundry cards | Y | Y | Y | Y (W/L, bias, T) | Y | Y | simulation | method-dependent, not quantified | no |
| inv_1 energy within −1.6 … +5.6 % of Liberty | SPICE vs Liberty | Y | Y | Y | Y | Y | Y | simulation | range shown | no |
| E_MAC = 5.60 pJ (csa) | gate-level on Liberty | Y (foundry data) | Y | Y | Y (tt, 25 °C, 1.8 V, uniform, inertial) | P (NLDM, no wires) | Y | model | SPICE of six multipliers is 19–37 % above the inertial gate level (a systematic under-estimate); ±20 % used as an illustrative 1σ | no, stated pre-layout |
| f_max 307 / 145 MHz | gate-level STA | Y | Y | Y | Y | P (no wires, no skew) | Y | model | not quantified; optimistic | stated as an upper estimate |
| Liberty-vs-SPICE leakage gap at 100 °C | both foundry data sets | Y | Y | Y | P (Liberty conditions undocumented) | Y | Y | simulation | 1–3 decades | cause stated as inference |
| 0.18–2.7 TOPS thermal envelope | E_MAC × swept θ | P (θ not a fact) | — | Y | Y | Y (steady state) | Y | model | swept, not a distribution | no; conditional on θ |
| SRAM share 63–66 % at N = 1 | OpenRAM Liberty | N (analytical generator) | Y | Y | P | Y | Y | estimate | not quantified | flagged class H |
| Published accelerator figures (TPU, Eyeriss) | search summaries | Y (papers) | **N** | — | P | — | — | measured (by others) | — | not used numerically |

## 4. Distinctions the brief requires, and how they are kept

| Distinction | Where kept |
|---|---|
| Energy vs power | `Quantity` dimensions; `dynamic_power` returns W, `energy_*` returns J. A dimension error was caught in development (D10 §1) |
| Temperature vs temperature rise | `junction_temperature` returns T (K). Rises are reported as ΔT (D9 §4, §7: 0.06 mK, 0.04 K, 0.4 K) |
| Transistor switching energy vs energy per logic operation | D6 §1 (½CV² per transition) vs D7/D8 (per multiplication or MAC, including glitches, registers and leakage). The FO4 energy per transition (D4) is never quoted as an operation energy |
| Single-operation latency vs sustained throughput | D8 §1: latency 2 cycles, II = 1; throughput = f_clk/II per PE |
| f_max vs sustainable throughput | D9 §8: throughput = min(N_PE·f_max, (P_max − P_leak)/E_MAC) |
| Thermodynamic bound vs technology limit | D3 §5 column "Kind"; D2 hierarchy levels |
| Transistor-level estimate vs post-layout result | evidence ladder (D11 §2): nothing here is post-layout |
| Post-layout vs silicon | same; no silicon |

## 5. Where sources disagree, and what was done

| Disagreement | Investigation | Outcome |
|---|---|---|
| Liberty `ss_100C` leakage > `tt_100C` leakage (noted in the input research file) | simulated every cell state with every model set (D4 §5) | Liberty at 100 °C tracks the separate `leak` model set, not the same-named corner. Both are kept as an interval |
| Schematic cell netlists vs Liberty | three netlist views simulated (D4 §3) | extraction + LOD reproduces Liberty; schematic view rejected for energy and delay |
| Foundry device documentation vs model cards | V_th at documented geometries (D4 §2) | within 3–5 mV at two geometries, 20–50 mV elsewhere; documentation lacks bias and temperature, so unresolved |
| Liberty `internal_power` sign convention | SPICE per edge (D6 §6.2) | rise ≈ +½CV² + internal, fall ≈ −½CV² + internal (OpenSTA convention) reproduced within 1.7 %. The standard's text remains uninspected |
| Our gate-level power vs OpenSTA | same VCD, same Liberty | 0.2–4 % (D10 §5) |
| "Booth saves energy" (common rule of thumb) vs this project | measured across widths and distributions | contradicted for SKY130 HD at 8 and 16 bits; stated as library-specific |
| "Data movement dominates accelerator energy" (Horowitz 45 nm via secondary; Eyeriss design rationale) | array model (D8 §5) | in SKY130 at 1.8 V arithmetic dominates once reuse ≥ 16. Not a contradiction: different node and memory, and the SRAM input is class H |

## 6. Claims this report does not make

* That any number here is a physical maximum of throughput or a minimum of energy for SKY130. They are conditional results for specific circuits. The only proven minima are the thermodynamic and quantum bounds of D3, 10⁸ below practice.
* That gate-level f_max is achievable after layout. Wires, clock skew and setup margins will lower it.
* That 100 °C is a safe operating temperature. It is the characterisation limit, and no reliability data were available.
* That the conclusions transfer quantitatively to other nodes. Glitch dominance, the register share and the influence of operand statistics are structural and likely to transfer qualitatively. The Booth result and the memory-vs-arithmetic balance are library- and node-specific.

## 7. Arithmetic re-checks performed for this audit

Every table in D4, D7, D8 and D9 is regenerated from CSVs by `tools/make_report_tables.py`, so table-to-data drift is excluded. Prose numbers were checked against the CSVs by hand during writing. Corrections made at that stage included the leakage unit (nW, not µW), the Wallace FA/HA counts, the STA-vs-OpenSTA delay discrepancy (2–16 %, previously misquoted) and the share of the amortised output CPA (0.3 %, previously misquoted). Independent recomputation is automated for: Landauer and kT/q values, the multiplication entropy (brute force), accumulator widths (brute force), spreading resistance (numerical quadrature), the Foster step response, the electro-thermal fixed point (analytic linear case), Monte Carlo propagation (analytic σ) and the power arithmetic (OpenSTA). See `tests/`.
