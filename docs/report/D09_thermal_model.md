# D9 — Heat: from electrical power to junction temperature, and the thermal envelope

## 1. When does electrical power equal dissipated heat?

Energy balance of a logic block over a window $[t_0,t_1]$ (D3 §1.1):
$\int P_\text{el}\,dt = \Delta U + Q + W_\text{out}$. The supply power of the block equals the heat it releases, *at the same place and time*, only under these conditions:

| Condition | Holds for a CMOS MAC? | Effect if violated |
|---|---|---|
| No net change of stored energy ($\Delta U = 0$) | Over many cycles yes. Within a cycle no: the supply charges nodes ($+\tfrac12CV^2$ stored) and the heat of discharge appears on a later edge | Instantaneous supply power ≠ instantaneous heat. Irrelevant for temperature, which responds over ≳ µs (§4) |
| No energy leaves through outputs | Only if the loads are inside the block's accounting boundary | Energy delivered to off-block loads is dissipated *there* (driver plus load capacitance discharge elsewhere) |
| No radiation or mechanical work | yes (radiated power from on-chip wires at these frequencies is negligible; no moving parts) | — |
| Dissipation location | heat appears in the transistors that conduct (pull-up on rising edges, pull-down on falling edges) and in resistive wires | Local hot spots follow the activity map, not the supply pins |

So **heat = electrical power averaged over the thermal time constant of interest, distributed where the current flows**. The "maximum heat" of a block is its maximum average electrical power at the worst corner and activity. There is no separate heat number for a transistor. A transistor's dissipation depends on its activity, the capacitance it switches, its supply, its leakage state and its temperature, so per-device heat can only be stated for a defined circuit and workload (D8).

## 2. Equations and their assumptions (derivations in D6 §9–10)

| Expression | Use | Assumptions |
|---|---|---|
| $P = VI$ | supply power | DC or averaged over a period |
| $P = I^2R$, $P = V^2/R$ | Joule heating in a resistor (wires, power grid) | linear R, DC or RMS quantities |
| $T_j = T_\text{ref} + P\,R_\text{th}$ | steady-state junction temperature | single path; $R_\text{th}$ defined for the same boundary conditions |
| $C_\text{th}\,dT/dt = P(t) - (T-T_a)/R_\text{th}$ | single-pole transient | lumped die; one time constant |
| Foster $Z(t)=\sum R_i(1-e^{-t/\tau_i})$ | fitted package transient | linear, time-invariant heat path |
| Cauer/RC grid (HotSpot-style) | spatial on-die temperature | discretised conduction; boundary conditions explicit |
| $R_\text{spread}$ = 1/(4ka), 8/(3π²ka), 1/(πka) | hot spot over a block of radius a | half-space, constant k |
| $T = T_a + R_\text{th}[P_\text{dyn}+P_\text{leak}(T)]$ | electro-thermal fixed point | steady state; leakage depends on T only through the junction temperature |

Package metrics (JEDEC JESD51 family, via the input research file and vendor notes; not re-verified here). $\theta_{JA}$ is a package-comparison metric measured on a standard board in still air. For an actual system use $T_j = T_C + \Psi_{JT}P$ with a measured case temperature, or $T_j = T_A + P(\theta_{JC}+\theta_{CS}+\theta_{SA})$ with a heat sink. **No package has been chosen for a SKY130 die in this project, so $\theta$ is a design specification (class S) and is swept** instead of being taken from an unrelated product's datasheet.

## 3. What limits temperature for SKY130 logic

| Constraint | Value for SKY130 HD | Kind |
|---|---|---|
| Fundamental (thermodynamic) | none at these temperatures; heat removal is an engineering problem | — |
| Characterisation limit of the cell library | 100 °C (hottest Liberty corner); −40 °C coldest | model-validity limit (C) |
| Device self-heating | not modelled (BSIM4 cards have no thermal network) | I |
| Interconnect electromigration | rules exist but are not public ("Electrical DR") | I |
| Die-level spreading | $R \approx 0.27/(k_{Si}a)$ for a uniform-flux block of radius $a$ | E |
| Package/cooling | $\theta_{JA}$, $\theta_{JC}$ of the chosen package; heat-sink resistance | S (design choice) / B (datasheet) |
| Reliability (ageing, EM lifetime vs T) | Arrhenius/Black acceleration; parameters not public | I |

The "maximum junction temperature" used below is 100 °C. It is **the highest temperature at which the foundry characterised timing and leakage**, not a reliability limit and not a published absolute maximum.

## 4. Time scales

With bulk-silicon properties ($k\approx148$ W/m·K, $\rho c_p\approx1.64$ MJ/m³·K; class B), the diffusion time $L^2/\alpha$ is ≈0.11 ms across 100 µm and ≈2.8 ms across 500 µm (D6 §9). One MAC lasts 3–10 ns and dissipates ≈5 pJ. Deposited adiabatically in its own PE volume (≈70 × 70 µm² × 10 µm of silicon), it would raise that volume's temperature by only ≈0.06 mK **[derived]**. The die temperature therefore follows the power averaged over ≳ 0.1 ms. Peak instantaneous power (all PEs switching on one clock edge) matters for supply droop and IR drop, not for temperature.

## 5. Per-PE leakage across corners (Liberty, class C) and dynamic power

<!-- BEGIN:pe_leak -->
| PE variant | cells | Liberty leakage tt 25 °C (nW) | tt 100 °C (nW) | ss 100 °C (nW) | ff 100 °C (nW) | dynamic power at f_max(ss) (µW) |
|---|---|---|---|---|---|---|
| csa_acc_bw_kogge_stone | 433 | 2.24 | 677 | 3.03e+03 | 5.68e+03 | 811.3 |
| separate_bw_ripple_accripple | 206 | 1.13 | 351 | 1.66e+03 | 3.08e+03 | 233.7 |
<!-- END:pe_leak -->

Liberty leakage rises ≈300× from 25 °C to 100 °C (tt). At 100 °C the ff corner leaks another 8×, and the ss corner, unusually, 4.5× more than tt (D4 §5). Even the most pessimistic value (ff, 100 °C: 5.7 µW per carry-save PE) is < 1 % of the PE's dynamic power at its sign-off frequency (811 µW).

## 6. Thermal envelope of a MAC array (class E, swept over θ_JA)

Assumptions: all PEs active at their sign-off frequency $f_\text{max}(ss, 100\,°C)$; E/MAC from D8 (uniform operands, tt energy, conservative because ss/1.6 V would dissipate ≈(1.6/1.8)² = 0.79× of it); leakage at the pessimistic Liberty ff/100 °C value; 70 % placement utilisation; $T_{j,\max}$ = 100 °C; no clock tree, memory or I/O power (D8 §5).

<!-- BEGIN:thermal -->
| PE variant | θ_JA (K/W) | T_amb (°C) | P_max at T_j = 100 °C (W) | PEs at f_max(ss,100 °C) | TOPS | PE area (mm²) | power density (W/cm²) | electro-thermal loop gain |
|---|---|---|---|---|---|---|---|---|
| csa_acc_bw_kogge_stone | 10 | 25 | 7.5 | 9181 | 2.66 | 62.4 | 12 | 0.0545 |
| csa_acc_bw_kogge_stone | 10 | 70 | 3 | 3672 | 1.06 | 25 | 12 | 0.0218 |
| csa_acc_bw_kogge_stone | 20 | 25 | 3.75 | 4590 | 1.33 | 31.2 | 12 | 0.0545 |
| csa_acc_bw_kogge_stone | 20 | 70 | 1.5 | 1836 | 0.532 | 12.5 | 12 | 0.0218 |
| csa_acc_bw_kogge_stone | 30 | 25 | 2.5 | 3060 | 0.886 | 20.8 | 12 | 0.0545 |
| csa_acc_bw_kogge_stone | 30 | 70 | 1 | 1224 | 0.354 | 8.33 | 12 | 0.0218 |
| csa_acc_bw_kogge_stone | 40 | 25 | 1.88 | 2295 | 0.665 | 15.6 | 12 | 0.0545 |
| csa_acc_bw_kogge_stone | 40 | 70 | 0.75 | 918.1 | 0.266 | 6.24 | 12 | 0.0218 |
| csa_acc_bw_kogge_stone | 60 | 25 | 1.25 | 1530 | 0.443 | 10.4 | 12 | 0.0545 |
| csa_acc_bw_kogge_stone | 60 | 70 | 0.5 | 612 | 0.177 | 4.16 | 12 | 0.0218 |
| separate_bw_ripple_accripple | 10 | 25 | 7.5 | 3.168e+04 | 2.98 | 126 | 5.95 | 0.103 |
| separate_bw_ripple_accripple | 10 | 70 | 3 | 1.267e+04 | 1.19 | 50.5 | 5.95 | 0.0412 |
| separate_bw_ripple_accripple | 20 | 25 | 3.75 | 1.584e+04 | 1.49 | 63.1 | 5.95 | 0.103 |
| separate_bw_ripple_accripple | 20 | 70 | 1.5 | 6335 | 0.596 | 25.2 | 5.95 | 0.0412 |
| separate_bw_ripple_accripple | 30 | 25 | 2.5 | 1.056e+04 | 0.993 | 42.1 | 5.95 | 0.103 |
| separate_bw_ripple_accripple | 30 | 70 | 1 | 4224 | 0.397 | 16.8 | 5.95 | 0.0412 |
| separate_bw_ripple_accripple | 40 | 25 | 1.88 | 7919 | 0.745 | 31.5 | 5.95 | 0.103 |
| separate_bw_ripple_accripple | 40 | 70 | 0.75 | 3168 | 0.298 | 12.6 | 5.95 | 0.0412 |
| separate_bw_ripple_accripple | 60 | 25 | 1.25 | 5280 | 0.497 | 21 | 5.95 | 0.103 |
| separate_bw_ripple_accripple | 60 | 70 | 0.5 | 2112 | 0.199 | 8.41 | 5.95 | 0.0412 |
<!-- END:thermal -->

**Reading the table.**
* The power budget is $P_\text{max} = (T_{j,\max} - T_a)/\theta_{JA}$: 7.5 W at θ = 10 K/W and 25 °C ambient, 0.5 W at 60 K/W and 70 °C.
* **The sustainable throughput is set by the package, not by the transistors**: 0.18–2.7 TOPS for the carry-save array over the swept range. The die area to host that many PEs is 4–62 mm².
* The **power density of a fully used PE array** is 12 W/cm² (carry-save, at its ss sign-off clock) or 6 W/cm² (ripple variant). That is well below the ≈40–50 W/cm² that air-cooled heat sinks remove at a 45–50 °C budget (IEEE HIR 2023 via the input research file, not re-verified). In SKY130 an array is package- or budget-limited before it is power-density-limited.
* **Electro-thermal loop gain** $R_\text{th}\,dP_\text{leak}/dT$ is 0.02–0.10. Leakage–temperature feedback is weak and thermal runaway is impossible below 100 °C for these arrays, even with the pessimistic leakage. It would matter for mostly idle arrays with high leakage share, or at higher temperatures.

## 7. Hot spots inside the die

A single active block of radius $a$ on a thick substrate adds $\Delta T \approx P\cdot 0.27/(k_{Si}a)$ on average (uniform flux). For one PE ($a\approx 40$ µm, $P$ = 0.8 mW at its ss clock): 0.8 mW × 0.27/(148 × 40 µm) ≈ 0.04 K. For a 1 mm² array at 12 W/cm² ($a$ ≈ 0.56 mm, 120 mW): ≈0.4 K above the substrate average **[derived]**. Local gradients are small compared with the die-to-ambient rise through the package. A floorplan-level model (HotSpot, 3D-ICE) becomes necessary when the package is fixed and blocks of very different power density share a die.

## 8. Maximum sustainable throughput: the procedure

1. Fix $T_{j,\max}$ (here 100 °C, the characterisation limit) and the worst ambient $T_a$.
2. Obtain $\theta$ for the actual package and board, measured or from a datasheet under stated JESD51 conditions. Until then sweep it as above.
3. $P_\text{max} = (T_{j,\max}-T_a)/\theta$.
4. Evaluate leakage at $T_{j,\max}$ at the worst corner (here Liberty ff 100 °C, an upper bound) and solve the electro-thermal fixed point (`ugcal.thermal.ElectroThermal`); verify loop gain < 1.
5. Sustainable MAC rate = $(P_\text{max} - P_\text{leak}(T_{j,\max}) - P_\text{other}) / E_\text{MAC}$, capped by $N_\text{PE}\cdot f_\text{max}(T_{j,\max}$, slow corner$)$.
6. Re-check timing at $T_{j,\max}$, because the sign-off frequency itself depends on the temperature reached.
