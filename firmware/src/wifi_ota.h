// Wi-Fi access point + small web page: status, on/off switch, OTA upload.
// Off except for short windows (heat in the 7805: ~1 W with Wi-Fi on).
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

void wifi_ota_init(void);
// Bring the AP up (or extend it) until now + window_ms.
void wifi_ota_open(uint32_t now, uint32_t window_ms);
// Call from the control loop; closes the AP when the window has passed.
void wifi_ota_tick(uint32_t now);
bool wifi_ota_is_open(void);

// Implemented in main.c, called from the HTTP server task.
size_t app_status_json(char *buf, size_t len);
void app_request_enable(bool on);
bool app_pressing(void);
