"""
app/services/stt_service.py
Local speech-to-text using Faster-Whisper.

The "base" model (~140MB) auto-downloads from its normal source on first
run and is cached locally afterward — every run after the first is fully
offline. This is the one explicitly allowed network exception (see
Critical Constraints in the Phase 1 prompt).
"""
import numpy as np

_model = None


def _load_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel("base", device="cpu", compute_type="int8")
    return _model


def transcribe(audio_np: np.ndarray, sample_rate: int = 16000) -> str:
    """audio_np: int16 numpy array. Returns transcribed text, stripped."""
    model = _load_model()
    audio_f32 = audio_np.astype(np.float32) / 32768.0
    segments, _ = model.transcribe(audio_f32, language="en")
    text = "".join(segment.text for segment in segments)
    return text.strip()
