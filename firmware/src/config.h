// Parking Safety auto-disable: pins and tunables.
//
// Pin map follows the KiCad schematic on branch
// t3/esp32c3-recovery-kicad-schematic (commit a5637be,
// hardware/esp32c3-recovery/). Check it again if the schematic changes.
#pragma once

// ---- Pins (ESP32-C3 SuperMini) ------------------------------------------
#define PIN_PRESS 10     // 1k -> 2N3904 base; high = pull CON1-5 to GND via 200R
#define PIN_SENSE_ADC 3  // CON1-5 through 100k/27k divider (ADC1 channel 3)
#define PIN_CAN_SLNT 5   // CAN Pal S pin; high = transmitter off (4.7k pull-up)
#define PIN_CAN_TX 6     // CAN Pal TX; never used (listen-only)
#define PIN_CAN_RX 7     // CAN Pal RX
// GPIO2/8/9 are strapping pins (GPIO8 = LED): unused. GPIO20/21 = UART0.

// ---- CAN ----------------------------------------------------------------
// 0x05C17002 (29-bit), 10 Hz: byte 1 = 0x09 auto-brake on, 0x07 off.
// See docs/can-car-capture.md.
#define STATUS_ID 0x05C17002u
#define STATUS_ON 0x09
#define STATUS_OFF 0x07

// The status frame arrives every 100 ms in every car capture (no gaps).
#define STATUS_FRESH_MS 300   // last frame must be newer than this to act
#define STATUS_STABLE_N 10    // consecutive identical byte-1 frames (~1 s)
#define STATUS_GONE_MS 3000   // absence that counts as "car off" -> new drive

// ---- Timing (ms) ----------------------------------------------------------
// GUESS: nothing measured yet on how soon after start-up the parking module
// accepts a long press. The verify-and-retry covers a premature press.
#define SETTLE_MS 4000        // after status first appears in a drive
#define BTN_IDLE_MS 500       // button line must read released this long
#define HOLD_MS 3000          // long press; > 2 s needed (Dan)
#define HOLD_MAX_MS 3500      // hardware-timer failsafe release
#define VERIFY_MS 3000        // after release, wait this long for 0x07, then retry
#define MAX_ATTEMPTS 2
#define SENSE_CHECK_MS 200    // our own press must show on the sense line by now
#define SELF_MASK_MS 150      // sense line still settling after our release
#define USER_WINDOW_MS 1000   // a change this soon after Dan's press was his

// ---- Beep mute ---------------------------------------------------------------
// 0x05C17002 byte 0 bit 0 = parking warning sound on. Shifting into reverse
// sets it (~0.2 s after the shift, stage3_gear.log); a short press toggles
// it. One short press each time it turns on, unless Dan's press turned it on.
#define BEEP_PRESS_MS 300        // short press (well under the 2 s long press)

// ---- Button sense (mV at GPIO3) ------------------------------------------
// Released: 12.2-14.4 V -> ~2.6-3.1 V. Pressed: near 0 V (exact value
// unmeasured; depends on the pull-up inside the parking module).
#define SENSE_LOW_MV 900      // below -> pressed
#define SENSE_HIGH_MV 1300    // above -> released
#define SENSE_DEBOUNCE_MS 30

// ---- Gestures (Dan's own short presses) ----------------------------------
// Even counts leave the beep state as it was (each short press toggles it).
// Presses must be quick and close together so the normal "mute the beep in
// reverse" single press never adds up to a gesture.
#define GEST_PRESS_MIN_MS 40
#define GEST_PRESS_MAX_MS 600
#define GEST_GAP_MAX_MS 600   // release -> next press
#define GEST_TOGGLE_COUNT 4   // toggle automation on/off (stored in flash)
#define GEST_WIFI_COUNT 6     // open the Wi-Fi/OTA window

// ---- Wi-Fi / OTA ---------------------------------------------------------
// Off by default: an LDO drops ~9 V, so Wi-Fi (~80-120 mA) is 1-1.5 W of
// heat in a closed console vs ~0.3 W idle. Up only on request (6 taps), or
// once after an OTA so the new image can prove the update path still works.
#define WIFI_GESTURE_WINDOW_MS (2 * 60 * 1000) // with no client connected
#define WIFI_CLIENT_MAX_MS (10 * 60 * 1000)    // hard cap even with a client
#define WIFI_AP_SSID_PREFIX "ps-disable-"
#define WIFI_AP_CHANNEL 6
#define MARK_VALID_AFTER_MS (30 * 1000)        // OTA rollback confirmation
