# EdgeSense v3 — Multimodal Anomaly Detection Rig

This folder (`v3/`) contains the complete real-time implementation of **EdgeSense**, integrating live sensor streaming (or simulation) from an **ESP32-S3 (N16R8)** with:
* **ADXL345** (3-axis digital accelerometer connected via **SPI**)
* **INMP441** (Omnidirectional MEMS microphone connected via **I2S**)
* **9V DC Motor Test Rig** with interchangeable Normal vs. Broken fans
* **10-Second Baseline Calibration Flow** (self-learning Isolation Forest)
* **Real-time Live Streaming Graphs** (time-domain waveforms and FFT spectra)
* **Normality Index (0–100%) & Anomaly Scoring with Threshold Triggers**

---

## Directory Structure

```
v3/
├── app.py                     # Main Streamlit Dashboard (Live graphs, 10s calibration, scoring)
├── anomaly_detector.py        # Self-learning Isolation Forest & normality scoring engine
├── feature_engine.py          # Multimodal time-domain & FFT feature extraction
├── data_receiver.py           # USB Serial receiver + Test Rig simulator
├── requirements.txt           # Python dependencies
├── firmware/
│   ├── esp32s3_edgesense/
│   │   └── esp32s3_edgesense.ino # Production Arduino sketch for ESP32-S3 (SPI + I2S)
│   └── README.md              # Wiring diagrams, pinout table, and flashing guide
└── README.md                  # This file
```

---

## Hardware Pinout (ESP32-S3)

### ADXL345 Accelerometer (SPI Mode)
* **VCC** $\rightarrow$ `3.3V`
* **GND** $\rightarrow$ `GND`
* **CS** $\rightarrow$ `GPIO 10`
* **SCL** $\rightarrow$ `GPIO 12` (SPI SCK)
* **SDA** $\rightarrow$ `GPIO 11` (SPI MOSI)
* **SDO** $\rightarrow$ `GPIO 13` (SPI MISO)

### INMP441 MEMS Microphone (I2S Mode)
* **VDD** $\rightarrow$ `3.3V`
* **GND** $\rightarrow$ `GND`
* **L/R** $\rightarrow$ `GND` (Left Channel)
* **SCK** $\rightarrow$ `GPIO 4` (I2S BCLK)
* **WS** $\rightarrow$ `GPIO 5` (I2S LRCK / Word Select)
* **SD** $\rightarrow$ `GPIO 6` (I2S Serial Data)

---

## Running the Application

1. Activate your virtual environment:
   ```bash
   cd /home/kar908/Academics/TBP
   source venv_tbp/bin/activate
   ```

2. Run the Streamlit dashboard:
   ```bash
   streamlit run v3/app.py
   ```

---

## How to Test the 10-Second Calibration & Broken Fan Anomaly

### Mode 1: With Physical ESP32 Hardware
1. Connect the ESP32-S3 to your computer via USB-C.
2. Power the DC motor with the 9V battery with the **Normal Fan** attached.
3. In the sidebar, select **Data Source: ESP32-S3 USB Serial** and pick your port (e.g. `/dev/ttyACM0` or `/dev/ttyUSB0`).
4. Click **"🎯 Calibrate Normal Baseline (10s)"**.
5. The system records the motor's healthy vibration and acoustic signature for 10 seconds, fits the Isolation Forest model, and locks in the baseline profile.
6. The dashboard displays **NORMAL** (Normality score $\approx 85\% - 95\%$).
7. Now turn off the motor, attach the **Broken Fan**, and power it on.
8. The unbalance creates massive 1× vibration spikes and acoustic fluttering $\rightarrow$ Normality score plunges below **40%**, instantly triggering the **ABNORMAL** state and listing the root causes (e.g. *Vibration RMS: 4.8× baseline deviation*).

### Mode 2: Test Rig Simulator (Immediate Demo without Hardware)
1. Select **Data Source: Test Rig Simulator** in the sidebar.
2. With **Attached Fan Rotor: Normal Fan**, click **"🎯 Calibrate Normal Baseline (10s)"**.
3. Watch the progress bar count down 10 seconds and calibrate.
4. Once calibrated, change **Attached Fan Rotor** to **"Broken Fan"** in the sidebar.
5. Watch the real-time Normality Score History line plummet across the fault threshold, while the vibration waveform amplitudes surge and the acoustic spectra flare up!
