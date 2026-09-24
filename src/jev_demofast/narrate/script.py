"""A human-presenter voice-over script from a recorded run: one line per segment.

Output is plain "<id> | <label> | <text>" lines (models kept breaking JSON on quote marks in spoken text).
The line count is enforced by segment id, and the narrator only sees what was on screen.
"""
import json
import os
import re

SYSTEM = """You are a real person giving a live, screen-shared demo of a product to a potential customer, and this
is the transcript of what you say. You get the goal and the recorded segments in order; for each you know what was
done and what was on screen afterwards (screen_title, screen_text).

Reply with plain text only, no JSON and no markdown: exactly one line per segment, in order, each formatted as
<segment id> | <label> | <what you say>
e.g. "00 | Landing page | So this is Acme...". Use every given segment id exactly once, and nothing else.

How a real presenter sounds:
- First person, talking to the viewer: "Let me show you...", "I'll...", "you'll notice...", "so here...".
- Continuous speech that flows across segments. Quick mechanical steps get short fragments that continue the
  previous thought ("...pop in my email...", "...password...", "...and sign in."), not a full sentence each.
- Point at real things on screen, quoting short phrases from screen_text when they are interesting.
- Say why it matters to the viewer, not only what is clicked. Contractions, light natural fillers ("okay", "so")
  used sparingly. Never read out field names like a form ("Email field", "Password entry").
- Opening line: who you are showing and what they'll see. Closing line: land the value, briefly.
- It's your own product: state what the screen says as fact ("you go from syllabus to live tutor in 15 minutes"),
  never "they claim" or "apparently".
- Never say passwords, email addresses, account or user names shown on screen, "test account", "automation",
  "AI agent", "segment", or describe clicking in the abstract. Never introduce yourself by name.
- Length: the opening line, any segment that lands on a new important screen, and the closing/read line are full
  sentences of 15-30 words with something specific from screen_text. Only quick form steps (typing, submitting)
  are short fragments of 3-8 words that continue the previous line.

Bad (robotic): "Now, we're securing our account with a password." "Next, we're browsing the course catalog."
Good (human): "...drop in my password, and sign in." "So this is the catalog — every course this term, and each
one comes with its own AI tutor."
Label: 2-4 words naming the segment."""

NARRATOR_FIELDS = {"do", "target", "chose", "items", "url", "screen_title", "screen_text"}
LINE = re.compile(r"^\W*(\d\d)\W*\|\s*(.*?)\s*\|\s*(.+?)\s*$")


def parse_lines(text):
    """{segment id: (label, text)} from '<id> | <label> | <text>' lines; tolerates '**00** |' and '- 00 |'."""
    out = {}
    for raw in text.splitlines():
        m = LINE.match(raw)
        if m:
            out[m.group(1)] = (m.group(2) or "Segment", m.group(3).strip().strip('"'))
    return out


def write(cf, run_dir, product="", attempts=3, log=print):
    data = json.load(open(os.path.join(run_dir, "actions.json")))
    segs = data["actions"]
    ids = [a["segment"] for a in segs]
    context = {"goal": re.sub(r"\{\{\w+\}\}", "(secret)", data["goal"]), "product": product,
               "note": "The screen_text is what the viewer sees; quote it, don't invent features.",
               "segments": [{"id": a["segment"], **{k: v for k, v in a.items() if k in NARRATOR_FIELDS}} for a in segs]}
    for attempt in range(attempts):
        by_id = parse_lines(cf.chat(cf.s.script_model, SYSTEM, json.dumps(context), cf.s.script_extra))
        if all(i in by_id for i in ids):
            break
        log(f"  script attempt {attempt + 1}: got {sorted(by_id)} for {ids}; retrying")
    else:
        raise SystemExit("the script never covered every segment; not writing narration.txt")
    path = os.path.join(run_dir, "narration.txt")
    with open(path, "w") as f:
        f.write("Narration generated from the recorded run: one numbered line per video segment.\n\n")
        for i in ids:
            f.write(f"{i} — {by_id[i][0]}\n{by_id[i][1]}\n\n")
    return path


def read_lines(path):
    """Spoken lines from narration.txt, in order (the demo-kit narration format)."""
    with open(path) as f:
        return [m.group(1).strip() for m in re.finditer(r"^\d\d — .*\n(.+)$", f.read(), re.M)]
