"""
app/services/biometric_service.py
MFCC-based voice biometric enrollment and speaker verification.

Architecture:
- Feature extraction: 40 MFCC coefficients averaged across time → 40-dim vector
- Storage: per-user .npy file at var/data/voice_profiles/{user_id}.npy
- Similarity: cosine similarity between stored and live embeddings
- Threshold: 0.82 (configurable via BIOMETRIC_THRESHOLD env var)

No deep learning model is used here — pure MFCC + cosine similarity.
This keeps the biometric layer fully offline, deterministic, and testable
without any model download or internet access.
"""
import threading
from pathlib import Path
from typing import Optional

import numpy as np

from app.core.config import settings

_lock = threading.Lock()

BIOMETRIC_THRESHOLD = 0.82
MIN_ENROLLMENT_SAMPLES = 48000  # 3 seconds at 16kHz
N_MFCC = 40


# -- Pure feature extraction (no hardware, fully testable) -------------------

def extract_mfcc_embedding(audio_np: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
    """
    Extracts a fixed-size MFCC embedding from raw int16 audio.
    Returns a 40-dimensional float32 vector (mean of MFCC across time).
    Pure function — no file I/O, no DB, no hardware.
    """
    import librosa
    audio_f32 = audio_np.astype(np.float32) / 32768.0
    # Extract N_MFCC + 1 coefficients and drop the 0-th coefficient (energy)
    mfccs = librosa.feature.mfcc(y=audio_f32, sr=sample_rate, n_mfcc=N_MFCC + 1)
    return np.mean(mfccs[1:], axis=1).astype(np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Computes cosine similarity between two vectors.
    Returns float in [-1.0, 1.0]. Higher = more similar.
    Pure function — no I/O, fully testable.
    """
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# -- Profile I/O (filesystem + DB) ------------------------------------------

def _profile_path(user_id: str) -> Path:
    return settings.VOICE_PROFILE_DIR / f"{user_id}.npy"


def profile_exists(user_id: str) -> bool:
    return _profile_path(user_id).exists()


def save_profile(user_id: str, embedding: np.ndarray) -> Path:
    """Saves embedding to disk. Thread-safe."""
    path = _profile_path(user_id)
    with _lock:
        np.save(str(path), embedding)
    return path


def load_profile(user_id: str) -> Optional[np.ndarray]:
    """Loads embedding from disk. Returns None if not found."""
    path = _profile_path(user_id)
    if not path.exists():
        return None
    with _lock:
        return np.load(str(path))


def list_enrolled_users() -> list[str]:
    """Returns list of all enrolled user_ids (based on .npy files)."""
    return [p.stem for p in settings.VOICE_PROFILE_DIR.glob("*.npy")]


# -- Enrollment & Verification (high-level API) ------------------------------

def enroll_user(user_id: str, audio_np: np.ndarray, sample_rate: int = 16000) -> dict:
    """
    Enrolls a user by computing and saving their voice embedding.

    Returns dict with keys: success (bool), message (str), path (str or None)
    """
    if len(audio_np) < MIN_ENROLLMENT_SAMPLES:
        return {
            "success": False,
            "message": f"Audio too short ({len(audio_np)} samples). "
                       f"Need at least {MIN_ENROLLMENT_SAMPLES} samples (3 seconds). "
                       f"Please speak for longer during enrollment.",
            "path": None,
        }

    embedding = extract_mfcc_embedding(audio_np, sample_rate)
    path = save_profile(user_id, embedding)

    return {
        "success": True,
        "message": f"Enrolled user '{user_id}' successfully.",
        "path": str(path),
    }


def verify_speaker(
    audio_np: np.ndarray,
    sample_rate: int = 16000,
    threshold: float = BIOMETRIC_THRESHOLD,
) -> dict:
    """
    Verifies the speaker in audio_np against ALL enrolled profiles.
    Picks the best match. Returns the result regardless of threshold —
    the caller decides whether to accept or reject.

    Returns dict with keys:
        verified (bool), user_id (str or None),
        similarity (float), threshold (float)
    """
    enrolled = list_enrolled_users()

    if not enrolled:
        return {
            "verified": False,
            "user_id": None,
            "similarity": 0.0,
            "threshold": threshold,
            "message": "No enrolled profiles found. Run enroll.py first.",
        }

    live_embedding = extract_mfcc_embedding(audio_np, sample_rate)

    best_user = None
    best_score = -1.0

    for user_id in enrolled:
        stored = load_profile(user_id)
        if stored is None:
            continue
        score = cosine_similarity(live_embedding, stored)
        if score > best_score:
            best_score = score
            best_user = user_id

    verified = best_score >= threshold

    return {
        "verified": verified,
        "user_id": best_user if verified else None,
        "similarity": round(best_score, 4),
        "threshold": threshold,
        "message": (
            f"Verified as '{best_user}' (similarity={best_score:.4f})"
            if verified
            else f"Speaker not recognised (best={best_score:.4f}, need>={threshold})"
        ),
    }
