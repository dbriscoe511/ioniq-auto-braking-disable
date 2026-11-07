# Findings

Vehicle: 2025 Hyundai Ioniq 5 XRT (facelift, ccNC infotainment).

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
- Board: IP-678A with an Atmel SAM C21 MCU (U2, likely ATSAMC21G) and an NXP
  UJA1164A CAN system basis chip (U1), plus a CAN common mode choke. See
  [electronics.md](electronics.md). The panel is a CAN node, so the button
  press leaves as a CAN frame rather than on its own wire.

### Interpretation

5 buttons + 9 LEDs = 14 signals, equal to the populated pin count, yet the
panel also needs ground and likely supply/backlight. So some signals share
wires (common grounds, grouped LEDs, or a resistor-ladder button input).
The onboard MCU and CAN chip mean the button is probably read
on the board; the remaining wires are likely power, wake and backlight. Older Ioniq 5 / 2024 Ioniq 6 diagrams show dedicated
`PDW SW SIG` and `PDW SW IND` circuits, consistent with this.

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

Also measure, car off: switch-wire resting voltage and resistance to ground.

### Pin table (to fill in)

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
| 16 | | 0 V | | | Ground |

## Proposed circuit (pending measurements)

- Ignition-switched supply tapped elsewhere; small MCU.
- Open-collector transistor or optocoupler from the switch wire to ground, in
  parallel with the factory button (if the switch is active-low; a resistor
  ladder needs a matching resistor instead).
- On startup: wait for the system to boot, read the LED line, press for ~3 s
  only if Parking Safety is on, confirm the LED changed, retry once.

## Interception options

1. Plug-in pass-through adapter (both connector halves; fully reversible).
   Needs the housing part number, a donor `93310-…` switch or Hyundai repair
   pigtail.
2. Single-wire tap on the switch signal (plus ground/IGN from elsewhere).
3. Back-probe piggyback - testing only.

## Car behaviour with the panel unplugged

Observed: the car starts and drives normally with the switch panel unplugged.
Not yet checked: whether Parking Safety still comes on at startup, which
warnings or stored fault codes appear, and whether the seat and wheel heaters
still work from the screen.

Consequences:

- The panel is not required for driving, so bench work and failed experiments
  are low-stakes. Unplug and replug only with the car off.
- Capture CAN traffic on header pins 7/8 with the panel plugged in, then
  unplugged. Message IDs that disappear are the ones the panel sends; the
  Parking Safety button lives in one of those.
- Because the car tolerates the panel's absence, a man-in-the-middle board
  (panel on one side, car on the other, forwarding everything except the
  button signal) is a realistic option. A full replacement that impersonates
  the panel would also avoid fighting the real panel's messages.
