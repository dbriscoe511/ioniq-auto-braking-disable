#include "logic.h"

#include "config.h"

#define ELAPSED(now, t) ((uint32_t)((now) - (t)))

// ---- Button sense filter --------------------------------------------------

void sense_init(sense_t *s, uint32_t now) {
    s->pressed = false;
    s->candidate = false;
    s->candidate_ms = now;
    s->since_ms = now;
}

bool sense_update(sense_t *s, uint32_t now, int mv) {
    bool raw = s->candidate;
    if (mv < SENSE_LOW_MV) raw = true;
    else if (mv > SENSE_HIGH_MV) raw = false;
    // between the thresholds: hysteresis, keep the previous candidate

    if (raw != s->candidate) {
        s->candidate = raw;
        s->candidate_ms = now;
    }
    if (s->candidate != s->pressed &&
        ELAPSED(now, s->candidate_ms) >= SENSE_DEBOUNCE_MS) {
        s->pressed = s->candidate;
        s->since_ms = now;
    }
    return s->pressed;
}

// ---- Controller -----------------------------------------------------------

static void enter(ctl_t *c, uint32_t now, ctl_state_t s) {
    c->state = s;
    c->state_ms = now;
}

static void finish(ctl_t *c, uint32_t now, done_reason_t r) {
    c->done_reason = r;
    enter(c, now, ST_DONE);
}

static void new_drive(ctl_t *c, uint32_t now) {
    c->have_status = false;
    c->same_n = 0;
    c->attempts = 0;
    c->beep_pending = false;
    c->user_brake = false;
    c->done_reason = DONE_NONE;
    enter(c, now, ST_WAIT_STATUS);
}

void ctl_init(ctl_t *c, uint32_t now, bool enabled, bool mute_beep) {
    *c = (ctl_t){0};
    c->enabled = enabled;
    c->mute_beep = mute_beep;
    c->release_ms = now - SELF_MASK_MS;
    new_drive(c, now);
}

void ctl_init_resumed(ctl_t *c, uint32_t now, bool enabled, bool mute_beep) {
    ctl_init(c, now, enabled, mute_beep);
    c->have_status = true; // run the "status gone" timer from now
    c->last_rx_ms = now;
    c->b1 = 0;
    c->b0 = 1; // beep state unknown: the first frame is not a rising edge
    c->drives = 1;
    finish(c, now, DONE_RESUMED);
}

// Dan pressed (a press that started while the car was awake) now or within
// USER_WINDOW_MS: whatever the module reports changing now was him.
static bool user_recent(const ctl_t *c, uint32_t now) {
    return c->user_down || (c->user_seen && ELAPSED(now, c->user_last_ms) < USER_WINDOW_MS);
}

void ctl_status_frame(ctl_t *c, uint32_t now, uint8_t b0, uint8_t b1) {
    bool beep = b0 & 1;
    bool was_beep = c->have_status && (c->b0 & 1);
    if (beep && !was_beep) c->beep_pending = !user_recent(c, now); // Dan's -> leave it
    if (!beep) c->beep_pending = false;

    bool same = c->have_status && b1 == c->b1;
    // Auto-brake flipped under Dan's finger: his choice for this drive.
    if (c->have_status && !same && user_recent(c, now)) c->user_brake = true;
    if (!same) c->same_n = 1;
    else if (c->same_n < UINT16_MAX) c->same_n++;
    c->have_status = true;
    c->last_rx_ms = now;
    c->b0 = b0;
    c->b1 = b1;
}

static bool fresh(const ctl_t *c, uint32_t now) {
    return c->have_status && ELAPSED(now, c->last_rx_ms) <= STATUS_FRESH_MS;
}

bool ctl_status_fresh(const ctl_t *c, uint32_t now) { return fresh(c, now); }

static bool stable(const ctl_t *c, uint32_t now, uint8_t v) {
    return fresh(c, now) && c->b1 == v && c->same_n >= STATUS_STABLE_N;
}

bool ctl_sense_masked(const ctl_t *c, uint32_t now) {
    return c->press_out || ELAPSED(now, c->release_ms) < SELF_MASK_MS;
}

// Dan's presses: only ones that start while the car is awake (pin 5's level
// with the car off, or a line already low at boot, is not a press).
static void track_user(ctl_t *c, uint32_t now, bool btn) {
    if (ctl_sense_masked(c, now)) return;
    if (btn && !c->user_down && !c->user_ignore) {
        if (fresh(c, now)) c->user_down = true;
        else c->user_ignore = true; // low before the car woke: ignore till released
    }
    if (!btn) {
        c->user_down = false;
        c->user_ignore = false;
    }
    if (c->user_down) {
        c->user_seen = true;
        c->user_last_ms = now;
    }
}

bool ctl_step(ctl_t *c, uint32_t now, bool btn, uint32_t btn_since_ms) {
    bool was_out = c->press_out;

    // Status gone: car off. Whatever comes next is a new drive.
    if (c->have_status && ELAPSED(now, c->last_rx_ms) > STATUS_GONE_MS) new_drive(c, now);

    track_user(c, now, btn);
    if (c->user_brake && c->state != ST_WAIT_STATUS && c->state != ST_DONE)
        finish(c, now, DONE_USER);
    bool btn_idle = !btn && ELAPSED(now, btn_since_ms) >= BTN_IDLE_MS;

    // ---- auto-brake, once per drive ----
    switch (c->state) {
    case ST_WAIT_STATUS:
        if (c->have_status) {
            c->drives++;
            enter(c, now, ST_SETTLING);
        }
        break;
    case ST_SETTLING:
        if (ELAPSED(now, c->state_ms) >= SETTLE_MS) enter(c, now, ST_ARMED);
        break;
    case ST_ARMED:
        if (!c->enabled) finish(c, now, DONE_DISABLED);
        else if (stable(c, now, STATUS_OFF))
            finish(c, now, c->attempts ? DONE_TURNED_OFF : DONE_ALREADY_OFF);
        else if (c->attempts >= MAX_ATTEMPTS) finish(c, now, DONE_GAVE_UP);
        else if (stable(c, now, STATUS_ON) && btn_idle && !c->beep_pressing) {
            c->attempts++;
            c->presses++;
            enter(c, now, ST_PRESSING);
        }
        break;
    case ST_PRESSING: {
        uint32_t held = ELAPSED(now, c->state_ms);
        bool off_seen = fresh(c, now) && c->b1 == STATUS_OFF && c->same_n >= 2;
        if (off_seen || !fresh(c, now) || held >= HOLD_MS) enter(c, now, ST_VERIFY);
        break;
    }
    case ST_VERIFY:
        if (stable(c, now, STATUS_OFF)) finish(c, now, DONE_TURNED_OFF);
        else if (ELAPSED(now, c->state_ms) >= VERIFY_MS) enter(c, now, ST_ARMED); // retry
        break;
    case ST_DONE:
        break;
    }

    // ---- beep: one short press each time it turns on (not by Dan) ----
    if (c->beep_pressing) {
        if (ELAPSED(now, c->beep_ms) >= BEEP_PRESS_MS) c->beep_pressing = false;
    } else if (c->beep_pending && c->enabled && c->mute_beep && fresh(c, now) &&
               c->state != ST_PRESSING && btn_idle) {
        c->beep_pending = false; // one try per beep-on
        c->beep_pressing = true;
        c->beep_ms = now;
        c->beep_presses++;
    }

    // ---- output ----
    c->press_out = c->state == ST_PRESSING || c->beep_pressing;
    if (c->press_out && !was_out) c->sense_seen = false;
    if (c->press_out) {
        if (btn) c->sense_seen = true;
        uint32_t since = c->beep_pressing ? c->beep_ms : c->state_ms;
        if (ELAPSED(now, since) >= SENSE_CHECK_MS && !c->sense_seen) c->fault_no_sense = true;
    }
    if (was_out && !c->press_out) c->release_ms = now;
    return c->press_out;
}

const char *ctl_state_name(ctl_state_t s) {
    switch (s) {
    case ST_WAIT_STATUS: return "wait_status";
    case ST_SETTLING: return "settling";
    case ST_ARMED: return "armed";
    case ST_PRESSING: return "pressing";
    case ST_VERIFY: return "verify";
    case ST_DONE: return "done";
    }
    return "?";
}

const char *ctl_done_name(done_reason_t r) {
    switch (r) {
    case DONE_NONE: return "-";
    case DONE_ALREADY_OFF: return "already_off";
    case DONE_TURNED_OFF: return "turned_off";
    case DONE_GAVE_UP: return "gave_up";
    case DONE_DISABLED: return "disabled";
    case DONE_USER: return "user";
    case DONE_RESUMED: return "resumed";
    }
    return "?";
}

// ---- Gesture detector -----------------------------------------------------

void gest_init(gest_t *g) { *g = (gest_t){0}; }

gesture_t gest_step(gest_t *g, uint32_t now, bool pressed, bool masked) {
    gesture_t out = GEST_NONE;

    if (masked) {
        // Our own press: forget any sequence, and don't count a press that
        // is still held when the mask ends.
        g->count = 0;
        g->invalid = pressed;
        g->last_pressed = pressed;
        return GEST_NONE;
    }

    if (pressed && !g->last_pressed) { // press edge
        if (g->count && ELAPSED(now, g->release_ms) > GEST_GAP_MAX_MS) g->count = 0;
        g->press_ms = now;
        g->invalid = false;
    } else if (!pressed && g->last_pressed) { // release edge
        uint32_t dur = ELAPSED(now, g->press_ms);
        if (!g->invalid && dur >= GEST_PRESS_MIN_MS && dur <= GEST_PRESS_MAX_MS) {
            if (g->count < UINT8_MAX) g->count++;
            g->release_ms = now;
        } else {
            g->count = 0;
        }
        g->invalid = false;
    } else if (pressed && ELAPSED(now, g->press_ms) > GEST_PRESS_MAX_MS) {
        g->invalid = true; // long press cancels the sequence
        g->count = 0;
    }

    if (!pressed && g->count && ELAPSED(now, g->release_ms) > GEST_GAP_MAX_MS) {
        if (g->count == GEST_TOGGLE_COUNT) out = GEST_TOGGLE_ENABLE;
        else if (g->count == GEST_WIFI_COUNT) out = GEST_WIFI;
        g->count = 0;
    }

    g->last_pressed = pressed;
    return out;
}
