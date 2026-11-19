"""
Feature Extraction Engine for EdgeSense Multimodal Anomaly Detection.
Processes 1D vibration (accelerometer) and acoustic (microphone) sensor windows.
"""

import numpy as np
from scipy.stats import kurtosis


def compute_time_features(signal: np.ndarray) -> dict:
    """
    Extract time-domain statistical features from a 1D sensor window.
    """
    x = np.asarray(signal, dtype=np.float64)
    if len(x) == 0:
        return {"rms": 0.0, "var": 0.0, "peak": 0.0, "kurt": 3.0, "crest": 1.0}

    # Remove DC bias for dynamic vibration analysis
    x_ac = x - np.mean(x)

    rms = float(np.sqrt(np.mean(x_ac**2)))
    var = float(np.var(x_ac))
    peak = float(np.max(np.abs(x_ac)))
    
    # Pearson kurtosis (normal distribution = 3.0)
    if var > 1e-12:
        kurt = float(kurtosis(x_ac, fisher=False))
    else:
        kurt = 3.0

    crest = float(peak / (rms + 1e-9))

    return {
        "rms": rms,
        "var": var,
        "peak": peak,
        "kurt": kurt,
        "crest": crest
    }


def compute_frequency_features(signal: np.ndarray, fs: float = 1000.0) -> tuple[dict, np.ndarray, np.ndarray]:
    """
    Extract frequency-domain FFT features from a 1D sensor window.
    Returns:
        features (dict): dominant_freq, spectral_energy, spectral_centroid
        freqs (np.ndarray): frequency bins (Hz)
        mags (np.ndarray): magnitude spectrum
    """
    x = np.asarray(signal, dtype=np.float64)
    n = len(x)
    if n < 4:
        return {"dominant_freq": 0.0, "spectral_energy": 0.0, "spectral_centroid": 0.0}, np.array([0.0]), np.array([0.0])

    # Hanning window to suppress spectral leakage
    window = np.hanning(n)
    x_win = (x - np.mean(x)) * window

    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    fft_vals = np.fft.rfft(x_win)
    mags = np.abs(fft_vals) / (n / 2.0)
    
    # Zero out DC component
    mags[0] = 0.0

    # Dominant frequency
    dom_idx = int(np.argmax(mags))
    dom_freq = float(freqs[dom_idx])

    # Spectral Energy (sum of squared magnitudes normalized)
    spectral_energy = float(np.sum(mags**2))

    # Spectral Centroid (weighted center of spectral mass)
    mag_sum = np.sum(mags)
    if mag_sum > 1e-9:
        centroid = float(np.sum(freqs * mags) / mag_sum)
    else:
        centroid = 0.0

    features = {
        "dominant_freq": dom_freq,
        "spectral_energy": spectral_energy,
        "spectral_centroid": centroid
    }
    return features, freqs, mags


def extract_multimodal_features(vib_signal: np.ndarray, aud_signal: np.ndarray,
                                fs_vib: float = 800.0, fs_aud: float = 8000.0) -> dict:
    """
    Extract combined multimodal feature dictionary and feature vector.
    Feature vector structure (10 dimensions):
    [Vib_RMS, Vib_Var, Vib_Kurt, Vib_DomFreq, Vib_Energy,
     Aud_RMS, Aud_Var, Aud_Kurt, Aud_DomFreq, Aud_Energy]
    """
    fv_time = compute_time_features(vib_signal)
    fv_freq, freqs_v, mags_v = compute_frequency_features(vib_signal, fs=fs_vib)

    fa_time = compute_time_features(aud_signal)
    fa_freq, freqs_a, mags_a = compute_frequency_features(aud_signal, fs=fs_aud)

    feature_dict = {
        # Vibration features
        "vib_rms": fv_time["rms"],
        "vib_var": fv_time["var"],
        "vib_peak": fv_time["peak"],
        "vib_kurt": fv_time["kurt"],
        "vib_dom_freq": fv_freq["dominant_freq"],
        "vib_energy": fv_freq["spectral_energy"],
        # Acoustic features
        "aud_rms": fa_time["rms"],
        "aud_var": fa_time["var"],
        "aud_peak": fa_time["peak"],
        "aud_kurt": fa_time["kurt"],
        "aud_dom_freq": fa_freq["dominant_freq"],
        "aud_energy": fa_freq["spectral_energy"],
        # Spectra for plotting
        "freqs_v": freqs_v,
        "mags_v": mags_v,
        "freqs_a": freqs_a,
        "mags_a": mags_a,
    }

    feature_vector = np.array([
        feature_dict["vib_rms"],
        feature_dict["vib_var"],
        feature_dict["vib_kurt"],
        feature_dict["vib_dom_freq"],
        feature_dict["vib_energy"],
        feature_dict["aud_rms"],
        feature_dict["aud_var"],
        feature_dict["aud_kurt"],
        feature_dict["aud_dom_freq"],
        feature_dict["aud_energy"],
    ], dtype=np.float64)

    feature_dict["vector"] = feature_vector
    return feature_dict


FEATURE_NAMES = [
    "Vibration RMS",
    "Vibration Variance",
    "Vibration Kurtosis",
    "Vibration Dominant Freq",
    "Vibration Spectral Energy",
    "Acoustic RMS",
    "Acoustic Variance",
    "Acoustic Kurtosis",
    "Acoustic Dominant Freq",
    "Acoustic Spectral Energy"
]
