# Firmware: Parking Safety auto-disable (ESP32-C3 SuperMini)

ESP-IDF firmware for the add-on board in `hardware/esp32c3-recovery/`
(schematic on branch `t3/esp32c3-recovery-kicad-schematic`, commit
`a5637be`). It does two things through the Parking Safety button (CON1 pin 5):

- **Auto-brake:** once per drive, a long press if the car reports it on.
- **Reverse beep:** a short press each time reverse turns the warning sound on.

**Status: builds, and passes host tests against a simulated parking module
and the recorded car captures. Not yet run on hardware.**

## Inputs

- **CAN, listen-only.** `0x05C17002` (10 Hz): byte 1 `09`/`07` = auto-brake
  on/off; byte 0 bit 0 = warning sound on. TWAI is in listen-only mode with no
  transmit queue, GPIO5 holds the CAN Pal's S pin high (transmitter off), and
  there is no transmit call in the code. The hardware filter passes only this ID.
- **Button monitor.** GPIO3 reads pin 5 through the 100k/27k divider, so the
  firmware sees your presses directly (its own presses are masked out). That
  replaces any guessing about who changed what.

## Auto-brake (once per drive)

`wait_status → settling (4 s) → armed → pressing → verify → done`

- A **drive** starts when `0x05C17002` appears and ends when it has been gone
  for 3 s. Power-on alone never presses (the panel is also powered with the car off).
- **armed:** reads `07` → done. Reads `09` for 1 s and the button has been
  released ≥ 0.5 s → long press (GPIO10 high, up to 3 s; released early as
  soon as `07` shows).
- **verify:** `07` within 3 s → done. Otherwise back to armed for **one** retry,
  then give up.
- **You win:** if you long-press the button yourself (≥ 1.5 s) at any point in
  the drive, it stands down until the next drive. Short taps (the beep) don't count.
- A reset mid-drive (OTA reboot, watchdog) keeps the "done" latch in RTC
  memory. A brownout or power loss doesn't.

## Reverse beep (every time)

When byte 0 bit 0 turns on, it taps the button for 300 ms, once. A short
press only toggles the sound; auto-brake isn't affected.

- **You win:** if your own press came within 1 s before it turned on, you
  turned it on, so it's left alone (until it next goes off and on).
- It only taps right after the bit turns on, so it can't turn the sound on.
  If the tap doesn't take, it stays on; there's no retry, so it can never fight you.
- It waits for a long press in progress and for 0.5 s of button idle.
  Otherwise it taps about 0.1 s after the bit changes.
- Toggle on the web page ("mute reverse beep", default on, saved in flash).

## Safety backstops

- A hardware timer forces the button released at 3.5 s.
- If the loop hangs, the task watchdog (5 s) resets the chip; the 10k base
  pull-down keeps the NPN off through reset.
- `fault_no_sense` is flagged if a press of ours never pulls the line low.

## Button gestures

Counted only while the car is awake (status on the bus).

| Gesture | Effect |
|---|---|
| **4 quick taps** (each ≤ 0.6 s, gaps ≤ 0.6 s) | Automation on/off (both jobs; saved in flash) |
| **6 quick taps** | Turn Wi-Fi on for an update (below) |

Even counts leave the beep where it was. Taps more than 0.6 s apart, or any
press longer than 0.6 s, never add up to a gesture.

## Low power: Wi-Fi off, Bluetooth not built in

Per the LDO discussion: the 7805 drops ~9 V. At ~25–30 mA (CAN only) that's
about 0.3 W. With Wi-Fi on (~80–120 mA) it's 1–1.5 W, which gets hot in a
closed console. So:

- **Wi-Fi is off by default.** 6 taps turn it on. It turns itself off after
  2 min with nobody connected, and after 10 min regardless.
- **Bluetooth is compiled out**, and the CPU runs at 80 MHz.
- **Recovery now depends on the gesture.** If a bad build broke the button
  sense or the gesture code, the only way back is USB, which means opening
  the console. Rollback (below) guards against that for OTA updates.

## Update over Wi-Fi

1. In the car (awake), tap the Parking Safety button 6 times quickly.
2. Join `ps-disable-xxxx` (WPA2, password set at build time) and open
   `http://192.168.4.1/`. It shows live status, the two switches and a firmware upload.
   Or from a terminal:
   `curl --data-binary @.pio/build/supermini/firmware.bin http://192.168.4.1/ota`
3. **Rollback:** the new image starts Wi-Fi itself on first boot. It is
   confirmed only if that works and it runs for 30 s. Otherwise the
   bootloader goes back to the old image.

Uploads are refused while the board is pressing, the reboot waits for a press
to finish, and a stalled upload is dropped after 30 s.

## Build, flash, test

```sh
uv tool install platformio                     # once
PS_AP_PASS='...' pio run                        # build (fails if PS_AP_PASS < 8 chars)
PS_AP_PASS='...' pio run -t upload              # flash over USB (hold BOOT if needed)
pio device monitor                              # logs (USB, or UART0 on GPIO20/21)
host_test/run.sh                                # logic tests, no hardware
```

`host_test/run.sh` runs `src/logic.c` two ways:
- **Against a simulated parking module.** Its variants: toggling during the
  hold, toggling on release, ignoring presses, and reporting the beep late.
- **Against every log in `captures/2026-11-12-car-can/`.** Your long presses
  are reconstructed from the `07`/`09` changes. It checks that it never
  long-presses on `07` or on a drive you changed yourself, never more than
  twice, and never taps while the beep bit is off.

## Pins

| GPIO | Use |
|---|---|
| 3 (ADC1) | Button monitor: pressed < 0.9 V, released > 1.3 V |
| 5 | CAN Pal S (silent), always driven high |
| 6 | CAN Pal TX: assigned to the driver, never used |
| 7 | CAN Pal RX |
| 10 | Press output (NPN pulls CON1-5 to GND via 200 Ω) |

## Unmeasured, to check in the car (tunables in `src/config.h`)

- **Drive boundary.** Every capture starts with `0x05C17002` already present.
  If it keeps running through a stop and restart with the panel powered,
  that drive gets no auto-brake press. To find out, log car off → start → off → restart.
- **`SETTLE_MS` = 4 s.** How soon the module accepts a long press after
  start-up is a guess; the retry covers an early one.
- **Whether a 300 ms tap counts as a short press**, and how fast the beep bit follows.
- **Pressed voltage on pin 5.** Thresholds assume near 0 V. Check `sense_mv`
  on the status page while holding the button.
