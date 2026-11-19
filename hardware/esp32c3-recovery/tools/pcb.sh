#!/usr/bin/env bash
# Build the PCB: place -> Freerouting -> pours/silk -> DRC -> JLC outputs.
# Needs Java 25+ and a freerouting 2.x jar: set JAVA and FREEROUTING if not on PATH.
set -euo pipefail
cd "$(dirname "$0")/.."
JAVA=${JAVA:-java}
FREEROUTING=${FREEROUTING:?set FREEROUTING to the freerouting jar}
./tools/check.sh >/dev/null           # schematic + netlist first
python3 tools/gen_pcb.py place
# Freerouting is multithreaded and not always deterministic: retry while results
# vary. A leftover GND link is fine (the pours join it; DRC below is the check).
prev=
for try in 1 2 3 4 5 6; do
    log=$("$JAVA" -jar "$FREEROUTING" -de out/pcb/board.dsn -do out/pcb/board.ses -mp 200 \
        --gui.enabled=false 2>&1 | grep "session completed")
    echo "route try $try: $(echo "$log" | grep -oE 'final score: [0-9.]+( \([0-9]+ unrouted\))?')"
    echo "$log" | grep -q unrouted || break
    res=$(echo "$log" | grep -oE 'final score: [0-9.]+( \([0-9]+ unrouted\))?')
    [ "$res" = "$prev" ] && break
    prev=$res
done
python3 tools/gen_pcb.py finish
kicad-cli pcb drc --schematic-parity --severity-all --format report \
    -o out/pcb/drc.rpt esp32c3-recovery.kicad_pcb >/dev/null
grep -E "^\*\* Found" out/pcb/drc.rpt
python3 tools/gen_pcb.py fab
kicad-cli pcb export pdf --layers F.Cu,F.Fab,Edge.Cuts --mode-single \
    -o out/esp32c3-recovery-pcb-top.pdf esp32c3-recovery.kicad_pcb >/dev/null
kicad-cli pcb export pdf --layers B.Cu,F.Fab,Edge.Cuts --mode-single \
    -o out/esp32c3-recovery-pcb-bottom.pdf esp32c3-recovery.kicad_pcb >/dev/null
# README images: copper top over bottom (rendered 2D), 3D top and 3D angled
for side in top bottom; do
    if [ $side = top ]; then L=F.Cu,F.SilkS,Edge.Cuts; else L=B.Cu,B.SilkS,Edge.Cuts; fi
    kicad-cli pcb export svg --layers "$L" --mode-single --fit-page-to-board \
        --exclude-drawing-sheet -o out/pcb/$side.svg esp32c3-recovery.kicad_pcb >/dev/null 2>&1
    rsvg-convert -w 1400 -b white out/pcb/$side.svg -o out/pcb/$side.png
done
magick out/pcb/top.png out/pcb/bottom.png -append out/esp32c3-recovery-pcb.png
kicad-cli pcb render --side top --quality high --width 1600 --height 900 \
    -o out/esp32c3-recovery-pcb-3d.png esp32c3-recovery.kicad_pcb >/dev/null 2>&1
kicad-cli pcb render --quality high --width 1600 --height 1000 --rotate '-45,0,-25' --zoom 1.1 \
    -o out/esp32c3-recovery-pcb-3d-angle.png esp32c3-recovery.kicad_pcb >/dev/null 2>&1
echo "images in out/"
