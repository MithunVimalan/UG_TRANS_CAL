# UG_TRANS_CAL — Physical and thermodynamic limits of transistors, multipliers, MAC units and AI accelerators

A source-backed, reproducible study of how close a CMOS multiplier or MAC comes to the physical and technological limits of energy per operation, throughput and power density. It is carried out end to end on the open SkyWater **SKY130** process: foundry compact models → transistor-level SPICE → standard cells → multiplier and MAC netlists → glitch-aware power → arrays → heat.

Every number carries an evidence class (A–I, plus S for design specifications) and a source. Missing parameters are reported, never substituted.

**Start with the [executive summary](docs/report/D01_executive_summary.md)** and the [research map](docs/report/00_research_map.md).

## Report (docs/report)

| | Deliverable |
|---|---|
| [00](docs/report/00_research_map.md) | Research map: questions, calculations, exact inputs and their sources |
| [D1](docs/report/D01_executive_summary.md) | Executive summary |
| [D2](docs/report/D02_physical_hierarchy.md) | Physical hierarchy from fundamental physics to accelerators |
| [D3](docs/report/D03_fundamental_limits.md) | Fundamental limit catalogue (Landauer, information content of multiplication/MAC, kT/C, SS, minimum supply, quantum speed limits) |
| [D4](docs/report/D04_transistor_parameters.md) | Transistor parameter database (`data/sky130/parameter_database.csv`, 351 rows) and SPICE characterisation |
| [D5](docs/report/D05_foundry_pdk_catalogue.md) | Foundry and PDK catalogue: public / registration / NDA / unavailable |
| [D6](docs/report/D06_derivations.md) | Derivations: switching energy, power, delay, leakage, heat, electro-thermal coupling |
| [D7](docs/report/D07_multiplier_comparison.md) | Controlled multiplier comparison (array, Braun, Wallace, Dadda, Booth, Baugh–Wooley; 4 final adders; Yosys baseline; adders) with transistor-level arbitration |
| [D8](docs/report/D08_mac_model.md) | MAC energy accounting without double counting, array and data-movement model, same-process post-route reference |
| [D9](docs/report/D09_thermal_model.md) | Thermal model and sustainable-throughput envelope |
| [D10](docs/report/D10_calculation_framework.md) | Calculation framework, API, validation and reproduction |
| [D11](docs/report/D11_benchmarking_procedure.md) | Benchmarking procedure and evidence ladder |
| [D12](docs/report/D12_evidence_audit.md) | Evidence and uncertainty audit; quality-control checklist |
| [D13](docs/report/D13_research_gaps.md) | Missing parameters, inaccessible documents, open questions |
| [D14](docs/report/D14_roadmap.md) | 17-step workflow status and staged roadmap to silicon |
| [D15](docs/report/D15_bibliography.md) | Bibliography (generated from `data/sources.yaml`) |

## Repository layout

```
ugcal/            provenance-aware calculation package (units, evidence classes, physics, Liberty,
                  gate-level glitch simulator, arithmetic generators, MAC/array/thermal models, uncertainty)
sim/pdk/          fetch SKY130 at pinned commits, slim model library, Magic cell extraction
sim/spice/        ngspice studies: devices, cell calibration, leakage, VDD sweep, whole multipliers
sim/gatelevel/    multiplier/adder/MAC studies, functional verification, OpenSTA cross-check
sim/synth/        Yosys/ABC baselines
sim/envelope/     fundamental floors, array and thermal envelopes
tools/            parameter database, report tables, bibliography
examples/         worked example: sourced parameters -> MAC performance envelope
data/             parameter database, source catalogue
results/          every CSV/table the report is generated from
tests/            validation tests (pytest)
```

## Reproducing

Requirements: Python 3 (tested with 3.13), `pytest`, `numpy` (one test), PyYAML (bibliography only), ngspice 42, Yosys 0.33, Magic ≥ 8.3.411 (8.3.685 used), and OpenSTA (3.1.0 used). The full command sequence is in [D10 §6](docs/report/D10_calculation_framework.md). Quick checks:

```bash
python3 -m pytest -q                       # core tests; PDK tests run when $PDK_ROOT is set
python3 examples/mac_envelope_example.py   # provenance-tracked envelope of a 1000-PE int8 MAC array
bash sim/pdk/fetch_pdk.sh                  # SKY130 files at pinned commits into $PDK_ROOT
python3 tools/make_report_tables.py        # regenerate every table in the report from results/
```

## Key results (SKY130 HD, tt, 25 °C, 1.8 V unless stated)

* Thermodynamic floor of an int8 MAC that discards its operands: 4.6 × 10⁻²⁰ J. The best pre-layout MAC built here: 4.97 pJ, about 10⁸ higher.
* 8×8 multipliers: 1.58–4.81 pJ and 3.47–8.86 ns across architectures. Glitches are the dominant architecture-dependent term. Whole-multiplier SPICE (six designs) lies at 1.19–1.37× the inertial gate-level estimate and preserves the ranking.
* Radix-4 Booth costs more energy than Baugh–Wooley in this library. Operand statistics change energy by up to 6.5×.
* Registers and clock pins are about half or more of the energy of the lowest-energy MACs. A same-process post-route array costs 2.6–3.9× our pre-layout PEs.
* Throughput is package-limited: 0.18–2.7 TOPS for θ_JA = 10–60 K/W, with T_j ≤ 100 °C (the characterisation limit).

## Limitations

Pre-layout only for this project's own designs; no silicon. Foundry reliability data are not public. The container's network policy blocked publisher sites, arXiv and most documentation hosts, so bibliographic facts were confirmed via a search service and no paper's full text was opened (D13, D15).
