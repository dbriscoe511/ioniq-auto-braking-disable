# Ioniq 5 auto-braking disable

Hardware mod to automatically turn off **Parking Safety** (rear auto-braking,
PCA-R) shortly after a 2025 Hyundai Ioniq 5 XRT is switched on. A hitch bike
rack makes the rear sensors trigger hard braking when reversing; today this is
done by hand every drive.

Status: **investigation / bench teardown**. No automatic-disable circuit or
firmware modification is installed. Measurements and observations through
**2026-11-07** are recorded below; proposed tests are not completed results.

> Safety: the proposed mod disables a driver-assistance feature. It must mirror
> pressing the factory button, preserve manual controls, and avoid turning the
> feature back *on* unexpectedly or interfering with other console controls.
> These are design requirements, not validated behaviour. Use at your own risk.

## Approach

The preferred approach under investigation is to emulate a press across the
Parking Safety button's **PCB contacts**, not assume a dedicated harness wire.
The panel contains a SAM C21 MCU and CAN system basis chip. Button/LED traces
and CAN messages still need mapping.

The proposed controller would wait after startup, confirm Parking Safety is
on, hold the button for about 3 s (> 2 s required), and verify it turned off.
LED polarity, feedback reliability and startup timing are not yet measured.

Previously set aside:

- **OBD/CAN commands**: the earlier investigation reported the security gateway
  blocked the OBD route. Direct access at this panel has not yet been tested.
- **Infotainment firmware downgrade** (`NE1A.USA.ccNC.001.002.260821`):
  no verified working downgrade was identified in the earlier investigation.
- **Trailer wiring / fake trailer**: not wanted.

## Latest observations

- Console removal worked using the Reddit method; the button assembly has
  four edge clips and a removable PCB/rubber membrane/plastic carrier.
- `CON1`: pin 1 = VBAT via D1/D2, pin 7 = CAN-L, pin 8 = CAN-H,
  pin 16 = ground, as reported from bench tracing. Connector orientation
  still needs an annotated drawing.
- U2 marking: `ATSAMC21G17A-Z…`; U1 marking: `NXP U1164A`.
- `CON2`: pin 3 = ground; pin 1 connects to a capacitor and is probably the
  supply rail. Other debug pins and the powered voltage remain unconfirmed.
- Dan reports the car works fine with the module unplugged. Parking Safety,
  heater controls, warnings and stored faults have not been systematically
  checked in that state.
- STM32 Blue Pill boards are available for a possible debug probe. No debug
  connection, protection-bit result, firmware dump or CAN capture is recorded.

## Findings

- [Teardown guide](docs/teardown.md): removing the console panel and switch
  assembly. Panel removal credit:
  [r/Ioniq5 MagSafe install post](https://www.reddit.com/r/Ioniq5/comments/1t76ayr/built_in_magsafe_phone_charger_without_exposed/).
- [Electronics](docs/electronics.md): chip markings, bench power, measured vs
  tentative debug-header pinout, Blue Pill options and firmware questions.
- [Findings](docs/findings.md): dated observations, connector pin table,
  unplugged-module behaviour, circuit ideas and remaining checks.

## Layout

- `docs/` - guides and notes
- `photos/teardown/` - disassembly photos
- `photos/electronics/` - PCB and chip photos
