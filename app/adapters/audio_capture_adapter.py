"""
app/adapters/audio_capture_adapter.py
Thin microphone capture boundary. This is the only file in Phase 1 allowed
to touch audio hardware directly — everything downstream (VAD, STT,
segmentation, filtering) is pure and testable without a microphone.
"""
import queue
from typing import Iterator

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
BLOCKSIZE = 1024  # ~64ms per chunk at 16kHz


def iter_microphone_chunks(sample_rate: int = SAMPLE_RATE, blocksize: int = BLOCKSIZE) -> Iterator[np.ndarray]:
    """Yields int16 numpy audio chunks from the default microphone forever.
    Blocks and runs until the caller stops iterating (e.g. Ctrl+C)."""
    q: "queue.Queue[np.ndarray]" = queue.Queue()

    def _callback(indata, frames, time_info, status):
        q.put(indata.copy())

    with sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        blocksize=blocksize,
        callback=_callback,
    ):
        while True:
            yield q.get().flatten()
