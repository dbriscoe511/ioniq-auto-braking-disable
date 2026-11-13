# Switch panel electronics

Board silkscreen: **IP-678A, 3022901 VER.1.00**. Button labels on the board
include `RVM/AVM` (reverse/surround camera button, `3SW1`). Housing label
starts `93310…`; OEM part for the XRT console switch is `93310-GIAB0-MEE`.

Bench observations were supplied by Dan on **2026-11-07**. Distinguish the
16-position vehicle connector **CON1**, the five-hole debug header **CON2**,
and physical pins on U1/U2. Dan subsequently confirmed CON2 pin 1 as a 5 V
supply/reference on **2026-11-08**. The probe responds to its host, but target
SWD communication has not succeeded; see the probe status below.

![PCB front](../photos/electronics/01-pcb-front-ip-678a.jpg)

## ICs

The board has exactly two ICs.

### U2: Atmel ATSAMC21G17A (QFN48)

| | | |
|---|---|---|
| ![U2](../photos/electronics/02-u2-atmel-mcu.jpg) | ![U2 close](../photos/electronics/07-u2-marking-closeup.png) | ![U2 enhanced](../photos/electronics/09-u2-marking-enhanced.jpg) |

Marking as read under better light (`?` = unreadable):

```
Atmel
????C21
GH????
403
2403EQ
```

An earlier photo also showed `ARM`.

- Dan later read the part as **`ATSAMC21G17A-Z`**. Preserve that reported
  fragment rather than reconstructing an unread ordering suffix.
- The [Microchip product page](https://www.microchip.com/en-us/product/ATSAMC21G17A)
  identifies the G17A as a Cortex-M0+ with 128 KB flash and 16 KB SRAM.
  The G package has 48 pins; the SAM C21 family has CAN-FD controllers.
- CON2 pin 1 is confirmed as a 5 V supply/reference; its routing to the MCU
  and U1's V1 output remains to be checked.
- `2403EQ` and `403` are retained as raw markings; their meaning is unverified.
- SWD uses PA30/SWCLK (pin 45) and PA31/SWDIO (pin 46); RESET is pin 40
  in the 48-pin package. See the
  [SAM C20/C21 datasheet](https://ww1.microchip.com/downloads/aemDocuments/documents/MCU32/ProductDocuments/DataSheets/SAM-C20-C21-Family-Data-Sheet-DS60001479.pdf),
  sections 4.2 and 6.2.2.
- Crystal `X1` and load parts (`XR1`, `XR2`) next to it.
- Earlier guesses (ATA66xx LIN chips, AT90CAN/ATmega M1) are superseded.

### U1: NXP UJA1164A CAN system basis chip (HVSON14)

| | |
|---|---|
| ![U1](../photos/electronics/04-u1-soic14.jpg) | ![U1 close](../photos/electronics/08-u1-marking-closeup.png) |

Marking as read under better light:

```
NXP
U1164A
HN65150   (low confidence)
2624210
```

- The `U1164A` reading identifies U1 as the **UJA1164A**. NXP specifies a
  high-speed CAN transceiver, 5 V/100 mA regulator, watchdog, SPI and standby
  handling. Its package is **HVSON14**, not the earlier SO14 guess; existing
  photo filenames retain the old name. Source:
  [NXP UJA1164A datasheet](https://www.nxp.com/docs/en/data-sheet/UJA1164A.pdf),
  sections 1, 3 and 5.
- UJA1164A pins: 1 TXD, 2 GND, 3 V1, 4 RXD, 5 RSTN, 10 BAT,
  12 **CANL**, 13 **CANH**. Check pin-1 orientation before continuity work.
- `L1` has four pads and is marked `110`. Its identification as a TDK
  ACT1210-110 was an earlier candidate, not a confirmed exact part number.
  Dan's tracing connects it to the reported CAN pair on CON1.
- **The panel has CAN hardware.** On the bench it sends `0x451` at
  500 kbit/s carrying the seat heater buttons. The Parking Safety button
  produced no CAN change and traces to CON1 pin 5; see
  [can-bench-capture.md](can-bench-capture.md).

Reported connector mapping (bench, unplugged):

1. Measured: header pin 7 = CAN-L, pin 8 = CAN-H (through L1).
2. L1's top connection in Dan's bench orientation goes to pin 7 / CAN-L;
   its bottom connection goes to pin 8 / CAN-H.
3. Header pin 1 = VBAT (reverse-polarity protected by D1/D2), pin 16 = ground.

The connector-face orientation still needs documenting; see
[the CON1 table](findings.md#con1-16-position-vehicle-connector).

### Bench power and the debug-header power question

Proposed bench setup: panel disconnected from the vehicle, current-limited
12 V supply to **CON1 pin 1**, return to **CON1 pin 16**, initially around
100 mA limit. Dan later reported the panel powered and its 5 V reference good.
On 2026-11-09 the panel ran from a DP932E at 12.00 V / 0.10 A limit on CON1
pin 1/16, drawing 10–30 mA (supply readback) without reaching the limit.
Verify polarity/numbering
first, then record input current and
U1 V1 voltage. Unexpected current limiting or reset cycling
needs investigation, not an automatic increase in the limit.

Dan asked whether feeding 5 V into CON2 without battery power could damage
U1. Back-feed tolerance has **not** been established. If CON2 pin 1 is tied
to V1, external power there could back-feed U1's regulator; do not use it as
a power input. Use the identified VBAT input and treat CON2 pin 1 as a
target-voltage reference. Never join an enabled
probe power output to that rail.

## CON2: 5-pin header and test points

![CON2](../photos/electronics/06-con2-5pin-header.jpg)

- Unpopulated 5-hole through-hole header `CON2` with pin 1 marked by the
  triangle at `TP5`; test points `TP6` and others nearby.
- Dan confirmed pin 1 (the top pin in his description) as a 5 V
  supply/reference; it also connects to a capacitor. Pin 3 is ground.
- This is a candidate SWD port, not a confirmed UART/COM port. The proposed
  assignment below is **not a standard pinout or a ready-to-connect cable**;
  the earlier “odd pins of the 10-pin Cortex header” claim was incorrect.

| CON2 pin | Evidence / candidate function | Remaining check |
|---|---|---|
| 1 | 5 V supply/reference confirmed by Dan | Trace to U1 V1 / MCU supply |
| 2 | SWDIO proposed, not measured | Continuity to U2 pin 46 / PA31 |
| 3 | Ground measured | Use as probe ground after verifying orientation |
| 4 | SWCLK proposed, not measured | Continuity to U2 pin 45 / PA30 |
| 5 | RESET proposed, not measured | Continuity to U2 pin 40 / RESET |

### Probe options and firmware status

- **Selected probe:** STM32F411 Black Pill, flashed with Black Magic Probe
  v2.0.0 (`blackpill-f411ce` build, including bootloader). The flashing thread
  reported byte-for-byte verification; the saved build and readback also
  match in the consolidation audit. This is probe firmware, not panel firmware.
- The probe enumerated and responded on `labrador-pie`. Target SWD scans at
  approximately 195 kHz and 20 kHz failed. Dan confirmed the panel was powered,
  its 5 V reference was good, and Black Pill B8/B9 were used. Reset was not
  connected. No target writes, erases, unlocks or reset commands were reported.
- The build's target-facing mapping is PB8 = SWCLK, PB9 = SWDIO, PA5 = reset.
  This does not confirm the proposed CON2 signal assignments or their wiring.
  CON2 pin 1 and reset were left disconnected during the reported test.
- Verify the probe's I/O rating against the **measured** target voltage,
  including reset and bidirectional SWDIO. Do not assume a bare 3.3 V board
  or every J-Link variant supports this target. A suitable level interface
  or probe is needed if the ratings do not match. The earlier generic
  BSS138-module suggestion has not been validated for SWD here.
- U1's watchdog may reset a halted MCU; its board-specific configuration is
  unknown. A debug connection can affect execution even without flash writes.
- **Protection state is unknown.** The Microchip datasheet's DSU section
  describes `STATUSB.PROT` (bit 0), with external debug alias
  `0x41002102`. Checking it was proposed, not performed. A protected part may
  need reset/cold-plug attachment; failure to attach alone proves nothing.
- If ordinary read access is allowed, preserve a verified original dump
  before considering changes. No dump exists in this repo. **Never accept
  unlock/recover/chip-erase prompts:** chip erase removes the security bit
  by erasing flash; it does not recover its contents.
- The firmware research thread identified a SAM4C32 demonstration, not a
  demonstrated SAM C21 bypass. No applicable bypass, silicon revision,
  exploit attempt, firmware patch or successful panel extraction was established.

See the [investigation register](investigations.md) for provenance, local probe
backup checksums and conflicting equipment advice that remains unvalidated.

## What this means for the mod

The earlier expectation that the MCU reads every button and reports it on
the bus was only half right. The 2026-11-09 bench session showed the seat
heater buttons on CAN (`0x451`), but the Parking Safety button produced no
CAN change, and Dan traced its switch to **CON1 pin 5 via ~200 Ω**, with the
other side to ground. Steering wheel heat and camera were also silent on CAN
and are untraced. Details: [can-bench-capture.md](can-bench-capture.md).

So the mod most likely needs no CAN at all: emulate the switch on the pin 5
wire. No frames were transmitted on the bench, and none should be injected.

Next checks:

1. On the bench, unpowered: pin 5 to pin 16 released vs pressed (expect open
   vs ~200 Ω), and whether the pin 5 node also reaches a U2 pin.
2. In the car: pin 5 voltage with ignition on, released and pressed, to size
   the switching circuit.
3. In the car: listen-only capture at the panel with ignition on, to see
   whether `0x451` or the silent buttons behave differently.
