"""Is the goal's answer really on screen? A read step returning text isn't proof: one run typed "trending this week"
into a search box, read the same words back, and would have counted that as the answer."""
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
