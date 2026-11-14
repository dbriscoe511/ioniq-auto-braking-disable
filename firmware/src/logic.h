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
// Two jobs sharing one press output:
//  - auto-brake: once per drive, long-press if 0x05C17002 byte 1 reads 0x09.
//  - beep: each time byte 0 bit 0 turns on (reverse), one short press.
// Dan's own presses are seen directly on the sense line, so there's no
// guessing about who changed what:
//  - a long press by Dan during a drive -> leave auto-brake alone this drive
//  - the beep turning on right after Dan's press -> leave that beep on
typedef enum {
    ST_WAIT_STATUS, // no 0x05C17002 this drive
    ST_SETTLING,    // status present, waiting SETTLE_MS
    ST_ARMED,       // ready to press
    ST_PRESSING,    // long press held
    ST_VERIFY,      // released, waiting for 0x07 (then retry or done)
    ST_DONE,        // nothing more until the status disappears (car off)
} ctl_state_t;

typedef enum {
    DONE_NONE,
    DONE_ALREADY_OFF, // read 0x07 before we pressed
    DONE_TURNED_OFF,  // our press worked
    DONE_GAVE_UP,     // MAX_ATTEMPTS presses, still 0x09
    DONE_DISABLED,    // automation switched off
    DONE_USER,        // Dan long-pressed the button himself this drive
    DONE_RESUMED,     // rebooted mid-drive after being done
} done_reason_t;

typedef struct {
    // latest status frame
    bool have_status;
    uint32_t last_rx_ms;
    uint8_t b0, b1;
    uint16_t same_n; // consecutive frames with this byte 1

    // auto-brake state machine
    ctl_state_t state;
    done_reason_t done_reason;
    uint32_t state_ms;
    uint8_t attempts;

    // beep
    bool beep_pending;  // bit 0 just turned on, not by Dan: mute it
    bool beep_pressing; // short press in progress
    uint32_t beep_ms;

    // Dan's presses (from the sense line, ours masked out)
    bool user_down;
    uint32_t user_down_ms;
    uint32_t user_last_ms; // last moment his press was seen
    bool user_seen;

    // output
    bool press_out;
    uint32_t release_ms;
    bool sense_seen;

    // settings / diagnostics
    bool enabled, mute_beep;
    bool fault_no_sense;
    uint32_t drives, presses, beep_presses;
} ctl_t;

void ctl_init(ctl_t *c, uint32_t now, bool enabled, bool mute_beep);
// After a mid-drive software reset: start latched as done for this drive.
void ctl_init_resumed(ctl_t *c, uint32_t now, bool enabled, bool mute_beep);
// Every received 0x05C17002 data frame with DLC >= 2.
void ctl_status_frame(ctl_t *c, uint32_t now, uint8_t b0, uint8_t b1);
// Every ~10 ms. btn_pressed = debounced sense. Returns the press output.
bool ctl_step(ctl_t *c, uint32_t now, bool btn_pressed, uint32_t btn_since_ms);
bool ctl_status_fresh(const ctl_t *c, uint32_t now);
// True while the sense line shows our own press (not Dan's).
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
