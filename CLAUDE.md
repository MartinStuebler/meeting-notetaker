# CLAUDE.md

Standing instructions for this project. Read this and `PRD.md` at the start of every session.

## What this is

A local Mac tool that records an online interview, transcribes the interviewer's side locally, condenses it to the ~10% that matters, and writes a row into a Google Sheet. Full spec is in `PRD.md`. The PRD is the source of truth for *what* to build.

## How we work together

- **Build one phase at a time.** The PRD has five phases. Do not start a phase until the previous one works and I have confirmed it. Do not stub or scaffold future phases "to save time."
- **Step by step.** Walk me through changes as you make them. Explain what each new file or function does and why, in plain terms. I am using this project to learn, not just to ship.
- **Wait for me.** After a meaningful change, stop and let me run it and react before moving on. Do not chain many edits without checking in.
- **Small diffs.** Prefer small, reviewable changes over large rewrites. If a change is big, tell me why before making it.
- **Ask before installing.** Confirm with me before adding dependencies or running install commands, and say what each one is for.
- **Efficiency is a design constraint.** Token usage and API-call count matter and must be considered when designing any feature, not treated as an afterthought. Prefer designs that do the work once over designs that repeat calls. When a feature touches the Claude API, tell me the rough call count and token cost of the options before we choose. It is lunch money per session, but it accumulates, so default to the leaner design unless there is a real reason not to.
- **No em-dashes** in anything you write for me, including code comments and docs.

## Current phase

> Phase 2 complete and verified: whisper.cpp (whisper-cli + small.en) transcribes the saved WAV via transcribe.py and the /api/transcribe endpoint, with a Transcribe button in the UI. A 60 min file transcribes in about 72 s (roughly 50x realtime). Next up is Phase 3: the condense step plus the on-page review and trim UI.

Update this line as we finish each phase so a fresh session knows where we are.

## Tech stack

- Backend: Python + Flask
- Frontend: small local React or plain HTML page (Start/Stop + confirm fields for Person, Company, Role)
- Capture: BlackHole virtual device + a Multi-Output Device, system audio only (no microphone)
- Transcription: whisper.cpp, local, no audio leaves the machine
- Condense: Claude API, single call
- Output: Google Sheets API via Google OAuth

## Hard constraints (from the PRD, do not violate)

- **System audio only.** Never capture or record my microphone.
- **Local transcription only.** Audio must never be sent off the machine.
- **Delete the raw audio file** after transcription succeeds. Persist only the condensed text.
- **No auto-detect of call start** in v1. Manual Start/Stop button only.
- **No live transcript** in v1. Process on Stop.
- **Condensed bullets only.** No full-transcript output in v1.

## Environment

- macOS, single user, single machine.
- Online calls only (Google Meet ~80%, Zoom ~20%), up to ~60 minutes each.
- Google OAuth has been set up before on another project, so the pattern is familiar.

## Out of scope right now

Auto-detect call start, keeping my mic / both-sides transcripts, live transcript, a local search UI, and note-to-application linking are all v2. See the PRD backlog. Do not build these unless I move them into the current phase.
