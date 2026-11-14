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
- **You win:** if auto-brake changes while you're pressing the button, or
  within 1 s after, that was you, so it stands down until the next drive.
  Your press only counts if it started with the car awake; a line already low
  at wake-up isn't you. Holding too briefly to toggle it changes nothing.
- A reset mid-drive (OTA reboot, watchdog) keeps the "done" latch in RTC
  memory. A brownout or power loss doesn't.

## Reverse beep (every time)

When byte 0 bit 0 turns on, it taps the button for 300 ms, once. A short
press only toggles the sound; auto-brake isn't affected.

- **You win:** if it turned on during your press or within 1 s after, you
  turned it on, so it's left alone until it next goes off and on.
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

| Gesture | Effect |
|---|---|
| **4 quick taps** (each ≤ 0.6 s, gaps ≤ 0.6 s) | Automation on/off (both jobs; saved in flash). Only while the car is awake. |
| **6 quick taps** | Reopen Wi-Fi for 2 min (below). Works with or without CAN. |

Even counts leave the beep where it was. Taps more than 0.6 s apart, or any
press longer than 0.6 s, never add up to a gesture.

## Wi-Fi: 60 s after power-on, otherwise off

The 7805 drops ~9 V. At ~25–30 mA (CAN only) that's about 0.3 W; with Wi-Fi
on (~80–120 mA) it's 1–1.5 W, which gets hot in a closed console. So Wi-Fi is
up only in short windows:

- **60 s after every power-on.** This is the way in that doesn't depend on
  the button code.
- **6 quick taps** reopen it for 2 min (works without CAN, e.g. on the bench).
- Any page load or request keeps it open; it closes 10 min after opening at most.
- **Bluetooth is compiled out.** The CPU runs at 80 MHz.

While the window is open the board is reachable two ways (same page):

- **Its own AP** `ps-disable-xxxx` (WPA2) at `http://192.168.4.1/` (in the car).
- **Your home Wi-Fi** (if configured): it joins as `ps-disable` and logs its
  IP; the status JSON shows it as `home_ip`. At home that's the easy route.

The page has live status, automation on/off, mute/keep the reverse beep, and
a firmware upload. Or upload from a terminal:
`curl --data-binary @.pio/build/supermini/firmware.bin http://<ip>/ota`

**Rollback:** a new image is kept once it has run 30 s with its Wi-Fi up.
If it crashes or resets before then, the bootloader goes back to the old
image. Uploads are refused while the board is pressing, the reboot waits for
a press to finish, and a stalled upload is dropped after 30 s.

## Build, flash, test

Credentials live in `src/secrets.h`, which is gitignored and generated:

```sh
PS_AP_PASS='8+ chars' PS_STA_SSID='home' PS_STA_PASS='...' tools/make_secrets.py
#   (or --ap-pass-file/--sta-ssid-file/--sta-pass-file; home network optional)
```

```sh
uv tool install platformio            # once
pio run                                # build
tools/flash_pi.sh                      # build + flash the C3 on labrador-pie over USB, show 20 s of log
tools/flash_pi.sh --log 60             # just watch its log (USB) for 60 s
pio run -t upload                      # or flash a C3 plugged into this machine
host_test/run.sh                       # logic tests, no hardware
```

`tools/flash_pi.sh` copies the four images to the Pi and runs esptool there.
That needs `uv tool install esptool` on the Pi, which is already done. The
SuperMini's native USB needs no BOOT button: esptool resets it into the
bootloader.

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
