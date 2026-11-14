// Host tests for src/logic.c. Build and run with host_test/run.sh.
//
// 1. Simulated car: a model parking module that toggles auto-brake when the
//    button is held >= 2 s and reports 0x05C17002 every 100 ms.
// 2. Replay: the recorded in-car captures (captures/2026-11-12-car-can).
//    The recordings cannot react to our presses, so these check that the
//    logic never presses on 0x07 / unknown values and gives up after two.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../src/config.h"
#include "../src/logic.h"

static int failures;
#define CHECK(cond, ...)                                                   \
    do {                                                                   \
        if (!(cond)) {                                                     \
            failures++;                                                    \
            printf("  FAIL %s:%d: ", __FILE__, __LINE__);                  \
            printf(__VA_ARGS__);                                           \
            printf("\n");                                                  \
        }                                                                  \
    } while (0)

// ---- Simulated car --------------------------------------------------------
// Parking module model: a hold >= toggle_after_ms toggles auto-brake (during
// the hold, or on release); a shorter press (>= 50 ms) toggles the beep on
// release, reported beep_lag_ms later. Status frames every 100 ms.

typedef struct {
    bool powered;
    uint8_t b1;
    bool beep;
    uint32_t hold_ms;
    bool toggled;
    uint32_t toggle_after_ms;
    bool ignore_presses;
    bool on_release;
    uint32_t beep_lag_ms;
    int64_t beep_pending;
    int toggles, beep_toggles;
    bool finger; // Dan
    // device under test
    ctl_t ctl;
    sense_t sense;
    gest_t gest;
    bool out;
    int press_edges, beep_edges;
    bool pressed_while_not_on, beep_pressed_while_off;
    int gestures[3];
} sim_t;

static void sim_init(sim_t *s, uint32_t t, uint8_t b1, bool enabled) {
    memset(s, 0, sizeof *s);
    s->b1 = b1;
    s->toggle_after_ms = 2000;
    s->beep_pending = -1;
    ctl_init(&s->ctl, t, enabled, true);
    sense_init(&s->sense, t);
    gest_init(&s->gest);
}

static uint8_t flip(uint8_t b1) { return b1 == 0x09 ? 0x07 : (b1 == 0x07 ? 0x09 : b1); }

static void sim_run(sim_t *s, uint32_t *t, uint32_t end) {
    for (; *t < end; (*t)++) {
        uint32_t now = *t;
        bool low = s->out || s->finger;
        if (low && s->powered) {
            s->hold_ms++;
            if (!s->on_release && !s->toggled && !s->ignore_presses &&
                s->hold_ms >= s->toggle_after_ms) {
                s->b1 = flip(s->b1);
                s->toggled = true;
                s->toggles++;
            }
        } else {
            if (s->powered && !s->ignore_presses) {
                if (s->hold_ms >= 50 && s->hold_ms < s->toggle_after_ms)
                    s->beep_pending = now + s->beep_lag_ms;
                if (s->on_release && s->hold_ms >= s->toggle_after_ms) {
                    s->b1 = flip(s->b1);
                    s->toggles++;
                }
            }
            s->hold_ms = 0;
            s->toggled = false;
        }
        if (s->beep_pending >= 0 && now >= s->beep_pending) {
            s->beep = !s->beep;
            s->beep_toggles++;
            s->beep_pending = -1;
        }
        if (s->powered && now % 100 == 0)
            ctl_status_frame(&s->ctl, now, 0x2C | s->beep, s->b1);

        if (now % 10 == 0) {
            bool pressed = sense_update(&s->sense, now, low ? 50 : 2700);
            bool was = s->out;
            s->out = ctl_step(&s->ctl, now, pressed, s->sense.since_ms);
            if (s->out && !was) {
                if (s->ctl.beep_pressing) {
                    s->beep_edges++;
                    if (!s->beep) s->beep_pressed_while_off = true;
                } else {
                    s->press_edges++;
                    if (s->b1 != 0x09) s->pressed_while_not_on = true;
                }
            }
            s->gestures[gest_step(&s->gest, now, pressed, ctl_sense_masked(&s->ctl, now))]++;
        }
    }
}

static void finger_tap(sim_t *s, uint32_t *t, uint32_t down_ms, uint32_t up_ms) {
    s->finger = true;
    sim_run(s, t, *t + down_ms);
    s->finger = false;
    sim_run(s, t, *t + up_ms);
}

static void shift_reverse(sim_t *s) { s->beep = true; }

#define DONE_IS(s, r) CHECK((s).ctl.state == ST_DONE && (s).ctl.done_reason == (r), \
    "state=%s/%s", ctl_state_name((s).ctl.state), ctl_done_name((s).ctl.done_reason))

// ---- Auto-brake -------------------------------------------------------------

static void test_normal_start(void) {
    printf("normal start: 0x09 -> one long press -> 0x07, latched\n");
    sim_t s; uint32_t t = 1000;
    sim_init(&s, t, 0x09, true);
    s.powered = true;
    sim_run(&s, &t, t + 20000);
    CHECK(s.b1 == 0x07 && s.press_edges == 1 && s.toggles == 1, "b1=%02x presses=%d toggles=%d",
          s.b1, s.press_edges, s.toggles);
    DONE_IS(s, DONE_TURNED_OFF);
    CHECK(!s.ctl.fault_no_sense && !s.pressed_while_not_on && s.beep_edges == 0, "bad");
    CHECK(s.gestures[GEST_TOGGLE_ENABLE] == 0 && s.gestures[GEST_WIFI] == 0, "gesture from our press");

    printf("  ...Dan long-presses it back on: left alone\n");
    finger_tap(&s, &t, 2500, 100);
    sim_run(&s, &t, t + 30000);
    CHECK(s.b1 == 0x09 && s.press_edges == 1, "b1=%02x presses=%d", s.b1, s.press_edges);

    printf("  ...short status gap (<3 s): same drive\n");
    s.powered = false;
    sim_run(&s, &t, t + 2000);
    s.powered = true;
    sim_run(&s, &t, t + 20000);
    CHECK(s.press_edges == 1, "presses=%d", s.press_edges);

    printf("  ...car off then on: new drive, presses again\n");
    s.powered = false;
    sim_run(&s, &t, t + 10000);
    s.powered = true;
    sim_run(&s, &t, t + 20000);
    CHECK(s.press_edges == 2 && s.b1 == 0x07 && s.ctl.drives == 2, "presses=%d b1=%02x drives=%u",
          s.press_edges, s.b1, s.ctl.drives);
}

static void test_already_off(void) {
    printf("start at 0x07: never presses\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x07, true);
    s.powered = true;
    sim_run(&s, &t, 30000);
    CHECK(s.press_edges == 0, "presses=%d", s.press_edges);
    DONE_IS(s, DONE_ALREADY_OFF);
}

static void test_dan_turns_on_early(void) {
    printf("start at 0x07, Dan long-presses it on during settling: left on\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x07, true);
    s.powered = true;
    sim_run(&s, &t, 1000);
    finger_tap(&s, &t, 2500, 100);
    sim_run(&s, &t, t + 30000);
    CHECK(s.press_edges == 0 && s.b1 == 0x09, "presses=%d b1=%02x", s.press_edges, s.b1);
    DONE_IS(s, DONE_USER);
}

static void test_unknown_disabled_nostatus(void) {
    printf("unknown byte 1 / disabled / no status: never presses\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x05, true);
    s.powered = true;
    sim_run(&s, &t, 30000);
    CHECK(s.press_edges == 0 && s.ctl.state == ST_ARMED, "unknown: presses=%d", s.press_edges);
    sim_init(&s, t = 0, 0x09, false);
    s.powered = true;
    sim_run(&s, &t, 30000);
    CHECK(s.press_edges == 0, "disabled: presses=%d", s.press_edges);
    DONE_IS(s, DONE_DISABLED);
    sim_init(&s, t = 0, 0x09, true);
    sim_run(&s, &t, 60000);
    CHECK(s.press_edges == 0 && s.ctl.state == ST_WAIT_STATUS, "no status: presses=%d", s.press_edges);
}

static void test_retry_and_give_up(void) {
    printf("module ignores the first press: retries once, succeeds\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x09, true);
    s.powered = true;
    s.ignore_presses = true;
    sim_run(&s, &t, SETTLE_MS + 4000);
    s.ignore_presses = false;
    sim_run(&s, &t, 30000);
    CHECK(s.press_edges == 2 && s.b1 == 0x07, "presses=%d b1=%02x", s.press_edges, s.b1);
    DONE_IS(s, DONE_TURNED_OFF);
    printf("  ...never responds: two presses, gives up\n");
    sim_init(&s, t = 0, 0x09, true);
    s.powered = true;
    s.ignore_presses = true;
    sim_run(&s, &t, 120000);
    CHECK(s.press_edges == MAX_ATTEMPTS, "presses=%d", s.press_edges);
    DONE_IS(s, DONE_GAVE_UP);
}

static void test_module_timing_variants(void) {
    printf("module toggles at 2.9 s / on release: one press each\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x09, true);
    s.powered = true;
    s.toggle_after_ms = 2900;
    sim_run(&s, &t, 30000);
    CHECK(s.press_edges == 1 && s.b1 == 0x07, "2.9s: presses=%d b1=%02x", s.press_edges, s.b1);
    sim_init(&s, t = 0, 0x09, true);
    s.powered = true;
    s.on_release = true;
    sim_run(&s, &t, 30000);
    CHECK(s.press_edges == 1 && s.b1 == 0x07 && s.beep_toggles == 0,
          "release: presses=%d b1=%02x beep_toggles=%d", s.press_edges, s.b1, s.beep_toggles);
}

static void test_finger_on_button(void) {
    printf("Dan's finger on the button (< long) when armed: waits, then presses\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x09, true);
    s.powered = true;
    sim_run(&s, &t, SETTLE_MS - 500);
    s.finger = true;
    sim_run(&s, &t, t + 1200); // armed during this, 1.2 s < USER_LONG_MS
    CHECK(s.press_edges == 0, "pressed under his finger");
    s.finger = false;
    sim_run(&s, &t, t + BTN_IDLE_MS - 100);
    CHECK(s.press_edges == 0, "pressed before idle");
    sim_run(&s, &t, t + 15000);
    CHECK(s.press_edges == 1 && s.b1 == 0x07, "presses=%d b1=%02x", s.press_edges, s.b1);
}

static void test_no_sense_fault(void) {
    printf("sense line never drops during our press: fault flagged\n");
    ctl_t c; sense_t se; uint32_t t = 0;
    ctl_init(&c, t, true, true);
    sense_init(&se, t);
    for (; t < 20000; t += 10) {
        if (t % 100 == 0) ctl_status_frame(&c, t, 0x2C, 0x09);
        ctl_step(&c, t, sense_update(&se, t, 2700), se.since_ms);
    }
    CHECK(c.fault_no_sense && c.presses == 2, "fault=%d presses=%u", c.fault_no_sense, c.presses);
}

static void test_status_lost_while_pressing(void) {
    printf("status stops mid-press: releases\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x09, true);
    s.powered = true;
    s.ignore_presses = true;
    sim_run(&s, &t, SETTLE_MS + 1500);
    CHECK(s.out, "expected pressing");
    s.powered = false;
    sim_run(&s, &t, t + STATUS_FRESH_MS + 50);
    CHECK(!s.out, "still pressing");
}

static void test_resumed(void) {
    printf("reset mid-drive after done: stays latched until car off\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x09, true);
    ctl_init_resumed(&s.ctl, t, true, true);
    s.powered = true;
    sim_run(&s, &t, 30000);
    CHECK(s.press_edges == 0, "presses=%d", s.press_edges);
    s.powered = false;
    sim_run(&s, &t, t + 10000);
    s.powered = true;
    sim_run(&s, &t, t + 20000);
    CHECK(s.press_edges == 1 && s.b1 == 0x07, "presses=%d b1=%02x", s.press_edges, s.b1);
    printf("  ...no status ever arrives: unlatches after STATUS_GONE_MS\n");
    ctl_t c; t = 0;
    ctl_init_resumed(&c, t, true, true);
    for (; t < STATUS_GONE_MS + 100; t += 10) ctl_step(&c, t, false, 0);
    CHECK(c.state == ST_WAIT_STATUS, "state=%s", ctl_state_name(c.state));
}

// ---- Beep ---------------------------------------------------------------------

static void test_beep(void) {
    printf("beep: reverse turns it on -> one short press mutes it\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x07, true);
    s.powered = true;
    sim_run(&s, &t, 2000);
    shift_reverse(&s);
    uint32_t t0 = t;
    while (s.beep && t < t0 + 5000) sim_run(&s, &t, t + 10);
    CHECK(!s.beep && t - t0 < 600, "beep=%d took %u ms", s.beep, t - t0);
    sim_run(&s, &t, t + 5000);
    CHECK(s.beep_edges == 1 && s.press_edges == 0 && s.toggles == 0, "beep=%d long=%d",
          s.beep_edges, s.press_edges);

    printf("  ...5 more reverses: 5 more short presses\n");
    for (int i = 0; i < 5; i++) {
        shift_reverse(&s);
        sim_run(&s, &t, t + 3000);
    }
    CHECK(s.beep_edges == 6 && !s.beep, "presses=%d beep=%d", s.beep_edges, s.beep);

    printf("  ...Dan taps it back on: left on\n");
    finger_tap(&s, &t, 150, 100);
    sim_run(&s, &t, t + 5000);
    CHECK(s.beep && s.beep_edges == 6, "beep=%d presses=%d", s.beep, s.beep_edges);
    printf("  ...Dan taps it off; next reverse muted again\n");
    finger_tap(&s, &t, 150, 2000);
    shift_reverse(&s);
    sim_run(&s, &t, t + 3000);
    CHECK(!s.beep && s.beep_edges == 7, "beep=%d presses=%d", s.beep, s.beep_edges);
    CHECK(!s.beep_pressed_while_off, "pressed while off");
}

static void test_beep_with_autobrake(void) {
    printf("beep + auto-brake: reverse right after start, both handled\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x09, true);
    s.powered = true;
    sim_run(&s, &t, 1500);
    shift_reverse(&s);
    sim_run(&s, &t, 20000);
    CHECK(!s.beep && s.b1 == 0x07 && s.beep_edges == 1 && s.press_edges == 1,
          "beep=%d b1=%02x beep_p=%d long=%d", s.beep, s.b1, s.beep_edges, s.press_edges);
    printf("  ...reverse during the long press: short press waits, then mutes\n");
    sim_init(&s, t = 0, 0x09, true);
    s.powered = true;
    sim_run(&s, &t, SETTLE_MS + 1000);
    CHECK(s.out && s.ctl.state == ST_PRESSING, "not pressing");
    shift_reverse(&s);
    sim_run(&s, &t, 30000);
    CHECK(!s.beep && s.b1 == 0x07 && s.beep_edges == 1 && s.press_edges == 1,
          "beep=%d b1=%02x beep_p=%d long=%d", s.beep, s.b1, s.beep_edges, s.press_edges);
    CHECK(!s.pressed_while_not_on && !s.beep_pressed_while_off, "bad press");
}

static void test_beep_module_quirks(void) {
    printf("beep: module reports the toggle 1.2 s late: one press only\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x07, true);
    s.powered = true;
    s.beep_lag_ms = 1200;
    sim_run(&s, &t, 2000);
    shift_reverse(&s);
    sim_run(&s, &t, t + 10000);
    CHECK(!s.beep && s.beep_edges == 1, "beep=%d presses=%d", s.beep, s.beep_edges);
    printf("  ...module ignores the tap: one try, beep left on\n");
    sim_init(&s, t = 0, 0x07, true);
    s.powered = true;
    sim_run(&s, &t, 2000);
    s.ignore_presses = true;
    shift_reverse(&s);
    sim_run(&s, &t, t + 20000);
    CHECK(s.beep && s.beep_edges == 1, "presses=%d", s.beep_edges);
}

static void test_beep_disabled(void) {
    printf("beep: automation disabled / mute off -> no short press\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x07, false);
    s.powered = true;
    sim_run(&s, &t, 2000);
    shift_reverse(&s);
    sim_run(&s, &t, t + 5000);
    CHECK(s.beep && s.beep_edges == 0, "disabled: presses=%d", s.beep_edges);
    sim_init(&s, t = 0, 0x07, true);
    s.ctl.mute_beep = false;
    s.powered = true;
    sim_run(&s, &t, 2000);
    shift_reverse(&s);
    sim_run(&s, &t, t + 5000);
    CHECK(s.beep && s.beep_edges == 0, "mute off: presses=%d", s.beep_edges);
}

// ---- Gestures ---------------------------------------------------------------

static void test_gestures(void) {
    printf("gestures (taps also toggle the beep; ours never interferes)\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x07, true);
    s.powered = true;
    sim_run(&s, &t, 10000);
    for (int i = 0; i < 4; i++) finger_tap(&s, &t, 150, 250);
    sim_run(&s, &t, t + 1000);
    CHECK(s.gestures[GEST_TOGGLE_ENABLE] == 1, "4 taps: %d", s.gestures[GEST_TOGGLE_ENABLE]);
    for (int i = 0; i < 6; i++) finger_tap(&s, &t, 150, 250);
    sim_run(&s, &t, t + 1000);
    CHECK(s.gestures[GEST_WIFI] == 1, "6 taps: %d", s.gestures[GEST_WIFI]);
    CHECK(s.beep_edges == 0 && !s.beep, "beep presses=%d beep=%d", s.beep_edges, s.beep);
    printf("  ...taps 1.5 s apart / 5 / 3 taps / long press inside: nothing\n");
    for (int i = 0; i < 8; i++) finger_tap(&s, &t, 150, 1500);
    for (int i = 0; i < 5; i++) finger_tap(&s, &t, 150, 250);
    sim_run(&s, &t, t + 1000);
    for (int i = 0; i < 3; i++) finger_tap(&s, &t, 150, 250);
    sim_run(&s, &t, t + 1000);
    finger_tap(&s, &t, 150, 250);
    finger_tap(&s, &t, 150, 250);
    finger_tap(&s, &t, 1200, 250);
    finger_tap(&s, &t, 150, 250);
    finger_tap(&s, &t, 150, 250);
    sim_run(&s, &t, t + 1000);
    CHECK(s.gestures[GEST_TOGGLE_ENABLE] == 1 && s.gestures[GEST_WIFI] == 1, "extra gesture");
}

// ---- Replay of recorded captures -----------------------------------------

typedef struct {
    int frames, presses, beep_presses;
    bool press_on_non09, beep_press_while_off;
    uint8_t first_b1;
    ctl_t ctl;
} replay_t;

// The recordings have no button-line data, but every byte-1 change in them
// was Dan's long press (or the touchscreen): replay his finger as the line
// held low from 2.2 s before each change to 0.2 s after.
typedef struct { uint32_t t; uint8_t b0, b1; } frame_t;

static int replay(const char *path, replay_t *r) {
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    memset(r, 0, sizeof *r);
    static frame_t fr[20000];
    static uint32_t chg[200];
    int n = 0, nchg = 0;
    char line[256];
    while (fgets(line, sizeof line, f) && n < 20000) {
        double ts;
        char x[128];
        if (sscanf(line, "%lf %127s", &ts, x) != 2) continue;
        if (x[0] != 'T' || strlen(x) < 14 || strncmp(x + 1, "05C17002", 8) || x[9] < '2') continue;
        unsigned b0, b1;
        if (sscanf(x + 10, "%2x%2x", &b0, &b1) != 2) continue;
        fr[n] = (frame_t){(uint32_t)(ts * 1000.0 + 0.5), (uint8_t)b0, (uint8_t)b1};
        if (n && fr[n - 1].b1 != b1 && nchg < 200) chg[nchg++] = fr[n].t;
        n++;
    }
    fclose(f);
    if (!n) return 0;
    r->frames = n;
    r->first_b1 = fr[0].b1;

    sense_t se;
    ctl_init(&r->ctl, 0, true, true);
    sense_init(&se, 0);
    bool out = false;
    int i = 0;
    for (uint32_t t = 0; t <= fr[n - 1].t + 10; t += 10) {
        for (; i < n && fr[i].t <= t; i++) ctl_status_frame(&r->ctl, fr[i].t, fr[i].b0, fr[i].b1);
        bool finger = false;
        for (int k = 0; k < nchg; k++)
            if (t + 2200 >= chg[k] && t <= chg[k] + 200) finger = true;
        bool p = sense_update(&se, t, (out || finger) ? 50 : 2700);
        bool was = out;
        out = ctl_step(&r->ctl, t, p, se.since_ms);
        if (out && !was) {
            if (r->ctl.beep_pressing) {
                r->beep_presses++;
                if (!(r->ctl.b0 & 1)) r->beep_press_while_off = true;
            } else {
                r->presses++;
                if (r->ctl.b1 != 0x09) r->press_on_non09 = true;
            }
        }
    }
    return 0;
}

static void test_replays(const char *dir) {
    static const char *logs[] = {
        "baseline.log", "buttons.log", "buttons2.log", "monitor2.log", "scan_S6.log",
        "screen_toggle.log", "settings_screen.log", "stage1_short.log",
        "stage2_long.log", "stage3_gear.log", "stages.log",
    };
    for (size_t i = 0; i < sizeof logs / sizeof *logs; i++) {
        char path[1024];
        snprintf(path, sizeof path, "%s/%s", dir, logs[i]);
        replay_t r;
        if (replay(path, &r)) {
            printf("replay %-20s MISSING\n", logs[i]);
            failures++;
            continue;
        }
        printf("replay %-20s frames=%4d first=%02x long=%d beep=%d end=%s/%s\n", logs[i],
               r.frames, r.first_b1, r.presses, r.beep_presses, ctl_state_name(r.ctl.state),
               ctl_done_name(r.ctl.done_reason));
        CHECK(!r.beep_press_while_off, "%s: short press while beep off", logs[i]);
        CHECK(!r.press_on_non09, "%s: pressed while status != 09", logs[i]);
        CHECK(r.presses <= MAX_ATTEMPTS, "%s: %d presses", logs[i], r.presses);
        if (r.first_b1 == 0x07)
            CHECK(r.presses == 0, "%s: pressed on a drive that started at 07", logs[i]);
    }
}

int main(int argc, char **argv) {
    test_normal_start();
    test_already_off();
    test_dan_turns_on_early();
    test_unknown_disabled_nostatus();
    test_retry_and_give_up();
    test_module_timing_variants();
    test_finger_on_button();
    test_no_sense_fault();
    test_status_lost_while_pressing();
    test_resumed();
    test_beep();
    test_beep_with_autobrake();
    test_beep_module_quirks();
    test_beep_disabled();
    test_gestures();
    if (argc > 1) test_replays(argv[1]);
    else printf("(no capture dir given: replay tests skipped)\n");
    printf(failures ? "\n%d FAILURE(S)\n" : "\nALL PASS\n", failures);
    return failures ? 1 : 0;
}
