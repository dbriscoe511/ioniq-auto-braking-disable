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

typedef struct {
    // parking module
    bool powered;      // sends status frames
    uint8_t b1;        // 0x09 / 0x07 / other
    uint32_t hold_ms;  // how long the line has been low
    bool toggled;      // already toggled during this hold
    uint32_t toggle_after_ms;
    bool ignore_presses; // module not ready yet
    int toggles;
    // Dan's finger
    bool finger;
    // device under test
    ctl_t ctl;
    sense_t sense;
    gest_t gest;
    bool out;
    int press_edges;
    int gestures[3];
    bool pressed_while_not_on; // started a press while b1 != 0x09
} sim_t;

static void sim_init(sim_t *s, uint32_t t, uint8_t b1, bool enabled) {
    memset(s, 0, sizeof *s);
    s->b1 = b1;
    s->toggle_after_ms = 2000;
    ctl_init(&s->ctl, t, enabled);
    sense_init(&s->sense, t);
    gest_init(&s->gest);
}

// Advance the simulation by 1 ms steps from *t to end.
static void sim_run(sim_t *s, uint32_t *t, uint32_t end) {
    for (; *t < end; (*t)++) {
        uint32_t now = *t;
        bool line_low = s->out || s->finger;
        // module: long press toggles once per hold
        if (line_low && s->powered) {
            s->hold_ms++;
            if (!s->toggled && !s->ignore_presses && s->hold_ms >= s->toggle_after_ms) {
                s->b1 = (s->b1 == 0x09) ? 0x07 : (s->b1 == 0x07 ? 0x09 : s->b1);
                s->toggled = true;
                s->toggles++;
            }
        } else {
            s->hold_ms = 0;
            s->toggled = false;
        }
        if (s->powered && now % 100 == 0) ctl_status_frame(&s->ctl, now, 0x2C, s->b1);

        if (now % 10 == 0) { // firmware loop period
            int mv = line_low ? 50 : 2700;
            bool pressed = sense_update(&s->sense, now, mv);
            bool was = s->out;
            s->out = ctl_step(&s->ctl, now, pressed, s->sense.since_ms);
            if (s->out && !was) {
                s->press_edges++;
                if (s->b1 != 0x09) s->pressed_while_not_on = true;
            }
            gesture_t g = gest_step(&s->gest, now, pressed, ctl_sense_masked(&s->ctl, now));
            s->gestures[g]++;
        }
    }
}

static void finger_tap(sim_t *s, uint32_t *t, uint32_t down_ms, uint32_t up_ms) {
    s->finger = true;
    sim_run(s, t, *t + down_ms);
    s->finger = false;
    sim_run(s, t, *t + up_ms);
}

static void test_normal_start(void) {
    printf("normal start: 0x09 -> one press -> 0x07, latched\n");
    sim_t s; uint32_t t = 1000;
    sim_init(&s, t, 0x09, true);
    s.powered = true;
    sim_run(&s, &t, t + 20000);
    CHECK(s.b1 == 0x07, "b1=%02x", s.b1);
    CHECK(s.press_edges == 1, "presses=%d", s.press_edges);
    CHECK(s.ctl.state == ST_DONE && s.ctl.done_reason == DONE_TURNED_OFF,
          "state=%s/%s", ctl_state_name(s.ctl.state), ctl_done_name(s.ctl.done_reason));
    CHECK(!s.ctl.fault_no_sense, "fault_no_sense");
    CHECK(!s.pressed_while_not_on, "pressed while not 0x09");
    // Hold is released as soon as 0x07 shows (~2.2 s), never past HOLD_MS.
    CHECK(s.toggles == 1, "toggles=%d", s.toggles);
    CHECK(s.gestures[GEST_TOGGLE_ENABLE] == 0 && s.gestures[GEST_WIFI] == 0, "our press counted as gesture");

    printf("  ...Dan re-enables during the drive: left alone\n");
    finger_tap(&s, &t, 2500, 100);
    CHECK(s.b1 == 0x09, "b1=%02x", s.b1);
    sim_run(&s, &t, t + 30000);
    CHECK(s.b1 == 0x09 && s.press_edges == 1, "b1=%02x presses=%d", s.b1, s.press_edges);

    printf("  ...short stop (<3 s status gap): still the same drive\n");
    s.powered = false;
    sim_run(&s, &t, t + 2000);
    s.powered = true;
    sim_run(&s, &t, t + 20000);
    CHECK(s.press_edges == 1, "presses=%d", s.press_edges);

    printf("  ...car off then on (status gone 10 s): new drive, presses again\n");
    s.powered = false;
    sim_run(&s, &t, t + 10000);
    s.powered = true;
    sim_run(&s, &t, t + 20000);
    CHECK(s.press_edges == 2 && s.b1 == 0x07, "presses=%d b1=%02x", s.press_edges, s.b1);
    CHECK(s.ctl.drives == 2, "drives=%u", s.ctl.drives);
}

static void test_already_off(void) {
    printf("start with 0x07: never presses\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x07, true);
    s.powered = true;
    sim_run(&s, &t, t + 30000);
    CHECK(s.press_edges == 0, "presses=%d", s.press_edges);
    CHECK(s.ctl.done_reason == DONE_ALREADY_OFF, "%s", ctl_done_name(s.ctl.done_reason));
}

static void test_off_then_dan_reenables_early(void) {
    printf("starts 0x07, Dan turns it on during settling: left on\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x07, true);
    s.powered = true;
    sim_run(&s, &t, 1000);
    finger_tap(&s, &t, 2500, 100); // his long press: 07 -> 09
    CHECK(s.b1 == 0x09, "b1=%02x", s.b1);
    sim_run(&s, &t, t + 30000);
    CHECK(s.press_edges == 0 && s.b1 == 0x09, "presses=%d b1=%02x", s.press_edges, s.b1);
}

static void test_unknown_value(void) {
    printf("unknown byte 1 (0x05): never presses\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x05, true);
    s.powered = true;
    sim_run(&s, &t, t + 30000);
    CHECK(s.press_edges == 0, "presses=%d", s.press_edges);
    CHECK(s.ctl.state == ST_ARMED, "state=%s", ctl_state_name(s.ctl.state));
}

static void test_disabled(void) {
    printf("automation disabled: never presses\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x09, false);
    s.powered = true;
    sim_run(&s, &t, t + 30000);
    CHECK(s.press_edges == 0 && s.ctl.done_reason == DONE_DISABLED, "presses=%d", s.press_edges);
}

static void test_no_status(void) {
    printf("no status frames (car off / bench): never presses\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x09, true);
    sim_run(&s, &t, t + 60000);
    CHECK(s.press_edges == 0 && s.ctl.state == ST_WAIT_STATUS, "presses=%d", s.press_edges);
}

static void test_module_not_ready(void) {
    printf("module ignores the first press: retries once, succeeds\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x09, true);
    s.powered = true;
    s.ignore_presses = true;
    sim_run(&s, &t, SETTLE_MS + 4000); // first press under way / done
    s.ignore_presses = false;
    sim_run(&s, &t, t + 30000);
    CHECK(s.press_edges == 2, "presses=%d", s.press_edges);
    CHECK(s.b1 == 0x07 && s.ctl.done_reason == DONE_TURNED_OFF, "b1=%02x %s", s.b1,
          ctl_done_name(s.ctl.done_reason));
    CHECK(!s.pressed_while_not_on, "pressed while not 0x09");
}

static void test_gives_up(void) {
    printf("module never responds: two presses, then gives up\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x09, true);
    s.powered = true;
    s.ignore_presses = true;
    sim_run(&s, &t, 120000);
    CHECK(s.press_edges == MAX_ATTEMPTS, "presses=%d", s.press_edges);
    CHECK(s.ctl.done_reason == DONE_GAVE_UP, "%s", ctl_done_name(s.ctl.done_reason));
}

static void test_slow_toggle(void) {
    printf("module toggles only after 2.9 s: press held long enough\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x09, true);
    s.powered = true;
    s.toggle_after_ms = 2900;
    sim_run(&s, &t, 30000);
    CHECK(s.press_edges == 1 && s.b1 == 0x07, "presses=%d b1=%02x", s.press_edges, s.b1);
}

static void test_finger_on_button(void) {
    printf("Dan holding the button when armed: waits for release\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x09, true);
    s.powered = true;
    s.ignore_presses = true; // his hold isn't a toggle in this test
    s.finger = true;
    sim_run(&s, &t, SETTLE_MS + 3000);
    CHECK(s.press_edges == 0, "pressed while finger down: %d", s.press_edges);
    s.finger = false;
    s.ignore_presses = false;
    sim_run(&s, &t, t + BTN_IDLE_MS - 100);
    CHECK(s.press_edges == 0, "pressed before idle time");
    sim_run(&s, &t, t + 15000);
    CHECK(s.press_edges == 1 && s.b1 == 0x07, "presses=%d b1=%02x", s.press_edges, s.b1);
}

static void test_no_sense_fault(void) {
    printf("sense line never drops during our press: fault flagged\n");
    ctl_t c; sense_t se; uint32_t t = 0;
    ctl_init(&c, t, true);
    sense_init(&se, t);
    for (; t < 20000; t += 10) {
        if (t % 100 == 0) ctl_status_frame(&c, t, 0x2C, 0x09);
        bool p = sense_update(&se, t, 2700); // broken wire: always released
        ctl_step(&c, t, p, se.since_ms);
    }
    CHECK(c.fault_no_sense, "fault not flagged");
    CHECK(c.presses == 2, "presses=%u", c.presses);
}

static void test_status_lost_while_pressing(void) {
    printf("status stops mid-press: releases within ~1 s\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x09, true);
    s.powered = true;
    s.ignore_presses = true;
    sim_run(&s, &t, SETTLE_MS + 1500);
    CHECK(s.out, "expected to be pressing");
    s.powered = false;
    sim_run(&s, &t, t + 1200);
    CHECK(!s.out, "still pressing after status loss");
}

static void test_gestures(void) {
    printf("gestures\n");
    sim_t s; uint32_t t = 0;
    sim_init(&s, t, 0x07, true);
    s.powered = true;
    sim_run(&s, &t, 10000); // DONE (already off)

    for (int i = 0; i < 4; i++) finger_tap(&s, &t, 150, 250);
    sim_run(&s, &t, t + 1000);
    CHECK(s.gestures[GEST_TOGGLE_ENABLE] == 1, "4 taps -> toggle: %d", s.gestures[GEST_TOGGLE_ENABLE]);

    for (int i = 0; i < 6; i++) finger_tap(&s, &t, 150, 250);
    sim_run(&s, &t, t + 1000);
    CHECK(s.gestures[GEST_WIFI] == 1, "6 taps -> wifi: %d", s.gestures[GEST_WIFI]);

    printf("  ...beep-muting taps 1.5 s apart: nothing\n");
    for (int i = 0; i < 8; i++) finger_tap(&s, &t, 150, 1500);
    CHECK(s.gestures[GEST_TOGGLE_ENABLE] == 1 && s.gestures[GEST_WIFI] == 1, "spaced taps counted");

    printf("  ...5 taps / 3 taps: nothing\n");
    for (int i = 0; i < 5; i++) finger_tap(&s, &t, 150, 250);
    sim_run(&s, &t, t + 1000);
    for (int i = 0; i < 3; i++) finger_tap(&s, &t, 150, 250);
    sim_run(&s, &t, t + 1000);
    CHECK(s.gestures[GEST_TOGGLE_ENABLE] == 1 && s.gestures[GEST_WIFI] == 1, "odd counts fired");

    printf("  ...long press inside a sequence cancels it\n");
    finger_tap(&s, &t, 150, 250);
    finger_tap(&s, &t, 150, 250);
    finger_tap(&s, &t, 1200, 250); // long-ish (not a 2 s toggle)
    finger_tap(&s, &t, 150, 250);
    finger_tap(&s, &t, 150, 250);
    sim_run(&s, &t, t + 1000);
    CHECK(s.gestures[GEST_TOGGLE_ENABLE] == 1, "cancelled sequence fired");
}

// ---- Replay of recorded captures -----------------------------------------

typedef struct {
    int frames, presses;
    bool press_on_non09;
    uint8_t first_b1;
    ctl_t ctl;
} replay_t;

static int replay(const char *path, replay_t *r) {
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    memset(r, 0, sizeof *r);
    sense_t se;
    uint32_t t = 0, next_step = 0;
    ctl_init(&r->ctl, 0, true);
    sense_init(&se, 0);
    bool out = false;
    char line[256];
    while (fgets(line, sizeof line, f)) {
        double ts;
        char fr[128];
        if (sscanf(line, "%lf %127s", &ts, fr) != 2) continue;
        uint32_t ft = (uint32_t)(ts * 1000.0 + 0.5);
        for (; next_step <= ft; next_step += 10) {
            t = next_step;
            bool p = sense_update(&se, t, out ? 50 : 2700);
            bool was = out;
            out = ctl_step(&r->ctl, t, p, se.since_ms);
            if (out && !was) {
                r->presses++;
                if (r->ctl.b1 != 0x09) r->press_on_non09 = true;
            }
        }
        // T + 8 hex id + dlc + data
        if (fr[0] != 'T' || strlen(fr) < 14 || strncmp(fr + 1, "05C17002", 8)) continue;
        int dlc = fr[9] - '0';
        if (dlc < 2) continue;
        unsigned b0, b1;
        if (sscanf(fr + 10, "%2x%2x", &b0, &b1) != 2) continue;
        if (!r->frames) r->first_b1 = (uint8_t)b1;
        r->frames++;
        ctl_status_frame(&r->ctl, ft, (uint8_t)b0, (uint8_t)b1);
    }
    fclose(f);
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
        printf("replay %-20s frames=%4d first=%02x presses=%d end=%s/%s\n", logs[i],
               r.frames, r.first_b1, r.presses, ctl_state_name(r.ctl.state),
               ctl_done_name(r.ctl.done_reason));
        CHECK(!r.press_on_non09, "%s: pressed while status != 09", logs[i]);
        CHECK(r.presses <= MAX_ATTEMPTS, "%s: %d presses", logs[i], r.presses);
        if (r.first_b1 == 0x07)
            CHECK(r.presses == 0, "%s: pressed on a drive that started at 07", logs[i]);
    }
}

int main(int argc, char **argv) {
    test_normal_start();
    test_already_off();
    test_off_then_dan_reenables_early();
    test_unknown_value();
    test_disabled();
    test_no_status();
    test_module_not_ready();
    test_gives_up();
    test_slow_toggle();
    test_finger_on_button();
    test_no_sense_fault();
    test_status_lost_while_pressing();
    test_gestures();
    if (argc > 1) test_replays(argv[1]);
    else printf("(no capture dir given: replay tests skipped)\n");
    printf(failures ? "\n%d FAILURE(S)\n" : "\nALL PASS\n", failures);
    return failures ? 1 : 0;
}
