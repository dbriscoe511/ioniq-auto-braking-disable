#!/usr/bin/env bash
# Build here, flash the C3 plugged into labrador-pie over USB, then show its log.
#   tools/flash_pi.sh            build + flash + 20 s of log
#   tools/flash_pi.sh --log 60   just watch the log for 60 s
# Needs: src/secrets.h (tools/make_secrets.py); esptool on the Pi
# (uv tool install esptool); the C3 on the Pi's USB (native USB-Serial-JTAG).
set -euo pipefail
PI=${PI:-labrador-pie}
PORT=${PORT:-/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_*}
here="$(cd "$(dirname "$0")/.." && pwd)"
remote=/tmp/ps-disable-flash
log_secs=20

monitor() {
    # pyserial ships with esptool's environment on the Pi.
    ssh "$PI" "~/.local/share/uv/tools/esptool/bin/python - $1" <<'PY'
import glob, sys, time, serial
port = sorted(glob.glob("/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_*"))[0]
end = time.time() + float(sys.argv[1])
s = serial.Serial(port, 115200, timeout=0.2)
while time.time() < end:
    d = s.read(4096)
    if d: sys.stdout.write(d.decode("utf-8", "replace")); sys.stdout.flush()
PY
}

if [[ ${1:-} == --log ]]; then monitor "${2:-30}"; exit; fi

pio=$(command -v pio || echo ~/.local/bin/pio)
(cd "$here" && "$pio" run)
b="$here/.pio/build/supermini"
ssh "$PI" "mkdir -p $remote"
scp -q "$b/bootloader.bin" "$b/partitions.bin" "$b/ota_data_initial.bin" "$b/firmware.bin" "$PI:$remote/"
# ESP32-C3 offsets: bootloader 0x0, partition table 0x8000, otadata 0xe000,
# app ota_0 0x20000 (partitions.csv). Writing otadata resets boot to ota_0.
ssh "$PI" "~/.local/bin/esptool.py --chip esp32c3 -p \$(ls $PORT | head -1) -b 460800 \
    --before default_reset --after hard_reset write_flash -z \
    0x0 $remote/bootloader.bin 0x8000 $remote/partitions.bin \
    0xe000 $remote/ota_data_initial.bin 0x20000 $remote/firmware.bin && rm -rf $remote"
sleep 2 # USB re-enumerates after the reset
monitor "$log_secs"
