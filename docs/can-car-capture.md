# In-car CAN capture: Parking Safety status

Session **2026-11-12**, panel installed and plugged in, car on. CANable 2.0 on
CON1 pin 7 (CAN-L) / pin 8 (CAN-H), driven from `labrador-pie`, **listen-only
throughout; nothing was transmitted**. Raw logs:
[`captures/2026-11-12-car-can/`](../captures/2026-11-12-car-can/). Bench
results are in [can-bench-capture.md](can-bench-capture.md).

## Bus

- 500 kbit/s classic CAN, same as the bench. Nothing at 100k/125k/250k/1M.
- About **1,300 frames/s across 195 IDs**, a mix of 11-bit and 29-bit IDs.
  Many carry what look like a 2-byte checksum and a rolling counter.
- The panel's `0x451` reads `44 00 …` at idle, as on the bench. Driver seat
  heat still shows as byte 0 = `48` while pressed. `0x496` byte 0 follows the
  driver seat heat level (`12` → `42` → `3A` → `32` → `12` over four presses);
  its sender is unknown.

## Parking Safety status: `0x05C17002` (29-bit)

The Parking Safety button does not appear in the panel's own frame. Instead,
another module (sender not identified) reports the feature state:

| Field | Values | Changed by |
|---|---|---|
| Byte 0, bit 0 | `1` (`2D`) = parking warning sound active; `0` (`2C`) = muted / inactive | Short press toggles it; shifting into reverse sets it to `1` |
| Byte 1 | `09` = auto-brake **on**; `07` = auto-brake **off** | Long press toggles it; gear changes do not |
| Bytes 2–7 | `00 00 00 00 00 04` | No change seen |

`0x05C17001` byte 3 shows a **2.0 s notice** each time auto-brake changes:
`0x20` when it turns on, `0x10` when it turns off. Its bytes 0–1 look like a
checksum and byte 2 a counter (+5 per frame).

Evidence, from the staged captures in reverse:

- `stage1_short.log`: short presses (count not recorded), 17 toggles of
  byte 0 bit 0; byte 1
  stayed `07`; no `0x05C17001` notice.
- `stage2_long.log`: long presses alternately set byte 1 to `09` and `07`
  (8 changes),
  each with the matching 2 s notice. Byte 0 did not change.
- `stage3_gear.log`: byte 0 went to `2D` about 0.2 s after each of 4 shifts
  back into reverse (timed against `0x418`, which changed with each shift),
  then back to `2C` 2–3 s later when Dan muted it. Dan's one accidental long press produced no byte 1
  change or notice.
- `baseline.log` → `buttons2.log`: from the start of the session byte 1 read
  `09`, changed to `07` at Dan's long press (21.2 s into `buttons2.log`) and
  stayed there through later reverse cycles.

So a long press **toggles** auto-brake rather than only turning it off. The
start-up default was `09` (on) in the one fresh start captured.

## Other buttons

- Passenger seat heat: `0x451` byte 0 = `84` on the bench; not pressed in the
  car captures.
- Camera: possible match `0x05816A01` byte 7 = `0x90` for 0.37 s at 29.9 s of
  `buttons2.log`; unconfirmed.
- Steering wheel heat: not identified.
- Reverse changes dozens of IDs; the panel LED command was not isolated.

## Pin 5 in the car

Dan measured **CON1 pin 5 at 12.2 V** with the car on and the button released,
consistent with a switch input pulled up to battery voltage. The pressed
voltage was not measured.

## What this means for the mod

- **Input:** close CON1 pin 5 to ground through ~200 Ω for about 3 s, in
  parallel with the factory switch (e.g. a small N-channel MOSFET or
  optocoupler rated well above 12 V). The worst-case current is ~60 mA
  (12.2 V / 200 Ω); the real figure depends on the unmeasured pull-up.
- **Feedback:** read `0x05C17002` byte 1 listen-only. Press only when it reads
  `09`; after the press, confirm `07`; never press while it reads `07`. A blind
  press could turn auto-brake back on.
- **Do not transmit** these frames. `0x05C17002` is a status output from the
  module that reads pin 5; replaying it would conflict with that module's own
  frames and would not change its internal state.
- A software-only change would have to be in the module that reads pin 5,
  which has not been identified. The panel firmware (SAM C21) does not appear
  to handle Parking Safety, though whether the pin 5 node also reaches the MCU
  is still unchecked.
