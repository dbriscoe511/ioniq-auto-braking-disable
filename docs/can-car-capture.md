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

## Infotainment setting: command `0x2A3` (11-bit)

Toggling Parking Safety **off/on from the touchscreen settings menu** emits a
command frame that the earlier button/pin-5 work never produced. Captured in
`screen_toggle.log`.

| `0x2A3` payload | Effect ~0.1 s later |
|---|---|
| `00 02 00 00 00 00 00 00` | auto-brake **off** (`0x05C17002` byte 1 `09` → `07`) |
| `00 04 00 00 00 00 00 00` | auto-brake **on** (byte 1 `07` → `09`) |

- Each toggle sends **three request frames ~50 ms apart, then three all-zero
  frames**. (The ~50 ms figure is at the resolution limit of the logger.)
- `0x2A3` appears in **no other capture** — only when the screen setting is
  touched. It carries **no visible checksum or rolling counter**, unlike most
  frames on this bus.
- It moves **byte 1 only**. The warning-sound bit (`0x05C17002` byte 0) does
  **not** change, so this command disables the brake but leaves the beep. It
  also produces **no 2 s notice** in `0x05C17001`, unlike the button long press.
- In `screen_toggle.log`, all 8 toggles (4 off, 4 on) matched a request within
  ~0.1 s. The very first request also had `0F` in byte 3 (meaning unknown).

**Not yet proven:** that `0x2A3` *causes* the change (timing/exclusivity make
it very likely, but only transmitting it would confirm), and that the sender is
the head unit (assumed, not identified).

### Transmit test (2026-11-12): replay does not work from this bus

First time transmitting on the car bus (car in Park, stationary, parking brake
set). Using `captures/.../send_brake.py` (normal mode, guarded so it only sends
when `0x05C17002` byte 1 reads `09`): three `0x2A3` request frames ~50 ms apart
then three all-zero releases, mirroring the head unit.

| Frames sent (×3 + release) | Result |
|---|---|
| `0x2A3 00 02 00 00 00 00 00 00` | no change (byte 1 stayed `09`) |
| `0x2A3 00 02 00 0F 00 00 00 00` (first-from-idle form) | no change (byte 1 stayed `09`) |

The frames were ACKed (normal mode completed cleanly; an un-ACKed frame would
have jammed the adapter with retransmits), so they reached the bus and at least
one ECU received them. **The parking module did not act.** No warning lights,
chimes or messages appeared.

Follow-up diagnostic `settings_screen.log`: sitting on the Parking Safety
settings screen without toggling produces **no `0x2A3`** and **no new or
changed context frame** on this bus. So the replay did not fail for lack of
menu context.

**Working hypothesis — gateway.** The panel is on a body/sub-bus. `0x2A3` and
`0x05C17002` appear here as copies the gateway forwards, but an *unsolicited*
`0x2A3` injected onto this bus is not routed to the parking module (which may
live on another bus). This matches the project's earlier finding that the OBD
route was gateway-blocked: the ADAS traffic is readable here but not
injectable. Not proven — confirming would need access to the other bus.

**Consequence:** the CAN-command route is not usable from this access point.
Pin 5 is the route, because it drives the module's own physical input and
bypasses CAN entirely.

## What this means for the mod

Two independent routes now exist:

1. **Pin 5 button emulation (hardware).** Close CON1 pin 5 to ground through
   ~200 Ω for about 3 s, in parallel with the factory switch (e.g. a small
   N-channel MOSFET or optocoupler rated well above 12 V). Worst-case current
   ~60 mA (12.2 V / 200 Ω); the real figure depends on the unmeasured pull-up.
   This toggles **both** brake and beep.
2. **`0x2A3` command (CAN transmit).** ~~Send `0x2A3 00 02 …` as the head unit
   does.~~ **Tested 2026-11-12 and it does not work from this bus** — two
   faithful replays were ignored (see the transmit test above). Likely
   gatewayed. Treat this route as closed from the panel connector unless a
   different bus access point is found.

Route 1 (pin 5) is the working path. It is a device-in-car solution, not a
software-only change. A software-only
fix would have to live in the module that reads pin 5 and sends `0x05C17002`,
which has not been identified. The panel firmware (SAM C21) does not appear to
handle Parking Safety; whether the pin 5 node also reaches the MCU is unchecked.

**Feedback for either route:** read `0x05C17002` byte 1 listen-only. Act only
when it reads `09` (on); afterwards confirm `07` (off); never act while it
already reads `07`. A long press **or** a `0x2A3 00 04` toggles it back on, so
a blind action could re-enable the brake.

**Do not replay `0x05C17002` itself.** It is a status output from the module
that reads pin 5; replaying it conflicts with that module's own frames and does
not change its internal state. `0x2A3` is different — it is the actual command
input, sent only on a user action, so there is normally nothing to conflict
with.
