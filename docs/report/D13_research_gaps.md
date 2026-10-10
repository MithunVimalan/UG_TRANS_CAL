# D13 — Research gaps: missing parameters, inaccessible documents, unresolved questions

Each gap is stated as the brief's missing-data policy (§3) requires: what is missing, why it is needed, who holds the authoritative version, how it could be accessed, what it blocks, and the alternative used here, if any. In the framework each one is an `unavailable(...)` parameter (class I). Any calculation that needs it raises `MissingParameter` rather than proceeding with a guess.

## 1. Missing parameters

| # | Parameter | Needed for | Authority | Access | Blocks | Alternative used here |
|---|---|---|---|---|---|---|
| 1 | Interconnect parasitics of a real layout (R, C, coupling) | absolute energy and f_max of every multiplier/MAC (levels 3–4 of D11) | this project's own P&R + extraction (OpenROAD/OpenRCX or Magic) with foundry rule decks | open tools and rules exist; OpenROAD was not available in this container | absolute energy, absolute f_max, wire share of energy | pre-layout results; met2 capacitance bracket (0.078 fF/µm from LEF, class C, to 0.2 fF/µm, class H) for the array model |
| 2 | Clock-tree energy and skew | MAC and array energy (D8), timing margin | CTS on the placed array | same as 1 | E_MAC of an array; f_max with skew | flip-flop clock-pin energy is included (Liberty); the tree is **class I** |
| 3 | SKY130 "Stackup Capacitance Data" spreadsheet | wire capacitance per layer, including coupling | SkyWater (linked from the PDK docs) | external Google Docs link; host blocked here | an independent check of the extraction rules | LEF capacitance (lower bound) |
| 4 | Liberty characterisation conditions (simulator, model set, netlist view, temperature definition) | interpreting library leakage and energy | SkyWater / characterisation team | not public | resolving the 100 °C leakage discrepancy (16–560×; D4 §5) | carry leakage as an interval; SPICE calibration (D4 §3) |
| 5 | Gate tunnelling current | leakage completeness | foundry model with `igcmod/igbmod = 1` | not in the open cards | gate-leakage term | none (expected small at ≈4 nm SiO₂, not quantified) |
| 6 | Electromigration current limits ("Electrical DR") | power-grid and signal sizing; lifetime vs temperature | SkyWater | referenced by rule x.4, not released | EM-limited current density; Black's-equation lifetime | none |
| 7 | BTI / HCI / TDDB ageing models | end-of-life timing guard-band; temperature limit | foundry reliability manual | not public | ageing-aware f_max, reliability-based T_j,max | none; f_max is beginning-of-life |
| 8 | Qualified maximum junction temperature | thermal envelope (D9) | foundry qualification report | not public | a reliability-based thermal limit | 100 °C = hottest characterisation corner, explicitly *not* a reliability limit |
| 9 | Device self-heating | local temperature above the substrate | device thermal characterisation; compact model with a thermal network | BSIM4 cards have none | device-level ΔT | none; die-level spreading model only (D9 §7) |
| 10 | Package and board thermal resistances | T_j, P_max | package vendor (JESD51 data); own measurement | depends on the package chosen | absolute thermal envelope | θ_JA swept 10–60 K/W (class S) |
| 11 | Characterised SRAM energy (read, write, idle separately) | array energy with memory (D8 §5) | silicon-characterised macro or SPICE of the bit cell array | OpenRAM generator output only | memory share of energy | OpenRAM Liberty value (class H; identical for every access type) |
| 12 | Library characterisation below 1.28 V | low-voltage operation, minimum-energy point | own characterisation (SPICE of every cell) | possible with this framework; not done for all cells | minimum-energy point of a real MAC | FO4-based scaling model (D4 §4; class E, three stated approximations) |
| 13 | Variation-aware energy and delay of the multipliers | yield-aware f_max; near-threshold design | Monte Carlo SPICE with the `mc`/`_mm` sections | possible here; costly (hours per run) | statistical f_max; σ of energy | corners only |
| 14 | Silicon measurements of any SKY130 multiplier or MAC | D11 level 6; validating every model | a test chip (MPW) | requires fabrication | all "measured" claims | none: no conclusion here is experimentally established |

## 2. Documents that could not be inspected

| Document | Why needed | Status | Consequence |
|---|---|---|---|
| Liberty Reference Manual / User Guide (definition of `internal_power`, `switching_power_split_model`) | sign convention of rise/fall internal power | not retrievable from the hosts this container could reach; access terms not checked | convention established empirically by SPICE (D6 §6.2) and by OpenSTA's implementation; the text remains unverified |
| BSIM4 and BSIM-CMG manuals (bsim.berkeley.edu) | parameter definitions | host blocked | definitions taken from the model files and widely known BSIM conventions; no equation in this project depends on unverified BSIM internals (SPICE does the evaluation) |
| Primary papers on publisher sites (IEEE Xplore, APS, Nature, Springer, ACM) | exact statements, figures, measurement conditions | hosts blocked; bibliographic data verified via a search service (D15) | cited for what the search summary supports; quantitative details marked *via secondary* where not seen |
| arXiv preprints (e.g. finite-time Landauer bounds) | derivations | host blocked | cited with the bibliographic data only |
| NIST CODATA pages | constant values | host blocked | CODATA 2022 ε₀ value used as widely reproduced; SI-exact constants need no source |
| ISO 13528 (E_n statistic) | consistency criterion | paywalled standard | definition used is the standard textbook one; cited from memory |
| JEDEC JESD51 series | definition of θ_JA, θ_JC, Ψ_JT | registration required | used only to state that θ_JA is a package-comparison metric |
| SkyWater Electrical Design Rules, reliability and qualification data | items 6–8 above | not released | class I |
| Commercial PDKs (TSMC, Samsung, Intel Foundry, GF 22FDX) | leading-edge device data | NDA | not used numerically (D5) |
| IHP SG13G2 and GF180MCU open PDKs (model files) | second open process for cross-checking SKY130 conclusions | public on GitHub, but not checked out in this session | compact-model family and maturity unconfirmed (D5); a second-process check of the architecture rankings remains to be done |
| IRDS More Moore tables | node-to-node projections | site blocked; registration status unconfirmed | not used |

## 3. Claims taken from secondary sources and not re-verified

| Claim | Where used | Secondary source | Effect if wrong |
|---|---|---|---|
| 45 nm energy table (≈0.2 pJ 8-bit multiply; memory accesses orders of magnitude higher) | D8 §5 context only | search summaries of Horowitz (ISSCC 2014) | none on any calculation |
| Air-cooled heat sinks remove ≈40–50 W/cm² at a 45–50 °C budget | D9 §6 context | IEEE Heterogeneous Integration Roadmap 2023, via the input research file | none on any calculation; D9's power densities are far below |
| OpenRCX total-capacitance error ≈20 % vs a field solver | D5, D7, D12 | input research file | sizes the expected post-layout correction only |
| Veendrick short-circuit formula | implemented, flagged, unused | secondary description | none (unused) |
| Meindl & Davis minimum supply 2 ln2 kT/q | D3 §2.5 | secondary statements of the 2000 JSSC paper | a factor in a bound that does not constrain SKY130 |
| "40–100 kT" reliability floor often quoted | D3 §2.3 | no primary source found | the number is shown to depend on the target error probability; not used |
| Vendor process claims (TSMC N2, Intel 18A, Samsung 3GAE) | D5 context | search summaries | none on any calculation |

## 4. Unresolved physical and technical questions

1. **The size of the gap that cannot be closed.** E_MAC is ≈10⁸ above the Landauer floor for the MAC's output-level erasure. No accepted theory gives a tight, technology-independent lower bound for *irreversible CMOS-style logic at a specified error rate and speed*. The kT/C snapshot argument (D3 §2.3) gives ≈10² kT per node transition (126 kT for an error probability of 10⁻¹⁵). That is a scale, not a proof, because gates regenerate signals and noise is correlated. The defensible statement is therefore a chain of conditional bounds (D2, D12), not a single number.
2. **Gate-level glitch prediction.** Transistor-level SPICE lands between the inertial and transport brackets (1.19–1.37× inertial for the six 8×8 designs simulated). A general rule for where in the bracket a design lands is not known. It depends on path imbalance, cell slew and wire delay, so the latter needs layout to resolve.
3. **Which leakage data set represents silicon at high temperature.** The Liberty and same-corner SPICE values differ by 1–3 decades at 100 °C (D4 §5). Only measurement or the characterisation report can settle it. For the arrays here it does not change any conclusion (leakage ≤ 1.3 % of power), but it would for idle-dominated or low-voltage designs.
4. **Low-voltage SKY130 operation.** Below 1.28 V there is no foundry characterisation. Near threshold, mismatch (σ_Vth ≈ 11–14 mV for the inv_1 devices) becomes a significant fraction of the gate overdrive, so variability dominates delay. The minimum-energy-point estimate (D4 §4) ignores this.
5. **Timing at T_j,max and temperature inversion.** The sustainable-throughput procedure (D9 §8) needs f_max at the temperature reached. At 1.8 V, ss/100 °C is a sound bound: the FO4 chain is 1 % slower at 100 °C than at 25 °C. But the FO4 sweep shows temperature inversion below ≈1.6 V: at 0.6 V the chain is 6× faster hot than cold (D4 §4). Any low-voltage design must therefore be signed off at the cold corner. This was shown only for an inverter chain at tt; multi-corner, cell-level confirmation is open.
6. **Transferability to advanced nodes.** FinFET and GAA devices add self-heating (BSIM-CMG thermal network), stronger wire dominance and different cell libraries. The qualitative conclusions likely to transfer (glitch dominance, register share, operand statistics) are hypotheses for those nodes until checked with their PDKs.

## 5. Workflow steps not executed (see D14)

| Step (brief §16.1) | Status | Reason |
|---|---|---|
| 11 Physical layout | not done | no OpenROAD/LibreLane installation in this container |
| 12 Parasitic extraction of the designs | not done (cells only: Magic extraction of the 22 cells used) | depends on 11 |
| 14 Thermal behaviour with real boundary conditions | swept θ only | no package chosen |
| 17 Silicon comparison | not possible | no silicon |
