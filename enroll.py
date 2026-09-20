"""
enroll.py
Standalone enrollment script for Phase 3 voice biometrics.

Run with:
    python enroll.py
Speak clearly for at least 5 seconds when prompted, then pause.
Your voice profile is saved to var/data/voice_profiles/{user_id}.npy
"""
import sys
import uuid

import numpy as np

from app.adapters.audio_capture_adapter import iter_microphone_chunks
from app.services.capture_segmenter import segment_audio
from app.services.vad_service import is_speech
from app.services.biometric_service import enroll_user


def main():
    print("=" * 50)
    print("Vasuki Voice Enrollment")
    print("=" * 50)

    user_id = input("Enter a unique ID for this user (e.g. your name or a UUID): ").strip()
    if not user_id:
        user_id = str(uuid.uuid4())[:8]
        print(f"No ID entered — assigned: {user_id}")

    print(f"\nEnrolling user: '{user_id}'")
    print("Speak clearly for at least 5 seconds when you see [RECORDING].")
    print("Say your name, the wake word 'Vasuki', and a few sentences.")
    print("Press Ctrl+C to cancel.\n")

    input("Press Enter when you are ready to start recording...")
    print("\n[RECORDING] — speak now...")

    chunks = iter_microphone_chunks()
    captured = []

    try:
        for segment_chunks in segment_audio(chunks, silence_chunk_timeout=24, min_speech_chunks=10):
            audio = np.concatenate(segment_chunks)
            if is_speech(audio):
                captured.append(audio)
                print(f"  Captured segment ({len(audio)} samples)")
                duration = sum(len(c) for c in captured) / 16000
                print(f"  Total captured: {duration:.1f}s")
                if duration >= 5.0:
                    print("\n[DONE] Sufficient audio captured.")
                    break
    except KeyboardInterrupt:
        print("\nEnrollment cancelled.")
        sys.exit(0)

    if not captured:
        print("No audio captured. Try again in a quieter environment.")
        sys.exit(1)

    full_audio = np.concatenate(captured)
    print(f"\nProcessing {len(full_audio) / 16000:.1f}s of audio...")

    result = enroll_user(user_id, full_audio)

    if result["success"]:
        print(f"\n✓ {result['message']}")
        print(f"  Profile saved to: {result['path']}")
    else:
        print(f"\n✗ Enrollment failed: {result['message']}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nEnrollment cancelled.")
