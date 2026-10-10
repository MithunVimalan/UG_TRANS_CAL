# D6 — Mathematical derivations: energy, power, delay, leakage, reliability, heat

Every expression used by the framework (`ugcal`) is derived here with its assumptions. Section numbers are referenced from the code docstrings and from the other deliverables. Where a derivation was checked numerically or against SPICE, the check is named.

---

## 1. Charging a capacitance from a DC rail

A node of capacitance $C$ (linear, to ground) is charged from 0 to $V$ through a switch of arbitrary, possibly nonlinear and time-varying, resistance from a constant supply $V$.

* Charge delivered by the supply: $Q = CV$.
* Energy delivered by the supply: $E_\text{sup} = \int V\,i\,dt = V\int i\,dt = V Q = CV^2$. The supply voltage is constant, so this is exact and independent of the switch.
* Energy stored on the capacitor at the end: $E_C = \int v\,i\,dt = \int_0^V C v\,dv = \tfrac12 CV^2$.
* Energy dissipated in the pull-up during charging: $E_\text{sup} - E_C = \tfrac12 CV^2$. It is independent of the resistance, because a larger resistance gives a smaller current for a longer time.
* Discharging to ground through the pull-down dissipates the stored $\tfrac12 CV^2$; the supply delivers nothing.

**Per full cycle (0→1→0):** the supply delivers $CV^2$ and the circuit dissipates $CV^2$. **Per transition (either edge), averaged:** $\tfrac12 CV^2$ dissipated.

**Validity:** linear $C$; constant-voltage supply (no adiabatic ramp); full-swing transition; no charge sharing between nodes. For nonlinear $C(v)$ (MOS gate and junction capacitances), $E_\text{sup} = V\cdot Q(V)$ still holds with $Q(V)=\int_0^V C(v)\,dv$, but the stored energy is $\int_0^V v\,C(v)\,dv \ne \tfrac12 C_\text{eff}V^2$ in general. That is why the framework takes energies from SPICE charge integrals or from Liberty tables, not from a single "C".

**Check.** In the inv_1 calibration (results/spice/calibration_inv_1_*), the supply energy of a rising output edge minus ½C_LV² reproduces the Liberty `rise_power` entry, and the falling edge minus ½C_LV² reproduces `fall_power` (a negative number). Agreement is within a few tenths of a fJ over the 4×4 slew–load grid with the layout-extracted cell (§6.3).

## 2. Dynamic power and activity conventions

Let a node make $N_\uparrow$ rising and $N_\downarrow$ falling transitions in a window $T_w$ ($|N_\uparrow - N_\downarrow|\le1$). From §1, the supply energy is $N_\uparrow CV^2$, so

$$P_\text{dyn} = \frac{N_\uparrow CV^2}{T_w} = \alpha_{01} C V^2 f = \tfrac12 C V^2 D,$$

with $\alpha_{01} = N_\uparrow/(fT_w)$ the probability of a 0→1 transition per clock cycle and $D = (N_\uparrow+N_\downarrow)/T_w$ the transition density (both edges, s⁻¹). Then $D = 2\alpha_{01} f$, and transitions per cycle $tpc = 2\alpha_{01}$. A random-data node with signal probability ½ and independent cycles has $tpc = ½$, i.e. $\alpha_{01}=¼$. OpenSTA uses $D$ and the factor ½ (`Power.cc`: `.5 * load_cap * volt * volt * activity.density()`); textbooks use $\alpha_{01}$ (Chandrakasan et al. 1992). `ugcal.switching.Activity` stores $D$ and converts, and `tests/test_core.py::test_activity_conventions_agree` checks both forms give the same power.

**Glitches.** A glitch is a pair of transitions within one cycle that leaves the settled value unchanged. Full-swing glitches cost exactly like functional transitions. Partial-swing glitches cost less, $\approx C V_\text{swing} V_{DD}$ per charging excursion. Gate-level simulators count glitches either as full transitions (transport delay) or not at all once a pulse is shorter than the gate delay (inertial). This project reports both as a bracket and arbitrates with SPICE (D7).

## 3. Leakage and short-circuit power

**Leakage.** Static supply current in a fixed input state $s$: $P_\text{leak}(s) = V_{DD} I_\text{static}(s)$. For a cell, $\overline{P}_\text{leak} = \sum_s \pi_s P_\text{leak}(s)$, where $\pi_s$ is the fraction of time spent in state $s$. Liberty `cell_leakage_power` is the unweighted mean over the listed states (checked: `tests/test_pdk.py::test_cell_leakage_is_unweighted_state_mean`), i.e. it assumes $\pi_s = 1/N_s$. `ugcal.gatesim` uses the state occupancy from simulation instead.

Physical components (Roy et al. 2003): subthreshold conduction, $I_\text{sub} \approx I_0 \frac{W}{L}\exp\!\big(\frac{V_{GS}-V_{th}+\eta V_{DS}}{n k_BT/q}\big)\big(1-e^{-qV_{DS}/k_BT}\big)$, with DIBL coefficient $\eta$; gate-oxide tunnelling (absent from the SKY130 cards: `igcmod = igbmod = 0`); junction reverse current ∝ diffusion area and perimeter (`js`, `jsws`, `jswgs` in the cards; needs layout AD/AS/PD/PS); GIDL (`agidl`, `bgidl`). The subthreshold expression is a qualitative guide only. All numbers in this project come from the compact models (SPICE) or Liberty tables.

**Temperature dependence.** Two points $(T_1,P_1)$, $(T_2,P_2)$ define a log-linear interpolation $P(T)=P_1\exp[(T-T_1)\ln(P_2/P_1)/(T_2-T_1)]$, equivalent to $P \propto e^{T/T_c}$ with characteristic temperature $T_c = (T_2-T_1)/\ln(P_2/P_1)$ (`ugcal.thermal.leakage_vs_T_from_points`). For SKY130 inv_1 between 25 and 100 °C: Liberty gives $P_2/P_1 = 217$, so $T_c = 14.0$ K; the tt model card gives 33.6 (results/spice/leakage_study.csv), so $T_c = 21.3$ K. The two sources disagree; see D4 §5.

**Short-circuit.** While the input ramps through $V_{tn} < V_\text{in} < V_{DD}-|V_{tp}|$, both networks conduct. The Veendrick (1984) estimate for an unloaded symmetric inverter, as commonly quoted, is $P_\text{sc} = \frac{\beta}{12}(V_{DD}-2V_t)^3\frac{\tau}{T}$. This project did not re-derive or verify it against the paper (`ugcal.switching.short_circuit_power_veendrick` is flagged accordingly). It is **not** added to Liberty-based power: Liberty `internal_power` already contains short-circuit energy, visible as the growth of the table entries with input slew (inv_1: +4 fJ from 0.01 to 1.5 ns at the smallest load; D4).

## 4. Delay

**RC model.** A gate with effective switch resistance $R_\text{eff}$ driving $C_L$: $t_{pd} \approx \ln 2\, R_\text{eff}C_L + t_\text{int}$. $R_\text{eff}$ is not a device constant: it depends on the input slew and on how the output swing samples the I–V curve.

**Saturation-current estimate.** $t_{pd} \approx C_L V_{DD}/(2 I_\text{on})$ (charge $C_LV_{DD}/2$ to reach 50 %, at roughly constant current). The "intrinsic" metric $CV/I$ with $C=C_{gg}$ is listed in D4 (SKY130 nfet 5.4 ps, pfet_hvt 18 ps at W = 1 µm, tt, 25 °C). It is a device figure of merit, not a gate delay.

**Alpha-power law** (Sakurai & Newton 1990): $I_\text{D,sat}\propto (V_{GS}-V_{th})^\alpha$ with $1\le\alpha\le2$, giving $t_{pd}\propto C_LV_{DD}/(V_{DD}-V_{th})^\alpha$. `ugcal.switching.fit_alpha_power` fits $(V_{th},\alpha,k)$ to the SPICE FO4 sweep (D4 §4). It is used only to interpolate between simulated supplies, never to extrapolate outside them.

**Table-based (NLDM) delay.** Liberty gives $t_{pd}(s_\text{in},C_L)$ and output slew $s_\text{out}(s_\text{in},C_L)$ on 7×7 grids. Lookups interpolate bilinearly and extrapolate linearly (as OpenSTA does). A path delay is the sum of arc delays with slews propagated arc to arc.

**Synchronous timing.** For a register-to-register path, $T_\text{clk} \ge t_\text{clk→Q} + t_\text{logic,max} + t_\text{setup} + t_\text{skew} + t_\text{jitter/uncertainty}$, and $t_\text{clk→Q}+t_\text{logic,min} \ge t_\text{hold} + t_\text{skew}$. Maximum frequency is $f_\text{max} = 1/T_{\text{clk},\min}$. **Throughput** of a pipeline with initiation interval $II$ (cycles between new operations) is $f_\text{clk}/II$. **Latency** is (number of stages) × $T_\text{clk}$. An iterative (serial) multiplier with $k$ cycles per product has throughput $f_\text{clk}/k$.

## 5. Energy per operation and derived metrics

For a block processing $N_\text{op}$ operations in a window $T_w$ (integer number of operations, excluding reset/warm-up):

$$E_\text{op} = \frac{1}{N_\text{op}}\int_{T_w} P(t)\,dt = \frac{\overline{P}}{\text{throughput}},\qquad \overline P = \overline P_\text{dyn}+\overline P_\text{leak}.$$

Dynamic energy per operation is independent of clock frequency at fixed activity per operation. Leakage energy per operation is $\overline P_\text{leak}/\text{throughput}$ and grows as throughput falls. That is the origin of the minimum-energy point (§8). Derived metrics (`ugcal.mac.mac_metrics`): MAC/s/W $=1/E_\text{MAC}$; TOPS/W $=2/E_\text{MAC}[\text{pJ}]$ with the convention 1 MAC = 2 ops; EDP $=E_\text{op}\cdot t_\text{op}$; energy per op at a power budget $P_\text{max}$: throughput $\le (P_\text{max}-P_\text{leak})/E_\text{dyn,op}$.

## 6. From transistor models and libraries to cell energy

### 6.1 Gate capacitance from the model card (first order)

$C_\text{ox} = \varepsilon_0\varepsilon_{r,ox}/t_{ox,e}$: SKY130 nfet_01v8 8.32 fF/µm², pfet_01v8_hvt 8.16 fF/µm² (class E from class C inputs). Gate capacitance in inversion is $\approx C_\text{ox}WL_\text{eff} + 2W(C_{gso}+C_f)$ (overlap plus fringe). For the inv_1 devices (0.65 and 1.0 µm × 0.15 µm) the intrinsic part is 0.81 + 1.22 fF and the overlap part is 2·0.65·0.245 + 2·1.0·0.059 fF ≈ 0.44 fF. That gives ≈2.5 fF, against the Liberty pin capacitance of 2.30 fF and SPICE effective input capacitance of 2.40 fF (extracted cell). This is a plausibility check. Use the SPICE or Liberty value.

### 6.2 Liberty internal power, sign convention (resolved by simulation)

With `switching_power_split_model : "true"` the SKY130 tables satisfy, per output edge,

$$E_\text{table}(\text{edge}) = E_\text{supply}(\text{edge}) - \tfrac12 C_L V_{DD}^2 .$$

So `rise_power` ≈ +½C_LV² + (short-circuit and internal), and `fall_power` ≈ −½C_LV² + (short-circuit and internal). OpenSTA averages rise and fall and adds ½C_LV² per transition, which reproduces the average supply energy per transition. This was established in this project by SPICE with the layout-extracted inv_1 (class F). Over the 16 grid points, per-edge agreement is 0.01–1.3 fJ for loads up to 25 fF and within 1.7 % at the largest load (181 fF). The Liberty User Guide chapter that defines the attribute was not accessible, so the definition itself remains unverified (D13).

### 6.3 Which transistor-level netlist reproduces the library

| Cell view used in SPICE | inv_1 energy/transition vs Liberty (16 points) | rise delay vs Liberty | fall delay vs Liberty |
|---|---|---|---|
| Schematic netlist from the library (W, L only) | −39.4 % … +0.3 % | −21.3 % … +34.4 % | −66 % … −13 % for slew ≤ 0.28 ns; sign reversal at 1.5 ns |
| Layout-extracted (Magic, AD/AS/PD/PS + coupling C) | −18.2 % … +5.1 % | +10.7 % … +58.6 % | −31 % … −11 % for slew ≤ 0.28 ns |
| Extracted + LOD (sa, sb from AS/W, AD/W) | **−1.6 % … +5.6 %** | **−1.4 % … +12.1 %** (−1.4 … +7.0 % for slew ≤ 0.28 ns) | −10.1 % … −6.2 % for slew ≤ 0.28 ns; −50 % at 1.5 ns |

(results/spice/calibration_inv_1_tt_025C_1v80*.csv; tt, 25 °C, 1.8 V.) **Interpretation:** the foundry tables are consistent with layout-extracted netlists that include STI-stress (LOD) effects. The remaining NMOS fall-delay difference (6–10 % faster than Liberty for input slews up to 0.28 ns) is consistent with an un-extracted layout effect that weakens the NMOS (well-proximity is one candidate) or with a model revision after characterisation. Neither can be decided from public data.

## 7. Multiplier structure and delay (structural formulas)

For $n\times n$ unsigned AND-array partial products ($n^2$ bits):

* **Dadda reduction** uses $n^2-4n+3$ full adders and $n-1$ half adders and needs $s$ stages, where $s$ is the smallest index with $d_s \ge n$ in $d_1=2$, $d_{j+1}=\lfloor 1.5\,d_j\rfloor$ (2, 3, 4, 6, 9, 13, 19, …). For 8×8 that is 35 FA, 7 HA, 4 stages; for 16×16, 195 FA, 15 HA, 6 stages. Reproduced by `ugcal.arith.multipliers.reduce_dadda` (8×8: 35 FA + 7 HA in the 'red' group; exhaustively verified).
* **Wallace reduction** (FA on every complete triple, HA on a remaining pair) has the same number of stages and more counters: 36 FA + 25 HA at 8×8 and 196 FA + 78 HA at 16×16 in this implementation, against 35 + 7 and 195 + 15 for Dadda (D7).
* **Array/Braun** with a ripple final adder: $n^2$ AND, $n(n-2)$ FA and $n$ HA in total. Critical path for the ripple-row array is $[(n-1)+(n-2)]\,t_\text{carry} + (n-1)\,t_\text{sum} + t_\text{and}$ (Linköping TSTE86 lesson notes, via the input research file). For the carry-save Braun array it is $\approx (n-1)t_{FA} + (n-1)t_\text{carry,CPA}$.
* **Prefix final adders** on $m$ bits: Kogge–Stone has $\log_2 m$ levels and $m\log_2m - m + 1$ combine nodes; Brent–Kung has about $2\log_2 m$ levels and $2m - \log_2 m - 2$ nodes; Sklansky has $\log_2 m$ levels with fan-out up to $m/2$ [koggestone1973; brentkung1982].

Gate counts and logic depth are **not** proxies for energy or delay in a real library. The SKY130 `fa_1` has an A→SUM delay of ≈0.4–0.55 ns, while a xor2/maj3 pair is faster. Prefix adders spend more energy on glitches than ripple adders (D7, D8).

## 8. Minimum-energy operating point (model)

With dynamic energy per operation $E_\text{dyn}(V) = \alpha_\text{eff} C_\text{tot} V^2$, leakage power $P_\text{leak}(V)$ and cycle time $T(V) = L_d\,t_\text{FO4}(V)$ for a logic depth of $L_d$ FO4,

$$E_\text{op}(V) = \alpha_\text{eff}C_\text{tot}V^2 + P_\text{leak}(V)\,L_d\,t_\text{FO4}(V).$$

The first term falls with $V$ and the second rises steeply below threshold as $t_\text{FO4}$ grows exponentially. $E_\text{op}$ has a minimum $V_\text{opt}$ (Calhoun, Wang & Chandrakasan 2005). `ugcal` evaluates it with $t_\text{FO4}(V)$, energy per transition and leakage per inverter taken from the SPICE sweep (results/spice/vdd_sweep_*.csv). The result is a **model-derived (class E) technology envelope**, valid only where the SPICE models are valid (0–1.95 V); the cells are not characterised by the foundry below 1.28 V.

## 9. Heat flow

* **Steady state, single path:** $T_j = T_\text{ref} + P\,R_\text{th}$, with $R_\text{th}$ defined for the same boundary conditions as $T_\text{ref}$ (JESD51). Series paths add: $R_\text{JA} = R_\text{JC}+R_\text{CS}+R_\text{SA}$.
* **1-D slab:** $R = t/(kA)$.
* **Spreading from a disk of radius $a$ on a half-space** (thermal conductivity $k$). The surface Green's function is $T = P/(2\pi k r)$. For **uniform flux** $q=P/\pi a^2$: centre temperature $T_c = qa/k$, giving $R_\text{max} = 1/(\pi k a)$. Mean source temperature: $T_m = \frac{q}{2\pi k}\frac{1}{\pi a^2}\iint \frac{dA\,dA'}{|r-r'|} = \frac{q}{2\pi k}\cdot\frac{16 a}{3}$, giving $R_\text{mean} = 8/(3\pi^2ka) = 0.270/(ka)$. Both are verified by numerical quadrature in `tests/test_core.py::test_uniform_flux_disk_spreading_by_quadrature`. **Isothermal disk:** by the electrostatic analogy, an isolated conducting disk has capacitance $8\varepsilon a$ in full space, so a half-space conductance is $4ka$ and $R_\text{iso} = 1/(4ka)$. This is the classical Weber result, quoted here, not re-derived. Ordering: $R_\text{iso} < R_\text{mean} < R_\text{max}$.
* **Transient:** $C_\text{th}\,dT/dt = P(t) - (T-T_\text{amb})/R_\text{th}$ for a single node. Step response $T = T_\text{amb} + PR(1-e^{-t/RC})$. Real packages need several poles: a Foster network $Z(t) = \sum_i R_i(1-e^{-t/\tau_i})$ fitted to a measured or simulated step response, or a physical Cauer/RC grid (HotSpot-style) solved by implicit Euler (`ugcal.thermal.rc_network_transient`).
* **Diffusion time:** $\tau \sim L^2/\alpha$, $\alpha=k/(\rho c_p)$. For silicon at room temperature ($k\approx148$ W/m·K, $\rho = 2329$ kg/m³, $c_p\approx 705$ J/kg·K; bulk values, class B, Glassbrenner & Slack 1964 for $k$), $\alpha\approx 9\times10^{-5}$ m²/s: $\tau\approx 0.11$ ms through 100 µm and 2.8 ms through 500 µm **[derived]**. A single MAC (ns) cannot heat the die. Temperature follows power averaged over ≳ 0.1–1 ms on the die and seconds to minutes at the heat sink.

## 10. Electro-thermal coupling

Steady state requires $T = T_a + R_\text{th}[P_\text{dyn} + P_\text{leak}(T)]$. Define $g(T) = T_a + R_\text{th}P(T) - T$. A solution is stable if the loop gain $R_\text{th}\,dP_\text{leak}/dT < 1$ there. **Thermal runaway** occurs when no solution exists below the temperature limit. For an exponential leakage $P_\text{leak} = P_0e^{(T-T_0)/T_c}$, a stable solution exists only if $R_\text{th}P_\text{leak}(T^*) < T_c$ at the solution, the condition used in D9. `ugcal.thermal.ElectroThermal.solve` scans $g(T)$, finds the lowest root by bisection and reports the loop gain. It is tested against the analytic linear case and a runaway case.

## 11. Reliability models (form only; parameters unavailable for SKY130)

* Electromigration (Black 1969): $\text{MTTF} = A\,J^{-n}\exp(E_a/k_BT)$. $A$, $n$ and $E_a$ are process-specific (class I for SKY130: the docs refer to "Electrical DR" guidelines that are not public).
* Arrhenius acceleration between temperatures: $AF = \exp[\frac{E_a}{k_B}(\frac1{T_1}-\frac1{T_2})]$. For example, $E_a = 0.7$ eV gives AF = 2.5 between 85 °C and 100 °C **[derived]**. That 0.7 eV is a generic qualification default (AEC-Q100, per the input research file), not a SKY130 value.
* TDDB, BTI, HCI: no public SKY130 models (class I). Their effect on timing must be handled as a guard-band once data exist.
