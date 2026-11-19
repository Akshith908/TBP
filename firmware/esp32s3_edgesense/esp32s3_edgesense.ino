/*
 * =========================================================================================
 * EdgeSense ESP32-S3 Firmware (N16R8) - Fixed SPI & I2S Configuration
 * Multimodal Anomaly Detection: Vibration (ADXL345 via SPI) & Acoustics (INMP441 via I2S)
 * =========================================================================================
 *
 * Target Board: ESP32-S3 (ESP32S3 Dev Module / N16R8)
 *
 * VERIFIED PINOUT:
 * -----------------------------------------------------------------------------------------
 * ADXL345 Accelerometer (4-Wire SPI Mode):
 *   - VCC  -> 3.3V
 *   - GND  -> GND
 *   - CS   -> GPIO 10  (Chip Select)
 *   - SCL  -> GPIO 12  (SPI SCK)
 *   - SDA  -> GPIO 11  (SPI MOSI / SDI)
 *   - SDO  -> GPIO 13  (SPI MISO)
 *
 * INMP441 MEMS Microphone (I2S Audio):
 *   - VDD  -> 3.3V
 *   - GND  -> GND
 *   - L/R  -> GND      (Left Channel)
 *   - SCK  -> GPIO 14  (I2S BCLK / Bit Clock)
 *   - WS   -> GPIO 15  (I2S LRCK / Word Select)
 *   - SD   -> GPIO 16  (I2S DIN / Serial Data)
 * -----------------------------------------------------------------------------------------
 */

#include <Arduino.h>
#include <SPI.h>
#include "driver/i2s.h"

// ======================== PIN DEFINITIONS ========================
#define PIN_ADXL_CS    10
#define PIN_SPI_SCK    12
#define PIN_SPI_MOSI   11
#define PIN_SPI_MISO   13

#define PIN_I2S_SCK    14
#define PIN_I2S_WS     15
#define PIN_I2S_SD     16

// ======================== SENSOR CONFIG ========================
#define ADXL_REG_DEVID       0x00
#define ADXL_REG_BW_RATE     0x2C
#define ADXL_REG_POWER_CTL   0x2D
#define ADXL_REG_DATA_FORMAT 0x31
#define ADXL_REG_DATAX0      0x32

#define SPI_READ_BIT         0x80
#define SPI_MULTIBYTE_BIT    0x40

// I2S Configuration
#define I2S_PORT             I2S_NUM_0
#define I2S_SAMPLE_RATE      16000
#define I2S_DMA_BUF_LEN      512

// Streaming & Window Configuration
#define WINDOW_VIB_SAMPLES   128     // Points per packet
#define WINDOW_AUD_SAMPLES   256     // Points per packet
#define SEND_INTERVAL_MS     200     // 5 packets per second

// Hardware SPI instance (FSPI / SPI2)
SPIClass spiSensor(FSPI);
uint8_t spiMode = SPI_MODE3;

// Diagnostics & State
bool adxlFound = false;
bool i2sInitialized = false;
unsigned long lastSendTime = 0;

// ======================== ADXL345 SPI HELPERS ========================
void adxlWriteRegister(uint8_t reg, uint8_t value) {
  spiSensor.beginTransaction(SPISettings(1000000, MSBFIRST, spiMode));
  digitalWrite(PIN_ADXL_CS, LOW);
  spiSensor.transfer(reg & 0x3F);
  spiSensor.transfer(value);
  digitalWrite(PIN_ADXL_CS, HIGH);
  spiSensor.endTransaction();
}

uint8_t adxlReadRegister(uint8_t reg) {
  spiSensor.beginTransaction(SPISettings(1000000, MSBFIRST, spiMode));
  digitalWrite(PIN_ADXL_CS, LOW);
  spiSensor.transfer(reg | SPI_READ_BIT);
  uint8_t val = spiSensor.transfer(0x00);
  digitalWrite(PIN_ADXL_CS, HIGH);
  spiSensor.endTransaction();
  return val;
}

void adxlReadBurst(uint8_t reg, uint8_t *buffer, uint8_t len) {
  spiSensor.beginTransaction(SPISettings(1000000, MSBFIRST, spiMode));
  digitalWrite(PIN_ADXL_CS, LOW);
  spiSensor.transfer(reg | SPI_READ_BIT | SPI_MULTIBYTE_BIT);
  for (uint8_t i = 0; i < len; i++) {
    buffer[i] = spiSensor.transfer(0x00);
  }
  digitalWrite(PIN_ADXL_CS, HIGH);
  spiSensor.endTransaction();
}

bool testAdxlMode(uint8_t modeToTest) {
  spiMode = modeToTest;
  for (int attempt = 0; attempt < 3; attempt++) {
    uint8_t devId = adxlReadRegister(ADXL_REG_DEVID);
    if (devId == 0xE5) {
      return true;
    }
    delay(10);
  }
  return false;
}

bool initADXL345() {
  pinMode(PIN_ADXL_CS, OUTPUT);
  digitalWrite(PIN_ADXL_CS, HIGH);
  delay(20);

  // Initialize FSPI bus; pass -1 for SS so we retain manual GPIO control
  spiSensor.begin(PIN_SPI_SCK, PIN_SPI_MISO, PIN_SPI_MOSI, -1);

  // Try SPI Mode 3 first (standard ADXL345)
  if (testAdxlMode(SPI_MODE3)) {
    Serial.println("{\"status\":\"ok\",\"sensor\":\"ADXL345\",\"mode\":\"SPI_MODE3\",\"devid\":\"0xE5\"}");
  } else if (testAdxlMode(SPI_MODE0)) {
    Serial.println("{\"status\":\"ok\",\"sensor\":\"ADXL345\",\"mode\":\"SPI_MODE0\",\"devid\":\"0xE5\"}");
  } else {
    uint8_t badId = adxlReadRegister(ADXL_REG_DEVID);
    Serial.printf("{\"status\":\"error\",\"sensor\":\"ADXL345\",\"devid\":\"0x%02X\",\"msg\":\"Expected 0xE5. Check CS(10), SCL(12), SDA(11), SDO(13)\"}\n", badId);
    return false;
  }

  // Configure ADXL345
  adxlWriteRegister(ADXL_REG_BW_RATE, 0x0D);      // 800 Hz ODR
  adxlWriteRegister(ADXL_REG_DATA_FORMAT, 0x0B);  // +/- 16g, Full Resolution
  adxlWriteRegister(ADXL_REG_POWER_CTL, 0x08);    // Measurement Mode
  delay(10);

  return true;
}

void readADXL345(float &accelG) {
  if (!adxlFound) {
    accelG = 0.0f;
    return;
  }

  uint8_t raw[6];
  adxlReadBurst(ADXL_REG_DATAX0, raw, 6);

  int16_t x = (int16_t)((raw[1] << 8) | raw[0]);
  int16_t y = (int16_t)((raw[3] << 8) | raw[2]);
  int16_t z = (int16_t)((raw[5] << 8) | raw[4]);

  // Full-resolution sensitivity: 3.9 mg/LSB (0.0039 g/LSB)
  float gx = x * 0.0039f;
  float gy = y * 0.0039f;
  float gz = (z * 0.0039f) - 1.0f; // Subtract 1g static gravity component

  // Compute unbalance vibration
  accelG = gz + 0.5f * (gx + gy);
}

// ======================== INMP441 I2S HELPERS ========================
bool initINMP441() {
  // Use STEREO mode to eliminate the known ESP-IDF mono-channel clocking bug on ESP32-S3
  const i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = I2S_SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT,
    .communication_format = i2s_comm_format_t(I2S_COMM_FORMAT_STAND_I2S),
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 4,
    .dma_buf_len = I2S_DMA_BUF_LEN,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0
  };

  const i2s_pin_config_t pin_config = {
    .bck_io_num = PIN_I2S_SCK,
    .ws_io_num = PIN_I2S_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = PIN_I2S_SD
  };

  esp_err_t err = i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
  if (err != ESP_OK) {
    Serial.printf("{\"status\":\"error\",\"sensor\":\"INMP441\",\"code\":%d}\n", err);
    return false;
  }

  err = i2s_set_pin(I2S_PORT, &pin_config);
  if (err != ESP_OK) {
    Serial.printf("{\"status\":\"error\",\"sensor\":\"INMP441_PIN\",\"code\":%d}\n", err);
    return false;
  }

  Serial.println("{\"status\":\"ok\",\"sensor\":\"INMP441\",\"msg\":\"I2S Stereo 16kHz initialized on GPIO 14, 15, 16\"}");
  return true;
}

void readAudioBuffer(float *audArray, int count) {
  if (!i2sInitialized) {
    for (int i = 0; i < count; i++) {
      audArray[i] = 0.0f;
    }
    return;
  }

  int32_t stereo_samples[count * 2];
  size_t bytes_read = 0;

  esp_err_t res = i2s_read(I2S_PORT, stereo_samples, sizeof(stereo_samples), &bytes_read, pdMS_TO_TICKS(100));
  int frames_read = bytes_read / (2 * sizeof(int32_t));

  for (int i = 0; i < count; i++) {
    if (i < frames_read) {
      // INMP441 MSB justified 24 bits in 32-bit slot
      int32_t left = stereo_samples[i * 2] >> 8;
      int32_t right = stereo_samples[i * 2 + 1] >> 8;
      int32_t val = (abs(left) >= abs(right)) ? left : right;
      
      // True 24-bit linear audio normalization to [-1.0, 1.0]
      audArray[i] = (float)val / 8388608.0f;
    } else {
      audArray[i] = 0.0f;
    }
  }
}

// ======================== SETUP & MAIN LOOP ========================
void setup() {
  Serial.begin(115200);
  delay(1500);

  Serial.println("{\"status\":\"info\",\"msg\":\"EdgeSense ESP32-S3 starting up...\"}");

  adxlFound = initADXL345();
  i2sInitialized = initINMP441();

  Serial.printf("{\"status\":\"ready\",\"adxl_ok\":%s,\"inmp_ok\":%s}\n",
                adxlFound ? "true" : "false",
                i2sInitialized ? "true" : "false");
}

void loop() {
  unsigned long now = millis();
  if (now - lastSendTime < SEND_INTERVAL_MS) {
    delay(2);
    return;
  }
  lastSendTime = now;

  float vib_samples[WINDOW_VIB_SAMPLES];
  float aud_samples[WINDOW_AUD_SAMPLES];

  // 1. Read vibration window
  for (int i = 0; i < WINDOW_VIB_SAMPLES; i++) {
    readADXL345(vib_samples[i]);
    delayMicroseconds(250);
  }

  // 2. Read audio window
  readAudioBuffer(aud_samples, WINDOW_AUD_SAMPLES);

  // 3. Transmit JSON packet over Serial
  // Use 4 decimal places for vibration and 5 for audio so precision is preserved
  Serial.print("{\"type\":\"data\",\"ts\":");
  Serial.print(now);
  Serial.print(",\"adxl\":");
  Serial.print(adxlFound ? "true" : "false");
  Serial.print(",\"mic\":");
  Serial.print(i2sInitialized ? "true" : "false");

  Serial.print(",\"v\":[");
  for (int i = 0; i < WINDOW_VIB_SAMPLES; i++) {
    Serial.print(vib_samples[i], 4);
    if (i < WINDOW_VIB_SAMPLES - 1) Serial.print(",");
  }

  Serial.print("],\"a\":[");
  for (int i = 0; i < WINDOW_AUD_SAMPLES; i++) {
    Serial.print(aud_samples[i], 5);
    if (i < WINDOW_AUD_SAMPLES - 1) Serial.print(",");
  }
  Serial.println("]}");
}
