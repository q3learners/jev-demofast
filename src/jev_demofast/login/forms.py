"""The sign-in forms the founder chooses from. Each page the map marked `sign_in` is reopened live: the map holds no
password fields (the page reader skips them) and no submit button that's disabled while the form is empty.

A sign-up form has a password too (K-12's "Your account, current step"), and its wording gives no rule that holds, so
Clef decides from the screenshot. Measured on K-12 (29 October, 3 runs each, the same score every run): the three
sign-in forms 0.90-0.97, the three sign-up steps 0.01. Without a check model that reads images, nothing is offered.
"""
import base64
import re

from ..cloudflare import sees_images

SIGNS_IN_CONFIDENT = 0.8
QUESTION = ("Is this a form for signing in to an account that already exists (not for creating a new account, and not "
            "a later step of making one)?")
TRUE, FALSE = "yes: it signs in to an existing account", "no: it creates an account or is a step of making one"
PASSWORD_LABELS_JS = """[...document.querySelectorAll('input[type=password]')].filter(e => e.checkVisibility())
  .map(e => (e.getAttribute('aria-label') || e.placeholder || 'Password').split('\\n')[0].trim())"""


def _first_line(text):
    return (text or "").strip().split("\n")[0].strip()


def _slug(label):
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "field"


def _pages(index):
    pages = []
    for route, entry in index.items():
        if not route.startswith("_") and entry.get("sign_in"):
            pages += [p for p in entry.get("examples") or [route] if p not in pages]
    return pages


def _signs_in(cf, page, fields, buttons, screenshot):
    state = {"url": page["url"], "fields": fields, "buttons": buttons,
             "visible_text": " ".join((page.get("text") or "").split())[:1500]}
    try:
        return cf.yes(QUESTION, state, true=TRUE, false=FALSE, model=cf.s.check_model,
                      images=[screenshot()]) >= SIGNS_IN_CONFIDENT
    except Exception:  # the model is down or answered nonsense: don't offer the form
        return False


def _title(lines, shared, controls):
    """The form's heading: the shortest line of two words or more that isn't on every sign-in page ("TutorQ K-12")
    or a control's label. K-12's sidebar sentence comes before the card's "Welcome back."."""
    candidates = [t for t in lines if t not in shared and t not in controls and len(t.split()) >= 2 and len(t) < 120]
    return min(candidates, key=len) if candidates else (lines[0] if lines else "Sign in")


def sign_in_forms(s, origin, index, cf, log=print):
    """[{"id", "title", "page", "fields": [{"name", "label", "secret"}]}] for each distinct sign-in form."""
    if cf is None or not sees_images(cf.s.check_model):
        log("login: can't tell sign-in forms apart without the check model")
        return []
    seen = []
    for path in _pages(index):
        try:
            s.browser.call("Page.navigate", url=origin + path)
            s.wait_loaded()
            page = s.observe()
        except Exception as err:
            log(f"login: couldn't open {path} ({type(err).__name__})")
            continue
        els = s.elements()
        plain = [_first_line(e["label"]) for e in els if "fill" in e["actions"] and _first_line(e["label"])]
        secret = s.browser.evaluate(PASSWORD_LABELS_JS) or []
        if not secret:
            continue
        shot = lambda: base64.b64decode(s.browser.call("Page.captureScreenshot", format="jpeg", quality=80)["data"])
        buttons = [_first_line(e["label"]) for e in els if e["role"] == "button"]
        if not _signs_in(cf, page, plain + secret, buttons, shot):
            continue
        lines = [t.strip() for t in (page.get("text") or "").split("\n") if t.strip()]
        # only a password input is secret: a secret is typed only where one has focus, never through act
        fields = [{"name": _slug(l), "label": l, "secret": False} for l in plain] + \
                 [{"name": _slug(l), "label": l, "secret": True} for l in secret]
        seen.append({"page": path, "lines": lines, "controls": {_first_line(e["label"]) for e in els},
                     "fields": fields})
    shared = set.intersection(*(set(f["lines"]) for f in seen)) if len(seen) > 1 else set()
    offered, keys = [], set()
    for f in seen:
        title = _title(f["lines"], shared, f["controls"])
        key = (title, tuple(x["label"] for x in f["fields"]))
        if key in keys:
            continue
        keys.add(key)
        offered.append({"id": f"f{len(offered) + 1}", "title": title, "page": f["page"], "fields": f["fields"]})
    if not offered:
        log("login: no sign-in form found")
    return offered
