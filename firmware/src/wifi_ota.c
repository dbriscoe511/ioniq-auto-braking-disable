#include "wifi_ota.h"

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "config.h"

#ifndef PS_AP_PASS
#error "PS_AP_PASS not defined (set it in the environment, see platformio.ini)"
#endif
_Static_assert(sizeof(PS_AP_PASS) >= 9, "PS_AP_PASS must be set to 8+ characters "
                                        "(PS_AP_PASS='...' pio run)");

static const char *TAG = "wifi";

static bool is_open;
static uint32_t opened_ms, deadline_ms;
static volatile int clients;
static volatile bool ota_busy;
static httpd_handle_t server;

#define ELAPSED(now, t) ((uint32_t)((now) - (t)))

// ---- Web page --------------------------------------------------------------

static const char PAGE[] =
    "<!doctype html><html><head><meta charset=utf-8>"
    "<meta name=viewport content='width=device-width,initial-scale=1'>"
    "<title>Parking Safety auto-disable</title>"
    "<style>body{font-family:system-ui,sans-serif;margin:16px;max-width:520px}"
    "pre{background:#eee;padding:8px;overflow:auto}button{font-size:16px;margin:4px 4px 4px 0}"
    "</style></head><body><h2>Parking Safety auto-disable</h2>"
    "<pre id=s>loading...</pre>"
    "<button onclick=\"en(1)\">Enable automation</button>"
    "<button onclick=\"en(0)\">Disable automation</button><br>"
    "<button onclick=\"mu(1)\">Mute reverse beep</button>"
    "<button onclick=\"mu(0)\">Keep reverse beep</button>"
    "<h3>Firmware update</h3><input type=file id=f accept='.bin'> "
    "<button onclick=up()>Upload</button><p id=o></p>"
    "<script>"
    "async function r(){try{let j=await(await fetch('/status')).json();"
    "s.textContent=JSON.stringify(j,null,1)}catch(e){s.textContent='offline'}}"
    "setInterval(r,1000);r();"
    "async function en(v){await fetch('/enable?on='+v,{method:'POST'});r()}"
    "async function mu(v){await fetch('/mute?on='+v,{method:'POST'});r()}"
    "async function up(){let x=f.files[0];if(!x)return;o.textContent='uploading...';"
    "let q=await fetch('/ota',{method:'POST',body:x});o.textContent=await q.text()}"
    "</script></body></html>";

static esp_err_t h_root(httpd_req_t *req) {
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, PAGE, HTTPD_RESP_USE_STRLEN);
}

static esp_err_t h_status(httpd_req_t *req) {
    char buf[768];
    size_t n = app_status_json(buf, sizeof buf);
    httpd_resp_set_type(req, "application/json");
    return httpd_resp_send(req, buf, n);
}

static esp_err_t h_enable(httpd_req_t *req) {
    char q[32], v[4];
    if (httpd_req_get_url_query_str(req, q, sizeof q) != ESP_OK ||
        httpd_query_key_value(q, "on", v, sizeof v) != ESP_OK || (v[0] != '0' && v[0] != '1'))
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "use ?on=0 or ?on=1");
    app_request_enable(v[0] == '1');
    return httpd_resp_sendstr(req, v[0] == '1' ? "enabled\n" : "disabled\n");
}

static esp_err_t h_mute(httpd_req_t *req) {
    char q[32], v[4];
    if (httpd_req_get_url_query_str(req, q, sizeof q) != ESP_OK ||
        httpd_query_key_value(q, "on", v, sizeof v) != ESP_OK || (v[0] != '0' && v[0] != '1'))
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "use ?on=0 or ?on=1");
    app_request_mute(v[0] == '1');
    return httpd_resp_sendstr(req, v[0] == '1' ? "beep mute on\n" : "beep mute off\n");
}

static esp_err_t h_ota(httpd_req_t *req) {
    if (app_pressing()) {
        httpd_resp_set_status(req, "409 Conflict");
        return httpd_resp_sendstr(req, "busy pressing the button, retry in a few seconds\n");
    }
    const esp_partition_t *part = esp_ota_get_next_update_partition(NULL);
    if (!part || req->content_len == 0 || req->content_len > part->size)
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "bad image size");

    esp_ota_handle_t h;
    esp_err_t err = esp_ota_begin(part, OTA_WITH_SEQUENTIAL_WRITES, &h);
    if (err != ESP_OK)
        return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, esp_err_to_name(err));
    ota_busy = true;

    static char buf[2048];
    size_t left = req->content_len;
    int timeouts = 0;
    while (left > 0) {
        int n = httpd_req_recv(req, buf, left < sizeof buf ? left : sizeof buf);
        if (n == HTTPD_SOCK_ERR_TIMEOUT && ++timeouts < 3) continue; // 10 s each
        if (n <= 0) {
            esp_ota_abort(h);
            ota_busy = false;
            return ESP_FAIL;
        }
        err = esp_ota_write(h, buf, n);
        if (err != ESP_OK) {
            esp_ota_abort(h);
            ota_busy = false;
            return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, esp_err_to_name(err));
        }
        left -= n;
        timeouts = 0;
    }
    err = esp_ota_end(h); // validates the image
    if (err == ESP_OK) err = esp_ota_set_boot_partition(part);
    ota_busy = false;
    if (err != ESP_OK)
        return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, esp_err_to_name(err));

    ESP_LOGW(TAG, "OTA written to %s, rebooting", part->label);
    httpd_resp_sendstr(req, "OK: rebooting into the new firmware (rolls back if it "
                            "doesn't run for 30 s)\n");
    vTaskDelay(pdMS_TO_TICKS(500));
    // Never cut a long press short: a truncated hold is a short press,
    // which would toggle the beep.
    for (int i = 0; i < 100 && app_pressing(); i++) vTaskDelay(pdMS_TO_TICKS(100));
    esp_restart();
    return ESP_OK;
}

static bool server_start(void) {
    if (server) return true;
    httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
    cfg.stack_size = 6144;
    cfg.recv_wait_timeout = 10;
    if (httpd_start(&server, &cfg) != ESP_OK) {
        server = NULL;
        ESP_LOGE(TAG, "http server failed to start");
        return false;
    }
    const httpd_uri_t uris[] = {
        {.uri = "/", .method = HTTP_GET, .handler = h_root},
        {.uri = "/status", .method = HTTP_GET, .handler = h_status},
        {.uri = "/enable", .method = HTTP_POST, .handler = h_enable},
        {.uri = "/ota", .method = HTTP_POST, .handler = h_ota},
        {.uri = "/mute", .method = HTTP_POST, .handler = h_mute},
    };
    for (size_t i = 0; i < sizeof uris / sizeof *uris; i++)
        if (httpd_register_uri_handler(server, &uris[i]) != ESP_OK) return false;
    return true;
}

static void server_stop(void) {
    if (!server) return;
    httpd_stop(server);
    server = NULL;
}

// ---- Wi-Fi AP ------------------------------------------------------------------

static void on_wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data) {
    (void)arg; (void)base; (void)data;
    if (id == WIFI_EVENT_AP_STACONNECTED) clients++;
    else if (id == WIFI_EVENT_AP_STADISCONNECTED && clients > 0) clients--;
}

void wifi_ota_init(void) {
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_ap();
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_wifi_event, NULL));

    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_SOFTAP);
    wifi_config_t ap = {0};
    int n = snprintf((char *)ap.ap.ssid, sizeof ap.ap.ssid, WIFI_AP_SSID_PREFIX "%02x%02x",
                     mac[4], mac[5]);
    ap.ap.ssid_len = n;
    strlcpy((char *)ap.ap.password, PS_AP_PASS, sizeof ap.ap.password);
    ap.ap.channel = WIFI_AP_CHANNEL;
    ap.ap.authmode = WIFI_AUTH_WPA2_PSK;
    ap.ap.max_connection = 2;
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap));
    ESP_LOGI(TAG, "AP SSID %s (http://192.168.4.1/)", (char *)ap.ap.ssid);
}

bool wifi_ota_open(uint32_t now, uint32_t window_ms) {
    if (!is_open) {
        if (esp_wifi_start() != ESP_OK) {
            ESP_LOGE(TAG, "wifi start failed");
            return false;
        }
        esp_wifi_set_max_tx_power(52); // 13 dBm: enough in the car, less heat
        is_open = true;
        if (!server_start()) {
            esp_wifi_stop();
            is_open = false;
            return false;
        }
        opened_ms = now;
        deadline_ms = now + window_ms;
        ESP_LOGI(TAG, "AP up for %" PRIu32 " s", window_ms / 1000);
    } else if ((int32_t)(now + window_ms - deadline_ms) > 0) {
        deadline_ms = now + window_ms;
    }
    return server != NULL;
}

void wifi_ota_tick(uint32_t now) {
    if (!is_open || ota_busy) return;
    bool expired = (int32_t)(now - deadline_ms) >= 0;
    bool hard_cap = ELAPSED(now, opened_ms) >= WIFI_CLIENT_MAX_MS;
    if ((expired && clients == 0) || hard_cap) {
        server_stop();
        esp_wifi_stop();
        is_open = false;
        clients = 0;
        ESP_LOGI(TAG, "AP down");
    }
}

bool wifi_ota_is_open(void) { return is_open; }
