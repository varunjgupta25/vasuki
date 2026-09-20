"""
tests/test_phase1_audio_pipeline.py

Success-criteria oracle for Phase 1. Copy verbatim — do not edit
assertions to make them pass.

SCOPE NOTE: there is no real microphone in this test environment, so
these tests validate every PURE, testable piece of the pipeline
(segmentation, hallucination filtering, VAD fallback behavior, STT
transcription on synthetic audio) without needing physical hardware.
The actual mic-to-console flow in console_listener.py must additionally
be verified by hand — pytest cannot simulate a real microphone.
"""
import numpy as np

from app.services.capture_segmenter import energy_is_speech, segment_audio
from app.services.hallucination_filter import is_real_speech
from app.services.vad_service import is_speech
from app.services.stt_service import transcribe


def _silence(n_samples=1024):
    return np.zeros(n_samples, dtype=np.int16)


def _loud(n_samples=1024, amplitude=5000):
    rng = np.random.default_rng(42)
    return (rng.standard_normal(n_samples) * amplitude).astype(np.int16)


# -- Segmentation (pure, deterministic) --------------------------------------

def test_energy_is_speech_silence_vs_loud():
    assert energy_is_speech(_silence()) is False
    assert energy_is_speech(_loud()) is True


def test_segment_audio_extracts_one_segment_from_synthetic_stream():
    stream = (
        [_silence() for _ in range(5)]
        + [_loud() for _ in range(15)]
        + [_silence() for _ in range(15)]
    )
    segments = list(segment_audio(stream, silence_chunk_timeout=12, min_speech_chunks=10))
    assert len(segments) == 1
    assert len(segments[0]) >= 10


def test_segment_audio_drops_short_blips():
    stream = (
        [_silence() for _ in range(5)]
        + [_loud() for _ in range(3)]  # below min_speech_chunks
        + [_silence() for _ in range(15)]
    )
    segments = list(segment_audio(stream, silence_chunk_timeout=12, min_speech_chunks=10))
    assert len(segments) == 0


def test_segment_audio_yields_nothing_on_pure_silence():
    stream = [_silence() for _ in range(30)]
    segments = list(segment_audio(stream, silence_chunk_timeout=12, min_speech_chunks=10))
    assert len(segments) == 0


# -- Hallucination filter (pure, deterministic) ------------------------------

def test_is_real_speech_rejects_known_hallucinations():
    assert is_real_speech("Thank you.") is False
    assert is_real_speech("") is False
    assert is_real_speech("you") is False


def test_is_real_speech_accepts_real_command_text():
    assert is_real_speech("open notepad please") is True


# -- VAD (model-or-fallback — only assert what's actually deterministic) ----

def test_vad_is_speech_returns_bool_and_agrees_on_silence():
    result_silence = is_speech(np.concatenate([_silence()] * 16))
    assert isinstance(result_silence, bool)
    assert result_silence is False  # real VAD and energy fallback must agree: silence isn't speech

    result_noise = is_speech(np.concatenate([_loud()] * 16))
    assert isinstance(result_noise, bool)  # no fixed expectation here — model vs fallback may differ, that's fine


# -- STT (real model, synthetic audio) ---------------------------------------

def test_stt_transcribe_does_not_crash_on_silence():
    text = transcribe(np.concatenate([_silence()] * 16))
    assert isinstance(text, str)
