"""Pages behind buttons. A Flutter app navigates with buttons, not links (k12.tutorq.ai had none), so on a Flutter page
the explorer clicks the buttons that can't change anything and records where each leads, as a link.

Exploring never submits. Labels that sign up, delete or change data are never clicked (guards). A page with fields has
no <form> to tell its submit button from a navigation button, so Clef decides from the screenshot, measured on K-12
(29 October, 3 runs each, the same score every run): navigation 0.93-0.98 ("I need an account", "Back"), the two
"Sign in" submits 0.02-0.03, "Show password" 0.09. Anything short of NAVIGATES_CONFIDENT, an error, or a check model
that can't see images means no click: a miss costs a link, a wrong pass an (empty) form sent.
"""
import base64
from urllib.parse import urlparse

from ..cloudflare import sees_images
from ..drive.guards import CHANGES, blocked, on_site

NAVIGATES_CONFIDENT = 0.8
QUESTION = ("A visitor is on this page and has typed nothing into its fields. Does clicking the button named in "
            "'button' only take them to another page or step (navigation such as Back, or a link to a different form), "
            "without sending this page's form or signing in?")
TRUE, FALSE = "yes: it only navigates", "no: it sends the form, signs in, or changes something"
# A page behind a login sends a visitor to a sign-in form instead. Mapped, it carried the sign-in page's content, and
# reafi.ai's demo went to its login page and back. A redirect alone isn't a wall (/about-us → /pages/about).
SIGN_IN_FORM_JS = "!!document.querySelector('input[type=password]')"


def _first_line(label):
    return (label or "").strip().split("\n")[0].strip()


def _address(url):
    u = urlparse(url)
    return (u.path or "/") + (f"?{u.query}" if u.query else "")


def only_navigates(cf, label, page, fields, buttons, screenshot):
    """Clef's judgment that clicking `label` only navigates, at NAVIGATES_CONFIDENT or above. False on any doubt."""
    if cf is None or not sees_images(cf.s.check_model):
        return False
    state = {"url": page["url"], "button": label, "fields_on_page": fields, "buttons_on_page": buttons,
             "visible_text": " ".join((page.get("text") or "").split())[:1500]}
    try:
        score = cf.yes(QUESTION, state, true=TRUE, false=FALSE, model=cf.s.check_model, images=[screenshot()])
    except Exception:  # the model is down or answered nonsense: don't click
        return False
    return score >= NAVIGATES_CONFIDENT


def discover(s, origin, path, cf, log=print):
    """Links found by clicking the safe buttons of the page at `path`: [{"label", "to", "via": "button"}]. The session
    is back on the page when this returns."""
    host = urlparse(origin).hostname
    els = s.elements()
    fields = [_first_line(e["label"]) for e in els if "fill" in e["actions"]]
    has_fields = bool(fields) or s.browser.evaluate(SIGN_IN_FORM_JS) is True
    labels = list(dict.fromkeys(_first_line(e["label"]) for e in els
                                if e["role"] == "button" and "click" in e["actions"] and _first_line(e["label"])))
    page, shot, links = s.page, [], []

    def screenshot():
        if not shot:
            shot.append(base64.b64decode(s.browser.call("Page.captureScreenshot", format="jpeg", quality=80)["data"]))
        return shot[0]

    for label in labels:
        if blocked(label) or CHANGES.search(label):
            continue
        if has_fields and not only_navigates(cf, label, page, fields, labels, screenshot):
            continue
        e = next((e for e in s.elements() if e["role"] == "button" and _first_line(e["label"]) == label), None)
        if e is None:
            continue
        try:
            s.act(e, "click")
            s.wait_for_page()
            landed = s.observe()["url"]
        except Exception as err:  # the page changed under the click: skip this button
            log(f"  button {label!r}: {err}")
            landed = None
        if landed and on_site(landed, host) and _address(landed) != path:
            links.append({"label": label, "to": _address(landed), "via": "button"})
            log(f"  button {label!r} → {_address(landed)}")
        s.browser.call("Page.navigate", url=origin + path)  # back for the next button: Flutter's history isn't ours
        s.wait_loaded()
        s.observe()
    return links
