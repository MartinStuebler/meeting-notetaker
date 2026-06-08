"""Meeting Note-Taker — Phase 1: local Flask app for Start/Stop system-audio capture.

Local-first, single-user, bound to 127.0.0.1. Mirrors the Garden dashboard pattern
(static HTML SPA + /api/* routes) without the password gate — there is nothing here
worth exposing beyond localhost.

Later phases add whisper.cpp transcription, a Claude condense step, and a Google
Sheets row. Person/Company/Role are collected in the UI now and used in Phase 4.
"""

import datetime
import os

from dotenv import load_dotenv
from flask import (Flask, jsonify, request, send_from_directory)

import recorder
import transcribe
import condense
import sheets

load_dotenv()

HERE = os.path.dirname(os.path.abspath(__file__))
RECORDINGS_DIR = os.path.join(HERE, "recordings")
STATIC_DIR = os.path.join(HERE, "static")

app = Flask(__name__, static_folder=None)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-only-not-secret")


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.post("/api/start")
def api_start():
    if recorder.is_recording():
        return jsonify(error="Already recording."), 409
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(RECORDINGS_DIR, f"rec-{stamp}.wav")
    try:
        info = recorder.start(path)
    except recorder.RecorderError as e:
        return jsonify(error=str(e)), 500
    return jsonify(status="recording", started_at=info["started_at"])


@app.post("/api/stop")
def api_stop():
    try:
        info = recorder.stop()
    except recorder.RecorderError as e:
        return jsonify(error=str(e)), 400
    info["url"] = f"/recordings/{info['filename']}"
    return jsonify(status="stopped", **info)


@app.post("/api/transcribe")
def api_transcribe():
    # The frontend passes back the filename that /api/stop returned.
    data = request.get_json(silent=True) or {}
    name = os.path.basename(data.get("filename", ""))  # basename: no path escapes
    if not name:
        return jsonify(error="No filename provided."), 400
    path = os.path.join(RECORDINGS_DIR, name)
    if not os.path.exists(path):
        return jsonify(error=f"Recording not found: {name}"), 404
    try:
        text = transcribe.transcribe(path)
    except transcribe.TranscribeError as e:
        return jsonify(error=str(e)), 500
    return jsonify(text=text)


@app.post("/api/condense")
def api_condense():
    # Takes the (possibly edited) transcript text and returns five versions.
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify(error="No transcript text provided."), 400
    try:
        versions = condense.condense(text)
    except condense.CondenseError as e:
        return jsonify(error=str(e)), 500
    return jsonify(versions=versions)


@app.post("/api/save")
def api_save():
    data = request.get_json(silent=True) or {}
    notes = (data.get("notes") or "").strip()
    if not notes:
        return jsonify(error="Nothing to save: the notes are empty."), 400
    person = (data.get("person") or "").strip()
    company = (data.get("company") or "").strip()
    role = (data.get("role") or "").strip()
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    try:
        result = sheets.append_row(date, person, company, role, notes)
    except sheets.NeedsAuth as e:
        return jsonify(error=str(e)), 401
    except sheets.SheetsError as e:
        return jsonify(error=str(e)), 500
    return jsonify(status="saved", **result)


@app.get("/api/status")
def api_status():
    return jsonify(
        recording=recorder.is_recording(),
        elapsed_s=round(recorder.elapsed_s(), 1),
    )


@app.get("/recordings/<path:name>")
def serve_recording(name):
    return send_from_directory(RECORDINGS_DIR, name)


if __name__ == "__main__":
    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    app.run(host="127.0.0.1", port=5002, debug=True, use_reloader=False)
