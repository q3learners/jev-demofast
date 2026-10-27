"""After recording, the founder's script (story.txt) becomes one continuous voice-over with [NN] markers where each
recorded moment comes up (voiceover.txt), corrected only where the recording proves it wrong. narration.txt gets the
words per segment, for the page and the per-line fallback voice.

Fitted one line per segment, it read as captions: a presenter talks in one continuous thought across several actions.
"""
import json
import os

from . import voiceover

WORDS_PER_SEGMENT = 13  # about 5 s of speech per recorded moment on average; quick steps take less, the opening more
WORDS_PER_SHOT, WORDS_PER_MORE = 20, 8  # with a shot list: a screen of the founder's story, and each further moment
# in it (a scroll, a filter); 13 per click cut tutorq.ai's four-product script to a 19 s video
EMPTY = "…"  # narration.txt's entry for a quick step with no words of its own

SYSTEM = """You are the founder of this product, recording the voice-over for a demo of it in one take, the way you'd
present it live to the audience in the brief. Before the demo was recorded you wrote what you wanted to say
(founder_script). The recording is done: you get its moments in order (segments), each with what happened
(do, target) and what it showed (items, unavailable, outcome).

Write the voice-over as one continuous piece of speech that starts from your founder_script: keep its sentences and
ideas, trimmed and corrected, never replaced by descriptions of the screen. Place each segment's marker, [NN] with
its id, right BEFORE the words you say while that moment is on screen. Reply with the voice-over only: plain text
starting with [00], no headings, no lists, no markdown. Use every marker exactly once, in order. Two markers can sit
side by side when a quick step needs no words of its own.

The shape, from an unrelated product (never reuse its words): "[00] Every team tells us planning takes too long, so
let me show you how we fixed it. [01] Everything starts from your backlog, so nothing gets lost... [02] [03] drag in
what you want this week, and we flag what won't fit before you commit. [04] And that's a sprint, planned in under a
minute."

With a shot list, each moment says why you put it in the demo (show) and what's on screen there (headings, after a
scroll): speak to that reason in your own words, and never read the headings out as a list.

Never write stage directions or captions ("open the Men menu", "filters open", "Active takes us to the collection"):
the viewer sees those. Say what the founder would say over them.

Sound like a person presenting, not reading:
- Keep your script's ideas and words, spoken: contractions, short sentences, "you" for the viewer, an occasional
  "so", "now" or "okay" (sparingly).
- React briefly to what happens ("...and there it is."), and let a moment breathe with "..." while a page loads.
- One thought can run across several moments. Don't describe what the viewer can see; say why it matters to them.
- Never say "click", "hover", "select", "segment", "AI", "automation" or "agent".

Tell the truth about the recording:
- target is what was really chosen: if your script named another value, say the real one.
- unavailable lists filter values the site had greyed out: say so in a few words, the way a person would, then
  carry on with what was chosen.
- The results moment (do: read) names one to three of its items with their prices, in a spoken sentence.
- An outcome that says "not confirmed" means the demo didn't get there: say so plainly, never describe a success.
- Names, counts and prices come only from target and items.

About {budget} words in all, never more."""

FIELDS = {"do", "target", "items", "screen_title", "outcome", "unavailable", "show", "headings"}  # facts, not page text: given the
# page text, it described the screen again instead of keeping the script


def budget(segs):
    """The voice-over's length in words: per shot when the recording played a shot list, else per segment."""
    total, seen = 0, set()
    for seg in segs:
        if "shot" not in seg:
            total += WORDS_PER_SEGMENT
        else:
            total += WORDS_PER_MORE if seg["shot"] in seen else WORDS_PER_SHOT
            seen.add(seg["shot"])
    return total


def write(cf, run_dir, goal, segs, founder_script, attempts=3, log=print):
    """Write voiceover.txt and narration.txt; returns narration.txt's path."""
    ids = [a["segment"] for a in segs]
    context = {"goal": goal, "founder_script": founder_script,
               "segments": [{"id": a["segment"], **{k: v for k, v in a.items() if k in FIELDS}} for a in segs]}
    system = SYSTEM.format(budget=budget(segs))
    best = None
    for attempt in range(attempts):
        text = cf.chat(cf.s.script_model, system, json.dumps(context), cf.s.script_extra).strip()
        parts = voiceover.split(text, ids)
        if parts is None:
            log(f"  voice-over attempt {attempt + 1}: the markers don't cover {ids[0]}..{ids[-1]} once each; retrying")
            context["previous_attempt"] = "use every marker exactly once, in order, starting with [00]"
            continue
        words = len(voiceover.plain(text)[0].split())
        if best is None or words < best[1]:
            best = (text, words, parts)
        if words <= budget(segs) * 1.1:
            break
        log(f"  voice-over attempt {attempt + 1}: {words} words, the budget is {budget(segs)}; retrying")
        context["previous_attempt"] = f"it was {words} words; keep it to {budget(segs)}"
    if best is None:
        raise SystemExit("the voice-over never placed every marker; not writing narration.txt")
    text, _, parts = best
    with open(os.path.join(run_dir, "voiceover.txt"), "w") as f:
        f.write(text + "\n")
    path = os.path.join(run_dir, "narration.txt")
    with open(path, "w") as f:
        f.write("Narration from the founder's voice-over (voiceover.txt): the words over each video segment.\n\n")
        for a in segs:
            label = " ".join(str(a.get(k) or "") for k in ("do", "target")).strip()
            f.write(f"{a['segment']} — {label}\n{parts[a['segment']] or EMPTY}\n\n")
    return path
