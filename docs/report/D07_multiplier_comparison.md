# D7 — Multiplier architectures: a controlled comparison in SKY130

## 1. Conditions held equal

| Condition | Value |
|---|---|
| Process / library | SKY130, `sky130_fd_sc_hd` (pinned commit), Liberty corner `tt_025C_1v80` (1.80 V, 25 °C) for energy; `ss_100C_1v60` for sign-off timing of MACs (D8) |
| Arithmetic | n×n → 2n-bit product, exact; unsigned (AND partial products) or two's-complement signed (Baugh–Wooley or radix-4 Booth); verified exhaustively for 8×8 (65 536 pairs) and at 4/6 bits in the test suite |
| Cells | every primitive maps to one drive-strength-1 cell (and2_1, nand2_1, xor2_1, xnor2_1, a21o_1, ha_1, fa_1, inv_1, or2_1); no sizing or buffering, identical for all designs |
| Inputs | ideal ramps, 50 ps (20–80 %) |
| Outputs | 5 fF per product bit |
| Interconnect | none (pre-layout). Wire-load and extracted parasitics are the next evidence level (D11) |
| Stimulus | 1 001 operand pairs per distribution, same seed for all designs: uniform; sparse (50 % zeros); small (|x| < 2^(n/2)); Gaussian (NN-weight-like, σ = range/16) |
| Timing | worst register-to-register-style path from `ugcal.gatesim` STA (max over edges and when-conditions). 3–10 % pessimistic relative to OpenSTA on the same netlists (D10 §4) |
| Energy | `ugcal.gatesim` event-driven simulation in three delay modes. Zero-delay = functional transitions only; inertial = glitches shorter than a gate delay filtered; transport = all glitches propagate. Boundary: VPWR of the multiplier cells; input-net switching excluded |

Algorithm and implementation are kept apart in the names: `<partial products>_<reduction>_<final adder>`. For example, `dadda_ks` is an AND array + Dadda tree + Kogge–Stone adder, and `booth4_dadda_ks` is radix-4 Booth + Dadda + Kogge–Stone. `yosys_abc` is what Yosys 0.33 + ABC produce from a behavioural `p = a * b` with LibreLane's synthesis exclusion list.

## 2. Results, 8×8 unsigned (uniform operands)

<!-- BEGIN:arch8u -->
| design | cells | transistors | area (µm²) | critical path (ns) | E zero-delay (fJ) | E inertial (fJ) | E transport (fJ) | glitch factor (inertial/zero) | EDP inertial (fJ·ns) | leakage tt25 (nW) |
|---|---|---|---|---|---|---|---|---|---|---|
| array_rc | 120 | 1840 | 1461 | 8.86 | 1208 | 2434 | 4570 | 2.02 | 2.156e+04 | 0.583 |
| braun | 120 | 1840 | 1461 | 6.35 | 1241 | 1994 | 3760 | 1.61 | 1.266e+04 | 0.583 |
| wallace_rca | 136 | 2036 | 1647 | 6.13 | 1221 | 1618 | 3725 | 1.33 | 9923 | 0.71 |
| wallace_ks | 187 | 2292 | 1947 | 3.43 | 1417 | 2349 | 5476 | 1.66 | 8060 | 0.948 |
| dadda_rca | 120 | 1840 | 1461 | 5.9 | 1205 | 1584 | 3333 | 1.31 | 9346 | 0.583 |
| dadda_ks | 202 | 2284 | 1961 | 3.47 | 1578 | 2723 | 5549 | 1.73 | 9443 | 0.962 |
| dadda_bk | 162 | 2004 | 1685 | 3.72 | 1387 | 2194 | 4485 | 1.58 | 8154 | 0.791 |
| dadda_sk | 174 | 2088 | 1768 | 3.52 | 1441 | 2342 | 4796 | 1.62 | 8255 | 0.842 |
| booth4_dadda_ks | 269 | 2618 | 2341 | 3.83 | 2273 | 4806 | 1.615e+04 | 2.11 | 1.84e+04 | 1.28 |
| yosys_abc | 234 | 2120 | 1927 | 4.2 | 1811 | 2519 | 6884 | 1.39 | 1.059e+04 | 0.844 |
<!-- END:arch8u -->

## 3. Results, 8×8 signed (uniform operands)

<!-- BEGIN:arch8s -->
| design | cells | transistors | area (µm²) | critical path (ns) | E zero-delay (fJ) | E inertial (fJ) | E transport (fJ) | glitch factor (inertial/zero) | EDP inertial (fJ·ns) | leakage tt25 (nW) |
|---|---|---|---|---|---|---|---|---|---|---|
| bw_array_cs | 154 | 2194 | 1795 | 6.7 | 1405 | 2503 | 5441 | 1.78 | 1.677e+04 | 0.83 |
| bw_wallace_rca | 139 | 2040 | 1639 | 6.13 | 1319 | 1791 | 4238 | 1.36 | 1.098e+04 | 0.72 |
| bw_dadda_ks | 204 | 2260 | 1932 | 3.43 | 1725 | 3120 | 6833 | 1.81 | 1.071e+04 | 0.956 |
| booth4_wallace_ks | 244 | 2354 | 2126 | 3.83 | 1923 | 4181 | 1.384e+04 | 2.17 | 1.599e+04 | 1.21 |
| booth4_dadda_rca | 166 | 1834 | 1575 | 6.25 | 1557 | 2734 | 7498 | 1.76 | 1.709e+04 | 0.805 |
| booth4_dadda_ks | 254 | 2314 | 2111 | 3.67 | 2106 | 4429 | 1.462e+04 | 2.1 | 1.624e+04 | 1.2 |
| yosys_abc | 296 | 2640 | 2381 | 4.71 | 2294 | 3283 | 1.027e+04 | 1.43 | 1.547e+04 | 1.02 |
<!-- END:arch8s -->

## 4. Results, 16×16 unsigned (uniform operands)

<!-- BEGIN:arch16u -->
| design | cells | transistors | area (µm²) | critical path (ns) | E zero-delay (fJ) | E inertial (fJ) | E transport (fJ) | glitch factor (inertial/zero) | EDP inertial (fJ·ns) | leakage tt25 (nW) |
|---|---|---|---|---|---|---|---|---|---|---|
| array_rc | 496 | 8032 | 6286 | 19.5 | 5456 | 1.845e+04 | 5.068e+04 | 3.38 | 3.604e+05 | 2.44 |
| braun | 496 | 8032 | 6286 | 14 | 5587 | 1.415e+04 | 3.384e+04 | 2.53 | 1.978e+05 | 2.44 |
| wallace_rca | 555 | 8802 | 6994 | 12.2 | 5423 | 7836 | 2.307e+04 | 1.45 | 9.58e+04 | 2.91 |
| wallace_ks | 734 | 9814 | 8105 | 4.63 | 6143 | 1.165e+04 | 3.522e+04 | 1.9 | 5.389e+04 | 3.72 |
| dadda_rca | 496 | 8032 | 6286 | 12 | 5308 | 7256 | 2.083e+04 | 1.37 | 8.695e+04 | 2.44 |
| dadda_ks | 734 | 9408 | 7779 | 4.65 | 6543 | 1.163e+04 | 3.576e+04 | 1.78 | 5.403e+04 | 3.52 |
| dadda_bk | 598 | 8456 | 6843 | 5.1 | 5803 | 9358 | 2.766e+04 | 1.61 | 4.777e+04 | 2.94 |
| dadda_sk | 644 | 8778 | 7159 | 4.8 | 6041 | 1.007e+04 | 3.075e+04 | 1.67 | 4.838e+04 | 3.14 |
| booth4_dadda_ks | 866 | 9100 | 7924 | 5.11 | 7916 | 1.829e+04 | 8.053e+04 | 2.31 | 9.347e+04 | 4.18 |
| yosys_abc | 1109 | 9330 | 8374 | 8.8 | 8142 | 1.356e+04 | 4.636e+04 | 1.67 | 1.193e+05 | 3.41 |
<!-- END:arch16u -->

## 5. Data dependence (inertial-mode energy per multiplication, fJ)

<!-- BEGIN:arch_data -->
| width | design | uniform | sparse 50 % | small |x| < 2^(n/2) | gaussian | max/min |
|---|---|---|---|---|---|---|
| 8u | array_rc | 2434 | 662.1 | 447 | 1317 | 5.45 |
| 8u | braun | 1994 | 575.9 | 384 | 1160 | 5.19 |
| 8u | wallace_rca | 1618 | 466.4 | 335.2 | 881.5 | 4.83 |
| 8u | wallace_ks | 2349 | 629.1 | 361.6 | 1163 | 6.5 |
| 8u | dadda_rca | 1584 | 464.7 | 339.3 | 903.1 | 4.67 |
| 8u | dadda_ks | 2723 | 719.8 | 523.4 | 1500 | 5.2 |
| 8u | dadda_bk | 2194 | 606.3 | 457.9 | 1236 | 4.79 |
| 8u | dadda_sk | 2342 | 638.4 | 469.4 | 1292 | 4.99 |
| 8u | booth4_dadda_ks | 4806 | 2777 | 2209 | 3532 | 2.18 |
| 8u | yosys_abc | 2519 | 790.3 | 513.2 | 1368 | 4.91 |
| 8s | bw_array_cs | 2503 | 808.7 | 2071 | 2137 | 3.1 |
| 8s | bw_wallace_rca | 1791 | 578.4 | 1645 | 1622 | 3.1 |
| 8s | bw_dadda_ks | 3120 | 1005 | 3017 | 2981 | 3.11 |
| 8s | booth4_wallace_ks | 4181 | 2243 | 3378 | 3545 | 1.86 |
| 8s | booth4_dadda_rca | 2734 | 1407 | 2135 | 2276 | 1.94 |
| 8s | booth4_dadda_ks | 4429 | 2522 | 3762 | 3918 | 1.76 |
| 8s | yosys_abc | 3283 | 1297 | 3212 | 3134 | 2.53 |
| 16u | array_rc | 1.845e+04 | 5328 | 3517 | 1.414e+04 | 5.25 |
| 16u | braun | 1.415e+04 | 4265 | 3031 | 1.147e+04 | 4.67 |
| 16u | wallace_rca | 7836 | 2332 | 1929 | 5977 | 4.06 |
| 16u | wallace_ks | 1.165e+04 | 3211 | 2488 | 8711 | 4.68 |
| 16u | dadda_rca | 7256 | 2292 | 1762 | 5650 | 4.12 |
| 16u | dadda_ks | 1.163e+04 | 3362 | 2903 | 8997 | 4.01 |
| 16u | dadda_bk | 9358 | 2801 | 2341 | 7263 | 4 |
| 16u | dadda_sk | 1.007e+04 | 2978 | 2483 | 7758 | 4.06 |
| 16u | booth4_dadda_ks | 1.829e+04 | 1.101e+04 | 9041 | 1.59e+04 | 2.02 |
| 16u | yosys_abc | 1.356e+04 | 4311 | 3077 | 9844 | 4.41 |
<!-- END:arch_data -->

## 6. Adders (Part IX): ripple vs parallel-prefix, n-bit + n-bit → n+1 bits

Same conditions as above (uniform random operands). These are the final adders inside the multipliers and the accumulation adders of the MACs (D8).

<!-- BEGIN:adders -->
| n | adder | cells | transistors | area (µm²) | critical path (ns) | E zero (fJ) | E inertial (fJ) | E transport (fJ) | EDP inertial (fJ·ns) | errors (1 001 vectors) |
|---|---|---|---|---|---|---|---|---|---|---|
| 8 | ripple | 8 | 210 | 152.6 | 2.98 | 126.2 | 163.9 | 306.3 | 488.4 | 0 |
| 8 | kogge_stone | 42 | 378 | 351.6 | 1.04 | 414.6 | 462.4 | 781.7 | 479.7 | 0 |
| 8 | brent_kung | 30 | 294 | 269 | 1.3 | 317 | 358.7 | 593.3 | 466.8 | 0 |
| 8 | sklansky | 32 | 308 | 282.8 | 1.12 | 332.5 | 374.6 | 629.8 | 418.6 | 0 |
| 16 | ripple | 16 | 434 | 312.8 | 6.02 | 255.7 | 344.7 | 651.7 | 2076 | 0 |
| 16 | kogge_stone | 114 | 970 | 912.1 | 1.26 | 1028 | 1178 | 1999 | 1479 | 0 |
| 16 | brent_kung | 68 | 648 | 595.6 | 1.77 | 696.8 | 809.5 | 1306 | 1434 | 0 |
| 16 | sklansky | 80 | 732 | 678.2 | 1.43 | 779.9 | 904.4 | 1488 | 1294 | 0 |
| 22 | ripple | 22 | 602 | 432.9 | 8.3 | 354 | 484.5 | 916.8 | 4023 | 0 |
| 22 | kogge_stone | 180 | 1498 | 1415 | 1.37 | 1550 | 1780 | 3041 | 2444 | 0 |
| 22 | brent_kung | 94 | 896 | 823.3 | 1.81 | 966.5 | 1138 | 1815 | 2056 | 0 |
| 22 | sklansky | 112 | 1022 | 947.2 | 1.71 | 1091 | 1279 | 2077 | 2191 | 0 |
| 32 | ripple | 32 | 882 | 633.1 | 12.1 | 511.4 | 703.7 | 1347 | 8519 | 0 |
| 32 | kogge_stone | 290 | 2378 | 2253 | 1.49 | 2399 | 2752 | 4814 | 4102 | 0 |
| 32 | brent_kung | 146 | 1370 | 1262 | 2.27 | 1452 | 1722 | 2775 | 3913 | 0 |
| 32 | sklansky | 192 | 1692 | 1579 | 1.86 | 1742 | 2058 | 3371 | 3819 | 0 |
<!-- END:adders -->

Kogge–Stone is the fastest at every width (log₂n levels, fan-out 2) and costs the most energy and area. Its wiring (n log₂ n − n + 1 combine cells, long horizontal spans) will cost further energy after layout. Brent–Kung has the lowest energy among the prefix adders, at 1.3–1.5× the Kogge–Stone delay. Ripple-carry has by far the lowest energy (20–22 fJ per bit) but never the lowest energy-delay product: Sklansky has the lowest EDP at 8, 16 and 32 bits and Brent–Kung at 22 bits. Ripple's delay grows linearly at ≈0.37–0.38 ns per bit, which sets the clock of any loop that contains it (the accumulator, D8). Glitch overheads of adders are modest (inertial/zero 1.1–1.4) compared with multipliers (1.3–3.4).

## 7. Transistor-level arbitration (class F)

The same operand sequence was simulated in ngspice on the full transistor netlist of each multiplier: every cell instantiated from the layout-extracted + LOD view on the foundry BSIM4 cards (1,840–2,618 transistors plus extracted cell parasitics, no inter-cell wiring). The per-cycle supply energy was integrated and every product checked for correctness at the end of its cycle.

<!-- BEGIN:spice_mult -->
<!-- END:spice_mult -->

## 8. Findings

1. **Glitches are the dominant architecture-dependent term.** Functional (zero-delay) energy is nearly the same for every AND-array design at a given width (8×8: 1.21–1.24 pJ for array/Braun/Wallace/Dadda with ripple adders). The spread between architectures comes from spurious transitions. In inertial mode they add 31 % (Dadda + ripple) to 102 % (ripple-carry array) at 8×8, and 37 % to 238 % at 16×16. Transistor-level SPICE lands between the inertial and transport brackets: for the ripple array, SPICE is 1.19× the inertial estimate. Gate-level power that ignores glitches (zero-delay, or the 0.1-toggle default of an un-annotated STA run) under-estimates these multipliers by 1.3–3.4×.
2. **Tree reduction beats arrays on energy and delay, and Dadda edges out Wallace.** At 8×8 with ripple final adders, Dadda uses 35 FA + 7 HA in the tree against Wallace's 36 + 25. It has 16 fewer cells and the lowest inertial energy of any design (1.58 pJ), and its critical path (5.90 ns) is shorter than Wallace's (6.13 ns). The ripple-carry array is slowest (8.86 ns) and glitchiest.
3. **The final adder trades energy for delay.** Replacing the ripple CPA by a prefix adder cuts the 8×8 critical path from 5.90 to 3.47–3.72 ns but raises energy by 38–72 %. Brent–Kung is the most economical prefix network here (2.19 pJ, 3.72 ns), and it has the lowest energy-delay product among Dadda variants together with Sklansky. Kogge–Stone is the fastest and most glitch-prone.
4. **Radix-4 Booth does not pay off in this library at 8 or 16 bits.** It halves the partial-product rows, but the encoders and the XOR-based selectors are heavy in SKY130 HD and very glitchy (transport/zero factor 7–10). Signed 8×8: 4.43 pJ (Booth + Dadda + KS) vs 3.12 pJ (Baugh–Wooley + Dadda + KS) at about the same delay. At 16×16: 18.3 pJ vs 11.6 pJ (unsigned Dadda + KS). This contradicts the common rule of thumb that Booth saves energy. The rule assumes a library and widths where reducing adder count dominates, which is not the case here.
5. **Synthesis versus hand-built structure.** Yosys/ABC's netlist for `a*b` (8×8 unsigned: 234 cells, 4.20 ns, 2.52 pJ) is beaten on both delay and energy by the hand-built Dadda + Brent–Kung (162 cells, 3.72 ns, 2.19 pJ). It is beaten on energy, not delay, by Dadda + ripple (1.58 pJ). At 16×16 the gap is larger: Yosys 8.80 ns and 13.6 pJ against Dadda + BK at 5.10 ns and 9.4 pJ. **The synthesis tool does not make the architecture choice for you.** Specifying the structure explicitly is worth 13–37 % in energy and up to 1.7× in delay here.
6. **Operand statistics matter as much as architecture.** Unsigned AND-array designs spend 4.7–6.5× less energy on small-magnitude operands than on uniform ones at 8×8 (Dadda + ripple: 0.34 vs 1.58 pJ), 4.0–5.3× at 16×16, and 3.2–3.8× on 50 %-sparse operands. Booth designs gain only 2.0–2.2×. With two's complement, small-magnitude signed operands save almost nothing: 1.02–1.28× (BW + Dadda + KS: 3.02 vs 3.12 pJ), because every small negative number toggles all its sign-extension bits. Signed sparse operands still save 1.8–3.1×. For neural-network data, which are mostly small and centred on zero, this is a first-order effect. It argues for sign-magnitude or offset representations, or for gating the sign extension, before any change of multiplier architecture.
7. **Transistor count is not a predictor of energy.** The unsigned 8×8 Booth + Dadda + KS design has 42 % more transistors than Dadda + ripple (2,618 vs 1,840) but consumes 3.0× the energy. The Yosys netlist has fewer transistors than Dadda + KS (2,120 vs 2,284) and consumes slightly less (2.52 vs 2.72 pJ), at a 21 % longer delay (4.20 vs 3.47 ns). The ripple array, Braun and Dadda + ripple designs have identical cell counts (120) and transistor counts (1,840: 64 and2, 48 fa, 8 ha), yet their energies differ by up to 1.54× and their delays by up to 1.50× (ripple array vs Dadda).

## 9. Limits of this comparison

* Pre-layout: no wire capacitance or resistance. The SKY130 OpenRCX extractor's total-capacitance error has been reported as ≈20 % against a field solver (input research file, not re-verified). Wires add more energy to tree multipliers, whose wiring is irregular, than to arrays.
* No gate sizing or buffering. A timing-driven flow would upsize critical cells and buffer high-fanout nets (Booth select lines, AND-array operand bits), shifting delay and energy differently for each design.
* Gate-level delays are static (one slew per pin); the glitch bracket is inertial versus transport. The transistor-level runs (§6) arbitrate for 8×8 designs at one corner and one stimulus.
* Results are for tt/25 °C/1.8 V. Energy scales approximately with $V^2$ (D4 §4); delay rankings hold across corners for these netlists (same cells), which was checked for the MAC netlists at ss/100 °C (D8).
