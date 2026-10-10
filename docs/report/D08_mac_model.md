# D8 — The MAC: definition, energy accounting, throughput, array scaling

## 1. Definition (integer MAC; floating point is out of scope)

$$ACC[t+1] = \big(\overline{clr}\cdot ACC[t]\big) + A[t-1]\cdot B[t-1] \pmod{2^W}$$

| Item | Specification used here | Where enforced |
|---|---|---|
| Operands | A, B: 8-bit two's complement (signed) | `ugcal.arith.mac.build_mac(signed=True)` |
| Product | 16 bits, sign-extended into the accumulator width | partial products generated modulo $2^W$ (exact) |
| Accumulator | W = 22 bits = the exact minimum for K = 64 signed int8 products (`ugcal.mac.accumulator_width`). Proof: $\max|a b| = 2^{14}$, $64\cdot 2^{14} = 2^{20} \le 2^{21}-1$ | `tests/test_core.py::test_accumulator_width_bruteforce` (brute force for small n, K) |
| Overflow | cannot occur for ≤ 64 terms; otherwise wrap-around (modular). No saturation logic | by construction |
| Rounding | none (exact integer) | — |
| Clear | `clr` registered with the operands; gates the feedback with 22 AND2 cells | 'acc' group |
| Pipelining | operand registers (17 DFF incl. clr) → combinational multiply-add → accumulator register(s) | latency 2 cycles, initiation interval 1 |
| Operation count | 1 MAC = 1 multiplication + 1 addition = **2 ops** (TOPS/W = 2 / E_MAC[pJ]) | `ugcal.mac.mac_metrics` |
| Process, V, T | SKY130 HD, tt, 1.80 V, 25 °C for energy; ss, 1.60 V, 100 °C for sign-off f_max | Liberty corners |

All variants were verified cycle by cycle against a Python reference model (300 cycles with periodic clears, plus random tests in the suite).

**Variants (same arithmetic, different circuits):**
* `separate`: multiplier (tree + CPA) → 22-bit adder → accumulator register.
* `fused`: the 22 feedback bits enter the multiplier's reduction tree as one more row; a single 22-bit CPA per cycle.
* `csa_acc`: the accumulator is kept in carry-save form (2 × 22 register bits); the tree absorbs both rows, so no carry-propagate adder sits in the loop. A CPA converts the result once per K = 64 accumulations; its energy is charged per MAC as 1/64 of its simulated per-cycle energy.

Each was built with Booth radix-4 or Baugh–Wooley partial products and Kogge–Stone (or ripple) adders.

## 2. Energy accounting without double counting

Every cell instance belongs to exactly one functional group, assigned when the netlist is generated. Every net's switching energy is charged to the group of its driving cell, and the flip-flop clock pins to `clk`. The groups therefore sum to the total. Leakage is included per group (state-weighted). Input-port nets (driven from outside the MAC) are excluded.

| Group | Contents | Obtainable from |
|---|---|---|
| reg_op | 17 operand/clear flip-flops (internal + clock-pin + Q switching) | gate-level with Liberty (here); SPICE of the cell |
| enc | Booth recoders | gate-level |
| pp | partial-product AND/NAND or Booth selectors | gate-level |
| red | Dadda reduction tree | gate-level |
| cpa | multiplier final adder (`separate`) or the single adder (`fused`) | gate-level |
| acc | accumulation adder (`separate`) and the 22 clear-gating AND2 | gate-level |
| reg_acc | accumulator flip-flops (22, or 44 for carry-save) | gate-level |
| clk | switching of the flip-flop clock-pin capacitance (no clock tree) | gate-level; the tree needs CTS + extraction |
| outcpa | output conversion CPA of `csa_acc`, amortised over K | gate-level |
| (not included) | clock-tree buffers/wires, control/sequencing logic, I/O drivers, power-delivery losses, inter-PE wires, memories | physical design / package / system (§5) |

## 3. Results (gate level, tt 25 °C 1.8 V, 10 ns clock, uniform int8 operands, inertial glitches)

<!-- BEGIN:mac_uniform -->
| variant | cells | area (µm²) | crit tt (ns) | f_max tt (MHz) | f_max ss/100 °C (MHz) | E/MAC (fJ) | TOPS/W | reg_op (fJ) | enc (fJ) | pp (fJ) | red (fJ) | cpa (fJ) | acc (fJ) | reg_acc (fJ) | clk (fJ) | outcpa (fJ) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| separate_booth4_kogge_stone_acckogge_stone | 487 | 4385 | 5.85 | 171 | 86.08 | 1.112e+04 | 0.18 | 1.16e+03 | 201 | 1.12e+03 | 617 | 2.22e+03 | 4.36e+03 | 1.21e+03 | 227 | 0 |
| separate_bw_kogge_stone_acckogge_stone | 437 | 4207 | 5.25 | 190.6 | 92.42 | 9748 | 0.205 | 1.03e+03 | 0 | 391 | 724 | 1.93e+03 | 4.24e+03 | 1.21e+03 | 227 | 0 |
| separate_bw_ripple_accripple | 206 | 2788 | 9.6 | 104.2 | 47.04 | 4967 | 0.403 | 1.03e+03 | 0 | 395 | 883 | 511 | 753 | 1.17e+03 | 227 | 0 |
| fused_booth4_kogge_stone | 405 | 3872 | 4.9 | 204.1 | 103.5 | 8508 | 0.235 | 1.16e+03 | 206 | 1.15e+03 | 1.08e+03 | 3.38e+03 | 123 | 1.18e+03 | 227 | 0 |
| fused_bw_kogge_stone | 361 | 3730 | 4.15 | 240.9 | 116.7 | 6546 | 0.306 | 1.03e+03 | 0 | 403 | 1e+03 | 2.6e+03 | 122 | 1.16e+03 | 227 | 0 |
| csa_acc_booth4_kogge_stone | 477 | 4903 | 4.04 | 247.3 | 124.9 | 6881 | 0.291 | 1.16e+03 | 206 | 1.16e+03 | 1.45e+03 | 0 | 271 | 2.26e+03 | 355 | 19.7 |
| csa_acc_bw_kogge_stone | 433 | 4761 | 3.25 | 307.4 | 144.8 | 5603 | 0.357 | 1.03e+03 | 0 | 408 | 1.29e+03 | 0 | 270 | 2.23e+03 | 355 | 18.8 |
<!-- END:mac_uniform -->

Energy per MAC under three data distributions (fJ; zero-delay and inertial):

<!-- BEGIN:mac_dists -->
| variant | uniform zero | uniform inertial | gauss zero | gauss inertial | relu×gauss zero | relu×gauss inertial |
|---|---|---|---|---|---|---|
| separate_booth4_kogge_stone_acckogge_stone | 6105 | 1.112e+04 | 5650 | 1.051e+04 | 4809 | 8608 |
| separate_bw_kogge_stone_acckogge_stone | 5577 | 9748 | 5234 | 9296 | 3937 | 5770 |
| separate_bw_ripple_accripple | 4051 | 4967 | 3845 | 4715 | 2971 | 3351 |
| fused_booth4_kogge_stone | 5019 | 8508 | 4453 | 7808 | 3880 | 6339 |
| fused_bw_kogge_stone | 4570 | 6546 | 4107 | 6390 | 3105 | 4354 |
| csa_acc_booth4_kogge_stone | 5731 | 6881 | 5418 | 6344 | 5074 | 5622 |
| csa_acc_bw_kogge_stone | 5308 | 5603 | 5114 | 5382 | 4172 | 4317 |
<!-- END:mac_dists -->

### Findings
1. **Registers and clock are 49–64 % of the energy of the three most efficient MACs** (37 % for fused Baugh–Wooley). A dfxtp_1 costs ≈60 fJ per cycle even when its data does not change, mostly clock-pin internal energy. In the lowest-energy variant, the 17 operand registers (1.03 pJ) and 22 accumulator registers (1.17 pJ) together cost more than its whole multiplier datapath (partial products + tree + CPA = 1.79 pJ). A "multiplier energy" quoted without registers understates the MAC by 2.8× (separate BW + ripple) to 3.3× (carry-save BW).
2. **The accumulator adder is where Kogge–Stone hurts.** In the `separate` MACs, the 22-bit KS accumulation adder costs 4.2–4.4 pJ with glitches, more than the multiplier. A ripple accumulation adder costs 0.75 pJ but makes the loop slow (104 MHz tt, 47 MHz ss/100 °C).
3. **Carry-save accumulation gives the best energy–delay trade-off.** `csa_acc_bw_kogge_stone` reaches 307 MHz (tt) and 145 MHz (ss/100 °C) at 5.6 pJ/MAC. That is 13 % more energy than the slowest variant (separate BW + ripple) for 2.95× its frequency. Its cost is 22 extra flip-flops (≈1.1 pJ) and 13 % more cell area than the separate BW + KS MAC (71 % more than the ripple variant).
4. **Baugh–Wooley beats Booth here as well**, consistent with D7: −12 to −23 % energy at equal structure.
5. **Data statistics.** NN-like operands (ReLU activations × Gaussian weights) reduce MAC energy by 18–41 % versus uniform. The registers' clock energy does not shrink with data, so the relative saving is smaller than for the bare multiplier (D7 §5). Clock gating of idle PEs and operand isolation are the corresponding design levers (not implemented).

### Metric definitions applied
* E/MAC: total energy over the simulated window (1 024 MACs after warm-up) / 1 024.
* f_max: 1 / (clock-to-Q + worst combinational path + setup), from `ugcal.gatesim` STA with the same Liberty corner. No clock skew/uncertainty, no wires.
* TOPS/W = 2 / E_MAC[pJ]; MAC/s/W = 1 / E_MAC.
* Throughput of one MAC unit = $f_\text{clk}/II$ = $f_\text{clk}$ (II = 1); latency = 2 cycles.
* Power at f_max = E_MAC × f_max (+ leakage, < 0.1 % at 25 °C).

## 4. From one MAC to the envelope of a single PE

| Quantity | csa_acc_bw_kogge_stone | separate_bw_ripple_accripple | evidence |
|---|---|---|---|
| E/MAC (uniform, inertial) | 5.60 pJ | 4.97 pJ | E (gate level, Liberty) |
| f_max tt / ss 100 °C | 307 / 145 MHz | 104 / 47 MHz | E (STA, no wires) |
| Area (cells) | 4 761 µm² | 2 788 µm² | C (Liberty area) |
| Power at f_max(tt) | 1.72 mW | 0.52 mW | E |
| Power density at f_max(tt), cell area only | 36 W/cm² | 19 W/cm² | E |
| TOPS/W | 0.36 | 0.40 | E |

## 5. Array scaling and data movement (model with explicit unknowns)

`ugcal.array` models an N×N output-stationary systolic array (Kung 1982) whose PEs are the MACs above. Their operand registers double as forwarding registers. Per MAC:

$$E_\text{MAC,array} = E_\text{PE} + \underbrace{2n\,tpc\,\tfrac12 C_w L_\text{pitch}V^2}_{\text{operand forwarding}} + \underbrace{\Big(\frac{2n}{w N} + \frac{W/w}{K}\Big)E_\text{word}}_{\text{SRAM traffic}}$$

Inputs and their classes:
* $E_\text{PE}$ from §3 (E).
* $C_w$ for met2: lower bound 0.078 fF/µm, isolated wire to substrate from the tech LEF (C); upper bracket 0.2 fF/µm including coupling (H).
* $L_\text{pitch} = \sqrt{A_\text{PE}/0.7}$ (E, 70 % utilisation assumed).
* $E_\text{word}$ = 19.2 pJ per 32-bit access, from the OpenRAM-generated Liberty of `sky130_sram_1kbyte_1rw1r_32x256_8` (9.59 pJ per clock edge). That file gives the same energy for read, write and deselected states, so it is an analytical estimate (class H), not characterised silicon.
* $tpc$ = 0.5 for random operands.

<!-- BEGIN:array -->
| PE variant | reuse N | wire C | E_PE (fJ) | E_fwd (fJ) | E_SRAM (fJ) | E_MAC,array (fJ) | SRAM share (%) | TOPS/W |
|---|---|---|---|---|---|---|---|---|
| separate_bw_ripple_accripple | 1 | lo | 4967 | 63.7 | 9795 | 1.483e+04 | 66.1 | 0.135 |
| separate_bw_ripple_accripple | 1 | hi | 4967 | 164 | 9795 | 1.493e+04 | 65.6 | 0.134 |
| separate_bw_ripple_accripple | 4 | lo | 4967 | 63.7 | 2603 | 7635 | 34.1 | 0.262 |
| separate_bw_ripple_accripple | 4 | hi | 4967 | 164 | 2603 | 7734 | 33.7 | 0.259 |
| separate_bw_ripple_accripple | 16 | lo | 4967 | 63.7 | 805.4 | 5837 | 13.8 | 0.343 |
| separate_bw_ripple_accripple | 16 | hi | 4967 | 164 | 805.4 | 5936 | 13.6 | 0.337 |
| separate_bw_ripple_accripple | 64 | lo | 4967 | 63.7 | 355.9 | 5387 | 6.61 | 0.371 |
| separate_bw_ripple_accripple | 64 | hi | 4967 | 164 | 355.9 | 5487 | 6.49 | 0.365 |
| separate_bw_ripple_accripple | 256 | lo | 4967 | 63.7 | 243.5 | 5275 | 4.62 | 0.379 |
| separate_bw_ripple_accripple | 256 | hi | 4967 | 164 | 243.5 | 5375 | 4.53 | 0.372 |
| csa_acc_bw_kogge_stone | 1 | lo | 5603 | 83.2 | 9795 | 1.548e+04 | 63.3 | 0.129 |
| csa_acc_bw_kogge_stone | 1 | hi | 5603 | 214 | 9795 | 1.561e+04 | 62.7 | 0.128 |
| csa_acc_bw_kogge_stone | 4 | lo | 5603 | 83.2 | 2603 | 8290 | 31.4 | 0.241 |
| csa_acc_bw_kogge_stone | 4 | hi | 5603 | 214 | 2603 | 8421 | 30.9 | 0.238 |
| csa_acc_bw_kogge_stone | 16 | lo | 5603 | 83.2 | 805.4 | 6492 | 12.4 | 0.308 |
| csa_acc_bw_kogge_stone | 16 | hi | 5603 | 214 | 805.4 | 6622 | 12.2 | 0.302 |
| csa_acc_bw_kogge_stone | 64 | lo | 5603 | 83.2 | 355.9 | 6042 | 5.89 | 0.331 |
| csa_acc_bw_kogge_stone | 64 | hi | 5603 | 214 | 355.9 | 6173 | 5.76 | 0.324 |
| csa_acc_bw_kogge_stone | 256 | lo | 5603 | 83.2 | 243.5 | 5930 | 4.11 | 0.337 |
| csa_acc_bw_kogge_stone | 256 | hi | 5603 | 214 | 243.5 | 6061 | 4.02 | 0.33 |
<!-- END:array -->

**Reading the table.** Without reuse (N = 1, i.e. every operand fetched from SRAM for every MAC), memory traffic roughly triples the energy per MAC (SRAM share 63–66 %). With reuse, the SRAM share falls to 12–14 % at N = 16 and ≈6 % at N = 64, and forwarding wires stay at 1–4 % of the total. So in SKY130 at 1.8 V the arithmetic and its registers dominate once the dataflow reuses operands. Published advanced-node accelerators report the opposite balance: Eyeriss (65 nm) organises its whole design around minimising data movement (Chen et al. 2017), and Horowitz's 45 nm table puts memory accesses orders of magnitude above an 8-bit multiply (via secondary sources). That is a node- and memory-dependent conclusion. It should be recomputed for any target technology with characterised memory energies, not assumed.

**Not modelled (class I until physical design):** clock-tree wiring and buffers; global operand broadcast at the array edges; DRAM/off-chip I/O; power-delivery losses (IR drop, regulator efficiency); control and address generation.

## 6. Algorithmic transformations change the MAC count, not the MAC cost

im2col + GEMM, implicit GEMM and direct convolution perform the same multiplications in different orders and with different operand reuse. They change $N$ (reuse) and SRAM traffic in §5, not $E_\text{PE}$. Winograd $F(2\times2,3\times3)$ reduces multiplications per output by up to 2.25×, and larger tiles by up to 4× (Lavin & Gray 2016). It adds transforms (additions: an 8-bit ripple addition costs 0.16 pJ in SKY130 against 1.6–2.7 pJ for an 8×8 multiplication, D7 §2 and §6) and changes the dynamic range of the transformed operands, so accumulator and operand widths may grow. The energy per *inference* is therefore $\sum_\text{layers} N_\text{MAC}\cdot E_\text{MAC,array}(N_\text{reuse}, \text{widths}, \text{data})$. Every factor must come from the same corner and the same counting convention.
