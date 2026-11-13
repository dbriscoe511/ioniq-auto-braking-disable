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
    c->attempts = 0;
    c->seen_off = false;
    c->done_reason = DONE_NONE;
    c->sense_seen = false;
    enter(c, now, ST_WAIT_STATUS);
}

void ctl_init(ctl_t *c, uint32_t now, bool enabled) {
    *c = (ctl_t){0};
    c->enabled = enabled;
    c->release_ms = now;
    new_drive(c, now);
}

void ctl_init_resumed(ctl_t *c, uint32_t now, bool enabled) {
    ctl_init(c, now, enabled);
    c->have_status = true; // arm the "status gone" timer from now
    c->last_rx_ms = now;
    c->same_n = 0;
    c->b1 = 0;
    c->drives = 1;
    finish(c, now, DONE_RESUMED);
}

void ctl_status_frame(ctl_t *c, uint32_t now, uint8_t b0, uint8_t b1) {
    if (c->have_status && b1 == c->b1) {
        if (c->same_n < UINT16_MAX) c->same_n++;
    } else {
        c->same_n = 1;
    }
    c->have_status = true;
    c->last_rx_ms = now;
    c->b0 = b0;
    c->b1 = b1;
    if (b1 == STATUS_OFF && c->same_n >= 3) c->seen_off = true;
}

static bool fresh(const ctl_t *c, uint32_t now) {
    return c->have_status && ELAPSED(now, c->last_rx_ms) <= STATUS_FRESH_MS;
}

bool ctl_status_fresh(const ctl_t *c, uint32_t now) { return fresh(c, now); }

static bool stable(const ctl_t *c, uint32_t now, uint8_t v) {
    return fresh(c, now) && c->b1 == v && c->same_n >= STATUS_STABLE_N;
}

static void release(ctl_t *c, uint32_t now) {
    if (c->press_out) c->release_ms = now;
    c->press_out = false;
}

bool ctl_step(ctl_t *c, uint32_t now, bool btn_pressed, uint32_t btn_since_ms) {
    // Status gone for a while: car is off (or the bus went quiet). Anything
    // after this is a new drive. Always release first.
    if (c->have_status && ELAPSED(now, c->last_rx_ms) > STATUS_GONE_MS) {
        release(c, now);
        c->have_status = false;
        c->same_n = 0;
        new_drive(c, now);
    }

    switch (c->state) {
    case ST_WAIT_STATUS:
        if (c->have_status) {
            c->drives++;
            enter(c, now, ST_SETTLING);
        }
        break;

    case ST_SETTLING:
        // Already off at any point this drive (e.g. Dan's own long press,
        // then maybe back on): never second-guess him.
        if (c->seen_off) finish(c, now, DONE_ALREADY_OFF);
        else if (ELAPSED(now, c->state_ms) >= SETTLE_MS) enter(c, now, ST_ARMED);
        break;

    case ST_ARMED:
        if (!c->enabled) {
            finish(c, now, DONE_DISABLED);
        } else if (c->seen_off) {
            // Off at some point this drive, by us or by Dan. If it is back
            // on now, that was Dan: leave it.
            finish(c, now, c->attempts ? DONE_TURNED_OFF : DONE_ALREADY_OFF);
        } else if (c->attempts >= MAX_ATTEMPTS) {
            finish(c, now, DONE_GAVE_UP);
        } else if (stable(c, now, STATUS_ON) && !btn_pressed &&
                   ELAPSED(now, btn_since_ms) >= BTN_IDLE_MS) {
            // Fresh, stable 0x09 and nobody is touching the button.
            c->attempts++;
            c->presses++;
            c->sense_seen = false;
            c->press_out = true;
            enter(c, now, ST_PRESSING);
        }
        // Unknown byte-1 values or a stale status: keep waiting.
        break;

    case ST_PRESSING: {
        uint32_t held = ELAPSED(now, c->state_ms);
        if (btn_pressed) c->sense_seen = true;
        if (held >= SENSE_CHECK_MS && !c->sense_seen) c->fault_no_sense = true;
        bool off_seen = fresh(c, now) && c->b1 == STATUS_OFF && c->same_n >= 2;
        bool lost = !c->have_status ||
                    ELAPSED(now, c->last_rx_ms) > 1000; // status stopped
        if (off_seen || lost || held >= HOLD_MS) {
            release(c, now);
            enter(c, now, ST_VERIFY);
        }
        break;
    }

    case ST_VERIFY:
        if (stable(c, now, STATUS_OFF)) {
            finish(c, now, DONE_TURNED_OFF);
        } else if (ELAPSED(now, c->state_ms) >= VERIFY_MS) {
            if (c->attempts >= MAX_ATTEMPTS) finish(c, now, DONE_GAVE_UP);
            else enter(c, now, ST_RETRY_GAP);
        }
        break;

    case ST_RETRY_GAP:
        if (stable(c, now, STATUS_OFF)) finish(c, now, DONE_TURNED_OFF);
        else if (ELAPSED(now, c->state_ms) >= RETRY_GAP_MS) enter(c, now, ST_ARMED);
        break;

    case ST_DONE:
        // Latched for this drive, including when Dan turns auto-brake back
        // on himself. Cleared only by the status disappearing (above).
        break;
    }

    if (c->state != ST_PRESSING) release(c, now);
    return c->press_out;
}

bool ctl_sense_masked(const ctl_t *c, uint32_t now) {
    return c->press_out || ELAPSED(now, c->release_ms) < GEST_MASK_AFTER_MS;
}

const char *ctl_state_name(ctl_state_t s) {
    switch (s) {
    case ST_WAIT_STATUS: return "wait_status";
    case ST_SETTLING: return "settling";
    case ST_ARMED: return "armed";
    case ST_PRESSING: return "pressing";
    case ST_VERIFY: return "verify";
    case ST_RETRY_GAP: return "retry_gap";
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
