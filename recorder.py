"""Audio capture from the Background Music virtual device via ffmpeg.

Single-session: one recording at a time (single user, single machine). The PRD
captures *system audio only* (the interviewer's voice), now routed through the
Background Music app, so there is one track and no diarization.

Records mono 16 kHz WAV, which is exactly what whisper.cpp wants in Phase 2, so
no re-encode is needed later.
"""

import os
import re
import signal
import subprocess
import time

FFMPEG = "ffmpeg"

# Exact avfoundation device name to capture from. Must match exactly so we pick
# the full "Background Music" device and not "Background Music (UI Sounds)".
DEVICE_NAME = "Background Music"

# Cached avfoundation audio-device index for the capture device.
_device_index = None

# Single-session recording state.
_proc = None
_path = None
_started_at = None
_log = None  # open file handle for ffmpeg stderr


class RecorderError(RuntimeError):
    pass


def find_device_index(refresh=False):
    """Return the avfoundation audio-input index for the DEVICE_NAME device.

    ffmpeg prints the device list to stderr; lines look like:
        [AVFoundation indev @ 0x..] [2] Background Music (UI Sounds)
        [AVFoundation indev @ 0x..] [6] Background Music
    We match the device name exactly (not a substring) so "Background Music"
    wins over "Background Music (UI Sounds)". The bracketed number is the index
    we pass as ``-i ":<idx>"``.
    """
    global _device_index
    if _device_index is not None and not refresh:
        return _device_index

    proc = subprocess.run(
        [FFMPEG, "-hide_banner", "-f", "avfoundation",
         "-list_devices", "true", "-i", ""],
        capture_output=True, text=True,
    )
    listing = proc.stderr

    # Only consider the audio-devices section; video devices share the [N] format.
    in_audio = False
    for line in listing.splitlines():
        if "AVFoundation audio devices" in line:
            in_audio = True
            continue
        if "AVFoundation video devices" in line:
            in_audio = False
            continue
        if not in_audio:
            continue
        # Pull the "[N] <name>" at the end of the line and match name exactly.
        m = re.search(r"\[(\d+)\]\s+(.+?)\s*$", line)
        if m and m.group(2).strip().lower() == DEVICE_NAME.lower():
            _device_index = int(m.group(1))
            return _device_index

    raise RecorderError(
        f"'{DEVICE_NAME}' audio device not found in ffmpeg's avfoundation device "
        f"list. Is the Background Music app running?\n\n" + listing
    )


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

    idx = find_device_index()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # -i ":<idx>"  -> audio-only capture from that avfoundation audio device.
    cmd = [
        FFMPEG, "-hide_banner", "-loglevel", "warning",
        "-f", "avfoundation", "-i", f":{idx}",
        "-ac", "1", "-ar", "16000",
        "-y", path,
    ]
    # ffmpeg's stderr goes to a log file, not an undrained PIPE: an unread PIPE
    # fills (~64 KB) and ffmpeg blocks on write, silently halting capture after
    # a fraction of a second. Keep stdin open so we can send 'q' to finalize.
    log_path = path + ".log"
    _log = open(log_path, "wb")
    _proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL, stderr=_log,
    )
    _path = path
    _started_at = time.time()

    # Fail fast if ffmpeg died immediately (e.g. device busy / permissions).
    time.sleep(0.5)
    if _proc.poll() is not None:
        _log.flush()
        with open(log_path, "r", errors="replace") as f:
            err = f.read()
        _reset()
        raise RecorderError(f"ffmpeg failed to start recording:\n{err}")

    return {"path": path, "started_at": _started_at}


def stop():
    """Stop recording, finalize the file, and return its info."""
    global _proc, _path, _started_at
    if not is_recording():
        raise RecorderError("Not currently recording.")

    proc, path, started = _proc, _path, _started_at

    # Ask ffmpeg to quit cleanly so the WAV header/duration is finalized.
    try:
        proc.stdin.write(b"q\n")
        proc.stdin.flush()
    except (BrokenPipeError, ValueError, OSError):
        pass

    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.send_signal(signal.SIGINT)
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
            "Recording produced an empty file. Check that the Multi-Output Device "
            "is selected as system output and audio was actually playing."
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
