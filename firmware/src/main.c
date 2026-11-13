// Parking Safety auto-disable for the 2025 Ioniq 5 console panel.
//
// Listens (hardware-silent) to 0x05C17002 on the panel's CAN bus. Once per
// drive, if auto-brake reads on (0x09), it holds the Parking Safety button
// (CON1 pin 5) for up to 3 s and checks that it reads off (0x07).
// Decision logic lives in logic.c; this file is the hardware glue.
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/twai.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_app_desc.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs.h"
#include "nvs_flash.h"

#include "config.h"
#include "logic.h"
#include "wifi_ota.h"

static const char *TAG = "psd";

static ctl_t ctl;
static sense_t sense;
static gest_t gest;

// Shared with the HTTP task.
static portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
static struct {
    ctl_t ctl;
    int sense_mv;
    bool btn;
    uint32_t rx_frames, rx_missed, now;
    bool failsafe_tripped;
} snap;
static volatile int web_enable_req = -1; // -1 none, 0 off, 1 on

static esp_timer_handle_t failsafe_timer;
static volatile bool failsafe_tripped;
static bool press_cur;

static adc_oneshot_unit_handle_t adc;
static adc_cali_handle_t adc_cali;
static adc_channel_t adc_chan;

static uint32_t now_ms(void) { return (uint32_t)(esp_timer_get_time() / 1000); }

// ---- Pins: first thing at boot ------------------------------------------

static void pins_safe_init(void) {
    // Press output low (button released). The 10k base pull-down already
    // holds the NPN off through reset and boot; this just makes it explicit.
    gpio_set_level(PIN_PRESS, 0);
    gpio_config_t press = {
        .pin_bit_mask = 1ULL << PIN_PRESS,
        .mode = GPIO_MODE_OUTPUT,
    };
    ESP_ERROR_CHECK(gpio_config(&press));
    gpio_set_level(PIN_PRESS, 0);

    // CAN transceiver silent (S high). The 4.7k pull-up holds it high until
    // now; drive it high too. Nothing in this firmware ever drives it low.
    gpio_set_level(PIN_CAN_SLNT, 1);
    gpio_config_t slnt = {
        .pin_bit_mask = 1ULL << PIN_CAN_SLNT,
        .mode = GPIO_MODE_OUTPUT,
    };
    ESP_ERROR_CHECK(gpio_config(&slnt));
    gpio_set_level(PIN_CAN_SLNT, 1);
}

static void failsafe_cb(void *arg) {
    (void)arg;
    gpio_set_level(PIN_PRESS, 0);
    failsafe_tripped = true;
}

static void press_set(bool on) {
    if (on && !press_cur) {
        gpio_set_level(PIN_PRESS, 1);
        esp_timer_stop(failsafe_timer); // ok if not running
        ESP_ERROR_CHECK(esp_timer_start_once(failsafe_timer, HOLD_MAX_MS * 1000ULL));
        ESP_LOGI(TAG, "press");
    } else if (!on && press_cur) {
        gpio_set_level(PIN_PRESS, 0);
        esp_timer_stop(failsafe_timer);
        ESP_LOGI(TAG, "release");
    }
    press_cur = on;
}

// ---- CAN (listen-only) ------------------------------------------------------

static void can_init(void) {
    twai_general_config_t g =
        TWAI_GENERAL_CONFIG_DEFAULT(PIN_CAN_TX, PIN_CAN_RX, TWAI_MODE_LISTEN_ONLY);
    g.tx_queue_len = 0; // no transmit queue at all
    g.rx_queue_len = 32;
    g.alerts_enabled = TWAI_ALERT_NONE;
    twai_timing_config_t t = TWAI_TIMING_CONFIG_500KBITS();
    // Single filter, extended frame: ID in bits 31..3, RTR in bit 2.
    // Mask bit 1 = don't care. Accept only data frames with ID 0x05C17002.
    twai_filter_config_t f = {
        .acceptance_code = STATUS_ID << 3,
        .acceptance_mask = 0x3,
        .single_filter = true,
    };
    ESP_ERROR_CHECK(twai_driver_install(&g, &t, &f));
    ESP_ERROR_CHECK(twai_start());
}

static uint32_t rx_frames;

static void can_drain(uint32_t now) {
    twai_message_t m;
    while (twai_receive(&m, 0) == ESP_OK) {
        if (!m.extd || m.rtr || m.identifier != STATUS_ID || m.data_length_code < 2) continue;
        rx_frames++;
        ctl_status_frame(&ctl, now, m.data[0], m.data[1]);
    }
}

// ---- Button sense (ADC) ---------------------------------------------------

static void adc_init(void) {
    adc_unit_t unit;
    ESP_ERROR_CHECK(adc_oneshot_io_to_channel(PIN_SENSE_ADC, &unit, &adc_chan));
    adc_oneshot_unit_init_cfg_t u = {.unit_id = unit};
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&u, &adc));
    adc_oneshot_chan_cfg_t c = {.atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_DEFAULT};
    ESP_ERROR_CHECK(adc_oneshot_config_channel(adc, adc_chan, &c));
    adc_cali_curve_fitting_config_t cc = {
        .unit_id = unit, .chan = adc_chan, .atten = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    if (adc_cali_create_scheme_curve_fitting(&cc, &adc_cali) != ESP_OK) {
        ESP_LOGW(TAG, "ADC calibration unavailable, using raw scaling");
        adc_cali = NULL;
    }
}

static int sense_read_mv(void) {
    int raw = 0, mv = 0;
    if (adc_oneshot_read(adc, adc_chan, &raw) != ESP_OK) return -1;
    if (adc_cali && adc_cali_raw_to_voltage(adc_cali, raw, &mv) == ESP_OK) return mv;
    return raw * 3100 / 4095;
}

// ---- Settings (NVS) ---------------------------------------------------------

static bool load_enabled(void) {
    nvs_handle_t h;
    uint8_t v = 1;
    if (nvs_open("psd", NVS_READONLY, &h) == ESP_OK) {
        nvs_get_u8(h, "enabled", &v);
        nvs_close(h);
    }
    return v != 0;
}

static void save_enabled(bool on) {
    nvs_handle_t h;
    if (nvs_open("psd", NVS_READWRITE, &h) != ESP_OK) return;
    nvs_set_u8(h, "enabled", on);
    nvs_commit(h);
    nvs_close(h);
}

static void set_enabled(bool on, const char *why) {
    ctl.enabled = on;
    save_enabled(on);
    ESP_LOGW(TAG, "automation %s (%s); takes effect next drive",
             on ? "ENABLED" : "DISABLED", why);
}

// ---- Called from the HTTP task --------------------------------------------

size_t app_status_json(char *buf, size_t len) {
    taskENTER_CRITICAL(&lock);
    typeof(snap) s = snap;
    taskEXIT_CRITICAL(&lock);
    const esp_app_desc_t *d = esp_app_get_description();
    int n = snprintf(buf, len,
        "{\"fw\":\"%s\",\"uptime_s\":%" PRIu32 ",\"enabled\":%s,\"state\":\"%s\","
        "\"done\":\"%s\",\"status_seen\":%s,\"b0\":\"%02X\",\"b1\":\"%02X\","
        "\"attempts\":%u,\"presses\":%" PRIu32 ",\"drives\":%" PRIu32 ","
        "\"sense_mv\":%d,\"btn_pressed\":%s,\"fault_no_sense\":%s,"
        "\"failsafe_tripped\":%s,\"rx_frames\":%" PRIu32 ",\"rx_missed\":%" PRIu32 "}",
        d->version, s.now / 1000, s.ctl.enabled ? "true" : "false",
        ctl_state_name(s.ctl.state), ctl_done_name(s.ctl.done_reason),
        s.ctl.have_status ? "true" : "false", s.ctl.b0, s.ctl.b1, s.ctl.attempts,
        s.ctl.presses, s.ctl.drives, s.sense_mv, s.btn ? "true" : "false",
        s.ctl.fault_no_sense ? "true" : "false", s.failsafe_tripped ? "true" : "false",
        s.rx_frames, s.rx_missed);
    return n < 0 ? 0 : ((size_t)n < len ? (size_t)n : len - 1);
}

void app_request_enable(bool on) { web_enable_req = on; }

bool app_pressing(void) {
    taskENTER_CRITICAL(&lock);
    bool p = snap.ctl.press_out;
    taskEXIT_CRITICAL(&lock);
    return p;
}

// ---- Control loop -----------------------------------------------------------

static void control_task(void *arg) {
    (void)arg;
    ESP_ERROR_CHECK(esp_task_wdt_add(NULL));

    uint32_t now = now_ms();
    ctl_init(&ctl, now, load_enabled());
    sense_init(&sense, now);
    gest_init(&gest);
    ESP_LOGI(TAG, "automation %s", ctl.enabled ? "enabled" : "disabled");

    bool pending_verify = false;
    esp_ota_img_states_t st;
    if (esp_ota_get_state_partition(esp_ota_get_running_partition(), &st) == ESP_OK &&
        st == ESP_OTA_IMG_PENDING_VERIFY)
        pending_verify = true;

    ctl_state_t last_state = ctl.state;
    TickType_t wake = xTaskGetTickCount();
    for (;;) {
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(10));
        now = now_ms();

        can_drain(now);
        int mv = sense_read_mv();
        bool btn = mv >= 0 ? sense_update(&sense, now, mv) : sense.pressed;

        int req = web_enable_req;
        if (req >= 0) {
            web_enable_req = -1;
            set_enabled(req, "web");
        }

        press_set(ctl_step(&ctl, now, btn, sense.since_ms));

        switch (gest_step(&gest, now, btn, ctl_sense_masked(&ctl, now))) {
        case GEST_TOGGLE_ENABLE: set_enabled(!ctl.enabled, "button gesture"); break;
        case GEST_WIFI:
            ESP_LOGW(TAG, "Wi-Fi window opened by button gesture");
            wifi_ota_open(now, WIFI_GESTURE_WINDOW_MS);
            break;
        case GEST_NONE: break;
        }

        if (!ctl.press_out) wifi_ota_tick(now); // never stall mid-press

        if (ctl.state != last_state) {
            ESP_LOGI(TAG, "%s -> %s (b1=%02X, attempt %u, %s)", ctl_state_name(last_state),
                     ctl_state_name(ctl.state), ctl.b1, ctl.attempts,
                     ctl_done_name(ctl.done_reason));
            if (ctl.fault_no_sense)
                ESP_LOGW(TAG, "press did not pull the button line low: check wiring");
            last_state = ctl.state;
        }

        if (pending_verify && now >= MARK_VALID_AFTER_MS) {
            esp_ota_mark_app_valid_cancel_rollback();
            pending_verify = false;
            ESP_LOGI(TAG, "firmware marked valid");
        }

        twai_status_info_t ts = {0};
        twai_get_status_info(&ts);
        taskENTER_CRITICAL(&lock);
        snap.ctl = ctl;
        snap.sense_mv = mv;
        snap.btn = btn;
        snap.rx_frames = rx_frames;
        snap.rx_missed = ts.rx_missed_count + ts.rx_overrun_count;
        snap.now = now;
        snap.failsafe_tripped = failsafe_tripped;
        taskEXIT_CRITICAL(&lock);

        esp_task_wdt_reset();
    }
}

void app_main(void) {
    pins_safe_init();

    const esp_timer_create_args_t fa = {.callback = failsafe_cb, .name = "press_failsafe"};
    ESP_ERROR_CHECK(esp_timer_create(&fa, &failsafe_timer));

    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    ESP_LOGI(TAG, "Parking Safety auto-disable %s, reset reason %d",
             esp_app_get_description()->version, esp_reset_reason());

    adc_init();
    can_init();
    wifi_ota_init();
    // Recovery path that does not depend on the button/ADC code: the AP is
    // up for a minute after every power-on.
    wifi_ota_open(now_ms(), WIFI_BOOT_WINDOW_MS);

    xTaskCreate(control_task, "control", 4096, NULL, 10, NULL);
}
