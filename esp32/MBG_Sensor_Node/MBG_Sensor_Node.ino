#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>

// ============================================================================
// MBG Menu Detector - ESP32 Sensor Node
// Sensors: DHT22 + MQ135
// Sends data to Flask endpoint: POST /api/sensor
// ============================================================================

// WiFi configuration
const char* WIFI_SSID = "CIEBRO2";
const char* WIFI_PASSWORD = "1234566789";

// Use your laptop/server LAN IP, not localhost.
// Example: http://192.168.18.8:5000/api/sensor
const char* SERVER_URL = "https://mbg-menu-detector-mesinglearning-production.up.railway.app/api/sensor";
const char* CAPTURE_URL = "https://mbg-menu-detector-mesinglearning-production.up.railway.app/api/capture-request";

// Pin configuration
#define DHT_PIN 4
#define DHT_TYPE DHT22
#define MQ135_PIN 34
#define CAPTURE_BUTTON_PIN 27

// MQ135 raw ADC thresholds after the 10k/20k voltage divider.
// Initial calibration from spoiled rice/chicken test data around 371-450 ADC.
// Recalibrate with your own normal-air and spoiled-food samples.
const int GAS_WARNING_THRESHOLD = 400;
const int GAS_DANGEROUS_THRESHOLD = 430;
const int GAS_SAMPLE_COUNT = 8;
const int GAS_CONFIRM_READINGS = 2;

const unsigned long SEND_INTERVAL_MS = 10000;
const unsigned long GAS_WARMUP_MS = 120000;
const unsigned long BUTTON_DEBOUNCE_MS = 800;
unsigned long lastSendMs = 0;
unsigned long lastButtonPressMs = 0;
String confirmedGasStatus = "Warming Up";
String pendingGasStatus = "Warming Up";
int pendingGasStatusCount = 0;

DHT dht(DHT_PIN, DHT_TYPE);

void connectWiFi() {
  Serial.print("Connecting to WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.print("WiFi connected. ESP32 IP: ");
  Serial.println(WiFi.localIP());
}

String getGasStatus(int gasValue) {
  if (gasValue >= GAS_DANGEROUS_THRESHOLD) {
    return "Bahaya Bau Busuk";
  }
  if (gasValue >= GAS_WARNING_THRESHOLD) {
    return "Waspada Bau Busuk";
  }
  return "Normal";
}

int readAverageGasValue() {
  long total = 0;

  for (int i = 0; i < GAS_SAMPLE_COUNT; i++) {
    total += analogRead(MQ135_PIN);
    delay(80);
  }

  return total / GAS_SAMPLE_COUNT;
}

String confirmGasStatus(String currentStatus) {
  if (currentStatus == confirmedGasStatus) {
    pendingGasStatus = currentStatus;
    pendingGasStatusCount = 0;
    return confirmedGasStatus;
  }

  if (currentStatus != pendingGasStatus) {
    pendingGasStatus = currentStatus;
    pendingGasStatusCount = 1;
  } else {
    pendingGasStatusCount++;
  }

  if (pendingGasStatusCount >= GAS_CONFIRM_READINGS) {
    confirmedGasStatus = currentStatus;
    pendingGasStatusCount = 0;
  }

  return confirmedGasStatus;
}

String jsonNumberOrNull(float value, int decimals) {
  if (isnan(value)) {
    return "null";
  }

  return String(value, decimals);
}

void sendSensorData(float temperature, float humidity, int gasValue, String gasStatus) {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  HTTPClient http;
  http.begin(SERVER_URL);
  http.setTimeout(5000);
  http.addHeader("Content-Type", "application/json");

  String payload = "{";
  payload += "\"temperature\":" + jsonNumberOrNull(temperature, 1) + ",";
  payload += "\"humidity\":" + jsonNumberOrNull(humidity, 1) + ",";
  payload += "\"gas_status\":\"" + gasStatus + "\",";
  payload += "\"gas_value\":" + String(gasValue) + ",";
  payload += "\"source\":\"esp32\"";
  payload += "}";

  int httpCode = http.POST(payload);

  Serial.print("POST ");
  Serial.print(SERVER_URL);
  Serial.print(" -> ");
  Serial.println(httpCode);
  Serial.print("Payload: ");
  Serial.println(payload);

  if (httpCode > 0) {
    Serial.println(http.getString());
  } else {
    Serial.print("HTTP error: ");
    Serial.println(http.errorToString(httpCode));
  }

  http.end();
}

void sendCaptureRequest() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  HTTPClient http;
  http.begin(CAPTURE_URL);
  http.setTimeout(5000);
  http.addHeader("Content-Type", "application/json");

  String payload = "{\"source\":\"esp32_button\"}";
  int httpCode = http.POST(payload);

  Serial.print("POST ");
  Serial.print(CAPTURE_URL);
  Serial.print(" -> ");
  Serial.println(httpCode);

  if (httpCode > 0) {
    Serial.println(http.getString());
  } else {
    Serial.print("HTTP error: ");
    Serial.println(http.errorToString(httpCode));
  }

  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  dht.begin();
  analogReadResolution(12); // ESP32 ADC range: 0-4095
  pinMode(CAPTURE_BUTTON_PIN, INPUT_PULLUP);

  connectWiFi();
}

void loop() {
  if (
    digitalRead(CAPTURE_BUTTON_PIN) == LOW &&
    millis() - lastButtonPressMs >= BUTTON_DEBOUNCE_MS
  ) {
    lastButtonPressMs = millis();
    Serial.println("Capture button pressed");
    sendCaptureRequest();
  }

  if (millis() - lastSendMs < SEND_INTERVAL_MS) {
    return;
  }
  lastSendMs = millis();

  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();
  int gasValue = readAverageGasValue();
  String measuredGasStatus = millis() < GAS_WARMUP_MS ? "Warming Up" : getGasStatus(gasValue);
  String gasStatus = confirmGasStatus(measuredGasStatus);

  if (isnan(temperature) || isnan(humidity)) {
    Serial.println("DHT22 read failed; sending gas data with null temperature/humidity");
  }

  sendSensorData(temperature, humidity, gasValue, gasStatus);
}