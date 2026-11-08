# Findings

Vehicle: 2025 Hyundai Ioniq 5 XRT (facelift, ccNC infotainment).

## Evidence and scope

Updated from the teardown chat and Dan's bench observations on **2026-11-07**.
Pin assignments below are reported continuity/tracing results, not a Hyundai
service-manual pinout. No powered voltage measurements, scope traces, CAN
captures, debugger results or automatic-disable tests were reported.

The target is **Parking Safety / rear auto-braking**, not the electronic
parking brake (EPB), Auto Hold or the gear-selector Park button. The hitch
bike rack triggers unwanted braking when reversing. The goal remains an
automatic startup button hold without trailer wiring.

## Console teardown

See [teardown.md](teardown.md) for the step-by-step guide with photos.

## Switch panel

- Assembly label starts `93310…`; OEM catalogue lists the XRT console switch
  as `93310-GIAB0-MEE`.
- Panel contents:
  - Seat heater buttons (2), each with 3 level LEDs
  - Steering-wheel heater button with 2 LEDs
  - Parking Safety button with 1 LED
  - Reverse/camera button, no LED
- Connector: **KET, 16 positions (2x8), 14 populated**, yellow terminal-position
  lock. Exact KET part number not yet found.
- Board: `IP-678A, 3022901 VER.1.00`, with an Atmel `ATSAMC21G17A-Z…` MCU
  (U2, marking read by Dan) and an NXP
  UJA1164A CAN system basis chip (U1), plus a CAN common mode choke. See
  [electronics.md](electronics.md). CAN hardware is present; the specific
  Parking Safety signal path and frame are not yet traced or captured.

### Interpretation

Dan counted **5 buttons and 9 LEDs**, coincidentally matching the 14 populated
connector positions. The earlier conclusion that this ruled out CAN was
incorrect: the subsequent chip identification and L1 tracing supersede it.
Do not infer one connector wire per button or LED from that count.

The MCU likely reads the buttons locally, but the remaining connector wires
are unmapped. Older Ioniq 5 / 2024 Ioniq 6 diagrams discussed in the original
research had `PDW SW SIG` and `PDW SW IND`; they are not a verified pinout for
this facelift panel.

## Probing plan

Back-probe (do not pierce insulation), car on and in Park, scope ground on
verified chassis ground. Record each pin at idle, button held, > 2 s hold, and
after the feature toggles.

| Observation | Meaning |
|---|---|
| Steady voltage, drops to ~0 V only while pressed | Parking Safety switch signal |
| Intermediate level, shared with other buttons | Resistor ladder |
| Changes only when the feature toggles | Parking Safety LED |
| PWM that follows headlights/dimmer | Backlight |
| ~2.5 V pair splitting to ~3.5/1.5 V | CAN |
| ~12 V idle with fast dips | LIN |
| Constant 0 V / 12 V | Ground / supply |

Measure resting voltage before attempting resistance/continuity checks;
resistance checks require the board to be disconnected and unpowered.

### CON1: 16-position vehicle connector

Keep these numbers distinct from the five-pin `CON2` debug header and U1/U2
chip pins. Numbers follow Dan's bench notes; a numbered connector-face photo
showing viewing direction and latch orientation is still needed. Looking at
the mating harness face can mirror the layout; do not use “top” alone to wire
an adapter.

Reported tracing:

- `L1`, the four-pad part marked `110`: the top connection in Dan's bench
  orientation goes to CON1 pin 7, and the bottom connection to pin 8.
- Dan subsequently identified the top connection as **CAN-L**, giving pin 7
  = CAN-L and pin 8 = CAN-H. “Top/bottom” is not a fixed vehicle orientation.
- CON1 pin 16 is ground.
- CON1 pin 1 is VBAT, with polarity protection identified as D1 and D2.

Blank cells mean **not recorded**, including voltages and wire colours; they
do not mean zero. The two unpopulated positions have not been identified.

| Pin | Wire colour | Idle | Pressed | Toggled | Function |
|---|---|---|---|---|---|
| 1 | | | | | VBAT in (reverse-polarity protected by D1/D2) |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |
| 5 | | | | | |
| 6 | | | | | |
| 7 | | | | | CAN-L (via L1) |
| 8 | | | | | CAN-H (via L1) |
| 9 | | | | | |
| 10 | | | | | |
| 11 | | | | | |
| 12 | | | | | |
| 13 | | | | | |
| 14 | | | | | |
| 15 | | | | | |
| 16 | | | | | Ground |

## Proposed circuit (pending measurements)

- Small MCU with a suitable supply. CON1 VBAT is not yet shown to be
  ignition-switched; do not equate panel power with the car entering READY.
  Ignition/wake detection and standby current still need measuring.
- Emulate a closure across the PCB button contacts after tracing them. A
  transistor-to-ground circuit is only appropriate if an active-low input is
  confirmed; a matrix or resistor ladder needs a different interface.
- Read the Parking Safety indicator only after verifying its polarity,
  drive waveform and relationship to the actual feature state.
- The earlier proposal was: wait for boot, hold for ~3 s only when enabled,
  verify the state changed, and allow at most one retry. Neither that timing
  nor the retry is validated. Ambiguous feedback must not trigger a blind
  toggle or retry that might re-enable the feature.

## Interception options

1. PCB-contact tap: current preferred investigation route if the button is
   read locally; preserves the panel's own communication protocol.
2. Plug-in pass-through adapter (both connector halves; fully reversible).
   Needs the housing part number, a donor `93310-…` switch or Hyundai repair
   pigtail. Useful for power/CAN access, but does not create a dedicated
   Parking Safety wire if the button is read locally.
3. Single-wire harness tap only if tracing actually finds a dedicated signal.
4. Back-probe piggyback - testing only, not a permanent vibrating connection.

## Car behaviour with the panel unplugged

Dan's report: **“The car works fine with the module unplugged.”** No detailed
test conditions or fault scan were recorded. This does not establish that
Parking Safety is disabled, that every panel function is available, or that
the car stores no faults. Whether Parking Safety still comes on at startup,
warnings/fault codes, and screen-based seat/wheel heater control remain open.

Consequences:

- The observation supports taking the panel to the bench; it does not make
  firmware changes or CAN injection low-stakes. Follow the power-isolation
  precautions in [teardown.md](teardown.md) when disconnecting/reconnecting.
- A proposed listen-only comparison is CAN traffic on CON1 pins 7/8 with the
  panel attached versus absent, returning the car to the same awake state.
  Disappearing IDs are candidates, not proof of panel ownership: unplugging
  it can change other nodes' behaviour or bus wake state.
- A two-interface CAN bridge or full panel replacement was discussed, not
  built. The button frame, status feedback, counters/checksums, timing and
  effects on the other controls remain unknown. Blind injection could
  conflict with the real panel's messages.

## Equipment and open checks

- Rigol scope was discussed for live waveform checks; no captures are saved.
- Dan has STM32 Blue Pill development boards available. Probe firmware and
  electrical compatibility have not been tested; see
  [electronics.md](electronics.md#probe-options-and-firmware-status).
- Finish the CON1 orientation/empty-position drawing and measure the supply,
  wake behaviour, CAN bitrate and powered CON2 voltage.
- Trace the Parking Safety switch and LED before choosing a circuit.
- Confirm the remaining CON2 signals, then check debug protection without
  erasing or modifying the original firmware.
- Firmware-dump vulnerabilities were raised as a question, but no result was
  established in the chat. Protection state, silicon revision and any
  applicable readout issue remain unverified; no dump or bypass is recorded.
