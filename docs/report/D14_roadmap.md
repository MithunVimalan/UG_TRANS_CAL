# D14 — Implementation roadmap: from transistor models to silicon

## 1. The 17-step workflow (brief §16.1), as executed

Status: **done** = executed and validated here; **partial** = executed for a subset or without a required input; **not done** = the reason is given.

| # | Step | Inputs | Outputs (in this repository) | Validation criterion | Limitations | Status |
|---|---|---|---|---|---|---|
| 1 | Obtain authoritative process and device data | SKY130 repositories at pinned commits | `sim/pdk/fetch_pdk.sh`; D5 inventory | file-level provenance (commit hashes) | open PDK labelled experimental; reliability data absent | done |
| 2 | Verify model versions, operating conditions, documentation | model files, Liberty headers, device docs | D4 §1–2, D5 §4 | model version read from the cards (BSIM4 level 54, v4.5); slim library identical to full library (`check_slim_lib.py`) | characterisation conditions undocumented | done |
| 3 | Establish a baseline transistor-level circuit | cell netlists (schematic), GDS | layout-extracted + LOD netlists of 22 cells (`extract_cells.py`) | Magic extraction without errors; LVS-style netlist (`ext2spice lvs`) | intra-cell parasitics only | done |
| 4 | Simulate its electrical behaviour | ngspice 42, slim library | device table (D4 §2), FO4 sweep (D4 §4), leakage by state (D4 §5) | convergence; GMIN artefacts removed (leakage at GMIN 10⁻²⁰ S) | single-finger devices for the device table | done |
| 5 | Validate against documented characteristics | foundry device tables; Liberty | V_th vs documentation (3–5 mV at two geometries); inv_1 vs Liberty (energy −1.6…+5.6 %) | agreement within the stated tolerance at every characterised point | no silicon data; some documentation rows differ by 20–50 mV, unresolved | done |
| 6 | Build basic logic cells | foundry HD cells (not redesigned) | 22 cells used as given | — | no custom cells (e.g. compressors, Booth cells); library-specific conclusions (D7) | done (by reuse) |
| 7 | Characterise delay, energy, power | Liberty (C); SPICE (F) | calibration (D4 §3), leakage (D4 §5), FO4 vs V (D4 §4) | SPICE vs Liberty agreement | only inv_1 calibrated across views; other cells trusted from Liberty at 1.28–1.95 V | partial |
| 8 | Construct alternative multiplier architectures | `ugcal.arith` generators | array, Braun, carry-save, Wallace, Dadda × AND/BW/Booth-4 × ripple/KS/BK/Sklansky; 8×8 signed/unsigned, 16×16; adders 8–32 bits | generator unit tests | drive-1 cells, no sizing | done |
| 9 | Verify arithmetic correctness | Python reference model | `sim/gatelevel/verify_multipliers.py` → `results/power/verification.csv`: 71 netlists (every generated architecture at 4, 6, 8 bits exhaustively, including 65,536 pairs at 8×8; 100,000 random pairs at 16×16; Yosys netlists likewise); MAC cycle-by-cycle | 0 errors in 3.1 × 10⁶ vectors; every SPICE cycle also checked | 16×16 not exhaustive (2³²); formal equivalence not run | done |
| 10 | Synthesize the designs | Yosys 0.33 + ABC, Liberty | `results/synth/*` (behavioural `a*b` baselines) | functional re-simulation of the imported netlist | area-oriented ABC script; no timing-driven synthesis | done |
| 11 | Implement physical layouts | P&R tool, tech LEF, cell LEF | — | DRC/LVS clean | — | **not done**: no OpenROAD/LibreLane in the container |
| 12 | Extract relevant parasitics | layout, extraction rules | cell-level only (step 3) | — | — | **not done** for designs (depends on 11) |
| 13 | Timing and power analysis | netlists, Liberty, activity | D7, D8, OpenSTA cross-check (D10 §5) | OpenSTA agreement 0.2–4 % (power); SPICE inside the gate-level glitch bracket | pre-layout; STA pessimistic by 2–16 % vs OpenSTA | done (pre-layout) |
| 14 | Thermal behaviour with boundary conditions | P(T), θ (S), leakage(T) | D9 envelope, electro-thermal fixed point | analytic test cases (tests); loop gain < 1 | θ swept, not a chosen package; lumped die | partial |
| 15 | Benchmark against the bounds | D3 bounds, D7/D8 results | D3 §5 ratios; D11 procedure; worked example (D10) | same operation definition and temperature | evidence level 2 only | done (at level 2) |
| 16 | Record deviations, identify dominant inefficiencies | all of the above | D7 §8, D8 findings, D12 | each finding traced to data | — | done |
| 17 | Compare with silicon | measurements | — | E_n ≤ 1 (D11 §5) | — | **not possible** (no silicon) |

## 2. Tools: what each supports, and the evidence that it was adequate

| Tool | Needed for | Supports the required model format/analysis? | Evidence in this project | Caveats |
|---|---|---|---|---|
| ngspice 42 (KLU) | transistor level | yes: BSIM4 level 54 as used by the SKY130 cards, `.lib` sections, AGAUSS mismatch | runs at all corners; slim library identical to full | BSIM-CMG (ASAP7) needs OSDI/Verilog-A compilation, not established here |
| Xyce | parallel SPICE for large netlists | open_pdks ships SKY130 models for Xyce (not checked here) | not installed or evaluated | would be the candidate for post-layout whole-MAC SPICE |
| Magic 8.3.685 | layout extraction | yes, with the open_pdks tech file (≥ 8.3.411 required; the Ubuntu 8.3.105 package is too old) | extracted inv_1 reproduces Liberty | — |
| Icarus Verilog | RTL simulation | functional only with the SKY130 cell models | conditional specify paths gave zero delay with SDF, so it is unusable for glitch power | use a gate-level simulator that reads Liberty (ours) or a commercial one |
| Yosys 0.33 + ABC | synthesis | yes (Liberty mapping) | netlists re-verified functionally | not timing-driven here |
| OpenSTA 3.1.0 | STA, power from VCD | yes (NLDM, `report_power` with VCD) | 0.2–4 % agreement with our power | without a VCD its default activity (0.1 per clock at inputs) ignores glitches |
| OpenROAD / OpenRCX (via LibreLane) | P&R, CTS, extraction | yes for SKY130 (open_pdks configs present) | **not installed here** | the next required tool |
| Formal tools (Yosys SAT/ABC `cec`, SymbiYosys) | equivalence at 16×16 and beyond | yes, in principle | not run; exhaustive simulation suffices at 8×8 | multiplier equivalence is hard for SAT at large widths |
| HotSpot / 3D-ICE | floorplan-level thermal | yes (compact thermal RC models) | not used: no floorplan | our `rc_network_transient` covers small networks |
| `ugcal` (this project) | provenance, units, gate-level glitch power, envelopes | — | validated per D10 §4–5 | NLDM, no wires |

## 3. Staged plan

Each stage ends at a decision gate: a quantitative question it must answer before the next stage is worth its cost.

**Stage A — Device and cell models (complete).** Gate: does the SPICE setup reproduce the foundry library? Answered for inv_1 (extracted + LOD view). Remaining: repeat the calibration for fa_1, ha_1, xor2_1, dfxtp_1 and a21o_1, the cells that carry most of the energy (D7/D8), at tt and ss/100 °C. Cost: hours with the existing scripts.

**Stage B — Logic characterisation at the operating points of interest.** Gate: is there a supply below 1.28 V where E/MAC drops enough to matter, with acceptable variability? Work: characterise the 22 cells with `cellchar` at 0.6–1.2 V into a Liberty-like table, then rerun D7/D8 at those supplies. Run Monte Carlo with the `_mm` mismatch sections on the critical path. Output: minimum-energy point of a real MAC, with variability (replacing the FO4 scaling model of D4 §4).

**Stage C — Multiplier implementation (next).** Candidates: Dadda + ripple (lowest energy), Dadda + Brent–Kung (energy–delay), BW + Dadda + KS (signed), Yosys baseline (control). Work:
1. LibreLane/OpenROAD P&R of each 8×8 design with identical floorplan density and I/O placement.
2. OpenRCX (and Magic) extraction.
3. OpenSTA timing and power with our VCDs and SPEF.
4. ngspice of the extracted netlist for the two extreme designs, to re-arbitrate the glitch bracket with wires.

Gate: do the pre-layout rankings survive wires? Expected risk: tree multipliers lose more than arrays (D7 §9).

**Stage D — MAC and small array implementation.** Candidates: `csa_acc_bw_kogge_stone` and `separate_bw_ripple`. Work: P&R of a 4×4 PE array with CTS, clock gating and operand isolation as options, the full SRAM macro from OpenRAM, and power intent with a separate supply domain for the array. Gate: the clock-tree share and the SRAM share with real wires. These are the two class-I/H items that now dominate the uncertainty of D8 §5.

**Stage E — Post-layout and thermal closure.** Work: choose a package (for an MPW test chip, the shuttle's standard package) and obtain θ_JA/θ_JC (datasheet or JESD51 measurement). Solve the electro-thermal fixed point with leakage(T) from post-layout power at the slow and fast corners. Re-time at T_j. Gate: is the design thermally or timing-limited at the target throughput?

**Stage F — Silicon validation.** Test-chip content:
1. The two MAC variants and two multiplier variants on **separate supply pins**, so each block's current can be measured.
2. On-chip LFSR operand generators with selectable statistics (uniform, sparse, small magnitude, an NN-like pattern), plus a signature register to check correctness at speed.
3. A ring oscillator of each key cell for corner identification.
4. On-die temperature sensing (a diode or ring-oscillator thermometer) to tie measurements to T_j.

Measurement: source-measure units on each supply. Energy per operation = (I_active − I_idle,clock-gated) × V / rate, with the idle and leakage terms measured separately. Use a temperature-controlled chuck at 25 and 85–100 °C, and sweep supply and frequency to the failure point. Report expanded uncertainty from instrument specifications and repeatability. Compare with the post-layout predictions by E_n (D11 §5).

Gate: which of the discrepancy sources in D11 §6 dominate in silicon, and how much of the gap to the post-layout prediction is closed.

## 4. What would change the conclusions

| Conclusion | Would be overturned by |
|---|---|
| Glitches dominate architecture-dependent energy | post-layout SPICE showing wire delays equalise path arrival times (unlikely, since wires add imbalance) |
| Booth radix-4 is worse in SKY130 HD | custom Booth encoder/selector cells, or wider operands (≥ 24 bits) |
| Registers and clock ≈ half or more of the energy of the lowest-energy MACs | a clock tree adding substantially (would *strengthen* it); a low-power flip-flop library; clock gating |
| Arithmetic dominates over SRAM at reuse ≥ 16 | characterised SRAM energy much higher than OpenRAM's estimate |
| Package, not transistors, limits throughput | a high-θ package with high ambient (would strengthen it); or a very low θ, where f_max·N_PE becomes the limit |
