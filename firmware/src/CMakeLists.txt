idf_component_register(
    SRCS "main.c" "logic.c" "wifi_ota.c"
    INCLUDE_DIRS "."
    REQUIRES driver esp_adc esp_timer esp_wifi esp_netif esp_event
             esp_http_server app_update nvs_flash esp_app_format)
