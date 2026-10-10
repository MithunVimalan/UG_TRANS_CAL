#!/usr/bin/env bash
# Fetch the SKY130 files used by this project at pinned commits.
# Only the subsets needed (Liberty corners, cell netlists/Verilog/LEF,
# FET model cards) are checked out, using blobless sparse clones.
#
# Usage: PDK_ROOT=/path/to/pdk sim/pdk/fetch_pdk.sh
set -euo pipefail
PDK_ROOT="${PDK_ROOT:-$HOME/pdk}"
SC_HD_COMMIT=9cb2d7cb8ed4619094263614039a61b6b2d22a88   # fossi-foundation/skywater-pdk-libs-sky130_fd_sc_hd
FD_PR_COMMIT=16f93a795d87ea2b393fe5c74d32674e111e44a2   # fossi-foundation/skywater-pdk-libs-sky130_fd_pr
mkdir -p "$PDK_ROOT"; cd "$PDK_ROOT"

if [ ! -d sc_hd ]; then
  git clone --filter=blob:none --no-checkout \
    https://github.com/fossi-foundation/skywater-pdk-libs-sky130_fd_sc_hd sc_hd
fi
( cd sc_hd
  git sparse-checkout init --no-cone
  git sparse-checkout set '/timing/*.lib' '/tech/*' '/README*' '/LICENSE' \
     '/cells/*/*.spice' '/cells/*/*.functional.v' '/cells/*/*.functional.pp.v' \
     '/cells/*/*.timing.v' '/cells/*/*.behavioral.v' '/cells/*/*.lef' '/models/*/*.v'
  git checkout -q "$SC_HD_COMMIT" )

if [ ! -d fd_pr ]; then
  git clone --filter=blob:none --no-checkout \
    https://github.com/fossi-foundation/skywater-pdk-libs-sky130_fd_pr fd_pr
fi
( cd fd_pr
  git sparse-checkout init --no-cone
  git sparse-checkout set '/models/' '/README*' '/LICENSE' '/cells/*/*.spice' '/cells/*/*.csv'
  git checkout -q "$FD_PR_COMMIT" )

echo "PDK subsets at $PDK_ROOT"
echo "  sc_hd @ $(git -C sc_hd rev-parse HEAD)"
echo "  fd_pr @ $(git -C fd_pr rev-parse HEAD)"
