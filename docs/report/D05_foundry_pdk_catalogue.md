# D5 — Foundry and PDK source catalogue

**What this deliverable answers.** For each foundry or open PDK: what exists, what was actually inspected (and at which commit), what needs registration, licence or NDA, and which questions each data set can answer reliably. "Inspected" means the file was read from a pinned git commit. Documents known only through a web-search summary are marked *search*. This container's network policy allows GitHub, PyPI and Ubuntu mirrors only; publisher sites, arXiv, readthedocs, nist.gov and bsim.berkeley.edu were blocked.

---

## 1. Kinds of models and kits

| Kind | Definition used in this report | Example | Fit for |
|---|---|---|---|
| Generic model | Textbook-style or default model parameters, not tied to a process | SPICE level-1 with invented $K'$, $V_t$ | teaching only |
| Predictive model | Parameters projected from physics and published data for a node that is not a real process | PTM (ASU/UMN, Zhao & Cao 2006); ASAP7 BSIM-CMG cards; FreePDK45 + Nangate | relative and architectural studies; not absolute energy/delay of any product |
| Public research PDK | Complete kit for a fictitious process | FreePDK45, ASAP7 | flow development, DTCO exploration; **cannot be fabricated** |
| Foundry-derived open PDK | Released by or with a foundry for a real process, but not production-qualified | **SKY130** ("experimental preview / alpha release", README), GF180MCU ("not intended to be used for production"), IHP SG13G2 (preview) | everything up to test chips, including absolute numbers *within* the stated maturity |
| Foundry-qualified model | Model cards the foundry stands behind for design, with corners and statistical models | commercial kits under NDA | design and sign-off within the stated validity |
| Production-qualified PDK | Qualified kit including DRC/LVS/PEX decks, reliability rules, EM limits, ageing models, qualified libraries | TSMC, Samsung, Intel Foundry, GF commercial kits | manufacturing sign-off |

## 2. Compact models in use

| Model | Device class | Where used in this project | Notes |
|---|---|---|---|
| BSIM4 (level 54, v4.5 in the SKY130 cards) | planar bulk MOSFET | SKY130 nfet_01v8, pfet_01v8_hvt, and other flavours | Binned cards: 180 bins (nfet_01v8) and 198 (pfet_01v8_hvt); `igcmod = igbmod = 0` (no gate current); `rdsmod = 0`; `capmod = 2`; LOD stress via SA/SB with SAREF = SBREF = 1.04 µm; Gaussian mismatch through `AGAUSS` terms on toxe, vth0, voff, nfactor |
| BSIM-CMG | FinFET, nanowire/nanosheet (multi-gate) | not used (ASAP7 cards exist; ngspice support not established here) | surface-potential model, self-heating network available [bsimcmg_manual] |
| BSIM-SOI / UTSOI / Leti-UTSOI | FD-SOI and PD-SOI | not used | needed for FD-SOI back-bias studies (e.g. GF 22FDX, under NDA) |
| PSP | bulk MOSFET (surface potential) | not used | IHP SG13G2 open PDK (model family not confirmed in this project; see D13) |

**Do not read physics from a binned card.** In the SKY130 bin that covers the inv_1 NMOS (W 0.65, L 0.15 µm), `vth0` is 0.0905 V and `nfactor` 4.98. The neighbouring narrow bin has `vth0` = 1.44 V, and a PMOS bin has negative `vsat`. These are regression coefficients that only become physical after the simulator applies the binning terms. Thresholds, slopes and currents in this report come from simulation (D4).

## 3. Foundry-by-foundry

| Foundry / kit | Public (inspected) | Registration | Licence / NDA | Not verifiable here |
|---|---|---|---|---|
| **SkyWater SKY130** | Model cards, corners, mismatch and MC sections (`fossi-foundation/skywater-pdk-libs-sky130_fd_pr` @16f93a79); HD standard-cell Liberty (16 NLDM + 2 CCS-noise corners), cell netlists, Verilog, LEF, GDS (`…sky130_fd_sc_hd` @9cb2d7cb); documentation sources incl. device tables vs. e-test, design rules, RCX resistance tables (`google/skywater-pdk` @7198cf64); Magic tech, OpenRCX rules, LibreLane configs (`RTimothyEdwards/open_pdks` @0ec4fa67) | none (Apache 2.0) | none for the open content | Liberty characterisation conditions (SPICE corner/model version/netlist view); "Electrical DR" incl. electromigration (referenced by periphery rule x.4, absent); reliability/qualification data; T_j,max; the external "SKY130 Stackup Capacitance Data" spreadsheet (Google Docs link, host blocked) |
| GlobalFoundries GF180MCU | Repository `google/gf180mcu-pdk` (HEAD de3240d7; not checked out) | none (Apache 2.0) | none for open content | model family; maturity statement says not for production (search) |
| IHP SG13G2 (130 nm BiCMOS) | Repository `IHP-GmbH/IHP-Open-PDK` (HEAD 5e6d592e; not checked out) | none | free MPW shuttles for non-commercial use (search) | model family; maturity "preview" (search) |
| ASAP7 (predictive 7 nm FinFET) | `The-OpenROAD-Project/asap7` @d24f8b85: README (BSD-3), sub-modules for PDK r1.7, 7.5-track and 6-track libraries, SRAM | Calibre decks from asap.asu.edu | none | BSIM-CMG cards not inspected; ngspice support for them not established |
| FreePDK45 / Nangate | `foss-eda-tools.googlesource.com/third_party/freepdk45` (search); Nangate library characterised with the ASU PTM 45 nm BSIM4 card (search) | none | none | not inspected |
| PTM (ASU/UMN) | model cards for 130–7 nm bulk/FinFET (search) | none | none | site blocked; not inspected |
| TSMC | public process announcements and conference papers (e.g. IEDM 2024 N2 paper, *search*: 15 % speed or 30 % power vs N3 at >1.15× density; ≈38 Mb/mm² SRAM) | customer portal | **PDK requires NDA** (university programmes cite a 3-way NDA, *search*) | everything at device level |
| Samsung Foundry | public announcements (3 nm GAA "MBCFET", PDK v0.1 for 3GAE released April 2019, *search*) | customer portal | NDA (inferred; no public access route found) | everything at device level |
| Intel Foundry | 18A platform paper (VLSI 2025, *search*: RibbonFET GAA + PowerVia; >30 % density, ≈25 % performance or ≈36 % power vs Intel 3; later Intel briefs quote different bases) | customer portal | NDA (inferred) | everything at device level |
| GlobalFoundries 22FDX (FD-SOI) | press/conference summaries of back-bias capability (*search*) | customer | NDA | device data |
| imec | research publications (nanosheet, forksheet, CFET), not PDKs | — | — | not used numerically |
| IRDS (IEEE) | roadmap tables (More Moore) | IEEE IRDS site | free with registration (not confirmed) | tables not retrieved (search found nothing; site blocked) |

**Conclusion for the project.** SKY130 is the only manufacturable process for which every file needed to go from compact model to cell library to extracted layout could be read in full. Absolute numbers in this report are therefore SKY130 numbers, labelled with corner, voltage, temperature and netlist view. Leading-edge processes enter only as published, process-level claims. Those are vendor-reported, comparison-basis-dependent and not reproducible here, and are not used in any calculation.

## 4. The SKY130 document inventory against the brief (§7)

| # | Item requested | Present? | File(s) inspected | Notes |
|---|---|---|---|---|
| 1 | PDK documentation | yes | `google/skywater-pdk/docs/**` | maturity: "experimental preview / alpha release" |
| 2 | Transistor compact-model files | yes | `sky130_fd_pr/models/sky130.lib.spice`, `models/corners/*`, `cells/*/…pm3.spice` | sections tt, ss, ff, sf, fs, ll/hh/hl/lh, *_mm (mismatch), mc; plus `corners/leak.spice` and `corners/tt/leak.spice` model sets **not referenced by any section** |
| 3 | Device parameter documentation | partial | `docs/rules/device-details.rst` and tables | model vs e-test (EDR) Vth/Idsat windows for a few geometries; extraction method not stated |
| 4 | Design-rule manual | yes (periphery, layers) | `docs/rules/periphery*`, `docs/rules/layers*` | |
| 5 | Electrical-rule documentation | **no** | — | rule x.4 points to "Electrical DR … electromigration" not included |
| 6 | Standard-cell library documentation | partial | library READMEs; per-cell definitions | |
| 7 | Liberty timing and power | yes | `timing/sky130_fd_sc_hd__*.lib` | NLDM only; `switching_power_split_model: true`; characterised −40/25/100 °C, 1.28–1.95 V; HSPICE `sim_opt` strings indicate the characterisation simulator |
| 8 | Standard-cell LEF | yes | `cells/*/…lef` | |
| 9 | Technology LEF / extraction rules | yes | `tech/*.tlef`; open_pdks OpenRCX rules (min/nom/max) | |
| 10 | RC extraction technology files | yes (open) | Magic `sky130.tech` (preprocessed); OpenRCX rules | Magic ≥ 8.3.411 required; built 8.3.685 from source |
| 11 | Interconnect stack documentation | partial | `docs/rules/rcx/*.tsv` (sheet R: M1/M2 125, M3/M4 47, M5 29 mΩ/sq; li1 12.8 Ω/sq) | capacitance spreadsheet external |
| 12 | Reliability / operating limits | **no** (beyond model validity 0–1.95 V) | `device-details.rst` (model validity) | no EM, TDDB, BTI, HCI, T_j,max |
| 13 | Statistical model documentation | in the cards | `*_mismatch.corner.spice`, `parameters/critical.spice`, `montecarlo.spice` | mismatch: Gaussian, σ ∝ 1/√(WL) (A_VT 3.356 mV·µm nfet, 5.5 mV·µm pfet_hvt); process: Gaussian `AGAUSS` on named parameters |
| 14 | V/T operating conditions | yes (Liberty corners) | 16 NLDM corners | |
| 15 | Characterisation reports | **no** | — | which models/netlists produced the Liberty data is undocumented; this project's calibration supplies indirect evidence (D6 §6) |

## 5. What each SKY130 data set can be trusted for

| Use | Data | Verdict from this project |
|---|---|---|
| Conceptual analysis | all | yes |
| Relative architecture comparison | Liberty + gate-level simulation | yes. Same library, corner and stimulus for every design; ranking is robust to the documented Liberty/SPICE differences |
| Preliminary SPICE | BSIM4 cards + cell netlists | yes, **but use layout-extracted cells**. The repository's schematic netlists omit junction and wiring capacitance (−39 % energy at light load) and LOD stress (PMOS 13–30 % slower than Liberty) |
| Timing and power estimation | Liberty | yes at the characterised corners. **Leakage at 100 °C** in Liberty is 16× (tt) to 560× (ss) above the same-named SPICE model corner and close to the separate "leak" model set (D4 §5) |
| Post-layout analysis | Magic/OpenRCX + Liberty | yes for parasitics, with the OpenRCX accuracy reported by others (≈20 % total-capacitance error vs a field solver; input research file, not re-verified) |
| Manufacturing sign-off | — | **no**. Missing EM rules, reliability models and qualification; the kit is labelled experimental |
