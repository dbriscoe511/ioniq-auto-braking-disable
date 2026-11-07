# Ioniq 5 auto-braking disable

Hardware mod to automatically turn off **Parking Safety** (rear auto-braking,
PCA-R) shortly after a 2025 Hyundai Ioniq 5 XRT is switched on. A hitch bike
rack makes the rear sensors trigger hard braking when reversing; today this is
done by hand every drive.

Status: **investigation**. Nothing is installed in the car yet.

> Safety: this disables a driver-assistance feature. It mirrors pressing the
> factory button, keeps the button working normally, and must never be able to
> turn the feature back *on* unexpectedly or interfere with other console
> controls. Use at your own risk.

## Approach

Tap the Parking Safety button's signal wire behind the centre-console switch
panel and emulate a press (> 2 s hold) once after startup, using the button's
LED line as feedback so the controller only presses when the feature is
actually on.

Ruled out so far:

- **OBD/CAN commands**: blocked by the security gateway on the 2025 car.
- **Infotainment firmware downgrade** (`NE1A.USA.ccNC.001.002.260821`):
  unsupported; signature-checked; no verified ccNC downgrade.
- **Trailer wiring / fake trailer**: not wanted.

## Findings

- [Teardown guide](docs/teardown.md): removing the console panel and switch
  assembly. Panel removal credit:
  [r/Ioniq5 MagSafe install post](https://www.reddit.com/r/Ioniq5/comments/1t76ayr/built_in_magsafe_phone_charger_without_exposed/).
- [Electronics](docs/electronics.md): switch PCB, ICs, debug header.
- [Findings](docs/findings.md): connector, probing plan, pin table, circuit
  ideas.

## Layout

- `docs/` - guides and notes
- `photos/teardown/` - disassembly photos
- `photos/electronics/` - PCB and chip photos
