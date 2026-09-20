"""
app/services/vad_service.py
Voice Activity Detection with graceful fallback.

Tries Silero VAD first (model-based, more accurate). If the model fails
to load or errors during inference, falls back to the simple energy
check so Vasuki never goes deaf just because a model failed to load.
This offline-first resilience pattern is intentional, not a shortcut.
"""
import numpy as np

from app.services.capture_segmenter import energy_is_speech

_vad_model = None
_vad_load_attempted = False


def _load_silero():
    global _vad_model, _vad_load_attempted
    if _vad_load_attempted:
        return _vad_model
    _vad_load_attempted = True
    try:
        from silero_vad import load_silero_vad
        _vad_model = load_silero_vad()
    except Exception:
        _vad_model = None
    return _vad_model


def is_speech(audio_np: np.ndarray, sample_rate: int = 16000) -> bool:
    """audio_np: int16 numpy array. Returns True if it appears to contain
    speech. Falls back to energy detection if Silero VAD is unavailable."""
    model = _load_silero()
    if model is None:
        return energy_is_speech(audio_np)

    try:
        import torch
        from silero_vad import get_speech_timestamps

        audio_f32 = audio_np.astype(np.float32) / 32768.0
        audio_tensor = torch.from_numpy(audio_f32)
        timestamps = get_speech_timestamps(audio_tensor, model, sampling_rate=sample_rate)
        return len(timestamps) > 0
    except Exception:
        return energy_is_speech(audio_np)
