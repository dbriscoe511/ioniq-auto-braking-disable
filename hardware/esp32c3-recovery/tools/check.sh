#!/usr/bin/env bash
# Regenerate, run ERC, export netlist/PDF/SVG and diff nets against expectations.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 tools/gen.py
mkdir -p out
erc_ok=0
kicad-cli sch erc --severity-all --exit-code-violations --format report -o out/erc.rpt esp32c3-recovery.kicad_sch || erc_ok=$?
kicad-cli sch export netlist --format kicadsexpr -o out/netlist.net esp32c3-recovery.kicad_sch
python3 tools/check_nets.py out/netlist.net
python3 tools/check_lib.py esp32c3-recovery.kicad_sch esp32c3_recovery.kicad_sym esp32c3_recovery
kicad-cli sch export pdf -o out/esp32c3-recovery.pdf esp32c3-recovery.kicad_sch
kicad-cli sch export svg -o out/ esp32c3-recovery.kicad_sch
pdftoppm -r 150 -png -singlefile out/esp32c3-recovery.pdf out/esp32c3-recovery
cat out/erc.rpt
if [ "$erc_ok" -ne 0 ]; then echo "ERC FAILED"; exit 1; fi
echo "ALL CHECKS PASSED"
