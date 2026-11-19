import time
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from collections import deque

from feature_engine import extract_multimodal_features, FEATURE_NAMES
from anomaly_detector import EdgeSenseDetector
from data_receiver import DataStreamer, list_available_ports

# ======================== PAGE CONFIG ========================
st.set_page_config(
    page_title="EdgeSense v3 | Multimodal Machine Anomaly Detection",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ======================== CSS STYLING ========================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600;700&display=swap');

:root {
    --bg: #0B0E14;
    --card-bg: #121721;
    --border: rgba(255,255,255,0.08);
    --text-primary: #E6EDF3;
    --text-muted: #8B949E;
    --accent-green: #2EA043;
    --accent-amber: #D29922;
    --accent-red: #F85149;
    --accent-cyan: #38BDF8;
    --accent-purple: #A855F7;
}

[data-testid="stAppViewContainer"], [data-testid="stHeader"] {
    background: var(--bg);
    color: var(--text-primary);
}

html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', system-ui, sans-serif;
}

.block-container {
    padding-top: 1.2rem;
    padding-bottom: 2rem;
    max-width: 1560px;
}

[data-testid="stSidebar"] {
    background: var(--card-bg);
    border-right: 1px solid var(--border);
}

.header-box {
    background: linear-gradient(135deg, #161B26 0%, #0F131C 100%);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 18px 24px;
    margin-bottom: 18px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.pulse-dot {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background-color: var(--accent-cyan);
    margin-right: 8px;
    animation: pulse-ring 2s infinite;
}

@keyframes pulse-ring {
    0% { box-shadow: 0 0 0 0 rgba(56, 189, 248, 0.6); }
    70% { box-shadow: 0 0 0 8px rgba(56, 189, 248, 0); }
    100% { box-shadow: 0 0 0 0 rgba(56, 189, 248, 0); }
}

.stat-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-left: 4px solid var(--accent-cyan);
    border-radius: 8px;
    padding: 14px 16px;
    min-height: 110px;
}

.stat-label {
    font-size: 12px;
    font-weight: 500;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.stat-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 26px;
    font-weight: 700;
    margin-top: 4px;
}

.stat-sub {
    font-size: 12px;
    color: var(--text-muted);
    margin-top: 4px;
}

.alert-badge {
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
}

.explain-box {
    background: rgba(22, 27, 38, 0.7);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 18px;
    margin-top: 10px;
}
</style>
""", unsafe_allow_html=True)


# ======================== GLOBAL SINGLETONS ========================
@st.cache_resource
def get_global_streamer() -> DataStreamer:
    s = DataStreamer(mode="simulation")
    s.start()
    return s

@st.cache_resource
def get_global_detector() -> EdgeSenseDetector:
    return EdgeSenseDetector(normal_threshold=65.0, warning_threshold=40.0)

streamer: DataStreamer = get_global_streamer()
detector: EdgeSenseDetector = get_global_detector()

if "score_history" not in st.session_state:
    st.session_state.score_history = deque(maxlen=60)

if "calibrating" not in st.session_state:
    st.session_state.calibrating = False


# ======================== SIDEBAR ========================
st.sidebar.markdown("## ⚙️ System Configuration")
st.sidebar.caption("ESP32-S3 Multimodal EdgeSense v3")
st.sidebar.divider()

# Input source selection
input_mode = st.sidebar.radio(
    "Data Source",
    ["Test Rig Simulator", "ESP32-S3 USB Serial"],
    index=0 if streamer.mode == "simulation" else 1
)

if input_mode == "ESP32-S3 USB Serial":
    available_ports = list_available_ports()
    col_p1, col_p2 = st.sidebar.columns([3, 1])
    with col_p1:
        selected_port = st.selectbox(
            "Serial Port",
            available_ports if available_ports else ["No ports found"],
            index=0
        )
    with col_p2:
        if st.button("🔄"):
            st.rerun()

    baud_rate = st.sidebar.selectbox("Baud Rate", [115200, 921600], index=0)

    if available_ports and selected_port != "No ports found":
        streamer.configure("serial", selected_port, baud_rate)
        
        # Diagnostics & Reconnect
        col_r1, col_r2 = st.sidebar.columns([1, 1])
        with col_r1:
            if st.button("🔌 Reconnect", use_container_width=True):
                streamer.reconnect()
                st.rerun()
        with col_r2:
            st.caption(f"{streamer.packets_received} pkts")

        if streamer.last_serial_error:
            st.sidebar.error(f"⚠️ {streamer.last_serial_error}")
        elif streamer.packets_received > 0:
            st.sidebar.success(f"🟢 Streaming from {selected_port}")
        else:
            st.sidebar.info(f"⏳ Connecting to {selected_port}...")
    else:
        st.sidebar.warning("Connect ESP32-S3 via USB-C to stream live hardware data.")
        streamer.configure("simulation")
else:
    streamer.configure("simulation")
    
    st.sidebar.markdown("**Simulation Machine State:**")
    sim_fan_state = st.sidebar.selectbox(
        "Attached Fan Rotor",
        ["Normal Fan", "Broken Fan", "Acoustic Disturbance Only", "Motor Off"],
        index=0 if streamer.sim_condition == "Normal Fan" else 1
    )
    streamer.set_simulation_condition(sim_fan_state)
    st.sidebar.caption("Switch between Normal Fan (balanced) and Broken Fan to test threshold flip.")

st.sidebar.divider()
st.sidebar.markdown("**Detection Thresholds**")
norm_thresh = st.sidebar.slider("Normal Health Cutoff (%)", 50, 85, 65)
warn_thresh = st.sidebar.slider("Abnormal Fault Cutoff (%)", 20, 50, 40)
detector.normal_threshold = float(norm_thresh)
detector.warning_threshold = float(warn_thresh)

st.sidebar.divider()
if st.sidebar.button("🧹 Reset Baseline Calibration", use_container_width=True):
    st.session_state.detector = EdgeSenseDetector(norm_thresh, warn_thresh)
    st.session_state.score_history.clear()
    st.rerun()


# ======================== HEADER ========================
latest = streamer.get_latest_window()
source_name = latest["source"] if latest else "Connecting..."

st.markdown(f"""
<div class="header-box">
    <div>
        <div style="display:flex; align-items:center; gap:8px;">
            <span class="pulse-dot"></span>
            <span style="font-size: 22px; font-weight: 700; letter-spacing: -0.3px;">EdgeSense v3</span>
            <span style="background: rgba(56,189,248,0.15); color: #38BDF8; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">ACTIVE STREAM</span>
        </div>
        <div style="font-size: 13px; color: #8B949E; margin-top: 4px;">
            Multimodal Anomaly Detection Rig · ADXL345 (SPI) & INMP441 (I2S) · Source: <b>{source_name}</b>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)


# ======================== 10s CALIBRATION BANNER ========================
calib_col1, calib_col2 = st.columns([3, 1])

with calib_col1:
    if not detector.is_calibrated:
        st.info("⚠️ **System Uncalibrated:** Click the button below while your DC motor is running with the **Normal Fan** to learn its 10-second healthy baseline.")
    else:
        st.success("✅ **Baseline Calibrated:** Machine baseline locked in. Real-time inputs are currently being evaluated against this baseline.")

with calib_col2:
    start_calib = st.button("🎯 Calibrate Normal Baseline (10s)", type="primary", use_container_width=True)

if start_calib:
    st.session_state.calibrating = True
    streamer.start_calibration(duration=10.0)
    
    # Progress countdown loop
    progress_bar = st.progress(0, text="Recording 10s normal operating baseline...")
    start_t = time.time()
    while time.time() - start_t < 10.0:
        elapsed = time.time() - start_t
        pct = min(1.0, elapsed / 10.0)
        samples_count = len(streamer.calibration_buffer)
        progress_bar.progress(pct, text=f"Calibrating baseline... {10.0 - elapsed:.1f}s remaining ({samples_count} windows gathered)")
        time.sleep(0.15)
        
    is_done, progress, collected_windows = streamer.get_calibration_progress()
    progress_bar.progress(1.0, text="Calibration complete! Fitting Isolation Forest...")
    time.sleep(0.3)
    
    # Extract features from all gathered windows
    if len(collected_windows) >= 3:
        feature_vectors = []
        for win in collected_windows:
            feats = extract_multimodal_features(
                win["vibration"], win["audio"],
                fs_vib=win["fs_vib"], fs_aud=win["fs_aud"]
            )
            feature_vectors.append(feats["vector"])
        
        detector.calibrate(feature_vectors)
        st.session_state.calibrating = False
        progress_bar.empty()
        st.toast("Normal baseline calibrated successfully!", icon="✅")
        st.rerun()
    else:
        st.error("Insufficient samples collected during calibration. Please check sensor connection and try again.")
        st.session_state.calibrating = False


# ======================== REAL-TIME MONITORING FRAGMENT ========================
@st.fragment(run_every="500ms")
def render_live_dashboard():
    window = streamer.get_latest_window()
    if window is None:
        st.warning("Waiting for incoming sensor data packets...")
        return

    if window.get("adxl_connected") is False:
        st.error("⚠️ **ADXL345 SPI Error:** The sensor did not return Device ID `0xE5`. Check SPI wiring: CS (10), SCL (12), SDA/MOSI (11), SDO/MISO (13).")
    if window.get("mic_connected") is False:
        st.error("⚠️ **INMP441 I2S Error:** Check microphone wiring: SCK (14), WS (15), SD (16).")

    # Extract multimodal features
    feats = extract_multimodal_features(
        window["vibration"], window["audio"],
        fs_vib=window["fs_vib"], fs_aud=window["fs_aud"]
    )
    
    # Evaluate score
    score_res = detector.score(feats["vector"])
    normality = score_res.get("normality_score", 100.0)
    anomaly = score_res.get("anomaly_score", 0.0)
    status = score_res.get("status", "UNCALIBRATED")
    status_color = score_res.get("status_color", "#838C97")
    fusion = score_res.get("fusion", "Uncalibrated")
    fusion_color = score_res.get("fusion_color", "#838C97")

    # Append to history
    st.session_state.score_history.append({
        "time": time.time(),
        "normality": normality,
        "anomaly": anomaly,
        "status": status
    })

    # ---------- STAT CARDS ----------
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(f"""
        <div class="stat-card" style="border-left-color: {status_color};">
            <div class="stat-label">Machine Status</div>
            <div class="stat-value" style="color: {status_color};">{status}</div>
            <div class="stat-sub">{window['source']}</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="stat-card" style="border-left-color: {status_color};">
            <div class="stat-label">Normality Score</div>
            <div class="stat-value" style="color: {status_color};">{normality:.1f}%</div>
            <div class="stat-sub">Normal: &ge; {detector.normal_threshold:.0f}% · Fault: &lt; {detector.warning_threshold:.0f}%</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="stat-card" style="border-left-color: var(--accent-cyan);">
            <div class="stat-label">Anomaly Score</div>
            <div class="stat-value">{anomaly:.2f}</div>
            <div class="stat-sub">Isolation Forest Outlier Metric</div>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
        <div class="stat-card" style="border-left-color: {fusion_color};">
            <div class="stat-label">Multimodal Fusion</div>
            <div class="stat-value" style="font-size: 19px; color: {fusion_color};">{fusion}</div>
            <div class="stat-sub">Vib & Aud Evidence</div>
        </div>
        """, unsafe_allow_html=True)

    # ---------- ROLLING TREND HISTORY ----------
    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    
    if len(st.session_state.score_history) > 1:
        hist_df = pd.DataFrame(list(st.session_state.score_history))
        t_rel = hist_df["time"] - hist_df["time"].iloc[-1]
        
        fig_trend = go.Figure()
        
        # Normality trace
        fig_trend.add_trace(go.Scatter(
            x=t_rel, y=hist_df["normality"],
            mode="lines+markers",
            name="Normality Index (%)",
            line=dict(color="#38BDF8", width=2.5),
            marker=dict(size=4)
        ))
        
        # Threshold guide lines
        fig_trend.add_hline(
            y=detector.normal_threshold,
            line_dash="dash", line_color="#2EA043",
            annotation_text=f"Normal Threshold ({detector.normal_threshold:.0f}%)",
            annotation_position="top left",
            annotation_font_color="#2EA043"
        )
        fig_trend.add_hline(
            y=detector.warning_threshold,
            line_dash="dash", line_color="#F85149",
            annotation_text=f"Fault Threshold ({detector.warning_threshold:.0f}%)",
            annotation_position="bottom left",
            annotation_font_color="#F85149"
        )
        
        fig_trend.update_layout(
            title=dict(text="<b>Normality Score History (Last 60s)</b>", font=dict(size=14, color="#E6EDF3")),
            xaxis_title="Time Offset (seconds)",
            yaxis_title="Normality Index (%)",
            yaxis=dict(range=[0, 105], fixedrange=True),
            xaxis=dict(fixedrange=True),
            height=230,
            margin=dict(l=35, r=15, t=35, b=25),
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(18, 23, 33, 0.6)",
            font=dict(color="#8B949E"),
            uirevision="constant",
            transition_duration=0,
        )
        st.plotly_chart(fig_trend, use_container_width=True, key="fig_trend", config={"displayModeBar": False, "responsive": True})

    # ---------- LIVE STREAMING SENSOR WAVEFORMS (UNIFIED SUBPLOT) ----------
    st.markdown("### 📡 Live Sensor Waveforms")
    
    v_data = window["vibration"]
    t_v = np.arange(len(v_data)) / window["fs_vib"]
    a_data = window["audio"]
    t_a = np.arange(len(a_data)) / window["fs_aud"]

    fig_wave = make_subplots(
        rows=1, cols=2,
        subplot_titles=("<b>Vibration Waveform (ADXL345 SPI)</b>", "<b>Acoustic Waveform (INMP441 I2S)</b>"),
        horizontal_spacing=0.07
    )
    fig_wave.add_trace(go.Scatter(
        x=t_v, y=v_data, mode="lines",
        line=dict(color="#38BDF8", width=1.5), name="ADXL345"
    ), row=1, col=1)
    fig_wave.add_trace(go.Scatter(
        x=t_a, y=a_data, mode="lines",
        line=dict(color="#A855F7", width=1.2), name="INMP441"
    ), row=1, col=2)

    fig_wave.update_yaxes(title_text="Accel (g)", row=1, col=1)
    fig_wave.update_xaxes(title_text="Time (s)", row=1, col=1)
    fig_wave.update_yaxes(title_text="Normalized Amp", row=1, col=2)
    fig_wave.update_xaxes(title_text="Time (s)", row=1, col=2)

    fig_wave.update_layout(
        height=240,
        margin=dict(l=35, r=15, t=35, b=25),
        showlegend=False,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(18, 23, 33, 0.6)",
        font=dict(color="#8B949E"),
        uirevision="constant",
        transition_duration=0,
    )
    st.plotly_chart(fig_wave, use_container_width=True, key="fig_waveforms", config={"displayModeBar": False, "responsive": True})

    # ---------- LIVE FREQUENCY SPECTRA (UNIFIED SUBPLOT) ----------
    st.markdown("### 📊 Frequency-Domain Spectra (FFT)")
    
    freqs_v = feats["freqs_v"]
    mags_v = feats["mags_v"]
    mask_v = (freqs_v <= 400.0)

    freqs_a = feats["freqs_a"]
    mags_a = feats["mags_a"]
    mask_a = (freqs_a <= 2000.0)

    fig_spec = make_subplots(
        rows=1, cols=2,
        subplot_titles=(
            f"<b>Vibration FFT Spectrum (Peak: {feats['vib_dom_freq']:.1f} Hz)</b>",
            f"<b>Acoustic FFT Spectrum (Peak: {feats['aud_dom_freq']:.1f} Hz)</b>"
        ),
        horizontal_spacing=0.07
    )
    fig_spec.add_trace(go.Scatter(
        x=freqs_v[mask_v], y=mags_v[mask_v], mode="lines",
        fill="tozeroy", line=dict(color="#38BDF8", width=1.5),
        fillcolor="rgba(56, 189, 248, 0.15)", name="Vib FFT"
    ), row=1, col=1)
    fig_spec.add_trace(go.Scatter(
        x=freqs_a[mask_a], y=mags_a[mask_a], mode="lines",
        fill="tozeroy", line=dict(color="#A855F7", width=1.5),
        fillcolor="rgba(168, 85, 247, 0.15)", name="Aud FFT"
    ), row=1, col=2)

    fig_spec.update_yaxes(title_text="Magnitude", rangemode="tozero", row=1, col=1)
    fig_spec.update_xaxes(title_text="Frequency (Hz)", row=1, col=1)
    fig_spec.update_yaxes(title_text="Magnitude", rangemode="tozero", row=1, col=2)
    fig_spec.update_xaxes(title_text="Frequency (Hz)", row=1, col=2)

    fig_spec.update_layout(
        height=230,
        margin=dict(l=35, r=15, t=35, b=25),
        showlegend=False,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(18, 23, 33, 0.6)",
        font=dict(color="#8B949E"),
        uirevision="constant",
        transition_duration=0,
    )
    st.plotly_chart(fig_spec, use_container_width=True, key="fig_spectra", config={"displayModeBar": False, "responsive": True})

    # ---------- EXPLAINABILITY & ROOT CAUSE ----------
    st.markdown("### 🔍 Anomaly Explanation & Diagnostics")
    top_devs = score_res["top_deviations"]
    
    if not detector.is_calibrated:
        st.info("Calibrate the 10-second healthy baseline to enable automatic feature deviation analysis.")
    elif status == "NORMAL":
        st.markdown(f"""
        <div class="explain-box" style="border-left: 4px solid #2EA043;">
            <b style="color: #2EA043;">Normal Operating Condition</b><br>
            <span style="font-size: 13px; color: #8B949E;">All vibration and acoustic features remain within the calibrated statistical envelope (&plusmn;2&sigma;).</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        dev_rows = "".join([
            f"<li><b>{d['feature']}</b>: <code>{d['deviation_ratio']:.1f}&times;</code> normal baseline deviation (Current: {d['current_val']:.3f} | Baseline: {d['base_val']:.3f})</li>"
            for d in top_devs
        ])
        st.markdown(f"""
        <div class="explain-box" style="border-left: 4px solid {status_color};">
            <b style="color: {status_color};">Alert Root Cause & Significant Feature Deviations:</b>
            <ul style="margin-top: 6px; font-size: 13px; color: #E6EDF3;">
                {dev_rows if dev_rows else "<li>Multimodal boundary shift detected by Isolation Forest.</li>"}
            </ul>
            <div style="font-size: 12px; color: #8B949E; margin-top: 6px;">
                <b>Fusion Note:</b> {score_res['fusion_detail']}
            </div>
        </div>
        """, unsafe_allow_html=True)

# Render the streaming dashboard
render_live_dashboard()
