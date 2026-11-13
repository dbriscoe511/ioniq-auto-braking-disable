# Bench CAN capture and Parking Safety wiring

Bench session **2026-11-09**, panel out of the car. Raw logs and the capture
scripts are in [`captures/2026-11-09-bench-can/`](../captures/2026-11-09-bench-can/).

## Setup

- Panel powered on CON1 pin 1 (VBAT) and pin 16 (ground) from a Rigol DP932E,
  CH1 at **12.00 V with a 0.10 A limit**. That setpoint was already configured;
  the output was switched on and off remotely. Readback: 10 mA after switch-on,
  30 mA once running; the limit was never reached.
- CANable 2.0 (slcan firmware `16e7497-dirty`, normaldotcom/canable2) on
  CON1 pin 7 (CAN-L) and pin 8 (CAN-H), driven from `labrador-pie`.
- **Nothing was transmitted.** Captures used slcan listen-only (`M1`) or
  normal mode (`M0`, adapter may ACK) only; `slcan.py` has no transmit path.
- Bus termination was not checked or changed.

## Bus parameters

| | |
|---|---|
| Bitrate | **500 kbit/s**, classic CAN (frames received at slcan `S6`) |
| Other rates tried | 100k (`S3`), 125k (`S4`), 250k (`S5`), 1M (`S8`): nothing received in 1.5 s each |
| CAN FD | Not tested; not needed to receive this traffic |
| IDs seen | **`0x451` only**, 11-bit, DLC 8 |
| Idle payload | `44 00 00 00 00 00 00 00` |
| Idle period | 200 ms (5 Hz) |

- The panel transmits **on its own**, with no vehicle on the bus and no frames
  sent to it. It does not need a wake/ignition message to start sending.
- At power-up and on every button change it sends a short burst of faster
  frames before returning to 200 ms. The logs suggest ~50 ms spacing, but
  timestamps are taken at host read with a 50 ms serial timeout, so that
  spacing is **not resolved**. The 200 ms period is reliable.
- Traffic looked the same with `M1` and `M0` commanded. It was not verified
  that the adapter really withheld ACK in `M1`.
- The time from power-on to the first frame was not measured (the PSU switch
  was a backgrounded command with unknown startup delay).
- No rolling counter or checksum: all idle frames were byte-identical
  (91 in 20 s, 452 in 90 s).

## `0x451` byte 0: seat heater buttons

Byte 0 changed with the seat heater buttons; bytes 1–7 stayed `00` in every
capture.

| Byte 0 | Binary | Meaning |
|---|---|---|
| `44` | `01 00 01 00` | idle |
| `48` | `01 00 10 00` | bits 3:2 = `10`: **driver seat heat** pressed |
| `84` | `10 00 01 00` | bits 7:6 = `10`: **passenger seat heat** pressed |

- Inferred encoding: 2-bit fields, `01` = released, `10` = pressed.
  Bits 5:4 and 1:0 stayed `00`.
- Driver/passenger assignment comes from `five_btns.log`, where Dan pressed
  driver seat, steering wheel, camera, Parking Safety, passenger seat in that
  order (each pressed twice). The first change was `48`, the last `84`.
  `seat_heat.log` repeats the same two patterns, but its press order was not
  stated; the buttons pressed in `other_btns.log` were not recorded.
- Dan reports the PCB has **7 button positions, 2 depopulated** (possibly for
  another trim). Reading `00` in the unused fields as "not fitted" is an
  inference, not a measurement.

## Buttons with no CAN activity on the bench

**Parking Safety, steering wheel heat and camera (`RVM/AVM`) produced no
change** in `0x451` and no other ID, across these captures:

| Log | Length | Presses (Dan) | Result |
|---|---|---|---|
| `parking_btn.log` | 90 s | Parking Safety: 3 short, 3 × ~3 s | 452 identical idle frames |
| `parking_btn2.log` | 90 s | Same, after a power cycle | 441 identical idle frames |
| `five_btns.log` | 30 s | All five in order, twice each | Only the two seat heaters changed |

Possible explanations: the button is wired off-board (see below), or the MCU
reads it but only reports it when it sees vehicle conditions not present on
the bench. The bench capture cannot separate these alone.

## Parking Safety switch: CON1 pin 5

Reported by Dan after the captures (power state during the measurement was not
recorded; CH1 had last been left on):

- One side of the Parking Safety switch connects to **CON1 pin 5 through about
  200 Ω**.
- The other side of the switch is **ground**.
- Other CON1 pins measured more than ~5 MΩ from the switch.

This fits a **hardwired** switch: pressing pulls the pin 5 wire to ground
through ~200 Ω, and a module elsewhere in the car reads it and times the hold.
It is consistent with the button never appearing on CAN. Not yet checked:

- Whether the pin 5 / switch node also reaches a U2 (MCU) pin.
- Pin 5 to pin 16 with the board unpowered, released vs pressed (expected:
  open vs ~200 Ω).
- How steering wheel heat and camera are wired.

## Feature behaviour (reported by Dan, not tested here)

- **Short press** of Parking Safety silences the parking-distance beep. The beep
  is re-enabled whenever the car enters parking assist mode, e.g. selecting
  reverse or requesting the camera at low speed.
- **Hold for 2 s or longer** disables the reverse auto-brake. It is re-enabled
  only at the next car start.

So the mod needs one long hold after each start. If pin 5 is confirmed as the
switch line, that is a ~200 Ω closure from the pin 5 wire to ground, held
longer than 2 s, wired in parallel with the factory switch. No CAN frames are
involved.

## Needs the car

- Pin 5 voltage with ignition on, released and pressed: shows the receiving
  module's pull-up voltage and current, which decide the switching part
  (transistor, optocoupler or relay).
- How soon after start the module accepts a long press, and whether a hold that
  begins too early is ignored.
- A reliable "car started" signal for the controller (for example an
  ignition-switched supply; CON1 pin 1 is not yet known to be switched).
- Listen-only capture at the panel connector with ignition on: does `0x451`
  change, and do the three silent buttons appear anywhere?
