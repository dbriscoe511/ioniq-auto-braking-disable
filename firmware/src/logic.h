// Pure decision logic: no ESP-IDF includes, so it builds and runs on the
// host (see host_test/). All times are a free-running uint32 ms clock;
// comparisons use unsigned subtraction, so wrap-around is harmless.
#pragma once
#include <stdbool.h>
#include <stdint.h>

// ---- Button sense filter --------------------------------------------------
typedef struct {
    bool pressed;          // debounced state
    bool candidate;
    uint32_t candidate_ms; // when the candidate state was first seen
    uint32_t since_ms;     // when the debounced state last changed
} sense_t;

void sense_init(sense_t *s, uint32_t now);
// Feed one ADC reading (mV at the GPIO). Returns the debounced state.
bool sense_update(sense_t *s, uint32_t now, int mv);

// ---- Controller -----------------------------------------------------------
typedef enum {
    ST_WAIT_STATUS, // no 0x05C17002 seen this drive
    ST_SETTLING,    // status present, waiting SETTLE_MS
    ST_ARMED,       // ready to decide / press
    ST_PRESSING,    // holding the button
    ST_VERIFY,      // released, waiting for 0x07
    ST_RETRY_GAP,   // before the single retry
    ST_DONE,        // nothing more until the status disappears (car off)
} ctl_state_t;

typedef enum {
    DONE_NONE,
    DONE_ALREADY_OFF, // status was 0x07 before we pressed
    DONE_TURNED_OFF,  // our press worked (0x09 -> 0x07)
    DONE_GAVE_UP,     // MAX_ATTEMPTS presses, still 0x09
    DONE_DISABLED,    // automation switched off by Dan
    DONE_RESUMED,     // rebooted mid-drive after being done
} done_reason_t;

typedef struct {
    // status frame tracking
    bool have_status;
    uint32_t last_rx_ms;
    uint8_t b0, b1;
    uint16_t same_n; // consecutive frames with this b1
    bool seen_off;   // 0x07 seen (3+ frames) this drive: Dan's choice stands

    // state machine
    ctl_state_t state;
    done_reason_t done_reason;
    uint32_t state_ms; // when the current state was entered
    uint8_t attempts;
    bool press_out;
    uint32_t release_ms; // last time press_out went false
    bool sense_seen;     // our press showed up on the sense line

    // configuration / diagnostics
    bool enabled;
    bool fault_no_sense; // a press did not pull the line low (wiring?)
    uint32_t drives;     // drive cycles seen since boot
    uint32_t presses;    // presses made since boot
} ctl_t;

void ctl_init(ctl_t *c, uint32_t now, bool enabled);
// After a mid-drive reset (OTA, watchdog): start latched as done, so a
// manual re-enable is not undone. Clears like any drive once the status is
// absent for STATUS_GONE_MS (counted from now if no frame ever arrives).
void ctl_init_resumed(ctl_t *c, uint32_t now, bool enabled);
// Status frame received within STATUS_FRESH_MS.
bool ctl_status_fresh(const ctl_t *c, uint32_t now);
// Call for every received 0x05C17002 data frame with DLC >= 2.
void ctl_status_frame(ctl_t *c, uint32_t now, uint8_t b0, uint8_t b1);
// Call periodically (~10 ms). btn_pressed = debounced sense state.
// Returns whether the press output should be on.
bool ctl_step(ctl_t *c, uint32_t now, bool btn_pressed, uint32_t btn_since_ms);
// True while the sense line reflects our own press (gestures must ignore it).
bool ctl_sense_masked(const ctl_t *c, uint32_t now);
const char *ctl_state_name(ctl_state_t s);
const char *ctl_done_name(done_reason_t r);

// ---- Gesture detector -----------------------------------------------------
typedef enum { GEST_NONE, GEST_TOGGLE_ENABLE, GEST_WIFI } gesture_t;

typedef struct {
    bool last_pressed;
    bool invalid; // current press too long, or began while masked
    uint32_t press_ms, release_ms;
    uint8_t count;
} gest_t;

void gest_init(gest_t *g);
gesture_t gest_step(gest_t *g, uint32_t now, bool pressed, bool masked);
