# ESP32-C3 add-on: Parking Safety auto-disable

KiCad 10 schematic for the add-on board that taps the console switch panel
(CON1 of PCB IP-678A, see [../../docs/electronics.md](../../docs/electronics.md))
and presses the Parking Safety button at startup based on CAN status.

![Schematic](out/esp32c3-recovery.png)

PDF: [out/esp32c3-recovery.pdf](out/esp32c3-recovery.pdf)

## Files

| File | What |
|---|---|
| `esp32c3-recovery.kicad_pro` / `.kicad_sch` | KiCad project and the single sheet |
| `esp32c3_recovery.kicad_sym` + `sym-lib-table` | Project symbols: ESP32-C3 SuperMini, Adafruit CAN Pal (no stock symbols exist) |
| `tools/gen.py` | Generates the sheet and project library; **edit this, not the sheet** |
| `tools/check.sh` | Regenerate, ERC, netlist check against intended nets, library check, PDF/SVG/PNG export |

Everything else uses stock KiCad symbols (LM7805_TO220, SMAJ18A, 1N5819,
2N3904, Polyfuse, R/C, Conn_01x05_Pin, power symbols).

## Pin map (ESP32-C3 SuperMini)

| GPIO | Use |
|---|---|
| GPIO3 (ADC) | Press sense: BTN through 100k/27k divider, ~1 V threshold |
| GPIO5 | CAN Pal SLNT (no resistor on the CAN Pal itself). 4.7k pull-up keeps the transceiver silent; firmware drives it high by default |
| GPIO6 | CAN Pal TX (transmit possible, but off by default) |
| GPIO7 | CAN Pal RX |
| GPIO10 | Button press drive on CON1-5 (1k to 2N3904 base, 10k base pull-down) |
| GPIO2/8/9 | Strapping pins (GPIO8 = LED): unused |
| GPIO20/21 | UART0, kept free for serial debug |

## Assumptions to verify before building

- **BTN line = CON1 pin 5.** The Parking Safety switch is hardwired there
  (~200 ohms in series, other side to ground; not read by the panel MCU) and
  pin 5 idles at 12.2 V in the car. See docs/findings.md. Measured in the car
  with the firmware running: GPIO3 reads ~2.5 V released (BTN ~11.8 V) and
  ~0.1 V with Q1 on (BTN ~0.5 V), so R3 = 200 ohms (mirroring the factory switch
  path) carries at most ~2.4 mA. The panel's pull-up is weak (roughly 5k), so
  R3 dissipates well under 10 mW; the 1 W rating is margin, not a requirement.
- **Regulator:** LM7805 (stock symbol) instead of the LM2940 from the design
  chat. It has no reverse-battery protection, but the tap is behind the
  panel's D1/D2. Its 35 V max input sits above the SMAJ18A clamp (~29 V).
- **Parts added after the design review:** F1 PTC fuse, which limits fault
  current if the TVS fails short. D2 Schottky, which stops USB 5 V from
  back-feeding the regulator.
- **CAN Pal:** termination switch OFF. Symbol pin numbers follow its header
  JP2 from Adafruit's schematic (1 CAN_L, 2 CAN_H, 3 S, 4 TX, 5 RX, 6 GND,
  7 VCC).
- **SuperMini pin numbers** follow the common header order (left 5V, GND,
  3V3, GPIO4..0; right GPIO5..10, 20, 21). Check them against your board's
  silkscreen.
