"""Did the run really get there? Two judgments by the decision model, instead of trusting text matches:
- a read step returning text isn't proof: one run typed "trending this week" into a search box, read the same words
  back, and would have counted that as the answer;
- a planner's guessed finish phrase isn't either: GitHub's weekly Trending page doesn't say "trending repositories".
"""
from ..cloudflare import sees_images

CONFIDENT = 0.5
# Asking whether the screen shows everything asked for failed real runs (Jev 0.19-0.39: a read lists more than any one
# screen shows). Asking for the right page with real content of that kind: real runs 0.82-0.95, the typed-text run 0.05.
QUESTION = ("Is this the page the goal is about, showing real content of the kind asked for ({asked}), even if not "
            "every item? It must be the page's own content, not a search box, a menu, a suggestion list, or text the "
            "user typed.")


def shows_answer(cf, goal, asked, items, page, screenshot=None):
    """(verified, score). No items: not verified, and no model call. `screenshot` (a callable returning JPEG bytes)
    is only taken when the check model reads images."""
    if not items:
        return False, 0.0
    state = {"goal": goal, "asked_for": asked, "extracted": items[:8], "url": page["url"],
             "visible_text": " ".join((page.get("text") or "").split())[:1500]}
    images = [screenshot()] if screenshot and sees_images(cf.s.check_model) else None
    score = cf.yes(QUESTION.format(asked=asked), state, true="the screen shows it",
                   false="it doesn't: the wrong page, a search box or menu, an error, or only typed text",
                   model=cf.s.check_model, images=images)
    return score >= CONFIDENT, score


# Stricter than CONFIDENT: with Jev, GitHub's Trending page in the wrong time range ('Today' for "this week") scored
# 0.30-0.54, and passed once at 0.54; the right page scored 0.96-0.97 and the wrong page 0.03-0.04. A miss here costs a
# re-plan, a wrong pass a false success.
GOAL_CONFIDENT = 0.75
GOAL_QUESTION = ("Does this screen show the goal accomplished: the page or result the goal asks for, in the state it asks "
                 "for (for example the right filter, tab or time range)? Not a search box, a menu, an error, or a "
                 "different page.")


def goal_reached(cf, goal, page, screenshot=None):
    """(verified, score) for the screen a run ended on."""
    state = {"goal": goal, "url": page["url"], "title": page.get("title", ""),
             "visible_text": " ".join((page.get("text") or "").split())[:1500]}
    images = [screenshot()] if screenshot and sees_images(cf.s.check_model) else None
    score = cf.yes(GOAL_QUESTION, state, true="yes: this is where the goal leads, as asked",
                   false="no: the wrong page or state, a search box or menu, or an error",
                   model=cf.s.check_model, images=images)
    return score >= GOAL_CONFIDENT, score
