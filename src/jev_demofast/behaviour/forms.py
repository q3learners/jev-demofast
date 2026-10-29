"""Forms, dialogs and wizards inside the walk, done the way a person would: made-up values typed, the button that
moves the form forward pressed, a dialog answered the way that carries on (K-12's "Add Maya first?" → Add), and each
next step with fields walked as a wizard step. Every press and fill goes through Session.act.

A one-time account step (K-12's setup) is walked up to, never through, the click that would finish it: the founder's
demo may need to show it, and finishing it uses it up. Clef judges that click from the screen; unsure means don't."""
import base64
import re

from urllib.parse import urlparse

from ..drive.guards import HazardStop, on_site
from ..drive.session import StalePage
from .model import add_action, add_screen
from .rules import may_press, outcome
from .screens import in_dialog, read_screen

MAKE_VALUES = """You are mapping a web app with a demo account. Make up believable values for the form's fields, the way
a person trying the product would (a child's first name, an age, a short title). Never reuse a name in "names_used".
Leave out any field you can't fill sensibly. Reply with JSON only: {"values": {"<field label as given>": "<value>"}}."""
FORWARD_Q = "Which button moves this form forward (adds, saves or goes to the next step)?"
DIALOG_Q = "Which button in this dialog carries on with what was being done?"
FINISHES = ("Would pressing '{label}' finish a setup the account goes through only once (an onboarding step it can't "
            "come back to), leaving it for good?")
FINISH_TRUE, FINISH_FALSE = ("yes: it finishes or leaves a one-time setup step",
                             "no: it adds or moves within something that can be done again")
ONE_TIME = 0.5  # at or above: not pressed; a model error counts as finishing
EMAIL = re.compile(r"e-?mail", re.I)
# What dismisses a dialog without committing to anything. A dialog mapping didn't open with an add ("Archive Ava?
# Yes / Cancel") is only ever dismissed: confirming would change something that was already there.
DISMISS = re.compile(r"^\s*(got it|close|dismiss|cancel|not now|no thanks|skip|later|back|maybe later)\s*$", re.I)
OWN_EMAIL = "(the account's email)"  # what the map records for it: the email itself never reaches a file or a prompt


def _label(e):
    return (e.get("label") or "").strip().split("\n")[0]


def _values(cf, fields, screen, m, own_email, log):
    """{label: value} for the fields; {} when the model can't make them (nothing is then submitted)."""
    used = sorted({v for a in m["actions"] for v in (a.get("values") or {}).values()} - {OWN_EMAIL})
    try:
        made = cf.chat_json(cf.s.read_model, MAKE_VALUES, {"fields": fields, "screen": screen["texts"][:8],
                                                           "names_used": used[:40]}).get("values") or {}
    except Exception as err:
        log(f"blueprint: no values for {screen['title']!r} ({type(err).__name__}); not submitted")
        return {}
    if not isinstance(made, dict):  # the model answered with the wrong shape: nothing is typed
        return {}
    values = {f: str(v) for f, v in made.items() if f in fields and v}
    for f in fields:  # an email is only ever the account's own
        if EMAIL.search(f):
            values[f] = own_email or ""
    return {f: v for f, v in values.items() if v}


def _finishes(s, cf, label):
    try:
        shot = base64.b64decode(s.browser.call("Page.captureScreenshot", format="jpeg", quality=80)["data"])
        return cf.yes(FINISHES.format(label=label), {"url": s.page.get("url"), "button": label,
                                                     "visible_text": " ".join((s.page.get("text") or "").split())[
                                                         :1500]},
                      true=FINISH_TRUE, false=FINISH_FALSE, model=cf.s.check_model, images=[shot]) >= ONE_TIME
    except Exception:
        return True


def _escape(s):
    for kind in ("keyDown", "keyUp"):
        s.browser.call("Input.dispatchKeyEvent", type=kind, key="Escape", code="Escape", windowsVirtualKeyCode=27)


def _dialog(s, cf, m, key, now, chain, from_our_form, dismiss_only=False):
    """The dialog's button to press, or None (closed, nothing pressed). A change label ("Save changes") is allowed
    only when the dialog came from a form this walk filled."""
    buttons = [e for e in in_dialog(s, s.elements()) if "click" in e["actions"]]
    allowed = [e for e in buttons if may_press(e, filled_here=from_our_form)
               and (not dismiss_only or DISMISS.search(_label(e)))]
    pick = None
    if allowed:
        try:
            node, _ = cf.choose(DIALOG_Q, {str(e["node"]): _label(e) for e in allowed},
                                {"dialog": key, "text": s.page.get("text", "")[:500]}, allow_none=True)
            pick = next((e for e in allowed if str(e["node"]) == node), None)
        except Exception:
            pick = None
    if pick is None:
        for e in buttons:
            chain.append(add_action(m, key, _label(e), "click", "refused: no safe way", now))
        _escape(s)
        return None
    for e in buttons:
        if e is not pick:
            chain.append(add_action(m, key, _label(e), "click", "not pressed", now))
    return pick


def handle(s, cf, m, key, screen, account, budget, log, now, section=None, dismiss_only=False):
    """Walk the form, dialog or wizard on screen. Returns the indexes of the actions it recorded, also kept as one
    chain in m["chains"] (the jobs are made from chains)."""
    chain, filled, typed, steps = [], set(), [], 0
    state = m["account"].get("state") or account
    nav = set(m["account"].get("sections") or [])
    try:
        while steps < budget.steps_per_section:
            steps += 1
            before = s.page.get("text", "")
            if screen["kind"] == "dialog":
                e = _dialog(s, cf, m, key, now, chain, from_our_form=bool(filled),
                            dismiss_only=dismiss_only and not filled)
                if e is None:
                    return chain
            else:
                fields = [e for e in s.elements() if "fill" in e["actions"]]
                if fields and key not in filled:
                    values = _values(cf, [_label(e) for e in fields], screen, m, s.own_email, log)
                    if not values:
                        return chain
                    for f in fields:
                        if _label(f) in values:
                            v = values[_label(f)]
                            try:
                                s.act(f, "fill", text=v)
                            except (HazardStop, StalePage):  # a value the rules refuse: this form isn't sent
                                chain.append(add_action(m, key, _label(f), "fill", f"refused: {_label(f)}", now))
                                return chain
                            if v != s.own_email:  # an outcome ("added '…'") never names the account's email
                                typed.append(v)
                            chain.append(add_action(m, key, _label(f), "fill", "no change", now,
                                                    values={_label(f): OWN_EMAIL if v == s.own_email else v}))
                    filled.add(key)
                buttons = [e for e in s.elements() if "click" in e["actions"] and _label(e) not in nav
                           and may_press(e, filled_here=key in filled)]
                if not buttons:
                    return chain
                try:
                    node, _ = cf.choose(FORWARD_Q, {str(b["node"]): _label(b) for b in buttons},
                                        {"screen": key, "text": before[:500]})
                except Exception:
                    return chain
                e = next((b for b in buttons if str(b["node"]) == node), None)
                if e is None:
                    return chain
            # anything but a set-up account ("unknown" too) gets the one-time check, on a dialog's button as well
            if account != "set up" and _finishes(s, cf, _label(e)):
                chain.append(add_action(m, key, _label(e), "click", "seen, not finished", now))
                if screen["kind"] == "dialog":
                    _escape(s)
                return chain
            try:
                s.act(e, "click")
            except HazardStop:
                chain.append(add_action(m, key, _label(e), "click", f"refused: {_label(e)}", now))
                return chain
            except StalePage:
                return chain
            s.wait_for_page()
            landed = s.observe().get("url") or ""
            if not on_site(landed, s.host):  # a hand-off to another site (a partner's form) is never filled
                chain.append(add_action(m, key, _label(e), "click",
                                        f"refused: leaves the app → {urlparse(landed).hostname or landed}", now))
                return chain
            after_key, after = read_screen(s)
            if after["kind"] != "dialog" and after["fields"]:
                after_key, after = read_screen(s, wizard=True)
            chain.append(add_action(m, key, _label(e), "click",
                                    outcome(key, before, after_key, after["kind"], s.page.get("text"), typed), now))
            add_screen(m, after_key, {**after, "section": section}, now)
            if after["kind"] != "dialog" and not after["fields"]:
                return chain
            key, screen = after_key, after
        return chain
    finally:
        if chain:  # the account's state as it was when this ran: a job keeps it (one-time or repeatable)
            m["chains"].append({"steps": chain, "state": state})
