#!/usr/bin/env python3
"""Layout-extract sky130_fd_sc_hd cells from the foundry GDS with Magic.

The cell ``.spice`` netlists in the library repository are schematic
netlists: transistors carry W and L only (no source/drain area or perimeter,
so no junction capacitance) and there is no wiring capacitance.  The foundry
Liberty data were characterised on something closer to layout.  This script
produces layout-extracted cell netlists:

  * Magic (built from source, >= 8.3.411 required by the open_pdks tech file)
  * tech file: open_pdks sky130/magic/sky130.tech preprocessed for sky130A
  * extraction: ``extract all``; ``ext2spice cthresh 0 rthresh 0`` (all
    capacitances kept, no resistance extraction), so devices get AD/AS/PD/PS
    and every coupling/ground capacitance appears as an explicit C element.
    (Note: ``ext2spice lvs`` alone sets the thresholds to infinity and would
    drop all parasitics.)

STI-stress (LOD) instance parameters (sa, sb, sd) are NOT produced by this
extraction; see sim/spice/calibrate_cells.py --lod for a sensitivity test.

Usage: PDK_ROOT=~/pdk MAGIC=/path/to/magic python3 sim/pdk/extract_cells.py
Output: build/cells_ext/<cell>.spice and build/sky130_fd_sc_hd_ext.spice
"""
import os
import subprocess
import sys

CELLS = ["inv_1", "buf_1", "nand2_1", "nor2_1", "and2_1", "or2_1", "xor2_1", "xnor2_1", "and3_1",
         "a21o_1", "a21oi_1", "o21ai_1", "maj3_1", "xor3_1", "mux2_1", "ha_1", "fa_1", "dfxtp_1",
         "dfrtp_1", "dlclkp_1", "clkbuf_1", "conb_1"]


def main():
    pdk = os.path.expanduser(os.environ.get("PDK_ROOT", "~/pdk"))
    magic = os.environ.get("MAGIC", "magic")
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    build = os.path.join(repo, "build")
    tech = os.path.join(build, "sky130A.tech")
    if not os.path.exists(tech):
        op = os.path.join(pdk, "open_pdks", "sky130")
        subprocess.run([sys.executable, os.path.join(op, "..", "common", "preproc.py"),
                        "-DTECHNAME=sky130A", "-DREVISION=unknown", "-DMETAL5", "-DMIM", "-DREDISTRIBUTION",
                        "-DMAGIC_CURRENT=8.3.685", os.path.join(op, "magic", "sky130.tech"), tech], check=True)
    outdir = os.path.join(build, "cells_ext")
    os.makedirs(outdir, exist_ok=True)
    combined = []
    for cell in CELLS:
        base = cell.rsplit("_", 1)[0]
        gds = os.path.join(pdk, "sc_hd", "cells", base, f"sky130_fd_sc_hd__{cell}.gds")
        if not os.path.exists(gds):
            print(f"skip {cell}: no GDS")
            continue
        name = f"sky130_fd_sc_hd__{cell}"
        script = os.path.join(outdir, f"{cell}.tcl")
        with open(script, "w") as fh:
            fh.write(f"""tech load {tech}
gds read {gds}
load {name}
select top cell
extract all
ext2spice lvs
ext2spice cthresh 0
ext2spice rthresh 0
ext2spice -o {os.path.join(outdir, cell + '.spice')}
quit -noprompt
""")
        r = subprocess.run([magic, "-dnull", "-noconsole", script], cwd=outdir, capture_output=True, text=True,
                           timeout=300)
        path = os.path.join(outdir, cell + ".spice")
        if not os.path.exists(path):
            print(r.stdout[-2000:], r.stderr[-2000:])
            raise SystemExit(f"extraction failed for {cell}")
        txt = open(path).read()
        ndev = sum(1 for l in txt.splitlines() if l.startswith("X"))
        ncap = sum(1 for l in txt.splitlines() if l.startswith("C"))
        print(f"{cell}: {ndev} devices, {ncap} capacitors")
        combined.append(txt)
    with open(os.path.join(build, "sky130_fd_sc_hd_ext.spice"), "w") as fh:
        fh.write("* Layout-extracted sky130_fd_sc_hd cells (Magic, cthresh 0, no R)\n")
        fh.write("\n".join(combined))


if __name__ == "__main__":
    main()
