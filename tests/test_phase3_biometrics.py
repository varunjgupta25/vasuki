"""
tests/test_phase3_biometrics.py

INDEPENDENT verification for Phase 3. Copy verbatim — do not edit
assertions to make them pass.

HOW TO RUN (no server, no mic needed):
    pytest tests/test_phase3_biometrics.py -v
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from app.services.biometric_service import (
    cosine_similarity,
    enroll_user,
    extract_mfcc_embedding,
    list_enrolled_users,
    load_profile,
    profile_exists,
    save_profile,
    verify_speaker,
    MIN_ENROLLMENT_SAMPLES,
    N_MFCC,
)


def _make_audio(n_samples: int = 80000, seed: int = 42) -> np.ndarray:
    """Synthetic audio — deterministic, no mic needed."""
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(n_samples) * 8000).astype(np.int16)


def _make_silence(n_samples: int = 80000) -> np.ndarray:
    return np.zeros(n_samples, dtype=np.int16)


# -- Pure functions (no I/O) -------------------------------------------------

def test_extract_mfcc_embedding_shape():
    audio = _make_audio()
    embedding = extract_mfcc_embedding(audio)
    assert embedding.shape == (N_MFCC,)
    assert embedding.dtype == np.float32


def test_extract_mfcc_embedding_deterministic():
    audio = _make_audio(seed=1)
    emb1 = extract_mfcc_embedding(audio)
    emb2 = extract_mfcc_embedding(audio)
    np.testing.assert_array_equal(emb1, emb2)


def test_cosine_similarity_identical_vectors():
    v = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    assert cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-6)


def test_cosine_similarity_orthogonal_vectors():
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0], dtype=np.float32)
    assert cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-6)


def test_cosine_similarity_zero_vector():
    a = np.zeros(10, dtype=np.float32)
    b = np.ones(10, dtype=np.float32)
    assert cosine_similarity(a, b) == 0.0


def test_same_audio_has_high_similarity():
    audio = _make_audio(seed=7)
    emb1 = extract_mfcc_embedding(audio)
    emb2 = extract_mfcc_embedding(audio)
    score = cosine_similarity(emb1, emb2)
    assert score > 0.99


def test_different_audio_has_lower_similarity():
    emb1 = extract_mfcc_embedding(_make_audio(seed=1))
    emb2 = extract_mfcc_embedding(_make_audio(seed=999))
    score = cosine_similarity(emb1, emb2)
    assert score < 0.99


# -- Profile I/O (uses temp dir) ---------------------------------------------

def test_save_and_load_profile(tmp_path):
    with patch("app.services.biometric_service.settings") as mock_settings:
        mock_settings.VOICE_PROFILE_DIR = tmp_path
        embedding = np.ones(N_MFCC, dtype=np.float32)
        save_profile("test_user", embedding)
        loaded = load_profile("test_user")
        assert loaded is not None
        np.testing.assert_array_equal(embedding, loaded)


def test_profile_exists_false_when_missing(tmp_path):
    with patch("app.services.biometric_service.settings") as mock_settings:
        mock_settings.VOICE_PROFILE_DIR = tmp_path
        assert profile_exists("nonexistent_user") is False


def test_list_enrolled_users_empty(tmp_path):
    with patch("app.services.biometric_service.settings") as mock_settings:
        mock_settings.VOICE_PROFILE_DIR = tmp_path
        assert list_enrolled_users() == []


# -- Enrollment (uses temp dir) ----------------------------------------------

def test_enroll_user_success(tmp_path):
    with patch("app.services.biometric_service.settings") as mock_settings:
        mock_settings.VOICE_PROFILE_DIR = tmp_path
        audio = _make_audio(n_samples=MIN_ENROLLMENT_SAMPLES + 1000)
        result = enroll_user("user_001", audio)
        assert result["success"] is True
        assert "user_001" in result["message"]
        assert Path(result["path"]).exists()


def test_enroll_user_rejects_short_audio(tmp_path):
    with patch("app.services.biometric_service.settings") as mock_settings:
        mock_settings.VOICE_PROFILE_DIR = tmp_path
        audio = _make_audio(n_samples=MIN_ENROLLMENT_SAMPLES - 1000)
        result = enroll_user("user_002", audio)
        assert result["success"] is False
        assert "too short" in result["message"].lower()


# -- Verification (uses temp dir) --------------------------------------------

def test_verify_returns_no_profiles_message(tmp_path):
    with patch("app.services.biometric_service.settings") as mock_settings:
        mock_settings.VOICE_PROFILE_DIR = tmp_path
        result = verify_speaker(_make_audio())
        assert result["verified"] is False
        assert result["user_id"] is None


def test_verify_same_speaker_passes(tmp_path):
    with patch("app.services.biometric_service.settings") as mock_settings:
        mock_settings.VOICE_PROFILE_DIR = tmp_path
        audio = _make_audio(seed=42, n_samples=MIN_ENROLLMENT_SAMPLES + 1000)
        enroll_user("user_a", audio)
        result = verify_speaker(audio, threshold=0.5)
        assert result["verified"] is True
        assert result["user_id"] == "user_a"
        assert result["similarity"] > 0.5
