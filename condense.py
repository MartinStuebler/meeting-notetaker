"""Condense an interview transcript into five importance-driven versions.

One Claude API call per interview returns all five versions at once (80, 50, 25,
10, and 5 percent of the original). The UI slider then switches between the
pre-made versions with no further API calls. This is the deliberate efficiency
choice from the PRD (section 9a): one call, not one per slider move.

We use structured outputs so the single response comes back as clean JSON with a
fixed set of fields, instead of parsing free text.
"""

import json
import os

import anthropic

# Haiku 4.5: cheapest model, fine here because the user reviews and edits output.
MODEL = "claude-haiku-4-5"

SYSTEM = """You condense the transcript of one side of a job interview: the \
interviewer speaking. The reader is the candidate, who wants only what matters \
from what the interviewer said. The candidate's own words are not in the \
transcript and must never be invented.

Produce five versions of the content at decreasing lengths: roughly 80, 50, 25, \
10, and 5 percent of the original word count. Each shorter version keeps what \
matters most and drops filler, rather than trimming evenly.

Priority order to keep as the versions get shorter (highest first):
1. Commitments and concrete next steps: compensation, timeline, who does what \
next, when the candidate will hear back.
2. Logistics: interview rounds, format, who the candidate will meet.
3. Role and team details: scope, reporting line, what they actually need.
4. Things the candidate should follow up on or send.
5. Red flags or anything that gave pause.
6. Company facts dropped on the call: funding, headcount, org changes.

Write clear bullet points, grouped lightly by these categories when content \
exists. Omit categories that have no content rather than writing "none". The 5 \
percent version should be only the few must-keep items (commitments, red flags). \
Do not add information that is not in the transcript."""

# Structured-output schema: one string per version. Length is steered by the
# prompt (JSON schema does not support length constraints).
SCHEMA = {
    "type": "object",
    "properties": {
        "v80": {"type": "string", "description": "~80% of original length, lightly trimmed"},
        "v50": {"type": "string", "description": "~50% of original length"},
        "v25": {"type": "string", "description": "~25% of original length"},
        "v10": {"type": "string", "description": "~10% of original length"},
        "v5": {"type": "string", "description": "~5% of original length, must-keep items only"},
    },
    "required": ["v80", "v50", "v25", "v10", "v5"],
    "additionalProperties": False,
}


class CondenseError(RuntimeError):
    pass


def condense(transcript):
    """Return {"v80","v50","v25","v10","v5"} for a transcript via one Claude call."""
    transcript = (transcript or "").strip()
    if not transcript:
        raise CondenseError("Empty transcript.")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise CondenseError("ANTHROPIC_API_KEY is not set.")

    client = anthropic.Anthropic()
    try:
        # Stream so long transcripts do not trip the SDK's non-streaming timeout
        # guard; get_final_message still returns the whole response synchronously.
        with client.messages.stream(
            model=MODEL,
            max_tokens=24000,
            system=SYSTEM,
            messages=[{"role": "user", "content": transcript}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        ) as stream:
            message = stream.get_final_message()
    except anthropic.APIError as e:
        raise CondenseError(f"Claude API error: {e}") from e

    text = next((b.text for b in message.content if b.type == "text"), "")
    try:
        versions = json.loads(text)
    except json.JSONDecodeError as e:
        raise CondenseError(f"Could not parse model output as JSON: {e}") from e

    return versions
