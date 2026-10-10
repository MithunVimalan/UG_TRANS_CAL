# Research map: questions, calculations, required inputs and where each comes from

This is the starting point the brief asks for (§22): the research questions, the calculations that answer them, the exact inputs each calculation needs, the authoritative source of each input, its evidence class and whether it was obtained. Deliverables D1–D15 are in this directory. The code is in `ugcal/`, `sim/` and `tools/`; data in `data/` and `results/`.

## 1. Questions and where they are answered

| Question (brief) | Answered in | Kind of answer |
|---|---|---|
| Which limits are fundamental, which technology-dependent, which architectural, which from implementation or cooling? | D3 §5, D2, D12 §2 | classification with numbers |
| What is the minimum energy of a multiplication or MAC? | D3 §1.5–1.6 | exact information content × kT ln2 (absolute floor); everything above it is conditional |
| What does SKY130 actually allow? | D4 (devices), D7 (multipliers), D8 (MAC, array), D9 (heat) | conditional results at stated corner, V, T, activity, interconnect |
| How close is a design to the limits? | D3 §5, D11 | ratio to each bound; evidence ladder |
| What can be established before circuit design? | D1 §4 | list |
| How should a built circuit be benchmarked? | D11 | procedure, record format, E_n criterion |
| What is missing? | D13 | parameter-by-parameter |

## 2. Calculations and their exact inputs

Classes: A constant, B measured, C foundry, D peer-reviewed theory, E model-derived, F circuit-simulated, G post-layout, H estimated, I unavailable, S specification.

| Calculation | Equation (D6) | Required inputs | Source of each input | Class | Obtained? |
|---|---|---|---|---|---|
| Thermodynamic floor per operation | $N_\text{bits}\,k_BT\ln2$ | $k_B$; T; bits erased | SI 2019; S; exact enumeration (`ugcal.infotheory`) | A, S, E | yes |
| Reliability scale per node | $E=2k_BT[Q^{-1}(p)]^2$ | T; target error probability p | S; S | — | yes (as a function of p) |
| Subthreshold-swing and min-supply bounds | $(k_BT/q)\ln10$; $2\ln2\,k_BT/q$; $8k_BT/q$ | $k_B$, q, T | SI 2019 | A | yes |
| Device characteristics | BSIM4 evaluated by ngspice | model cards; W, L; V; T; corner | `sky130_fd_pr` @16f93a79 | C → F | yes (D4 §2) |
| Gate capacitance (check) | $C_{ox}WL + 2WC_{ov}$ | toxe, epsrox, cgso/cgdo | model cards | C → E | yes |
| Mismatch | $\sigma_{V_{th}} = A_{VT}/\sqrt{WL}$ | AGAUSS coefficients | `*_mm` sections | C | yes |
| Cell energy and delay | Liberty NLDM interpolation, or SPICE | Liberty tables; input slew; output load; V; T | `sky130_fd_sc_hd` @9cb2d7cb; S (50 ps, 5 fF) | C, S | yes |
| Cell leakage | state-weighted Liberty leakage, or SPICE DC | Liberty; state probabilities; cell netlists | Liberty; simulation | C, E/F | yes, with a 1–3-decade data-set disagreement at 100 °C (D4 §5) |
| Switching energy of a node | $\tfrac12CV^2$ per transition | C, V, transition count | Liberty pin C + load; S; simulation | C, S, E | yes |
| Multiplier/MAC energy per operation | $\sum$(internal + ½CV² + leakage·t) over a stimulus | netlist; Liberty; stimulus statistics; glitch model | generators; Liberty; S; three modes | E (F with SPICE) | yes, pre-layout |
| Interconnect energy | $\tfrac12 C_w L V^2$ per transition | C per length; wire lengths | tech LEF (lower bound, C); layout (**I**) | C, I | bracket only |
| Critical path / f_max | NLDM STA | Liberty delays at slow corner; setup; clock-to-Q | Liberty ss/100 °C | C → E | yes, pre-layout |
| Clock-tree energy | — | CTS netlist and wires | layout (**I**) | I | **no** |
| Array energy with memory | D8 §5 | E_PE; reuse; SRAM energy per word; wire C | §above; S; OpenRAM (H); LEF/H | E, H | yes, with class-H inputs |
| Implementation overhead (empirical) | ratio post-route / pre-layout | an implemented design in the same process | third-party SKY130 array (G, D8 §5.1) | G | one data point |
| Power, energy per op, EDP, TOPS/W | D6 §5 | E_op; f; II; ops per MAC = 2 | above; S | E, S | yes |
| Junction temperature | $T_a + P\,R_{th}$ | P; R_th (package, board, airflow) | above; **package datasheet (I until chosen)** → swept (S) | E, S | conditional |
| Sustainable throughput (thermal) | $(P_\text{max} - P_\text{leak}(T_\text{max}))/E_\text{op}$ | T_j,max; T_a; R_th; leakage(T) | characterisation limit (C, not reliability); S; S; Liberty (C) | C, S, E | conditional |
| Electro-thermal stability | loop gain $R_{th}\,dP_\text{leak}/dT$ | leakage vs T | Liberty corners (C), SPICE (F) | E | yes |
| Reliability-limited lifetime | Black, Arrhenius | EM and ageing parameters | foundry reliability data (**I**) | I | **no** |
| Silicon validation | E_n | measurements | test chip (**I**) | I | **no** |

## 3. Primary sources by area (full entries in D15)

* **Thermodynamics:** landauer1961, bennett1973, berut2012 and jun2014 (experiments), proesmans2020 (finite time), margolus1998, meindl2000, swanson1972, zhirnov2003, kish2002, freitas2021, gao_limmer2021.
* **Device physics and models:** roy2003, ortizconde2002, pelgrom1989, lundstrom1997, sakurai1990; BSIM4 and BSIM-CMG manuals (not reachable; models exercised through ngspice).
* **Foundry and PDK:** SKY130 repositories at pinned commits (sky130_docs, sky130_fd_pr, sky130_fd_sc_hd, open_pdks); asap7_repo and clark2016asap7; zhao2006ptm; public claims of commercial foundries (NDA kits not accessible).
* **Arithmetic:** booth1951, wallace1964, dadda1965, baughwooley1973, kogge1973, brentkung1982, chandrakasan1992, veendrick1984, calhoun2005.
* **Tools and standards:** ngspice, OpenSTA, Yosys, Magic, OpenRAM (guthaus2016openram); Liberty manual, JESD51 and ISO 13528 (restricted).
* **Accelerators:** kung1982, horowitz2014, chen2017eyeriss, sze2017, jouppi2017, lavin2016; nivi9944_systolic (same-process post-route reference).
* **Thermal and reliability:** huang2006hotspot, pop2010, glassbrenner1964, black1969, vassighi2006, jesd51.

## 4. Network limitation that shaped the source work

The container could reach GitHub, PyPI and Ubuntu mirrors only. Publisher sites (IEEE Xplore, APS, Nature, Springer, ACM), arXiv, readthedocs, nist.gov and bsim.berkeley.edu were blocked. Bibliographic facts were therefore confirmed through a web-search service, and no paper's full text was opened. All PDK, tool and repository content was read directly from pinned commits. D13 §2–3 list what this leaves unverified.
