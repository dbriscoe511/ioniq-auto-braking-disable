# Firmware: Parking Safety auto-disable (ESP32-C3 SuperMini)

ESP-IDF firmware for the add-on board in
`hardware/esp32c3-recovery/` (schematic on branch
`t3/esp32c3-recovery-kicad-schematic`, commit `a5637be`). Once per drive it
long-presses the Parking Safety button (CON1 pin 5) if the car reports
auto-brake **on**, then checks that it turned **off**.

**Status: builds and passes host tests against the recorded car captures.
Not yet run on hardware.**

## What it does

1. **Listens only.** TWAI runs in listen-only mode with no transmit queue,
   and GPIO5 holds the CAN Pal's S pin high (transmitter off). There is no
   transmit call anywhere in the code. Only `0x05C17002` passes the hardware filter.
2. **Waits for a drive.** A drive starts when `0x05C17002` appears (10 Hz) and
   ends when it has been missing for 3 s. Power-on alone never triggers a press,
   because the panel is also powered with the car off. **Unmeasured:** every
   capture starts with the status already present, so nobody has yet seen it
   appear or stop. If it keeps running through a stop and restart while the
   panel stays powered, the latch never clears and that drive gets no press.
3. **Settles for 4 s**, then decides:
   - byte 1 = `07` at any point this drive → **done** (already off, or you
     turned it off yourself).
   - byte 1 = `09` for ≥ 1 s (10 frames, latest < 300 ms old), and the button
     line released for ≥ 0.5 s → **press**.
   - anything else (unknown value, stale status) → keep waiting, no press.
4. **Press:** GPIO10 high for up to 3 s. It releases early as soon as `07`
   shows. A hardware timer forces release at 3.5 s whatever the loop is
   doing, and the task watchdog (5 s) resets the chip if the loop hangs.
5. **Verify:** waits 3 s for a stable `07`. If it still reads `09`, it waits
   2 s and retries **once** (again only on a fresh, stable `09`), then gives up.
6. **Done for this drive.** If you long-press it back on, it is left alone
   until the next drive (status gone ≥ 3 s). The latch survives software
   resets (OTA reboot, watchdog, crash) in RTC memory, but **not** a brownout
   or power loss. After one of those mid-drive, a manual re-enable would be
   undone once.

It also flags `fault_no_sense` if its own press never pulls the sense line
low (wiring problem).

## Button gestures (your own short presses, read through the 100k/27k divider)

| Gesture | Effect |
|---|---|
| **4 quick taps** (each ≤ 0.6 s, gaps ≤ 0.6 s) | Toggle automation on/off (saved in flash, takes effect next drive) |
| **6 quick taps** | Open the Wi-Fi window for 5 min |

Taps only count while `0x05C17002` is on the bus (car awake), since pin 5's
level with the car off is unmeasured. Even tap counts leave the beep state
where it was. A single tap to mute the
beep, or taps more than 0.6 s apart, never add up to a gesture. Any press
longer than 0.6 s cancels the sequence.

## Wi-Fi / OTA

- The AP `ps-disable-xxxx` (WPA2) is up for **60 s after every power-on**, so
  recovery doesn't depend on the gesture code. It stays up while a client is
  connected (15 min cap) and is otherwise off, which keeps the 7805 cool.
- Page at `http://192.168.4.1/`: live status, enable/disable buttons, firmware upload.
- Upload from the command line:
  `curl --data-binary @.pio/build/supermini/firmware.bin http://192.168.4.1/ota`
- **Rollback:** a new image has 30 s to prove itself. It is confirmed only if
  the recovery AP and web server came up. If they didn't, or it crashes or
  resets first, the bootloader returns to the previous image.
- Uploads are refused while it's pressing, and the reboot after an upload
  waits for any press to finish. A stalled upload is dropped after 30 s.
- The password is not in git. Set it at build time:
  `PS_AP_PASS='something-long' pio run`. The build fails if it's shorter than 8.

## Build, flash, test

```sh
uv tool install platformio                     # once
PS_AP_PASS='...' pio run                        # build
PS_AP_PASS='...' pio run -t upload              # flash over USB (hold BOOT if needed)
pio device monitor                              # logs (USB or UART0 on GPIO20/21)
host_test/run.sh                                # logic tests, no hardware
```

`host_test/run.sh` runs `src/logic.c` against a simulated parking module
(toggles during a 2 s hold, or on release after one) and replays every log in
`captures/2026-11-12-car-can/`. On the replays it checks that it never presses
on `07` or unknown values and never presses more than twice.

## Pins

| GPIO | Use |
|---|---|
| 3 (ADC1) | Button sense: pressed < 0.9 V, released > 1.3 V |
| 5 | CAN Pal S (silent), always driven high |
| 6 | CAN Pal TX: assigned to the driver, never used |
| 7 | CAN Pal RX |
| 10 | Press output (NPN pulls CON1-5 to GND via 200 Ω) |

## Tunables (`src/config.h`) and guesses to check in the car

- `SETTLE_MS` = 4 s after the status first appears. **A guess:** how soon the
  parking module accepts a long press after start-up hasn't been measured. If
  the first press is sometimes ignored, the retry covers it; raise this if
  logs show that happening.
- `HOLD_MS` = 3 s (needs > 2 s). The press releases early on `07`.
- Sense thresholds assume the pressed voltage at pin 5 is near 0 V. That
  hasn't been measured; check `sense_mv` on the status page while holding the
  button.
- Capture to get next: car off → start → shut down → wait → restart, logging
  continuously, to see when `0x05C17002` appears and stops relative to panel
  power. That would confirm `STATUS_GONE_MS`.
- Bench check: with the panel on the bench there is no `0x05C17002`, so the
  board stays in `wait_status` and never presses.
