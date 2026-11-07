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

See [docs/findings.md](docs/findings.md) for the console teardown, connector
details, and the probing plan.

## Layout

- `docs/findings.md` - hardware notes and measurements
- `docs/photos/` - teardown photos
