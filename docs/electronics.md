# Switch panel electronics

Board silkscreen: **IP-678A, 3022901 VER.1.00**. Button labels on the board
include `RVM/AVM` (reverse/surround camera button, `3SW1`). Housing label
starts `93310…`; OEM part for the XRT console switch is `93310-GIAB0-MEE`.

![PCB front](../photos/electronics/01-pcb-front-ip-678a.jpg)

## ICs

The board has exactly two ICs.

### U2: Atmel microcontroller (QFN)

| | | |
|---|---|---|
| ![U2](../photos/electronics/02-u2-atmel-mcu.jpg) | ![U2 close](../photos/electronics/07-u2-marking-closeup.png) | ![U2 enhanced](../photos/electronics/09-u2-marking-enhanced.jpg) |

- Readable marking: `Atmel` / `…21` (first digits obscured) / a lot or trace
  line ending `…03EU`, with a partial line containing `…LQ…` and `…H` in
  earlier photos. The full part number is still unreadable.
- Crystal `X1` and load parts (`XR1`, `XR2`) next to it.
- Candidates:
  - Atmel LIN system-in-package (ATA6612C/6613C/6614Q): QFN48 7x7 mm,
    ordering suffix `-PLQW`, which could explain the `LQ` fragment.
  - An Atmel AVR with built-in CAN (AT90CAN or ATmega16/32/64M1/C1), which
    would fit if the board is a CAN node (see U1).
- ATA6621 is ruled out: it is a 5x5 mm QFN20, and this package has far more
  pins.
- Count the pins and measure the body size: 48 pins on 7x7 mm points to the
  LIN SiP; 32 or 64 pins points elsewhere.

### U1: SOIC-14, probably a CAN transceiver

| | |
|---|---|
| ![U1](../photos/electronics/04-u1-soic14.jpg) | ![U1 close](../photos/electronics/08-u1-marking-closeup.png) |

- Laser marking too faint to read, even with contrast enhancement.
- The strongest clue is `L1`, the 4-pad black part marked `110` beside it, close
  to the board connector. That matches the TDK ACT1210-110 (11 µH), a common
  mode choke made for CAN and FlexRay lines
  ([LCSC](https://www.lcsc.com/product-detail/C694257.html)). Common mode
  chokes are what sit between a CAN transceiver and the connector.
- Many automotive CAN transceivers come in SO14 (e.g. NXP TJA1043 and
  TJA1145, TI TCAN1043). Typical SO14 CAN transceivers put CANL/CANH on
  pins 12/13 and also have INH, WAKE and VBAT pins.
- If correct, the panel is a **CAN node**, and the Parking Safety press likely
  leaves as a CAN frame on whichever bus segment the panel sits on.

To confirm on the bench (car side unplugged):

1. Check that L1 has four terminals and that two of them go to adjacent
   connector pins, ideally a twisted pair in the harness.
2. Follow L1's other two terminals to U1 and note the pin numbers.
3. In the car, scope those two connector pins. CAN idles with both at ~2.5 V
   and splits to ~3.5 V / ~1.5 V during traffic.

## CON2: 5-pin header and test points

![CON2](../photos/electronics/06-con2-5pin-header.jpg)

- Unpopulated 5-hole through-hole header `CON2` with pin 1 marked by the
  triangle at `TP5`; test points `TP6` and others nearby.
- Most likely a factory programming/debug port for U2 (AVR ISP, debugWIRE or
  a UART). Map each pin to U2 with a continuity tester before connecting
  anything.

## What this means for the mod

A microcontroller on the panel, likely behind a CAN transceiver, means the
Parking Safety button probably does **not** have its own connector wire. The
MCU reads the buttons locally and reports them on the bus. The other wires
are probably power, ground, wake/ignition and backlight, plus any loads the
panel drives directly.

If it is CAN, this is the bus access the earlier OBD attempt could not get
past the security gateway: sniff these two pins, press Parking Safety, and
look for the frame that changes. Replaying a frame is still riskier than
emulating the button, so the simplest reliable tap remains across the switch
pads on the PCB.

Next checks:

1. On the bench: follow the Parking Safety switch pads. Do they go to a U2 pin
   or straight to a connector pin?
2. In the car: confirm CAN (or LIN, ~12 V idle with fast dips to 0 V) on the
   connector pins identified above.
3. If the button only goes to U2, the simplest tap is across the switch pads on
   the PCB (emulate the press there), rather than on the harness.
