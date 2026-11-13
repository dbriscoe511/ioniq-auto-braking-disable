# Ioniq 5 auto-braking disable

Hardware mod to automatically turn off **Parking Safety** (rear auto-braking,
PCA-R) shortly after a 2025 Hyundai Ioniq 5 XRT is switched on. A hitch bike
rack makes the rear sensors trigger hard braking when reversing; today this is
done by hand every drive.

Status: **investigation / bench teardown**. No automatic-disable circuit or
firmware modification is installed. Measurements and observations through
**2026-11-09** are recorded below; proposed tests are not completed results.

> Safety: the proposed mod disables a driver-assistance feature. It must mirror
> pressing the factory button, preserve manual controls, and avoid turning the
> feature back *on* unexpectedly or interfering with other console controls.
> These are design requirements, not validated behaviour. Use at your own risk.

## Approach

The bench session on 2026-11-09 found the Parking Safety button appears to be
**hardwired**: its switch connects CON1 pin 5 to ground through ~200 Ω, and
pressing it produced no CAN change. The panel's CAN frame (`0x451`,
500 kbit/s) carries only the two seat heater buttons. The preferred approach
is now to emulate a press on the **pin 5 wire**, with no CAN involved. The
in-car voltage on pin 5 still needs measuring. See
[docs/can-bench-capture.md](docs/can-bench-capture.md).

The proposed controller would wait after startup, confirm Parking Safety is
on, hold the button for about 3 s (> 2 s required), and verify it turned off.
Per Dan, a short press only silences the beep; the long hold disables
auto-brake until the next start, so one hold per start is enough.
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
- `CON1`: pin 1 = VBAT via D1/D2, pin 5 = Parking Safety switch (~200 Ω,
  switch to ground), pin 7 = CAN-L, pin 8 = CAN-H, pin 16 = ground, as
  reported from bench tracing. Connector orientation
  still needs an annotated drawing.
- U2 marking: `ATSAMC21G17A-Z…`; U1 marking: `NXP U1164A`.
- `CON2`: pin 1 = 5 V supply/reference, confirmed by Dan; pin 3 = ground.
  The other debug pins remain unconfirmed.
- Dan reports the car works fine with the module unplugged. Parking Safety,
  heater controls, warnings and stored faults have not been systematically
  checked in that state.
- An STM32F411 Black Pill now runs Black Magic Probe v2.0.0. It responds to
  the host, but target SWD scans failed; MCU protection remains unknown.
  No panel firmware dump is recorded.
- Bench CAN capture (2026-11-09): panel sends `0x451` every 200 ms at
  500 kbit/s without the car; byte 0 carries driver/passenger seat heat.
  Parking Safety, wheel heat and camera did not appear.

## Findings

- [Teardown guide](docs/teardown.md): removing the console panel and switch
  assembly. Panel removal credit:
  [r/Ioniq5 MagSafe install post](https://www.reddit.com/r/Ioniq5/comments/1t76ayr/built_in_magsafe_phone_charger_without_exposed/).
- [Electronics](docs/electronics.md): chip markings, bench power, measured vs
  tentative debug-header pinout, Blue Pill options and firmware questions.
- [Bench CAN capture](docs/can-bench-capture.md): bitrate, `0x451` layout,
  silent buttons, and the Parking Safety pin 5 trace.
- [Findings](docs/findings.md): dated observations, connector pin table,
  unplugged-module behaviour, circuit ideas and remaining checks.
- [Investigation register](docs/investigations.md): cross-thread results,
  probe artifact checksums, unresolved equipment advice and next gates.

## Layout

- `docs/` - guides and notes
- `captures/` - raw CAN logs and capture scripts
- `photos/teardown/` - disassembly photos
- `photos/electronics/` - PCB and chip photos
