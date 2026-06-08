"""Local transcription via whisper.cpp.

Runs the `whisper-cli` binary (installed with Homebrew's whisper-cpp) on a WAV
file and returns the plain text. No audio leaves the machine, which is the whole
point of the privacy design.

Our recordings are already mono 16 kHz, which is exactly what whisper wants, so
there is no conversion step here.
"""

import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(HERE, "models", "ggml-small.en.bin")


class TranscribeError(RuntimeError):
    pass


def _whisper_bin():
    """Find the whisper-cli binary (PATH first, then the Homebrew location)."""
    return shutil.which("whisper-cli") or "/opt/homebrew/bin/whisper-cli"


def transcribe(wav_path):
    """Transcribe a WAV file and return the text.

    Flags: -nt drops per-segment timestamps (we want flowing text), -np silences
    whisper's own progress/log output so stdout is just the transcript.
    """
    if not os.path.exists(wav_path):
        raise TranscribeError(f"Audio file not found: {wav_path}")
    if not os.path.exists(MODEL):
        raise TranscribeError(
            f"Whisper model not found: {MODEL}. "
            "Download ggml-small.en.bin into the models/ folder."
        )

    cmd = [_whisper_bin(), "-m", MODEL, "-f", wav_path, "-nt", "-np"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise TranscribeError(f"whisper-cli failed:\n{proc.stderr.strip()}")

    return proc.stdout.strip()
