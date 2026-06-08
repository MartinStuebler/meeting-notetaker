# PRD: Interview Note-Taker

**Owner:** Martin
**Status:** Draft v1
**One-line:** A local Mac tool that records an online interview, transcribes the interviewer's side, condenses it to the ~10% that matters, and writes a row into a Google Sheet so I never take manual notes during a call.

---

## 1. Problem and purpose

I do a high volume of interviews and I do not want to split attention between the conversation and note-taking. I want to be fully present on the call and have clean, structured notes waiting for me afterward.

I am the interviewee, not the hiring manager. The notes are for me. The only content worth capturing is what the *other person* says: commitments, logistics, role details, things to follow up on, and red flags. My own words do not need to be recorded.

## 2. User and use case

- Single user (me), single machine (Mac).
- All interviews are online: ~80% Google Meet, ~20% Zoom.
- Calls run up to one hour.
- No in-person interviews.

Typical flow: I join a call, click "Start," talk normally, click "Stop" when done. A minute or so later I have a condensed bullet summary of what the interviewer said, saved as a row in my interview tracker sheet.

## 3. Goals and non-goals

**Goals (v1)**
- Capture the other person's audio from any online call without per-app setup.
- Transcribe locally for free and for privacy.
- Produce a short bullet summary of the interviewer's side.
- Write that summary into a Google Sheet, searchable later by company, person, date, role.
- Zero manual note-taking during the call.

**Non-goals (v1)**
- No real-time / live transcript. Process on stop only.
- No recording of my own voice. Their side only.
- No auto-detection of call start. Manual button.
- No in-person / room recording.
- No multi-user, no cloud transcription, no mobile.

## 4. Definition of done (v1)

The first real interview where I take zero manual notes, and afterward see the transcript on the page, trim it with the slider to the length I want, edit if needed, and save it as a new row in my Google Sheet.

## 5. Functional requirements

### 5.1 Audio capture
- Capture **system audio only** (the interviewer's voice plays through my speakers). My microphone is not captured.
- Use **BlackHole** (virtual audio device) with a one-time setup in Audio MIDI Setup.
- Because routing system audio into BlackHole means I would otherwise stop hearing the call, set up a **Multi-Output Device** (BlackHole + my headphones/speakers) so I still hear everything while it records.
- Manual **Start / Stop** button in the app.
- On Stop, save the captured audio to a temporary local file.
- Must handle up to ~60 minutes in one recording.

### 5.2 Transcription
- Local transcription with **whisper.cpp**. No audio leaves the machine.
- Run on the single captured track after Stop.
- Because only the interviewer's track is captured, no speaker diarization or "me vs them" labelling is needed. The whole transcript is them.

### 5.3 Condense step (review and trim on the same page)
After transcription, the full text appears on the same page. I review it, choose how hard to cut, edit by hand if needed, then save. Flow:

- **One API call, five versions.** A single Claude API call produces five condensed versions of the transcript at once: 80%, 50%, 25%, 10%, and 5% of the original. They are generated together in one request and held in the app. This is a deliberate efficiency choice: one call, not one call per slider move.
- **Slider switches between pre-made versions.** A slider with five stops (5 / 10 / 25 / 50 / 80%) plus full. Dragging it instantly swaps the displayed text between the already-generated versions. No wait, no extra API calls while dragging.
- **Cutting is importance-driven.** Each shorter version keeps what matters and drops filler, rather than trimming evenly. Priorities to keep as the text shrinks: commitments and next steps (comp, timeline, when I hear back), logistics (rounds, format, who I meet), role and team details, things to follow up on, red flags, company facts (funding, headcount, org).
- **Fully editable.** The displayed text is editable by hand before saving. I can fix or tweak any version.
- **Then save.** Once I have the version I want and have made any edits, I save it (see 5.4).

### 5.4 Output to Google Sheet
- After I trim and edit, the chosen text is written into a Google Sheet via the Sheets API (Google OAuth, same pattern as the Garden dashboard).
- If the target sheet does not exist yet, create it with the schema below.
- Each interview = one new row. The saved text is whatever version I landed on, including my hand edits.

### 5.5 Storage and retrieval
- The Google Sheet is the record of truth. No separate local notes database in v1.
- Searchable by company, person, date, role because those are columns.
- **Delete the raw audio file after transcription succeeds.** Keep nothing on disk beyond what is needed.

## 6. Google Sheet schema (v1)

Fresh sheet, header row in this order:

| Date | Person | Company | Role | Notes |
|------|--------|---------|------|-------|

- **Date:** date of the call (auto-filled).
- **Person:** interviewer name (I enter or confirm before/after recording).
- **Company:** (I enter or confirm).
- **Role:** (I enter or confirm).
- **Notes:** the trimmed and edited text I chose to save.

I will confirm Person / Company / Role in the app before the row is written, since the tool cannot reliably infer them from audio.

## 7. Data and privacy

This is a deliberate strength of the design, not an afterthought.
- Audio never leaves the machine: local transcription only.
- Raw audio is deleted immediately after transcription.
- Only the condensed text reaches Google (via the Sheet I own).
- My own voice is never recorded.
- Consent note: New York is one-party consent, so recording a call I am on is fine for me. Some interviewers sit in two-party-consent states. A quick "mind if I take recorded notes?" at the top of a call covers it.

## 8. Tech stack

- **Frontend:** small local React or plain HTML page with Start/Stop and the three confirm fields (Person, Company, Role). Reuses my frontend comfort zone.
- **Backend:** Python (Flask), matching the Garden dashboard pattern.
- **Capture:** BlackHole + Multi-Output Device, recorded via the backend.
- **Transcription:** whisper.cpp, local.
- **Condense:** Claude API, single call.
- **Output:** Google Sheets API, Google OAuth (already done this once).

## 9. End-to-end flow

1. I enter/confirm Person, Company, Role in the app.
2. Click **Start**. Backend begins recording the BlackHole system-audio stream.
3. Call happens. I hear it normally via the Multi-Output Device.
4. Click **Stop**. Audio saved to a temp file.
5. whisper.cpp transcribes the file locally.
6. Temp audio file is deleted.
7. The full transcript appears on the page. In the background, one Claude API call generates all five condensed versions (5 / 10 / 25 / 50 / 80%).
8. I drag the slider to switch instantly between full and the five versions, edit the text by hand if I want, and pick the length I want.
9. Click **Save**. The chosen, edited text is written as a new row (Date, Person, Company, Role, Notes) to the Google Sheet.

## 9a. Token efficiency (design rule)

Condensing uses exactly **one** Claude API call per interview, producing all five versions together. The slider never calls the API; it only switches between text already generated. This is a deliberate choice over a live per-drag design that would fire a call on every slider move. Cost is small either way, but call count compounds across many interviews, so the default is the leaner design.

## 10. Build phases

**Phase 1: capture + save**
- BlackHole + Multi-Output setup documented.
- Flask app with Start/Stop that records system audio to a file. Verify a clean recording of a test call.

**Phase 2: transcription**
- Wire whisper.cpp. Confirm a 60-minute file transcribes locally in acceptable time.

**Phase 3: condense + review UI**
- One Claude API call that returns all five versions (5 / 10 / 25 / 50 / 80%) for a transcript. Iterate the prompt on real transcripts until the cuts keep what matters and drop filler.
- On-page review: show the full transcript, a slider that switches instantly between full and the five versions, and make the displayed text editable by hand.

**Phase 4: Google Sheet output**
- Google OAuth + Sheets API. Create sheet if missing, append the trimmed/edited text as a new row, confirm schema.

**Phase 5: cleanup + polish**
- Auto-delete audio after success. Confirm fields in the UI. Error handling (transcription fails, no audio captured, Sheets auth expired).

Ship after Phase 5 is the working tool. Anything below is later.

## 11. v2 backlog (explicitly out of scope now)

- Auto-detect call start (watch for a Meet tab or Zoom process). Cut from v1 because it adds disproportionate code and false-start handling for marginal benefit.
- Optionally keep my mic track for full both-sides transcripts.
- Live transcript while recording.
- Local search UI over past notes (instead of relying on the Sheet).
- Tagging / linking notes to specific application threads.

## 12. Portfolio note (honest read)

This is a solid working tool and a clean end-to-end build (capture, local ML transcription, an LLM pipeline, OAuth, Sheets output). Its strongest portfolio story is **data minimization and local-first privacy**: sensitive conversation audio never leaves the machine and is deleted after use, with only condensed text persisted.

It does **not** showcase the multi-tenant access control, field-level RBAC, or prompt-injection defense that the Access Control Demonstrator is built to show. It complements that project rather than replacing it. If the goal is a Credal-relevant centerpiece, the Access Control Demonstrator stays the lead; this is a credible secondary "I build useful things end to end and handle sensitive data responsibly" piece.

## 13. Risks and open items

- **BlackHole setup friction.** One-time, ~10 minutes, well-documented. The only real manual step.
- **whisper.cpp speed on long files.** Test a full hour early (Phase 2) so processing time is a known quantity, not a surprise.
- **Condense quality.** The prompt is where the tool earns its value. Budget real iteration in Phase 3 against actual interview transcripts.
- **Consent in two-party states.** Behavioral, handled by asking at the top of the call.
