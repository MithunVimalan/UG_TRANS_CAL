# D3 — Fundamental limit catalogue

**Scope.** Every bound below is stated with its derivation, its assumptions, the systems to which it applies, its evidence class (A–I, see [D12](D12_evidence_audit.md)) and how far it lies from the SKY130 circuits measured in this project. Numbers come from `tools/build_tables.py`, which calls the same `ugcal.fundamental` and `ugcal.infotheory` functions the framework uses (`results/tables/*.csv`).

**Bottom line.** For a SKY130 int8 multiply-accumulate, the strongest *fundamental* (technology-independent) lower bound on energy is set by logical irreversibility. Keeping only the result erases 16 bits per MAC, or about 3 bits per multiplication alone, which is 4.6×10⁻²⁰ J or 9.0×10⁻²¹ J at 300 K. Every implementation in this project dissipates 10⁸ to 10⁹ times more. The bounds that actually constrain a SKY130 design are not thermodynamic. They come from device electrostatics, the cell library, the circuit's switching activity and the package (D4, D7–D9). The physics here explains *why* supply voltage and node capacitance cannot shrink without limit. It does not provide a design target.

---

## 1. Thermodynamics of computation

### 1.1 First and second law for a computing block

Treat the logic block, its supply and its surroundings (a heat bath at temperature $T$) as the system.

* **First law (energy conservation).** Over any interval $[t_0,t_1]$,
  $$\int_{t_0}^{t_1} P_\text{in}(t)\,dt = \Delta U_\text{block} + Q_\text{out} + W_\text{out},$$
  where $P_\text{in}$ is the electrical power delivered at the supply and signal ports, $\Delta U_\text{block}$ is the change of stored energy (charge on node capacitances, $\tfrac12 CV^2$; magnetic energy is negligible at these sizes), $Q_\text{out}$ is the heat given to the bath and $W_\text{out}$ is the work delivered to other systems (energy carried out on output wires, radiation). For a block run over a window that starts and ends in statistically equivalent states and whose outputs drive on-chip loads included in the block, $\overline{\Delta U}=0$ and $W_\text{out}\approx 0$. The average electrical input power then equals the average heat output. See D9 §1 for the exceptions.
* **Second law.** The total entropy of block plus bath cannot decrease on average: $\Delta S_\text{block} + Q_\text{out}/T \ge 0$. Entropy produced inside the device (Joule heating in channel resistance, irreversible charge transfer) shows up as heat.

### 1.2 Landauer's bound (derivation)

Consider a one-bit memory, a physical system whose microstates split into two macrostates "0" and "1". Before erasure the bit is unknown (probabilities $\tfrac12,\tfrac12$). Erasure (reset to "0") is a logically irreversible map: two input states, one output state. If the memory's microstates within each macrostate are in local equilibrium and the macrostates have equal free energy, the reset lowers the memory's entropy by $\Delta S_\text{mem} = -k_B\ln 2$. The second law requires the bath to receive at least the compensating entropy, so the heat released on average is

$$Q \;\ge\; -T\,\Delta S_\text{mem} \;=\; k_B T \ln 2 .$$

More generally, a logically irreversible operation whose input $X$ and output $Y=f(X)$ are random variables must release on average $Q \ge k_B T \ln 2\,[H(X) - H(Y)]$ (Shannon entropies in bits), in the limit of quasi-static, reversible driving of the physical degrees of freedom [landauer1961; bennett1973].

| Quantity | Expression | 300 K | 25 °C | 100 °C | Class |
|---|---|---|---|---|---|
| Thermal energy | $k_BT$ | 4.142×10⁻²¹ J | 4.116×10⁻²¹ J | 5.152×10⁻²¹ J | A (k_B exact) × S (T chosen) |
| Landauer, one bit | $k_BT\ln2$ | **2.871×10⁻²¹ J** | 2.853×10⁻²¹ J | 3.571×10⁻²¹ J | D |

**Assumptions** (each one matters):
1. The erased information is measured as Shannon entropy of the *logical* state; correlations with other retained information reduce it (erasing a copy of a bit you keep elsewhere costs nothing in principle).
2. A single heat bath at temperature $T$; Markovian (memoryless) bath.
3. Quasi-static (infinitely slow) protocol. The bound is reached only as the protocol duration $\tau \to \infty$.
4. It bounds the *mean*. Individual realisations can dissipate less (fluctuation theorems), as Jun et al. 2014 observed.

**Experimental status (class B).** Single-particle experiments in double-well potentials approach $k_BT\ln 2$ as cycle time grows: colloidal particle in a modulated optical double well [berut2012]; feedback trap [jun2014]. The source catalogue records which details were checked. The full texts were not readable from this environment, and the "0.71 ± 0.03 kT" figure quoted in the input research file could not be re-verified.

### 1.3 Reversible computation (Bennett)

A computation is **logically reversible** when its map from input to output is injective, so the input can be reconstructed. Bennett showed that any computation can be embedded in a reversible one: compute, copy the result, then uncompute. This costs roughly twice the steps and extra temporary storage, and erases nothing, so it has no Landauer floor [bennett1973]. For a multiplier, that means keeping $A$ and $B$, or (garbage) bits from which they can be recovered, alongside the product. The physical counterpart is adiabatic (ramped-supply) or charge-recovery logic. It trades dissipation for time: dissipation per transition scales as $\sim(RC/T_\text{ramp})\,CV^2$, which tends to zero only as $T_\text{ramp}\to\infty$. Static CMOS as used in every standard-cell library, including SKY130 HD, is **not** reversible at any level.

### 1.4 Finite time and reliability

* **Finite time.** Erasure completed in time $\tau$ costs on average $k_BT\ln2 + \mathcal{O}(1/\tau)$. The excess depends on the protocol and on the variance of the bit's microscopic distribution; Proesmans et al. give optimal finite-time bounds [proesmans2020], and the experiments in §1.2 show the $1/\tau$ approach. This project uses no specific numeric finite-time bound, because the prefactor depends on the physical system's relaxation time, which is not defined for a CMOS node.
* **Reliability of the erasure itself.** Resetting a bit only to residual error probability $\varepsilon$ lowers the entropy decrease to $\ln 2 - h(\varepsilon)$ nats, where $h(\varepsilon)=-\varepsilon\ln\varepsilon-(1-\varepsilon)\ln(1-\varepsilon)$. So $Q_\text{min} = k_BT[\ln2 - h(\varepsilon)]$. For $\varepsilon = 10^{-3}, 10^{-6}, 10^{-15}$ this is 0.9886, 0.999979, 1 − 5×10⁻¹⁴ times $k_BT\ln2$ **[derived]**. *Reliability does not make Landauer's bound larger.* The energy cost of reliability comes from somewhere else: keeping the bit stable against thermal fluctuations (barriers, §2.3–2.4) and switching it quickly (finite time).
* **Throughput.** At a required throughput of $N$ operations per second, a block that erases $b$ bits per operation dissipates at least $N b\,k_BT\ln 2$ watts in the quasi-static limit, and more at finite speed. At 10¹² int8 MACs per second with 16 bits erased each, that is 1×10¹² × 16 × 2.871×10⁻²¹ J = 46 nW. Any CMOS implementation at the energies found in D8 would need 5–11 W for the same throughput **[derived]**.

### 1.5 Information content of multiplication and MAC (exact)

`ugcal.infotheory.multiplication_entropy_loss` enumerates every operand pair (independent, uniformly distributed operands):

| n | operands | $H(A\cdot B)$ (bits) | erased $H(A,B)-H(AB)$ (bits) | distinct products | Landauer floor at 300 K |
|---|---|---|---|---|---|
| 4 | unsigned | 6.088 | 1.912 | 90 | 5.49×10⁻²¹ J |
| 4 | signed | 5.583 | 2.417 | 60 | 6.94×10⁻²¹ J |
| 8 | unsigned | 13.705 | **2.295** | 17 578 | 6.59×10⁻²¹ J |
| 8 | signed | 12.856 | **3.144** | 9 390 | 9.03×10⁻²¹ J |
| 12 | unsigned | 21.380 | 2.620 | 3 902 357 | 7.52×10⁻²¹ J |
| 12 | signed | 20.458 | 3.542 | 2 009 954 | 1.02×10⁻²⁰ J |

For a MAC $ACC' = ACC + A\cdot B \pmod{2^W}$ with uniform $ACC$, the map $ACC\mapsto ACC'$ is a bijection for each fixed $(A,B)$. So $H(ACC')=W$, and discarding the operands erases exactly $2n$ bits: 16 bits for int8 (4.59×10⁻²⁰ J at 300 K) and 32 bits for int16 (9.19×10⁻²⁰ J). These are class D/E results (exact enumeration of a theoretical bound). They depend on the operand distribution: sparse or low-entropy data erase less.

**Gate-level irreversibility (a model, not a law).** Suppose instead that every gate's inputs are erased after evaluation, the conventional reading of irreversible logic. Then each gate erases $H(\text{inputs})-H(\text{outputs})$ under the actual signal statistics. Summed over the verified 8×8 netlists with exhaustive uniform inputs (`gate_level_erasure`), this gives 110.9 bits (ripple array), 117.0 (Dadda + ripple), 118.1 (Wallace + ripple), 192.3 (Dadda + Kogge–Stone) and 264.7 (radix-4 Booth + Dadda + Kogge–Stone) per multiplication. That is 3.2–7.6×10⁻¹⁹ J at 300 K **[derived]**. This number depends on the netlist. Static CMOS does not dissipate in proportion to it: CMOS dissipates $CV^2$ per charge cycle whether or not information is erased.

### 1.6 Answers to the questions in the brief (§4.1)

| # | Question | Answer |
|---|---|---|
| 1 | Does $k_BT\ln2$ apply to every transistor switching event? | No. It applies to *logically irreversible erasure of information*, accounted at whatever level information is actually discarded. A transistor turning on or off erases nothing by itself; a node being overwritten erases its previous value only if that value is not correlated with retained information. |
| 2 | Does it give the minimum energy of a CMOS inverter? | No. An inverter is logically reversible (a bijection). Its dissipation is $\tfrac12 C V^2$ per transition (D6 §1), set by the supply and the capacitance, ≈10⁶ kT at SKY130 node sizes. |
| 3 | Of a NAND gate? | Only if the inputs are discarded: a NAND with uniform independent inputs erases $2 - h_2(1/4) = 1.189$ bits, about 3.4×10⁻²¹ J at 300 K **[derived]**. A CMOS NAND dissipates its output and internal node $CV^2$ regardless. |
| 4 | Of a multiplication? | Output-only: 2.3 bits (unsigned 8×8) or 3.1 bits (signed 8×8), §1.5. Zero if computed reversibly. |
| 5 | Of a MAC? | $2n$ bits if the operands are discarded (16 bits for int8), zero if computed reversibly. |
| 6 | Conditions for logical reversibility? | The input→output map is injective at every step (or the computation keeps enough history to invert it), and erasure of temporary garbage is avoided by uncomputation [bennett1973]. |
| 7 | Effect of reliability and speed? | Reliability of the *final state* barely changes the bound (§1.4). Reliability *against fluctuations* needs barrier or signal energies of tens to hundreds of kT (§2). Finite speed adds dissipation that grows as the protocol time shrinks. |
| 8 | Constraints at a specified throughput? | Power ≥ throughput × energy per operation, for every bound in this table. In practice the binding throughput constraints are the circuit delay (D7) and the thermal budget (D9), not thermodynamics. |

---

## 2. Statistical mechanics and thermal noise

### 2.1 Carrier statistics

Electrons occupy states according to the Fermi–Dirac distribution $f(E)=1/(1+e^{(E-E_F)/k_BT})$. Where $E-E_F \gg k_BT$ (the tail above a barrier), $f \approx e^{-(E-E_F)/k_BT}$ (Boltzmann). The current over a barrier of height $\phi_B$, controlled by a gate through a body factor $n = 1 + C_\text{dep}/C_\text{ox} \ge 1$, is therefore $I \propto \exp[-q(\phi_B - V_{GS}/n)/k_BT]$. This assumes non-degenerate carriers in the source and a quasi-equilibrium injecting reservoir. It is a non-equilibrium device described by equilibrium statistics in the source, which is a standard approximation that holds in subthreshold.

### 2.2 Subthreshold swing limit

From §2.1, $SS \equiv dV_{GS}/d\log_{10}I = n\,(k_BT/q)\ln 10 \ge (k_BT/q)\ln10$:

| T | 300 K | 25 °C | 100 °C |
|---|---|---|---|
| $SS_\text{min}$ (n = 1) | **59.53 mV/dec** | 59.16 mV/dec | 74.04 mV/dec |

This is a hard limit for any thermionic-injection FET: planar bulk, FD-SOI, FinFET and nanosheet alike. It does not bind tunnel FETs or negative-capacitance FETs (other mechanisms). **SKY130 check (class F):** at W/L = 1/0.15 µm the simulated minimum SS is 90.1 mV/dec (nfet, tt, 25 °C), 112.8 mV/dec at 100 °C and 70.5 mV/dec at −40 °C (limit 46.3 mV/dec). That gives $n \approx 1.5$ ([D4](D4_transistor_parameters.md)). No result in this project goes below the limit, which is a basic consistency check of the simulation set-up.

### 2.3 Johnson–Nyquist noise and the kT/C limit

A resistor at temperature $T$ has open-circuit voltage-noise spectral density $S_V = 4k_BTR$ (one-sided). Integrated over the bandwidth of a node with capacitance $C$ driven through that resistance, the mean-square voltage is $\langle v^2\rangle = k_BT/C$, independent of $R$. This follows from equipartition for a linear capacitor in thermal equilibrium. In the off state, or in subthreshold, a transistor's channel noise has a shot-noise character, $S_I = 2qI$; for $V_{DS}\gg k_BT/q$ the device is not in equilibrium and the equipartition result is only an estimate [freitas2021].

**Snapshot error probability of a static node (model).** A logic node held at 0 V with decision threshold $V/2$ is read wrongly at one instant with probability $p = Q\big((V/2)/\sqrt{k_BT/C}\big) = Q\big(\sqrt{E_s/2k_BT}\big)$, where $E_s=\tfrac12 CV^2$ is the stored energy and $Q$ the Gaussian tail. Inverting gives the stored energy needed for a target $p$:

| p | $E_s = 2k_BT[Q^{-1}(p)]^2$ | $E_s/k_BT$ | barrier $E_b = k_BT\ln(1/p)$ | $E_b/k_BT$ |
|---|---|---|---|---|
| 10⁻³ | 7.91×10⁻²⁰ J | 19.1 | 2.86×10⁻²⁰ J | 6.9 |
| 10⁻⁶ | 1.87×10⁻¹⁹ J | 45.2 | 5.72×10⁻²⁰ J | 13.8 |
| 10⁻¹² | 4.10×10⁻¹⁹ J | 99.0 | 1.14×10⁻¹⁹ J | 27.6 |
| 10⁻¹⁵ | 5.22×10⁻¹⁹ J | 126.1 | 1.43×10⁻¹⁹ J | 34.5 |
| 10⁻¹⁸ | 6.35×10⁻¹⁹ J | 153.4 | 1.72×10⁻¹⁹ J | 41.4 |
| 10⁻²⁴ | 8.62×10⁻¹⁹ J | 208.0 | 2.29×10⁻¹⁹ J | 55.3 |

(300 K; `results/tables/error_probability_energy_300K.csv`.) Class E: model-derived from equipartition and Gaussian statistics. **Limits:** a CMOS gate regenerates its output (positive gain restores the level), samples are correlated, and non-equilibrium noise differs from kT/C. So this is an *engineering* scale, not a proven minimum. The often-quoted "40–100 kT reliability floor" falls inside the range of these two columns for p = 10⁻¹⁸…10⁻⁴³. No primary source fixing a single number was found (see [D13](D13_research_gaps.md)). **SKY130 comparison:** one transition of a small inverter output node of ≈4 fF (pin, junction and wiring capacitance) at 1.8 V dissipates ½·4 fF·(1.8 V)² ≈ 6.5 fJ in the load alone, about 1.6×10⁶ kT. Practical node energies are four orders above the noise scale.

### 2.4 Barrier retention

A bit stored behind a barrier $E_b$ flips by thermal activation with per-attempt probability $\sim e^{-E_b/k_BT}$ (Arrhenius/Kramers). The table above lists $E_b = k_BT\ln(1/p)$ per attempt. A retention budget must multiply by the attempt frequency (≈10¹²–10¹³ s⁻¹) times the lifetime, which adds roughly $\ln(10^{21})\approx 48$ kT for ten years [zhirnov2003]. In static CMOS the "barrier" is maintained actively by the supply. The relevant quantity is the noise margin, which shrinks as $V_{DD}$ approaches the limits in §2.5.

### 2.5 Minimum supply voltage of CMOS logic

| Bound | Expression | 300 K | 25 °C | 100 °C | Status |
|---|---|---|---|---|---|
| Ideal inverter, unity gain | $2\ln2\,k_BT/q$ | 35.84 mV | 35.62 mV | 44.58 mV | D, via secondary [meindl2000] |
| Swanson–Meindl functional limit | $\approx 8\,k_BT/q$ | 206.8 mV | 205.5 mV | 257.2 mV | D [swanson1972] |

These assume weak-inversion devices with ideal (or 1972-technology) slope factors. **SKY130 context (class F):** the HD cells use high-Vt PMOS (|V_th| ≈ 0.89 V at 7/0.15 µm, tt). The simulated FO4 delay is 84 ps at 1.8 V, 84 ns at 0.6 V and 71 µs at 0.3 V (25 °C, D4 §4). The inverter chain still switches at 0.3 V, about 1.5× the Swanson–Meindl figure, but at a speed no synchronous design would use. The practical minimum supply of this library is therefore set by speed, by variability (mismatch σ_Vth of 11–14 mV for the inv_1 devices, against a 85–90 mV/dec slope) and by the absence of foundry characterisation below 1.28 V, not by these bounds.

---

## 3. Electronic transport limits (technology-dependent, listed for completeness)

Physical laws: drift–diffusion current $J = q n\mu E + qD\nabla n$ with Einstein relation $D=\mu k_BT/q$ (non-degenerate). High-field velocity saturation ($v_\text{sat}\approx10^7$ cm/s in Si at 300 K is a material property; the SKY130 cards fit $vsat$ per bin, as a regression coefficient). Ballistic limit: when channel length approaches the carrier mean free path, current is limited by injection from the source, $I = W Q_\text{inv} v_\text{inj}(1-r)/(1+r)$ with backscattering coefficient $r$ [lundstrom1997]. These give upper bounds on drive current per width *for a given* inversion charge (∝ $C_\text{ox}(V_{GS}-V_{th})$) and injection velocity. They are technology parameters, not universal constants, and are not used numerically in this project. The SKY130 drive currents (502 µA/µm nfet, 148 µA/µm pfet_hvt at 1.8 V, tt, 25 °C; class F) come from the foundry compact models.

Gate-oxide tunnelling and source–drain tunnelling limit how far $t_{ox}$ and $L$ can scale. In SKY130's BSIM4 cards the gate-tunnelling mechanisms are switched off (`igcmod = igbmod = 0`), so gate leakage is **not modelled** (class I, D13).

---

## 4. Quantum limits

| Bound | Expression | Value | Applies to |
|---|---|---|---|
| Margolus–Levitin | $t_\perp \ge h/(4E)$, $E$ = mean energy above ground state | 1.66×10⁻¹⁹ s at 1 fJ; 1.66×10⁻¹⁶ s at 1 aJ | isolated quantum system evolving to an orthogonal state [margolus1998] |
| Mandelstam–Tamm | $t_\perp \ge h/(4\Delta E)$ | same scale | energy spread $\Delta E$ |

A 1 fJ SKY130 switching event lasting ~20 ps is about 10⁸ times slower than the Margolus–Levitin time for that energy. The bound is not relevant to dissipative CMOS, because the switching time there is set by $CV/I$, not by quantum dynamics. Quantum capacitance $C_Q = q^2 D(E_F)$ matters for 2D/1D channels and ultra-thin bodies. It is negligible next to $C_\text{ox}$ for 130 nm bulk silicon and is not used.

---

## 5. Summary catalogue

| Bound | Value (300 K) | Kind | Applies directly to a SKY130 MAC? | Ratio of SKY130 int8 MAC energy (D8) to bound |
|---|---|---|---|---|
| Landauer, output-only 8×8 signed multiply (3.14 bits) | 9.0×10⁻²¹ J | hard law for irreversible erasure | only as an absolute floor | ≈ 2–5×10⁸ (multiplier alone, 1.6–4.7 pJ) |
| Landauer, MAC with operands discarded (16 bits) | 4.6×10⁻²⁰ J | hard law | only as an absolute floor | ≈ 1–2×10⁸ (5–11 pJ) |
| Gate-level irreversible model, 8×8 (111–265 bits) | 3.2–7.6×10⁻¹⁹ J | model | no (CMOS dissipation is not erasure-driven) | ≈ 10⁶–10⁷ |
| kT/C snapshot reliability, p = 10⁻¹⁵, per transition | 5.2×10⁻¹⁹ J | model | per node, as a scale | per-transition ratio ≈ 10⁴ |
| Thermionic subthreshold swing | 59.5 mV/dec | hard law (thermionic FETs) | yes (simulation sanity check) | SKY130 SS ≈ 1.5× limit |
| Minimum CMOS supply | 36–207 mV | model-dependent | no (library minimum 1.28 V characterised) | ≈ 9–50× |
| Margolus–Levitin time at 1 fJ | 1.7×10⁻¹⁹ s | hard law (quantum) | no | ≈ 10⁸ |

The "ratio" column uses the gate-level results of D7/D8 (class E/F inputs) and is meant only to show orders of magnitude.
