"""
Data Receiver and Ingestion Layer for EdgeSense.
Supports both real ESP32 USB Serial streaming and a high-fidelity Test Rig Simulator.
"""

import json
import time
import threading
from collections import deque
import numpy as np

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False


def list_available_ports() -> list[str]:
    """
    Find relevant USB serial ports on the host system.
    Prioritizes ESP32 / USB CDC / UART devices over raw virtual ttyS ports.
    """
    if not SERIAL_AVAILABLE:
        return []
    ports = serial.tools.list_ports.comports()
    
    usb_ports = []
    other_ports = []
    for p in ports:
        name = p.device
        desc = p.description or ""
        hwid = p.hwid or ""
        # Match Linux ttyACM/ttyUSB, Windows COM, or hardware descriptions
        if (
            "ACM" in name or "USB" in name or "COM" in name or
            "USB" in desc or "JTAG" in desc or "CDC" in desc or "CP210" in desc or "CH340" in desc
        ):
            usb_ports.append(name)
        else:
            other_ports.append(name)
            
    return usb_ports if usb_ports else other_ports


class DataStreamer:
    """
    Manages continuous streaming from ESP32 serial or synthetic test rig.
    Guarantees only one active serial handle exists in the Python process.
    """
    _active_instance = None

    def __init__(self, mode: str = "simulation", port: str = "", baud: int = 115200):
        # Stop and close any previous instance to prevent leaked serial handles
        if DataStreamer._active_instance is not None and DataStreamer._active_instance is not self:
            try:
                DataStreamer._active_instance.stop()
            except Exception:
                pass
        DataStreamer._active_instance = self

        self.mode = mode  # "serial" or "simulation"
        self.port = port
        self.baud = baud
        
        # Test Rig Simulation Condition
        self.sim_condition = "Normal Fan"  # "Normal Fan", "Broken Fan", "Motor Off", "Acoustic Disturbance Only"

        # Threading & Buffering
        self.running = False
        self.thread: threading.Thread | None = None
        self.serial_handle = None
        self.window_buffer = deque(maxlen=20)
        self.latest_window = None
        self.lock = threading.Lock()

        # Telemetry Diagnostics
        self.last_serial_error = None
        self.packets_received = 0
        self.last_packet_time = 0.0

        # Calibration state tracker
        self.is_calibrating = False
        self.calibration_buffer = []
        self.calib_start_time = 0.0
        self.calib_duration = 10.0

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self._close_serial()
        if self.thread and threading.current_thread() != self.thread:
            self.thread.join(timeout=0.5)

    def __del__(self):
        self._close_serial()

    def reconnect(self):
        """Forces immediate closing and reopening of serial port."""
        with self.lock:
            self._close_serial()
            self.last_serial_error = None
            self.packets_received = 0
            self.latest_window = None

    def _close_serial(self):
        if self.serial_handle:
            try:
                self.serial_handle.close()
            except Exception:
                pass
            self.serial_handle = None

    def configure(self, mode: str, port: str = "", baud: int = 115200):
        """Thread-safe reconfiguration of streaming source."""
        with self.lock:
            needs_serial_reset = (
                (self.mode != mode) or
                (self.port != port) or
                (self.baud != baud)
            )
            self.mode = mode
            self.port = port
            self.baud = baud
            if needs_serial_reset:
                self._close_serial()
                self.last_serial_error = None

    def set_simulation_condition(self, condition: str):
        self.sim_condition = condition

    def start_calibration(self, duration: float = 10.0):
        with self.lock:
            self.is_calibrating = True
            self.calibration_buffer = []
            self.calib_start_time = time.time()
            self.calib_duration = duration

    def get_calibration_progress(self) -> tuple[bool, float, list]:
        """
        Returns:
            (is_done, progress_ratio [0.0 - 1.0], collected_windows)
        """
        with self.lock:
            if not self.is_calibrating:
                return False, 0.0, []

            elapsed = time.time() - self.calib_start_time
            progress = min(1.0, elapsed / self.calib_duration)

            if elapsed >= self.calib_duration:
                self.is_calibrating = False
                collected = list(self.calibration_buffer)
                return True, 1.0, collected
            return False, progress, list(self.calibration_buffer)

    def get_latest_window(self) -> dict | None:
        with self.lock:
            return self.latest_window

    def _worker_loop(self):
        while self.running:
            if self.mode == "serial" and SERIAL_AVAILABLE:
                self._read_serial_data()
            else:
                self._generate_simulated_window()
                time.sleep(0.20)  # ~5 windows per second

    def _read_serial_data(self):
        if self.mode != "serial":
            self._close_serial()
            time.sleep(0.2)
            return

        try:
            if not self.serial_handle or not self.serial_handle.is_open:
                if not self.port or self.port == "No ports found":
                    time.sleep(0.3)
                    return
                # Open serial port with DTR/RTS enabled for ESP32-S3 USB CDC
                self.serial_handle = serial.Serial(self.port, self.baud, timeout=0.2)
                self.serial_handle.dtr = True
                self.serial_handle.rts = True
                time.sleep(0.1)
                self.serial_handle.reset_input_buffer()
                self.last_serial_error = None

            raw_bytes = self.serial_handle.readline()
            if not raw_bytes:
                return

            line = raw_bytes.decode("utf-8", errors="ignore").strip()
            if not line:
                return

            # Extract JSON block even if preceded by boot banners
            start_idx = line.find("{")
            end_idx = line.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = line[start_idx:end_idx + 1]
                data = json.loads(json_str)

                if data.get("type") == "data" and "v" in data and "a" in data:
                    vib = np.array(data["v"], dtype=np.float32)
                    aud = np.array(data["a"], dtype=np.float32)

                    window = {
                        "timestamp": data.get("ts", time.time() * 1000),
                        "vibration": vib,
                        "audio": aud,
                        "adxl_connected": data.get("adxl", True),
                        "mic_connected": data.get("mic", True),
                        "fs_vib": 800.0,
                        "fs_aud": 8000.0,
                        "source": f"Hardware ({self.port})"
                    }
                    self._push_window(window)
                    self.packets_received += 1
                    self.last_packet_time = time.time()
                    self.last_serial_error = None

        except serial.SerialException as se:
            err_msg = str(se)
            if "Device or resource busy" in err_msg or "Errno 16" in err_msg:
                self.last_serial_error = "Port busy: Arduino Serial Monitor is open! Please close it in Arduino IDE."
            else:
                self.last_serial_error = f"Serial port error: {se}"
            self._close_serial()
            time.sleep(0.5)
        except Exception as e:
            time.sleep(0.05)

    def _generate_simulated_window(self):
        """
        Generates realistic vibration (ADXL345) and acoustic (INMP441) signals
        for a 9V DC Motor test rig with normal vs broken fan.
        """
        fs_v = 800.0
        fs_a = 8000.0
        n_v = 160   # 200ms window
        n_a = 1600  # 200ms window
        
        t_v = np.arange(n_v) / fs_v
        t_a = np.arange(n_a) / fs_a

        # Motor rotation speed: ~50 Hz (3000 RPM on 9V battery)
        f_rot = 50.0 
        f_blade = 150.0  # 3-blade fan = 3 * 50Hz = 150 Hz

        rng = np.random.default_rng()

        if self.sim_condition == "Motor Off":
            vib = 0.005 * rng.normal(size=n_v)
            aud = 0.005 * rng.normal(size=n_a)

        elif self.sim_condition == "Normal Fan":
            # Smooth motor vibration: 1x small peak + bearing background
            vib = (
                0.14 * np.sin(2 * np.pi * f_rot * t_v) +
                0.04 * np.sin(2 * np.pi * 2 * f_rot * t_v) +
                0.06 * rng.normal(size=n_v)
            )
            # Smooth aerodynamic blade-pass noise + white motor hum
            aud = (
                0.15 * np.sin(2 * np.pi * f_blade * t_a) +
                0.05 * np.sin(2 * np.pi * (2 * f_blade) * t_a) +
                0.06 * rng.normal(size=n_a)
            )

        elif self.sim_condition == "Broken Fan":
            # 1. Strong dynamic unbalance at 1x rotational speed (0.75g peak)
            # 2. Harmonics at 2x and 3x due to asymmetric blade drag
            # 3. Intermittent mechanical impacts / impulsive kurtosis
            vib = (
                0.78 * np.sin(2 * np.pi * f_rot * t_v) +
                0.35 * np.sin(2 * np.pi * 2 * f_rot * t_v) +
                0.22 * np.sin(2 * np.pi * 3 * f_rot * t_v) +
                0.14 * rng.normal(size=n_v)
            )
            # Add sporadic blade-strike impact peaks (increases kurtosis significantly)
            impact_idx = rng.choice(n_v, size=4, replace=False)
            vib[impact_idx] += rng.uniform(0.6, 1.2, size=4)

            # Acoustic: Choppy fluttering turbulence + aerodynamic blade stall scream
            aud = (
                0.48 * np.sin(2 * np.pi * f_blade * t_a + 0.3 * np.sin(2 * np.pi * f_rot * t_a)) +
                0.32 * np.sin(2 * np.pi * 420.0 * t_a) +
                0.22 * rng.normal(size=n_a)
            )
            impact_aud_idx = rng.choice(n_a, size=15, replace=False)
            aud[impact_aud_idx] += rng.uniform(0.4, 0.8, size=15)

        elif self.sim_condition == "Acoustic Disturbance Only":
            # Motor is normal, but external ambient noise / speech is loud
            vib = 0.14 * np.sin(2 * np.pi * f_rot * t_v) + 0.05 * rng.normal(size=n_v)
            aud = 0.55 * np.sin(2 * np.pi * 650.0 * t_a) + 0.25 * rng.normal(size=n_a)

        else:
            vib = 0.15 * np.sin(2 * np.pi * f_rot * t_v) + 0.05 * rng.normal(size=n_v)
            aud = 0.15 * np.sin(2 * np.pi * f_blade * t_a) + 0.05 * rng.normal(size=n_a)

        window = {
            "timestamp": time.time() * 1000,
            "vibration": vib.astype(np.float32),
            "audio": aud.astype(np.float32),
            "adxl_connected": True,
            "mic_connected": True,
            "fs_vib": fs_v,
            "fs_aud": fs_a,
            "source": f"Simulator ({self.sim_condition})"
        }
        self._push_window(window)

    def _push_window(self, window: dict):
        with self.lock:
            self.latest_window = window
            self.window_buffer.append(window)
            if self.is_calibrating:
                self.calibration_buffer.append(window)
