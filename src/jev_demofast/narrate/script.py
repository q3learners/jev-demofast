"""The voice-over from a recorded run: one line per segment. With the founder's script (story.txt, written before
recording) it is fitted over the segments in the founder's words; without one, it is written from the screens.

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
- Tell the truth about outcomes: if the screen shows an error or warning, or a segment's outcome says it was not
  confirmed, say plainly what went wrong, quoting the on-screen message, and never describe a step as successful
  unless the screen shows it succeeded.
- Never say passwords, email addresses, account or user names shown on screen, "test account", "automation",
  "AI agent", "segment", or describe clicking in the abstract. Never introduce yourself by name.
- Length is strict, because every word adds to the video's running time:
  - no line over {cap} words, and the whole script under {budget} words;
  - the opening line and the closing line: one short sentence each, about 12-18 words;
  - a new screen: one point worth noticing, about 8-16 words;
  - quick steps (typing, submitting, opening a menu): a short spoken line that continues the previous one;
  - a line that reads information: name the two or three most telling items, not all of them.
  Cut anything the viewer can already see for themselves.

Bad (robotic): "Now, we're securing our account with a password." "Next, we're browsing the course catalog."
Bad (too long): "So the real signals: 56k stars but also 9.9k forks, 1,786 commits of history, and only 13 open issues
with 27 pull requests, meaning real people are using it, fixing it, and contributing back."
Good (human, short): "...drop in my password, and sign in." "So this is the catalog: every course this term, each
with its own tutor." "Forks, commits and pull requests are the real signal; stars alone can be bought."
Label: 2-4 words naming the segment."""

FIT = """You are the founder of this product. Before the demo was recorded you wrote its voice-over (founder_script). The
recording is done; you get its segments in order. Your job now is only to lay your script over the video: which of
your sentences is spoken over which segment.

Reply with plain text only, no JSON and no markdown: exactly one line per segment, in order, each formatted as
<segment id> | <label> | <what you say>
Use every given segment id exactly once, and nothing else.

- Every line comes from founder_script: one of your sentences, trimmed to fit, in their order. Don't describe what the
  segment shows; the viewer sees it.
- Match sentences to segments by what they talk about: the first segment (do: open) gets your opening, the promise;
  a segment that opens a menu gets your sentence about that menu; a filter segment gets your sentence about that
  filter; the results segment (do: read) gets the results and the payoff. A segment none of your sentences is about
  (opening a panel, say) gets a few words that carry the previous thought on.
- Split a sentence only at a natural pause (a comma, "and", "so"), never in the middle of a phrase; every line reads
  as something said in one breath, with a subject and a verb.
- Cut what the recording never shows: a feature the demo didn't use (a sort, a tab) isn't mentioned.
- Change your words only where the recording proves the script wrong, and then say what really happened:
  - a filter segment's target is what was really chosen: if your sentence names another value ("under $150" when the
    target is "Price: $126 - $150"), say the target's value instead;
  - unavailable lists filter values the site greyed out (nothing there right now): say it the way a person would, in
    a few words, then carry on with what was chosen;
  - the results segment (do: read) lands the payoff in one spoken sentence that names two or three of its items with
    their prices, never a bare list of names;
  - an outcome that says "not confirmed": say plainly it didn't get there, never describe a success;
  - names, counts and prices come from target and items, never from your script.
- No line over {cap} words, and the whole script under {budget} words.

Bad, never like this (captions of the screen): "Hovering Men reveals the Active category." "Clicking Active loads the
collection." "Select the $126 to $150 price band." "Filters expand, revealing size, color and price."
Label: 2-4 words naming the segment."""

LINE_CAP = 26           # words per line
WORDS_PER_SEGMENT = 17  # the whole script's budget, per segment: a founder's spoken sentence, about 6 s of speech


def word_budget(segment_count):
    return WORDS_PER_SEGMENT * segment_count


def too_long(by_id, ids):
    """What breaks the length rules, as instructions for a retry; empty when the script fits."""
    counts = {i: len(by_id[i][1].split()) for i in ids}
    problems = [f"line {i} has {n} words; the cap is {LINE_CAP}" for i, n in counts.items() if n > LINE_CAP]
    total, budget = sum(counts.values()), word_budget(len(ids))
    if total > budget * 1.1:  # a few words over isn't worth another model call
        problems.append(f"the total is {total} words; the budget is {budget}")
    return problems


NARRATOR_FIELDS = {"do", "target", "chose", "items", "url", "screen_title", "screen_text", "outcome", "unavailable"}
# Fitting the founder's script, the narrator gets the facts but not the page text: given the text, it described the
# screen again instead of keeping the script.
FIT_FIELDS = {"do", "target", "items", "screen_title", "outcome", "unavailable"}
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
    goal = re.sub(r"\{\{\w+\}\}", "(secret)", data["goal"])
    founder = os.path.join(run_dir, "story.txt")
    if os.path.exists(founder):  # the founder's script, written before recording: fit it over what was recorded
        with open(founder) as f:
            context = {"goal": goal, "founder_script": f.read().strip(),
                       "segments": [{"id": a["segment"], **{k: v for k, v in a.items() if k in FIT_FIELDS}}
                                    for a in segs]}
        system = FIT
    else:
        context = {"goal": goal, "product": product,
                   "note": "The screen_text is what the viewer sees; quote it, don't invent features.",
                   "segments": [{"id": a["segment"], **{k: v for k, v in a.items() if k in NARRATOR_FIELDS}}
                                for a in segs]}
        system = SYSTEM
    system = system.format(cap=LINE_CAP, budget=word_budget(len(ids)))
    best = None
    for attempt in range(attempts):
        by_id = parse_lines(cf.chat(cf.s.script_model, system, json.dumps(context), cf.s.script_extra))
        if not all(i in by_id for i in ids):
            log(f"  script attempt {attempt + 1}: got {sorted(by_id)} for {ids}; retrying")
            continue
        problems = too_long(by_id, ids)
        if best is None or sum(len(by_id[i][1].split()) for i in ids) < sum(len(best[i][1].split()) for i in ids):
            best = by_id
        if not problems:
            break
        log(f"  script attempt {attempt + 1}: too long ({'; '.join(problems)}); retrying")
        context["previous_attempt_was_too_long"] = problems  # say exactly what to shorten
    if best is None:
        raise SystemExit("the script never covered every segment; not writing narration.txt")
    by_id = best  # still over after the retries: keep the shortest complete script rather than fail the video
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
