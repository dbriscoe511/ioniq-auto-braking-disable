# Bench CAN captures, 2026-11-09

Panel on the bench, 12 V on CON1 pin 1/16, CANable 2.0 on CON1 pin 7/8.
Summary and interpretation: [docs/can-bench-capture.md](../../docs/can-bench-capture.md).

## Files

| File | Mode | What happened |
|---|---|---|
| `scan_S3/S4/S5/S6/S8.log` | listen-only, 1.5 s each | Bitrate scan; only `S6` (500k) received frames |
| `boot_silent.log` | listen-only, 12 s | Power cycle, idle |
| `boot_normal.log` | normal (ACK), 20 s | Power cycle, idle |
| `parking_btn.log` | normal, 90 s | Parking Safety 3 short, 3 × ~3 s |
| `parking_btn2.log` | normal, 90 s | Power cycle, then the same presses |
| `other_btns.log` | normal, 30 s | Several buttons; which ones not recorded |
| `five_btns.log` | normal, 30 s | Driver seat, wheel, camera, Parking Safety, passenger seat, twice each |
| `seat_heat.log` | normal, 15 s | Both seat heat buttons, twice each |
| `slcan.py` | | Capture script (no transmit path) |
| `psu.py` | | DP932E status/on/off/cycle helper |

slcan bitrate codes: `S3` 100k, `S4` 125k, `S5` 250k, `S6` 500k, `S8` 1M.

## Log format

`<seconds since capture start> <slcan frame>`, e.g. `2.2589 t45184400000000000000`
= standard ID `451`, DLC `8`, data `44 00 00 00 00 00 00 00`.

Timestamps are taken when the host reads the serial port, with a 50 ms read
timeout. Intervals below ~50 ms are not resolved.

## Checksums (SHA-256)

```
6c4ed601a906d96d28a1389ac25c36d1a2a1f5afb131c65c328322db228647a5  boot_normal.log
06e108034903a3c1b1312ad7a2dafd0ae8284a020c6282ea60fe03fa08b653cf  boot_silent.log
387bd0079949654f9820aa9bc1aca2771fb0657417acc2736b2cdfd37b46e0d0  five_btns.log
f023d4a0f9c1c79249525cdcb51cd1717faf90934c4d42eae983334b01c0dbe3  other_btns.log
7c43b9436a30288f9ccbc0dd27336169c7a40a361658136ef57c333177aac081  parking_btn2.log
48bfca90ae1f233d7b3aab9be9c82688775b90d4b64750e1ffb4d3a188c3b3b5  parking_btn.log
fe0f543ddb349d5d83ff71121a3eca01d9dda7715cb0b148923e6a0e32327924  scan_S6.log
84641b781a5a01053c9c6a7d9ecd85f92bdc98b8b2316f3446687ad31b0452cc  seat_heat.log
```

The other scan logs are empty.
