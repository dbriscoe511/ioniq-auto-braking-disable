# In-car CAN captures, 2026-11-12

Panel plugged in, CANable 2.0 on CON1 pin 7/8, **listen-only (`M1`) only**;
nothing transmitted. 500 kbit/s classic CAN (`S6`). Summary and
interpretation: [docs/can-car-capture.md](../../docs/can-car-capture.md).

Logs are xz-compressed (`xz -dk *.xz`). `SHA256SUMS` covers the uncompressed
logs. Format is the same as the
[bench captures](../2026-11-09-bench-can/README.md): `<seconds> <slcan frame>`;
`T` lines are 29-bit IDs (`T` + 8 hex ID + DLC + data).

| File | Length | What happened (Dan) |
|---|---|---|
| `scan_S6.log` | 3 s | Bitrate scan while the car came up; 100k/125k/250k/1M got nothing (files dropped) |
| `baseline.log` | 30 s | Car on, in Park, no buttons |
| `buttons.log` | 75 s | Driver seat heat, then Parking Safety short presses; capture ended before the sequence finished |
| `buttons2.log` | 150 s | Rest of the sequence: Parking Safety short ×3, long ×1, wheel heat, camera, reverse a few times, heaters off |
| `stages.log` | 92 s | In reverse; short, long, gear stages, but the stage boundaries were not called out, so timing is unknown |
| `stage1_short.log` | 30 s | In reverse, Parking Safety short presses |
| `stage2_long.log` | 30 s | In reverse, Parking Safety long presses |
| `stage3_gear.log` | 30 s | Out of reverse and back in several times, muting the beep; one accidental long press |
| `screen_toggle.log` | 60 s | Car boot, then Parking Safety toggled off/on ×5 from the touchscreen settings menu (shows command `0x2A3`) |
| `monitor2.log` | 60 s | Idle monitor; gear change near the end, no screen toggle |

An earlier 45 s baseline captured nothing (car not yet on) and was overwritten.
