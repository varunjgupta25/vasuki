"""
app/services/capture_segmenter.py
Pure, testable speech segmentation — decoupled from any audio hardware so
it can be unit tested with synthetic data instead of a real microphone.

Groups consecutive "loud" chunks into a speech segment, using a
chunk-count silence timeout instead of wall-clock time. This makes the
logic deterministic and testable, unlike a time.time()-based version.
"""
from typing import Iterable, Iterator, List

import numpy as np


def chunk_energy(chunk: np.ndarray) -> float:
    return float(np.linalg.norm(chunk))


def energy_is_speech(chunk: np.ndarray, threshold: float = 500.0) -> bool:
    return chunk_energy(chunk) > threshold


def segment_audio(
    chunk_stream: Iterable[np.ndarray],
    energy_threshold: float = 1500.0,
    silence_chunk_timeout: int = 3,
    min_speech_chunks: int = 10,
) -> Iterator[List[np.ndarray]]:
    """
    Consumes an iterable of fixed-size audio chunks and yields completed
    speech segments (lists of chunks).

    silence_chunk_timeout: consecutive quiet chunks needed to end a segment
    min_speech_chunks: segments with fewer loud chunks than this are dropped
                       as noise blips (trailing silence does not count)
    """
    recording: List[np.ndarray] = []
    is_talking = False
    silence_run = 0
    speech_chunk_count = 0  # count only loud chunks, not trailing silence

    for chunk in chunk_stream:
        loud = energy_is_speech(chunk, energy_threshold)

        if loud:
            is_talking = True
            silence_run = 0
            speech_chunk_count += 1
            recording.append(chunk)
        elif is_talking:
            silence_run += 1
            recording.append(chunk)
            if silence_run >= silence_chunk_timeout:
                if speech_chunk_count >= min_speech_chunks:
                    yield recording
                recording = []
                is_talking = False
                silence_run = 0
                speech_chunk_count = 0
        # else: silence before any speech started — ignore entirely

    if is_talking and speech_chunk_count >= min_speech_chunks:
        yield recording

