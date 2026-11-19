# EdgeSense ESP32-S3 Firmware Guide

This firmware reads synchronized vibration data from an **ADXL345** (over **SPI**) and acoustic data from an **INMP441** (over **I2S**), packages the data into time-synchronized windows, and streams it in real-time over USB Serial to the EdgeSense Streamlit application.

---

## Verified Hardware Pinout & Wiring

### 1. ADXL345 Accelerometer (SPI Mode)
> [!IMPORTANT]
> On the common **GY-291** breakout board:
> * **`SDA`** is the SPI **MOSI / SDI** pin (Slave Data In).
> * **`SDO`** is the SPI **MISO** pin (Slave Data Out).
> * **`CS`** must be pulled LOW by GPIO 10 to switch the chip into 4-wire SPI mode.

| ADXL345 Pin | ESP32-S3 Pin | Function |
| :--- | :--- | :--- |
| **VCC** | **3.3V** | Power (Do NOT use 5V) |
| **GND** | **GND** | Ground |
| **CS** | **GPIO 10** | Chip Select (Active LOW) |
| **SCL** | **GPIO 12** | SPI Clock (SCK) |
| **SDA** | **GPIO 11** | SPI MOSI (Master Out Slave In) |
| **SDO** | **GPIO 13** | SPI MISO (Master In Slave Out) |

> [!TIP]
> If you see `ADXL345 DEVID 0xFF` on boot:
> 1. Check whether **SDA** and **SDO** are swapped.
> 2. Ensure **CS** is firmly plugged into GPIO 10.

---

### 2. INMP441 Omnidirectional MEMS Microphone (I2S Mode)

| INMP441 Pin | ESP32-S3 Pin | Function |
| :--- | :--- | :--- |
| **VDD** | **3.3V** | Power |
| **GND** | **GND** | Ground |
| **L/R** | **GND** | Channel Select (GND = Left Channel) |
| **SCK** | **GPIO 14** | I2S Bit Clock (BCLK) |
| **WS** | **GPIO 15** | I2S Word Select / Left-Right Clock (LRCK) |
| **SD** | **GPIO 16** | I2S Serial Data Out (DOUT / DIN) |

---

## Flashing Instructions (Arduino IDE)

1. Open **Arduino IDE**.
2. Open `v3/firmware/esp32s3_edgesense/esp32s3_edgesense.ino`.
3. Go to **Tools > Board > esp32 > ESP32S3 Dev Module**.
4. Set the following under the **Tools** menu:
   - **Flash Size:** `16MB (128Mb)`
   - **Partition Scheme:** `16M Flash (3MB APP/9.9MB FATFS)` or `Default 4MB with spiffs`
   - **PSRAM:** `OPI PSRAM` (or `Enabled`)
   - **USB CDC On Boot:** `Enabled`
   - **Upload Speed:** `921600`
5. Connect your ESP32-S3 board to your PC via USB-C.
6. Select the port (e.g. `/dev/ttyACM0`).
7. Click **Upload**.
8. Open the Serial Monitor at **115200 baud** to see:
   ```json
   {"status":"ok","sensor":"ADXL345","mode":"SPI_MODE3","devid":"0xE5"}
   {"status":"ok","sensor":"INMP441","msg":"I2S Stereo 16kHz initialized on GPIO 14, 15, 16"}
   ```
