"""
EdgeSense Anomaly Detector & 10-Second Baseline Calibration Engine.
Trains an unsupervised Isolation Forest on healthy operating windows and
computes continuous Normality Score (0-100%), Anomaly Score (0.0-1.0),
sensor fusion state, and explainable feature deviations.
"""

import numpy as np
from sklearn.ensemble import IsolationForest
from feature_engine import FEATURE_NAMES


class EdgeSenseDetector:
    def __init__(self, normal_threshold: float = 65.0, warning_threshold: float = 40.0):
        self.normal_threshold = normal_threshold      # Above this = NORMAL
        self.warning_threshold = warning_threshold    # Above this = WARNING, below = ABNORMAL
        
        self.is_calibrated = False
        self.model: IsolationForest | None = None
        self.base_mean = np.zeros(10)
        self.base_std = np.ones(10)
        self.calibration_samples = []

    def calibrate(self, feature_vectors: list[np.ndarray]):
        """
        Calibrate model using windows collected during the 10-second calibration phase.
        Args:
            feature_vectors: List of 10-D numpy arrays collected from the healthy motor.
        """
        if len(feature_vectors) < 5:
            raise ValueError(f"Need at least 5 windows to calibrate (received {len(feature_vectors)})")

        X_raw = np.array(feature_vectors)
        self.base_mean = np.mean(X_raw, axis=0)
        self.base_std = np.std(X_raw, axis=0)
        # Prevent division by zero with minimum epsilon floor
        self.base_std = np.where(self.base_std < 1e-4, np.maximum(np.abs(self.base_mean) * 0.05, 1e-4), self.base_std)

        # Augment training set with slight jitter to build robust boundaries
        rng = np.random.default_rng(42)
        n_augment = max(150, len(X_raw) * 4)
        jitter = rng.normal(0, 0.08, size=(n_augment, 10)) * self.base_std
        bootstrap_idx = rng.choice(len(X_raw), size=n_augment, replace=True)
        X_train = np.vstack([X_raw, X_raw[bootstrap_idx] + jitter])

        # Train Isolation Forest on purely healthy data
        self.model = IsolationForest(
            n_estimators=120,
            contamination=0.04,
            random_state=42
        )
        self.model.fit(X_train)
        self.is_calibrated = True

    def score(self, feature_vector: np.ndarray) -> dict:
        """
        Evaluate a single 10-D window against the calibrated baseline.
        Returns detailed scoring, fusion status, and feature explanations.
        """
        if not self.is_calibrated or self.model is None:
            return {
                "calibrated": False,
                "normality_score": 100.0,
                "anomaly_score": 0.0,
                "status": "UNCALIBRATED",
                "status_color": "#838C97",
                "fusion": "Uncalibrated",
                "fusion_color": "#838C97",
                "fusion_detail": "Click 'Calibrate' to record 10s baseline.",
                "vib_dev": 0.0,
                "aud_dev": 0.0,
                "top_deviations": []
            }

        x = np.asarray(feature_vector, dtype=np.float64)

        # 1. Isolation Forest Decision Function
        # Decision function: positive for inliers, negative for outliers
        if_score = float(self.model.decision_function(x.reshape(1, -1))[0])

        # 2. Normalized Z-score Deviations
        z_scores = np.abs(x - self.base_mean) / (self.base_std + 1e-9)
        
        # Sub-modality deviations
        vib_dev = float(np.mean(z_scores[:5]))
        aud_dev = float(np.mean(z_scores[5:]))
        max_dev = float(np.max(z_scores))
        avg_dev = float(np.mean(z_scores))

        # 3. Normality Score (0% to 100%)
        # Normal machine produces high normality (>70-95%)
        # Broken fan causes high Z-scores and negative IF score -> drops below 40%
        penalty = 0.35 * avg_dev + 0.25 * max_dev - 1.2 * min(0.0, if_score)
        normality_score = float(np.clip(100.0 * np.exp(-0.28 * penalty), 0.0, 100.0))
        anomaly_score = float(np.clip(1.0 - (normality_score / 100.0), 0.0, 1.0))

        # 4. Status Thresholds
        if normality_score >= self.normal_threshold:
            status = "NORMAL"
            status_color = "#34D399"  # Emerald Green
        elif normality_score >= self.warning_threshold:
            status = "SUSPICIOUS"
            status_color = "#F2A93B"  # Amber
        else:
            status = "ABNORMAL"
            status_color = "#F0554A"  # Crimson Red

        # 5. Multimodal Fusion
        vib_is_anom = vib_dev > 2.2
        aud_is_anom = aud_dev > 2.2

        if vib_is_anom and aud_is_anom:
            fusion = "Corroborated Anomaly"
            fusion_detail = "Both vibration and acoustic evidence corroborate abnormal operation."
            fusion_color = "#F0554A"
        elif vib_is_anom and not aud_is_anom:
            fusion = "Sensor Disagreement"
            fusion_detail = "Abnormal vibration detected, but acoustic noise is within normal limits."
            fusion_color = "#F2A93B"
        elif aud_is_anom and not vib_is_anom:
            fusion = "Sensor Disagreement"
            fusion_detail = "Abnormal acoustic noise detected, but vibration is within normal limits."
            fusion_color = "#F2A93B"
        else:
            fusion = "Healthy & Stable"
            fusion_detail = "Both modalities match the learned healthy operating baseline."
            fusion_color = "#34D399"

        # 6. Top Deviations Explanation
        top_indices = np.argsort(z_scores)[::-1][:4]
        top_deviations = [
            {
                "feature": FEATURE_NAMES[i],
                "deviation_ratio": float(z_scores[i]),
                "current_val": float(x[i]),
                "base_val": float(self.base_mean[i])
            }
            for i in top_indices if z_scores[i] >= 1.2
        ]

        return {
            "calibrated": True,
            "normality_score": normality_score,
            "anomaly_score": anomaly_score,
            "status": status,
            "status_color": status_color,
            "fusion": fusion,
            "fusion_color": fusion_color,
            "fusion_detail": fusion_detail,
            "vib_dev": vib_dev,
            "aud_dev": aud_dev,
            "top_deviations": top_deviations
        }
