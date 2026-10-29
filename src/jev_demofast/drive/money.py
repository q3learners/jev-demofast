"""Is this a step that takes money or verifies the parent? Judged from the screen by Clef before a forward click in a
logged-in run, so no product's wording is written into the rules. Measured 29 October (3 runs each, the same score every
run): K-12's card check 0.98, its "Verify again" page 0.97, a generic checkout 0.99; K-12's kids page 0.07, a kid's
login 0.11, subjects 0.03, a workspace setup 0.01. Unsure, or the model is down: the demo stops there."""
import base64

MONEY_STEP = 0.5  # at or above: refused. Every page measured sits far from it (0.11 the highest ordinary page)
QUESTION = ("Is this screen a step about payment, billing or verification (proving who you are, proving you are a "
            "parent or adult, or confirming a card), or does its main button start one?")
TRUE, FALSE = ("yes: a payment, billing or verification step",
               "no: ordinary setup or content, with no payment or verification")


def judge(cf):
    """money_step(s) -> True when the screen s is on takes money or verifies; one question per screen."""
    seen = {}

    def money_step(s):
        page = s.page or {}
        key = (page.get("url"), page.get("text"))
        if key not in seen:
            state = {"url": page.get("url"), "visible_text": " ".join((page.get("text") or "").split())[:1500]}
            try:
                shot = base64.b64decode(s.browser.call("Page.captureScreenshot", format="jpeg", quality=80)["data"])
                seen[key] = cf.yes(QUESTION, state, true=TRUE, false=FALSE, model=cf.s.check_model,
                                   images=[shot]) >= MONEY_STEP
            except Exception:  # can't tell: a missed shot is cheaper than a charge
                return True
        return seen[key]
    return money_step
