"""Signing in with the founder's answer. Plain fields are filled by their label through the session; a secret is typed
straight into the focused password input with Input.insertText, so it never passes through observation, `act`, the
decisions log or a frame. Nothing returned or logged contains a value."""
import json
import re
from urllib.parse import urlparse

from ..drive.guards import hazard
from ..explore.buttons import SIGN_IN_FORM_JS
from .ask import question

SUBMIT = re.compile(r"\b(sign ?in|log ?in|continue|submit|next|verify)\b", re.I)
ERROR = re.compile(r"incorrect|invalid|wrong|doesn't match|does not match|try again|not found|no account", re.I)
CODE_PAGE = re.compile(r"\bcode\b|verif", re.I)
FOCUS_SECRET_JS_START = "(label => {"
FOCUSED_IS_PASSWORD_JS = "document.activeElement?.tagName === 'INPUT' && document.activeElement.type === 'password'"


def _focus_secret_js(label):
    """Focus the visible password input labelled `label` (else the first visible one); its centre, or null."""
    return FOCUS_SECRET_JS_START + """
  const all = [...document.querySelectorAll('input[type=password]')].filter(e => e.checkVisibility());
  const name = e => (e.getAttribute('aria-label') || e.placeholder || '').split('\\n')[0].trim();
  const e = all.find(e => name(e) === label) || (all.length === 1 ? all[0] : null);
  if (!e) return null;
  e.focus(); const r = e.getBoundingClientRect();
  return {x: r.x + r.width / 2, y: r.y + r.height / 2};
})(""" + json.dumps(label) + ")"


def _first_line(text):
    return (text or "").strip().split("\n")[0].strip()


def _hide(text, values):
    for v in values.values():
        if v:
            text = text.replace(v, "…")
    return text


def _type_secret(s, label, value):
    at = s.browser.evaluate(_focus_secret_js(label))
    if not at:
        return False
    if isinstance(at, dict):  # a real click focuses it for frameworks that ignore focus() (Flutter)
        for kind in ("mousePressed", "mouseReleased"):
            s.browser.call("Input.dispatchMouseEvent", type=kind, x=at["x"], y=at["y"], button="left", clickCount=1)
    if s.browser.evaluate(FOCUSED_IS_PASSWORD_JS) is not True:  # never type a secret into whatever else has focus
        return False
    s.browser.call("Input.insertText", text=value)
    return True


def _fill(s, fields, values):
    for field in fields:
        e = next((e for e in s.elements() if "fill" in e["actions"] and _first_line(e["label"]) == field["label"]), None)
        if field["secret"] and e is None:  # a password input: never observed, typed only where it has focus
            if not _type_secret(s, field["label"], values[field["name"]]):
                return f"no field for {field['label']}"
            continue
        if e is None:
            return f"no field for {field['label']}"
        s.act(e, "fill", text=values[field["name"]])
    return None


def _submit(s):
    s.observe()  # a submit button may only be enabled once the fields are filled (K-12's "Sign in")
    buttons = [e for e in s.elements() if e["role"] == "button" and "click" in e["actions"]
               and SUBMIT.search(_first_line(e["label"]))]
    if not buttons:
        return False
    s.act(buttons[-1], "click")
    s.wait_for_page()
    s.wait_loaded()
    s.observe()
    return True


def _error_line(page):
    return next((t.strip() for t in (page.get("text") or "").split("\n") if ERROR.search(t)), "")


def _code_field(s):
    fields = [e for e in s.elements() if "fill" in e["actions"]]
    if len(fields) == 1 and CODE_PAGE.search(s.page.get("text") or "") and s.browser.evaluate(SIGN_IN_FORM_JS) is not True:
        return fields[0]
    return None


def sign_in(s, origin, form, values, ask=None, log=print):
    """Sign in through `form` with `values`. Returns "signed in", "failed: <why>" or "stuck: <page>"."""
    for attempt in (1, 2):
        s.browser.call("Page.navigate", url=origin + form["page"])
        s.wait_loaded()
        s.observe()
        problem = _fill(s, form["fields"], values) or (None if _submit(s) else "no sign-in button")
        if problem:
            return f"failed: {problem}"
        if s.browser.evaluate(SIGN_IN_FORM_JS) is not True:
            break
        why = _hide(_error_line(s.page) or "the sign-in form is still showing", values)
        if attempt == 2 or ask is None:
            log(f"login: couldn't sign in ({why})")
            return f"failed: {why}"
        answer = ask(question([form], "That didn't work. Try the demo account again?", retry=why, qid="q2"))
        if answer is None:
            return f"failed: {why}"
        values.clear()  # the caller's answer is corrected in place: the recording signs in with what worked
        values.update(answer["values"])
    code = _code_field(s)
    if code is not None:
        label = _first_line(code["label"]) or "Code"
        step = {"id": "f1", "title": _first_line(s.page.get("text")), "page": form["page"],
                "fields": [{"name": "code", "label": label, "secret": False}]}
        answer = ask(question([step], "The site sent a code to the demo account. Enter it:", qid="q3")) if ask else None
        if answer is None:
            return "failed: a code was asked for"
        s.act(code, "fill", text=answer["values"]["code"])
        if not _submit(s) or _code_field(s) is not None:
            return "failed: the code wasn't accepted"
    page = s.observe()
    ways_on = [e for e in s.elements() if "click" in e["actions"] and e["role"] in ("button", "link")]
    if ways_on and all(hazard(_first_line(e["label"]), context=page.get("text") or "") for e in ways_on):
        where = _hide(urlparse(page["url"]).path or "/", values)  # never its query: it may carry a token or the email
        log(f"login: signed in, but {where} only offers steps a demo never takes")
        return f"stuck: {where}"
    log("login: signed in")
    return "signed in"
