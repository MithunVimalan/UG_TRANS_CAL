"""Tests that need the pinned SKY130 files (skipped when PDK_ROOT is absent)."""
import os
import random
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ugcal.sim.ngspice import pdk_root  # noqa: E402

LIB = os.path.join(pdk_root(), "sc_hd", "timing", "sky130_fd_sc_hd__tt_025C_1v80.lib")
pytestmark = pytest.mark.skipif(not os.path.exists(LIB), reason="SKY130 Liberty not available (set PDK_ROOT)")


@pytest.fixture(scope="module")
def lib():
    from ugcal.liberty import Library
    return Library(LIB)


def test_liberty_header_and_values(lib):
    assert lib.units.cap == pytest.approx(1e-12)
    assert lib.units.time == pytest.approx(1e-9)
    assert lib.units.leakage == pytest.approx(1e-9)
    assert lib.op_voltage == 1.8 and lib.op_temperature == 25.0
    assert lib.thresholds["slew_lower_threshold_pct_rise"] == 20.0
    assert lib.pin_cap_F("sky130_fd_sc_hd__inv_1", "A") == pytest.approx(2.302e-15)
    assert lib.cell("sky130_fd_sc_hd__fa_1").area == pytest.approx(20.0192)
    assert lib.delay_s("sky130_fd_sc_hd__inv_1", "A", "Y", "rise", 0.01e-9, 0.0005e-12) == pytest.approx(20.3433e-12)
    e_r = lib.internal_energy_J("sky130_fd_sc_hd__inv_1", "Y", "A", "rise", 0.01e-9, 0.1812843e-12)
    e_f = lib.internal_energy_J("sky130_fd_sc_hd__inv_1", "Y", "A", "fall", 0.01e-9, 0.1812843e-12)
    assert e_r == pytest.approx(0.2980101e-12) and e_f == pytest.approx(-0.2943854e-12)


def test_cell_leakage_is_unweighted_state_mean(lib):
    c = lib.cell("sky130_fd_sc_hd__inv_1")
    mean = sum(v for _, v in c.leakage_states) / len(c.leakage_states)
    assert c.leakage == pytest.approx(mean, rel=1e-4)


def test_gatesim_zero_delay_toggles_match_bitsliced(lib):
    from ugcal.arith.multipliers import build
    from ugcal.arith.netlist import pack_inputs
    from ugcal.gatesim import GateLevel
    nl = build("dadda_rca", 6, signed=False)
    rnd = random.Random(3)
    vecs = [{"a": rnd.randrange(64), "b": rnd.randrange(64)} for _ in range(300)]
    gl = GateLevel(nl, lib)
    r = gl.simulate(vecs, 20e-9, "zero")
    ins = pack_inputs({"a": 6, "b": 6}, vecs)
    v = nl.simulate(ins, len(vecs))
    mask = (1 << (len(vecs) - 1)) - 1
    for net in range(2, len(nl.nets)):
        if net not in v:
            continue
        x = v[net]
        expected = bin((x ^ (x >> 1)) & mask).count("1")
        assert r.toggles[net] == expected


def test_glitch_modes_ordering(lib):
    from ugcal.arith.multipliers import build
    from ugcal.gatesim import GateLevel
    nl = build("array_rc", 6, signed=False)
    rnd = random.Random(4)
    vecs = [{"a": rnd.randrange(64), "b": rnd.randrange(64)} for _ in range(200)]
    gl = GateLevel(nl, lib)
    e = {m: gl.simulate(vecs, 20e-9, m).power()["total_J"] for m in ("zero", "inertial", "transport")}
    assert e["zero"] <= e["inertial"] <= e["transport"]


@pytest.mark.skipif(shutil.which("sta") is None, reason="OpenSTA not installed")
def test_power_matches_opensta(lib, tmp_path):
    """Same netlist, Liberty and activity -> ugcal.gatesim within 5% of OpenSTA."""
    import subprocess
    from ugcal.arith.multipliers import build
    from ugcal.arith.verilog import emit
    from ugcal.gatesim import GateLevel
    nl = build("dadda_rca", 8, signed=False)
    rnd = random.Random(9)
    vecs = [{"a": rnd.randrange(256), "b": rnd.randrange(256)} for _ in range(101)]
    gl = GateLevel(nl, lib)
    r = gl.simulate(vecs, 20e-9, "inertial", trace=True)
    p = r.power()
    r.write_vcd(str(tmp_path / "d.vcd"))
    (tmp_path / "d.v").write_text(emit(nl, "top"))
    (tmp_path / "r.tcl").write_text(f"""read_liberty {LIB}
read_verilog {tmp_path / 'd.v'}
link_design top
create_clock -name v -period 20
set_load 0.005 [all_outputs]
set_input_transition 0.05 [all_inputs]
read_vcd -scope tb/dut -begin_time 20000 {tmp_path / 'd.vcd'}
report_power -digits 8
""")
    out = subprocess.run(["sta", "-no_init", "-exit", str(tmp_path / "r.tcl")], capture_output=True, text=True).stdout
    tot = [l for l in out.splitlines() if l.startswith("Total")][0].split()
    sta_total = float(tot[4])
    py_total = (p["total_J"] - p["switching_inputs_J"]) / r.T
    assert py_total == pytest.approx(sta_total, rel=0.05)
