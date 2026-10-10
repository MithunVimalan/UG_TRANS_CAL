# D11 — Benchmarking procedure: comparing a candidate design with its predicted limits

## 1. Purpose and principle

A benchmark answers two questions about a multiplier, MAC or array. How far is it from a stated bound (D3 for fundamental bounds, D8/D9 for technology and thermal envelopes)? And is it consistent with a prediction, or with a measurement made elsewhere? Both answers depend on conditions as much as on the design. A number without its supply, corner, temperature, activity source, loads and interconnect model cannot be compared with anything. The procedure below makes those conditions part of the result. The code is in `ugcal/benchmark.py`.

## 2. Evidence ladder

Each benchmark result is reported with the highest level actually reached, never the level intended.

| Level | Name | What has been done | What it can and cannot show | Reached in this project |
|---|---|---|---|---|
| 0 | FUNCTIONAL | arithmetic verified (exhaustive or random) against a reference model | correctness only | all multipliers: exhaustive at 4, 6 and 8 bits, 100,000 random pairs at 16 bits, 71 netlists with 0 errors (`results/power/verification.csv`); all MACs (cycle-accurate against a reference model, with clears); all adders (1001 random vectors) |
| 1 | CIRCUIT_SIMULATED | transistor-level SPICE with foundry models, for the cells as used | cell-level energy and delay; with whole-netlist runs, glitch activity without any gate-level abstraction | inv_1 calibration (3 netlist views at tt/25 °C plus 3 further corners with the schematic view, 16 slew–load points each); FO4 supply sweep; whole 8×8 multipliers on the extracted + LOD view (D7 §7) |
| 2 | SYNTHESIZED | mapped to a characterised library; STA and power with wire-load or no wires | relative energy and delay of architectures under controlled conditions; absolute values without wires | all D7/D8 results (no wires) |
| 3 | IMPLEMENTED | placed and routed | wire lengths, real fan-outs, buffers, clock tree | **not reached** |
| 4 | POST_LAYOUT | extracted parasitics (SPEF) back-annotated, STA and power re-run | absolute energy and f_max of the implementation | **not reached** |
| 5 | THERMALLY_VALIDATED | temperature computed with stated boundary conditions, or measured | T_j and the thermal throughput limit | computed for swept θ_JA only (D9); no package, so not validated |
| 6 | SILICON_MEASURED | measured on fabricated silicon, with stated instruments and uncertainty | everything, for that chip and test setup | **not reached** |

Levels 1 and 2 are not strictly ordered for every metric. A level-2 power number with simulated toggles is more complete than a level-1 inverter characterisation, and a level-1 whole-netlist SPICE run arbitrates the glitch model of level 2. In D7, level 1 is used for exactly that purpose. Any claim about "a multiplier in SKY130" in this report is at level 2, with level-1 arbitration for 8×8 designs.

## 3. Required record

A result is a record with the fields in `ugcal.benchmark.REQUIRED_FIELDS`. `missing_fields(record)` lists absent fields, which must be reported as **not established**. They are never filled with typical values.

| Field | Definition used | Why it is needed |
|---|---|---|
| operand_width, arithmetic | e.g. 8×8 signed two's complement, accumulator W = 22, modular | defines the work done |
| functional_check | exhaustive / random (count) / none | an incorrect circuit can be arbitrarily cheap |
| cells, transistors, area_um2 | from the netlist and Liberty; utilisation stated if area includes white space | density, leakage, cost |
| critical_path_s, latency_cycles, initiation_interval | at the stated corner | throughput and the clock of any loop |
| throughput_ops_s | MAC/s × 2 ops/MAC (one multiply plus one add), stated | TOPS conventions differ by 2× |
| P_dynamic_W, P_leakage_W, P_total_W | at stated V, f, T and activity | — |
| E_op_J | P_total / throughput, or the simulated energy per operation | the primary efficiency metric |
| EDP_Js | E_op × t_op, with t_op stated (1/f_clk or critical path) | — |
| T_junction_K, power_density_W_m2 | with R_th source and area definition | thermal feasibility |
| VDD_V, f_clk_Hz, corner | — | everything above depends on them |
| activity_source | operand distribution and glitch model (zero / inertial / transport / SPICE) | activity changes energy by 1.3–3.4× (glitch model) and 3–6.5× (operand statistics) in this project |
| output_load_F | load on every primary output | changes the output-stage energy |
| interconnect | none / wire-load model / SPEF | wires are absent at levels 0–2 |

## 4. Controlled-comparison rules

When comparing designs (D7 §1 lists the conditions actually used):

1. **Same library, corner, supply and temperature.** Do not mix tt and ss, and do not compare 1.8 V results with 1.2 V results through a V² rule. The rule fails as V approaches V_th (D4 §4).
2. **Same operand stream**, with the same seed, length and distribution. The first vector only sets the initial state, so every design starts from the same state and energy is averaged over the transitions that follow.
3. **Same input conditions**: identical input slews and output loads. Input-net switching energy (charging the operand wires from outside) is either excluded for all designs or included for all; here it is excluded, and reported separately.
4. **Same glitch model**, with the bracket reported (zero / inertial / transport). Comparing an inertial result for one design with a zero-delay result for another can reverse rankings. At 8×8 unsigned the inertial/zero factor ranges from 1.31 (Dadda + ripple) to 2.11 (Booth + Dadda + KS), and transport/zero from 2.8 to 7.1.
5. **Same functional definition.** A multiplier that drops the product's upper bits, or a MAC whose accumulator is too narrow, is a different function.
6. **Same accounting.** Each cell belongs to one group, each net is charged to its driver, the clock-pin energy goes to the clock group, and amortised parts carry an amortisation factor (here the csa_acc output CPA per K = 64). No energy is counted twice. `ugcal.mac.energy_accounting` checks that the groups sum to the total.
7. **Technology scaling across nodes is not a measurement.** If a result from another node must be compared, the scaling rule (e.g. E ∝ C V²) and its inputs are stated, and the scaled number is class H (estimated). This project does not scale any published accelerator figure to SKY130.

## 5. Consistency criteria

For a result x_m with expanded uncertainty U_m and a prediction x_p with U_p:

$$E_n = \frac{x_m - x_p}{\sqrt{U_m^2 + U_p^2}}, \qquad |E_n| \le 1 \Rightarrow \text{consistent}$$

This is the normalised-error statistic used in inter-laboratory comparisons (ISO 13528, cited from memory; the standard text was not inspected). When the prediction is a bracket [lo, hi] rather than a distribution, as for the glitch bracket, the result is consistent if it lies inside the bracket widened by U_m (`consistent(..., interval=(lo, hi))`).

Applied to this project. The transistor-level energy of the ripple-carry array multiplier (D7 §7; 3.07 pJ) is inside the gate-level [inertial, transport] bracket of [2.59, 5.14] pJ on the same 40 transitions. The bracket is therefore consistent at level 1, but the inertial value alone is not: SPICE is 1.19× the inertial value. The OpenSTA cross-check (D10 §5) agrees within 0.2–4 %. With an assigned tool-comparison uncertainty of 5 %, that gives |E_n| < 1 for all 16 comparisons.

**Gap to a bound.** `Candidate.gap_to(bound, value, metric)` returns the ratio and its decimal logarithm. Gaps are reported only between quantities with the same definition of "operation" and the same temperature. For example, Landauer for 16 erased bits at 300 K versus E_MAC at 25 °C (298 K) differs by < 1 % in kT and is stated as such.

## 6. Ranked sources of discrepancy, with the magnitude measured here

| Source | Effect measured in this project | Where | Handling |
|---|---|---|---|
| Operand statistics | 4.7–6.5× (unsigned 8×8, small vs uniform); 1.02–1.28× (signed small); 1.8–3.8× (sparse) | D7 §8, D8 §3 | report the distribution; benchmark on application data |
| Glitch model | inertial/zero 1.3–3.4×; transport/zero up to 10× (Booth) | D7 | report the bracket; arbitrate with SPICE |
| Transistor netlist view | schematic vs extracted + LOD: energy −39 %, fall delay −67 % (inv_1) | D4 §3 | use extracted netlists |
| Activity defaulting in STA | OpenSTA without a VCD assumes 0.1 transitions per minimum clock period at inputs (`Power.cc`) and propagates it probabilistically, which ignores glitches | D10 §5 | always annotate activity |
| Supply and corner | FO4 energy 18.6 → 3.0 fJ from 1.8 to 0.8 V; f_max tt vs ss/100 °C: 2.1–2.2× | D4 §4, D8 | state V, corner, T |
| Leakage data set | at 100 °C the Liberty leakage is 16× (tt), ≈560× (ss) and ≈4× (ff) above SPICE with the same-named model corner (geometric means over 46 cell states) | D4 §5 | carry leakage as an interval; neither is measured silicon |
| Wires | not measured (no layout); the brief's source file reports ~20 % OpenRCX total-capacitance error vs a field solver (not re-verified) | D7 §9 | level 3–4 needed |
| CV² vs ½CV² | factor 2 if supply energy per rising transition is confused with dissipation per transition | D6 §1 | `ugcal.switching` keeps both explicitly |
| TOPS convention | factor 2 (1 or 2 ops per MAC) | D8 | state 2 ops/MAC |
| Amortised units | csa_acc output CPA: 19 fJ = 0.3 % of E_MAC at K = 64; it would be 21 % if it ran every cycle | D8 | state K |
| Clock tree, SRAM, control | clock tree **not available**; SRAM by OpenRAM estimate (class H) multiplies energy per MAC by 2.8–3.0 without operand reuse | D8 §5 | flag as missing or class H |

## 7. Procedure (checklist)

1. Fix the specification: function, widths, accumulator, rounding, latency and throughput target, V, corner and T (D8 §1 format).
2. Verify functionality (level 0), exhaustively where 2^(2n) is feasible.
3. Fix the conditions table (D7 §1), including stimulus seeds.
4. Run the gate-level power in all three glitch modes and report the bracket.
5. Arbitrate with transistor level on at least one design per family, or state that it was not done.
6. Cross-check the power arithmetic against an independent tool (OpenSTA) with the same activity.
7. Fill the required record. List `missing_fields()` as not established.
8. Compute E_op, EDP, TOPS/W (2 ops/MAC), power density and T_j for stated R_th.
9. Compute the gaps to the bounds of D3 with the same operation definition.
10. Propagate uncertainty: a Monte Carlo on class-E/H inputs, intervals on class-S choices.
11. Assign the evidence level and the evidence class of every conclusion (D12).

## 8. External references

**Same process, same function (usable).** One open SKY130 design matches this project's MAC specification: signed int8, 22-bit accumulator, tt/25 °C/1.8 V, uniform data. It is a post-route 8×8 systolic array (D8 §5.1; class G, third party, not peer-reviewed; inspected at a pinned commit). Applying the rules above:
* same corner and data;
* different activity model (zero delay there, so compare with this project's zero-delay values);
* different boundary (whole array including clock tree, control and wires, versus a single PE without them);
* missing fields: uncertainty, temperature, per-group split by function.

Result: 15.9 pJ/MAC versus 4.1–6.1 pJ/MAC, i.e. 2.6–3.9×. This is not a consistency test (the boundaries differ). It is an empirical implementation factor, reported as such.

### Published accelerators at other nodes: why no ranking table is given

The brief asks for comparison with published accelerators. Published figures such as the TPU v1 (65,536 8-bit MACs, 92 TOPS peak; Jouppi et al. 2017) or Eyeriss (65 nm, 278 mW; Chen et al. 2017, JSSC) were verified only through search summaries in this session. Publisher pages were blocked; see D15. They come from other nodes, supplies, memory systems and operation definitions, and most records lack several required fields: activity source, per-MAC energy without memory, and temperature. Under rule 7 of §4 they can be placed on the same plot only after an explicit scaling model (class H). This report does not do that. It provides the record format and the gap computation so that a reader with access to the papers' full texts can do it consistently.
