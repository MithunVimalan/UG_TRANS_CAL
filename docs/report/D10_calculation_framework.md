# D10 — Reproducible calculation framework

## 1. What it is and the rules it enforces

`ugcal/` is a dependency-free Python package (standard library only; tested with Python 3.13; the tests need `pytest`, and one quadrature test needs `numpy`). Simulation drivers in `sim/` call the open tools ngspice, Magic, Yosys and OpenSTA. Every number in D3–D9 is produced by a script in this repository from files fetched at pinned commits. None was typed into the report by hand: report tables sit between `<!-- BEGIN:x -->`/`<!-- END:x -->` markers and are rewritten by `tools/make_report_tables.py`.

Three rules from the brief are enforced in code, not only by convention:

| Rule | Mechanism | Test |
|---|---|---|
| No unlabelled numbers | Every input is a `Param` with an evidence class A–I (plus S, design specification) and, unless it is a constant or a specification, a `source`. The functions in `fundamental`, `switching`, `thermal` and `array` accept only `Param`/`Result`; `val()` rejects a bare `Quantity` or float. | `test_unlabelled_inputs_rejected`, `test_param_needs_source_and_matching_unit` |
| No silent substitution of missing data | A missing parameter is `unavailable(name, unit, why, authority, access)` → class I, value `None`. Any use raises `MissingParameter`, with the reason and the authoritative source in the message. There are no defaults. | `test_unavailable_parameter_raises_and_is_not_substituted` |
| Units are checked | `Quantity` carries SI dimensions (m, kg, s, A, K). Addition of unlike dimensions, a unit that does not match a `Param`'s value, or a function returning the wrong dimension raises `DimensionError`. The checker caught a real bug during development: `dynamic_power` returned J instead of W. | `test_unit_conversion_and_prefixes`, `test_dimension_errors` |

Every output is a `Result`. It records the value, the equation as text, its inputs (which are themselves `Param` or `Result`), assumptions, validity conditions, unit and relative uncertainty. `Result.describe()` prints the lineage tree down to the sourced leaves. `Result.input_classes()` returns the evidence classes the result rests on, so a conclusion's class can be audited mechanically (D12).

## 2. Package layout

| Module | Contents | Brief part |
|---|---|---|
| `ugcal/units.py` | `Quantity`, `q(value, unit)` with SI prefixes, `celsius()`, `DimensionError` | §17 |
| `ugcal/provenance.py` | `Cls` (A–I, S), `Param`, `Result`, `spec()`, `unavailable()`, `val()`, `ParamSet`, `MissingParameter` | §17, §19 |
| `ugcal/constants.py` | k_B, q, h, ħ (exact, SI 2019), ε₀ (CODATA 2022) | III |
| `ugcal/fundamental.py` | Landauer, kT/q, SS limit, Meindl and Swanson–Meindl minimum supply, kT/C noise, static error probability, energy for a target error probability, barrier for retention, Margolus–Levitin, Mandelstam–Tamm | III, D3 |
| `ugcal/infotheory.py` | exact entropy loss of n×n multiplication and of the MAC; gate-level erasure count from simulated netlists | III, D3 |
| `ugcal/switching.py` | `Activity` (α₀₁, toggles/cycle and toggle density, inter-converted), CV² vs ½CV² bookkeeping, dynamic, leakage and short-circuit power, energy per op, EDP, α-power-law fit | VI, D6 |
| `ugcal/liberty.py` | Liberty parser (lazy), NLDM table interpolation, pin capacitance, leakage, delay/slew, internal energy | VII |
| `ugcal/modelcard.py` | BSIM4 binned model-card reader (`bin_for(W, L)`) | IV |
| `ugcal/gatesim.py` | event-driven gate-level simulator on Liberty data: `sta()`, `simulate()` with zero-delay, inertial and transport modes, per-group power with no double counting, VCD writer for OpenSTA | VII, VIII |
| `ugcal/arith/` | netlist builder with constant folding and pruning; multiplier generators (AND/Baugh–Wooley/Booth-4 partial products, array, Braun, carry-save, Wallace, Dadda, ripple/Kogge–Stone/Brent–Kung/Sklansky final adders); MAC generator (separate, fused, carry-save accumulator); Verilog emitter; Yosys netlist importer | VIII, IX |
| `ugcal/mac.py` | product range, exact accumulator width, `MACSpec`, metrics (TOPS/W = 2/E_MAC[pJ]), energy accounting by functional group | X, D8 |
| `ugcal/array.py` | operand forwarding, SRAM energy per MAC with reuse, array energy and PE density | XI, D8 |
| `ugcal/thermal.py` | T_j = T_a + PR_th, series stacks, slab and three spreading-resistance forms, diffusion time, adiabatic rise, Foster networks, RC-network transients, electro-thermal fixed point with loop gain and runaway detection | XII, D9 |
| `ugcal/uncertainty.py` | `Normal`, `LogNormal`, `monte_carlo()`, `interval()` (enumerates every combination of the bounds; exact for functions monotonic in each input) | §17 |
| `ugcal/benchmark.py` | evidence ladder `Level`, normalised error E_n, consistency test, required benchmark fields | §18, D11 |
| `ugcal/sim/ngspice.py`, `cellchar.py`, `netlist_spice.py` | ngspice runner and parser; cell views (schematic, extracted, extracted + LOD); cell benches; whole-netlist transistor-level decks | IV, VI, VII |

## 3. Using it

```python
from ugcal.provenance import Param, Cls, spec, unavailable
from ugcal.units import q, celsius
from ugcal import thermal as TH

P   = Param("P_total", q(0.818, "W"), Cls.E, source="examples/mac_envelope_example.py", unit="W")
Ta  = spec("T_amb", celsius(25), "K")
th  = spec("theta_JA", q(30, "K/W"), "K/W", note="package not chosen")
Tj  = TH.junction_temperature(Ta, P, th)
print(Tj.describe())            # value, equation, assumptions, sourced inputs
print(Tj.input_classes())       # ['E', 'S']

Rjc = unavailable("R_jc", "K/W", "no package selected", authority="package vendor datasheet / JESD51-14")
TH.series(Rjc, th)              # raises MissingParameter: the gap is reported, not filled
```

**Worked example.** `examples/mac_envelope_example.py` goes from sourced parameters to a performance envelope for 1000 carry-save int8 MAC PEs (D8): power, energy per op, EDP, power density, junction temperature, thermal power limit, and throughput limited by a power budget and by the thermal budget. It also computes local sensitivities, a Monte Carlo and an interval analysis, and the ratio to the Landauer floor. Its output is stored in `results/examples/mac_envelope_example.txt`, and `tests/test_core.py::test_worked_example_runs` re-runs it. Key lines:

| Quantity | Value | Class | Rests on |
|---|---|---|---|
| P_total (1000 PEs at 145 MHz) | 0.818 W | E | E_MAC (E, ±20 %), f_clk (S), P_leak at ff/100 °C (C) |
| T_j at θ_JA = 30 K/W, 25 °C ambient | 322.7 K (49.5 °C) | E | + θ (S) |
| P_max for T_j ≤ 100 °C | 2.5 W | E | T_j,max = hottest Liberty corner (C), θ (S) |
| Thermally limited throughput | 4.45 × 10¹¹ MAC/s | E | as above |
| Throughput under a 0.5 W power budget | 8.8 × 10¹⁰ MAC/s (61 % of the 1.45 × 10¹¹ the array could deliver) | E | P_budget (S), E_MAC, leakage bound |
| Elasticity of P_total w.r.t. V, f, activity, C | 1.99, 0.99, 0.99, 0.99 | E | leakage is 0.7 % of the total |
| Monte Carlo, E_MAC σ = 20 %, 5–95 % | 0.55–1.08 W | E | |
| Interval, activity 0.6–1.0, V 1.71–1.89 V | 0.45–0.90 W | E | |
| E_MAC / Landauer floor (16 bits, 300 K) | 1.2 × 10⁸ | E | |
| Clock-tree energy | not computed: `MissingParameter` | I | needs CTS + extraction |

## 4. Equations implemented, where, and how they are checked

| Equation | Function | Validity | Check |
|---|---|---|---|
| $E_L = k_BT\ln 2$ per bit | `fundamental.landauer` | quasi-static erasure into a bath at T | value at 300 K = 2.871 × 10⁻²¹ J (`test_landauer_and_thermal_voltage_at_300K`) |
| $S_\text{min} = (k_BT/q)\ln 10$ | `fundamental.subthreshold_swing_limit` | Boltzmann injection over a barrier, ideal gate coupling | 59.53 mV/dec at 300 K |
| $V_\text{min} = 2\ln2\,k_BT/q$; $V_\text{min} = 8\,k_BT/q$ | `min_supply_ideal_inverter`, `min_supply_swanson_meindl` | ideal / 1972-technology subthreshold inverters | D3 table |
| $v_n = \sqrt{k_BT/C}$, $p = Q(V/2v_n)$, $E = 2k_BT[Q^{-1}(p)]^2$ | `kTC_noise_rms`, `static_node_error_probability`, `energy_for_error_probability` | thermal-equilibrium snapshot, Gaussian noise, threshold at V/2 | round trip p → E → p (`test_noise_error_probability_roundtrip`) |
| $\tau \ge h/4E$, $\tau \ge h/4\Delta E$ | `margolus_levitin_time`, `mandelstam_tamm_time` | orthogonal-state transition | D3 table |
| $H_\text{in} - H_\text{out}$ of n×n multiplication | `infotheory.multiplication_entropy_loss` | uniform independent operands | brute-force against enumeration for small n (`test_multiplication_entropy_small`) |
| density $= 2\alpha_{01} f$; toggles/cycle $= 2\alpha_{01}$ | `switching.Activity` | stationary signals | `test_activity_conventions_agree` |
| $E_\text{supply} = CV^2$ per 0→1; $E_\text{diss} = \tfrac12CV^2$ per transition | `energy_from_supply_per_rise`, `energy_dissipated_per_transition` | full-swing, linear C | `test_switching_energy_bookkeeping` |
| $P = \tfrac12 C V^2 \cdot$ density | `dynamic_power` | as above | dimension check (W) |
| Liberty $E_\text{int}$ + $\tfrac12CV^2$ + state leakage | `gatesim.SimResult.power` | NLDM, one slew per pin per event | OpenSTA agreement (§5) |
| $t_d = kV/(V-V_t)^\alpha$ | `switching.fit_alpha_power` | strong inversion | fitted to the SPICE FO4 sweep for V_DD ≥ 1.0 V; fit residual reported in D4 §4 |
| smallest $W$ with $-2^{W-1} \le K\min(ab)$ and $K\max(ab) \le 2^{W-1}-1$ (signed; $K\max(ab) \le 2^W-1$ unsigned) | `mac.accumulator_width` | exact integer MAC | brute force (`test_accumulator_width_bruteforce`) |
| $T_j = T_a + P R_\text{th}$; $P_\text{max} = (T_\text{max} - T_a)/R_\text{th}$ | `thermal.junction_temperature`, `max_power` | steady state, one heat path | dimension checks |
| $R_\text{sp} = 1/(4ka)$, $8/(3\pi^2 ka)$, $1/(\pi ka)$ | `spreading_disk_*` | disk on a semi-infinite solid | uniform-flux mean by numerical quadrature (`test_uniform_flux_disk_spreading_by_quadrature`, `test_spreading_formulas`) |
| Foster step $\sum R_i(1-e^{-t/\tau_i})$ | `thermal.Foster` | linear, time-invariant | closed form (`test_foster_step_matches_closed_form`) |
| Fixed point $T = T_a + R_\text{th}[P_\text{dyn} + P_\text{leak}(T)]$; loop gain $R_\text{th}\,dP_\text{leak}/dT$ | `thermal.ElectroThermal` | leakage given as P(T) | analytic solution for linear leakage (`test_electrothermal_linear_leakage_analytic`) |
| Monte Carlo and interval propagation | `uncertainty.monte_carlo`, `interval` | independent inputs | linear model, analytic σ (`test_monte_carlo_linear`) |
| Multiplier and MAC netlists | `arith.multipliers.build`, `arith.mac.build_mac` | — | exhaustive 2^(2n) functional test of all architectures at n = 4 (signed and unsigned), random 8-bit, MAC cycle-by-cycle vs reference (`test_all_multiplier_architectures_exhaustive`, `test_mac_variants_random`) |

`short_circuit_power_veendrick` is implemented but flagged: its formula was transcribed from a secondary description of Veendrick (1984) and could not be checked against the paper (publisher site blocked). No result in this report uses it. Short-circuit energy enters only through Liberty internal power and SPICE.

## 5. Cross-checks against independent tools

| Check | Independent reference | Agreement | Where |
|---|---|---|---|
| Slim model library (only the five device families used) vs the full SKY130 library | full `sky130.lib.spice`, same deck | identical results (worst cumulative relative difference 0.0) at tt/ss/ff/sf/fs; 19–26× faster to load and run | `sim/spice/check_slim_lib.py` → `results/spice/slim_lib_check.csv` |
| inv_1 energy and delay vs the foundry Liberty | Liberty tt_025C_1v80 (class C) | energy −1.6 … +5.6 %, rise −1.4 … +7.0 %, fall −10.1 … −6.2 % with the extracted + LOD view | D4 §3, `sim/spice/calibrate_cells.py` |
| Gate-level power (internal + switching + leakage) | OpenSTA 3.1.0 `report_power` with a VCD from our simulator, same Liberty | total within 0.8–1.7 % for six 8×8 multipliers, 0.2–4.0 % for two MACs, in both zero-delay and inertial modes | `sim/gatelevel/crosscheck_opensta.py` → `results/power/crosscheck_opensta.csv`; `tests/test_pdk.py::test_power_matches_opensta` (5 % tolerance) |
| Gate-level critical path | OpenSTA worst arrival | ours is 2–16 % longer, because `GateLevel.sta()` takes the larger of the rise and fall delay at every arc (no edge or unateness tracking). The bias is pessimistic by construction | same CSV |
| Gate-level energy vs transistor level | ngspice on the full extracted + LOD transistor netlist | SPICE between the inertial and transport brackets; ripple array 1.19× inertial | D7 §7 |

The OpenSTA comparison checks the power arithmetic: interpolation, the internal/switching split and the state-weighted leakage. It does not check the activity, because both tools consume the same toggles. Activity is checked against transistor level (D7 §7). The comparison was not possible with Icarus Verilog + SDF: Icarus silently gave zero delay on the conditional specify paths of the SKY130 cell models, which would have removed every glitch. Our own simulator is used for that reason. This is recorded so that no-one repeats the attempt unknowingly.

## 6. Reproducing everything

```bash
# 0. tools: ngspice 42, Yosys 0.33, Icarus from Ubuntu 24.04 packages;
#    OpenSTA 3.1.0 built from github.com/parallaxsw/OpenSTA @7b261909;
#    Magic 8.3.685 built from source (the Ubuntu package, 8.3.105, is older than the 8.3.411 the sky130 tech file needs)
apt-get install ngspice yosys iverilog
export MAGIC=/path/to/magic-8.3.685/bin/magic
# 1. PDK at pinned commits (sky130_fd_sc_hd @9cb2d7cb, sky130_fd_pr @16f93a79, open_pdks @0ec4fa67, ...)
bash sim/pdk/fetch_pdk.sh                      # -> $PDK_ROOT (default /home/user/pdk)
python3 sim/pdk/make_slim_lib.py               # -> build/sky130_slim.lib.spice
python3 sim/pdk/extract_cells.py               # Magic extraction of the 22 cells used
python3 sim/spice/check_slim_lib.py
# 2. device and cell characterisation (class F)
python3 sim/spice/device_char.py
python3 sim/spice/calibrate_cells.py --view extracted_lod
python3 sim/spice/leakage_study.py
python3 sim/spice/vdd_sweep.py; python3 sim/spice/vdd_sweep.py --temp 100
# 3. arithmetic (class E: gate-level model on foundry Liberty data)
python3 sim/synth/yosys_flow.py
python3 sim/gatelevel/verify_multipliers.py      # exhaustive/random functional check -> results/power/verification.csv
python3 sim/gatelevel/arch_study.py
python3 sim/gatelevel/adder_study.py
python3 sim/gatelevel/mac_study.py
python3 sim/gatelevel/crosscheck_opensta.py
python3 sim/spice/multiplier_spice.py --designs array_rc --nvec 41 --period 12e-9
python3 sim/spice/multiplier_spice.py --designs braun,dadda_rca,wallace_rca,dadda_ks,booth4_dadda_ks --nvec 31 --period 12e-9
# 4. envelope, tables, database, report
python3 sim/envelope/build_envelope.py
python3 tools/build_tables.py
python3 tools/build_parameter_db.py
python3 tools/make_report_tables.py
python3 -m pytest -q
```

Approximate cost on the 4-core container used: device and cell scripts take minutes; each gate-level study takes minutes to tens of minutes; each 8×8 whole-multiplier transistor-level run takes 15–40 min per design with 2 ngspice threads (D7 §7 lists the wall times). Environment variables: `PDK_ROOT`, `UGCAL_CELL_VIEW` (schematic | extracted | extracted_lod; default extracted_lod), `UGCAL_NGSPICE_THREADS`.

## 7. Extending to another PDK or design

1. Write a `fetch_*.sh` with pinned commits and a slim-library generator for the device families used. Verify the slim library against the full one, as `check_slim_lib.py` does.
2. Point `Library(...)` at the new Liberty files. `gatesim` and `liberty` read only standard NLDM constructs (delay, transition, internal-power and leakage tables). CCS or ECSM data in the file are not read.
3. Replace the `CELLMAP` in `ugcal/arith/verilog.py` (gate kind → cell and pin names). A cell missing from the library raises an error when the netlist is bound to the library. Nothing is substituted.
4. For transistor level: cell netlists, preferably layout-extracted. D4 shows the schematic view of SKY130 is off by up to 39 % in energy and 67 % in delay.
5. Add each new parameter to `data/sky130/parameter_database.csv`, or an equivalent file, with its class and source location. Anything not obtainable is entered with `unavailable(...)` and its authority and access, so the gap propagates to every result that depends on it.

For a design under NDA (a commercial PDK), the same code runs on the user's machine. The data never needs to enter this repository, and the provenance strings then cite the confidential document by its internal identifier.

## 8. Limitations of the framework

* Gate-level timing is NLDM with one slew per pin and event. There is no RC-wire model. The optional `wire_load` argument selects a Liberty fan-out wire-load model (a lumped capacitance); none was used in the reported runs, so wires contribute nothing.
* The uncertainty model treats inputs as independent. Correlations, for example between corner leakage and delay, are represented only by evaluating corners jointly.
* `ElectroThermal` is lumped (one temperature). Hot spots need the RC-network solver with a floorplan, which this project does not have.
* The Liberty parser handles the SKY130 libraries and the NLDM subset. It is not a general Liberty implementation.
