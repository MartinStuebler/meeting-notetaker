"""System-audio capture via the native sysaudio-rec helper.

Single-session: one recording at a time (single user, single machine). The PRD
captures *system audio only* (the interviewer's voice). We now capture it with a
small native macOS helper (helper/sysaudio-rec, built from sysaudio-rec.swift)
that uses ScreenCaptureKit, the same engine behind Cmd+Shift+5 system-audio
recording. This replaces the old ffmpeg + Background Music virtual-device path.

Advantages over the old approach: it captures system audio only (never the mic),
it does not reroute the output device (so the speakers and volume keys keep
working), and there is nothing to configure.

The helper writes mono 16 kHz 16-bit PCM WAV directly, which is exactly what
whisper.cpp wants in transcribe.py, so no re-encode is needed later.

The helper records until it receives SIGINT, then finalizes the WAV header and
exits 0. We start it on start() and SIGINT it on stop(), the same clean-stop
path the standalone smoke test used.
"""

import os
import signal
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# Absolute path to the native helper binary. Absolute so capture works when the
# app is launched from the Dock, where PATH does not include anything useful.
HELPER = os.path.join(HERE, "helper", "sysaudio-rec")

# Single-session recording state.
_proc = None
_path = None
_started_at = None
_log = None  # open file handle for the helper's stderr


class RecorderError(RuntimeError):
    pass


def is_recording():
    return _proc is not None and _proc.poll() is None


def elapsed_s():
    if _started_at is None:
        return 0
    return time.time() - _started_at


def start(path):
    """Begin recording system audio to ``path`` (mono 16 kHz WAV)."""
    global _proc, _path, _started_at, _log
    if is_recording():
        raise RecorderError("Already recording.")

    if not os.path.exists(HELPER):
        raise RecorderError(
            f"Recorder helper not found at {HELPER}. Build it with:\n"
            f"  swiftc -O -o helper/sysaudio-rec helper/sysaudio-rec.swift"
        )

    os.makedirs(os.path.dirname(path), exist_ok=True)

    # The helper takes the output WAV path as its first argument and records
    # until it gets SIGINT. Its stderr goes to a log file (not an unread PIPE,
    # which could fill and block the process): startup errors, including a
    # denied Screen/System-Audio Recording permission, land there for us to
    # surface.
    log_path = path + ".log"
    _log = open(log_path, "wb")
    _proc = subprocess.Popen(
        [HELPER, path],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=_log,
    )
    _path = path
    _started_at = time.time()

    # Fail fast if the helper died immediately (e.g. permission denied). It
    # prints the reason to stderr (our log file) and exits non-zero.
    time.sleep(0.5)
    if _proc.poll() is not None:
        _log.flush()
        with open(log_path, "r", errors="replace") as f:
            err = f.read().strip()
        _reset()
        raise RecorderError(
            "System-audio recorder failed to start.\n\n" + err + "\n\n"
            "If this is the first run from the Dock, macOS may be asking for "
            "Screen & System Audio Recording permission. Grant it and try again."
        )

    return {"path": path, "started_at": _started_at}


def stop():
    """Stop recording, finalize the file, and return its info."""
    global _proc, _path, _started_at
    if not is_recording():
        raise RecorderError("Not currently recording.")

    proc, path, started = _proc, _path, _started_at

    # SIGINT is the helper's clean-stop signal: it finalizes the WAV header and
    # exits 0. This is the exact path the standalone smoke test used.
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        # Last resort: SIGTERM (also a clean stop), then hard kill.
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    duration = time.time() - started
    size = os.path.getsize(path) if os.path.exists(path) else 0
    _reset()

    if size == 0:
        raise RecorderError(
            "Recording produced an empty file. Check that audio was actually "
            "playing and that Screen & System Audio Recording permission is "
            "granted."
        )

    return {
        "path": path,
        "filename": os.path.basename(path),
        "duration_s": round(duration, 1),
        "size_bytes": size,
    }


def _reset():
    global _proc, _path, _started_at, _log
    if _log is not None:
        try:
            _log.close()
        except OSError:
            pass
    _proc = None
    _path = None
    _started_at = None
    _log = None
