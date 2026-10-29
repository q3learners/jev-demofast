"""Safety rules every run follows, whichever driver decides the steps."""
import re
from urllib.parse import unquote, urlparse

from ..config import secret

# Never clicked unless the step itself explicitly names such an action.
BLOCKED = re.compile(r"sign ?up|register|create (an )?account|google|apple|microsoft|github login|facebook|"
                     r"continue with|delete|remove|log ?out|sign ?out", re.I)
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
# A placeholder named like a password or other secret ({{PASSWORD}}, {{MYPASSWD}}, {{API_TOKEN}}, {{ADMIN_PIN}})
# goes only into the password field; any other ({{EMAIL}}) is typed into the visible field a model picked. When in
# doubt it counts as a secret: a secret typed into a visible field could show on screen or be sent somewhere else.
PASSWORD_NAME = re.compile(r"pass|pwd|secret|token|credential|(?:^|_)(?:pw|pin|otp|key|code)(?:_|$)", re.I)
# "Create a demo of how to X" / "Show me how to X" asks for X: the framing is about the video, not the task.
DEMO_FRAMING = re.compile(r"^\s*(?:(?:create|make|record|build|generate)\s+(?:a|an|the)?\s*(?:product\s+)?"
                          r"(?:demo|video|walkthrough)(?:\s+video)?(?:\s*[:\-]\s*|\s+(?:of|showing|on|for)\s+)"
                          r"(?:how\s+to\s+)?|show\s+(?:me\s+|us\s+)?how\s+to\s+)", re.I)
# In a dry run, the tool stops before any of these: submits and toggles change data, links only navigate.
CHANGES = re.compile(r"\b(save|submit|send|invite|update|confirm|apply|pay|subscribe|purchase|buy|unsubscribe|"
                     r"unwatch|watch|ignore|turn (on|off)|disable|enable|add|create|delete|remove)\b", re.I)
TOGGLES = {"checkbox", "switch", "radio", "menuitemcheckbox", "menuitemradio"}


# A logged-in run may act like a user (add a student, ask the tutor) but never pays, deletes, logs out, changes the
# account's sign-in details or reaches someone outside the account. Unlike BLOCKED, a brief can't unlock these.
LOGGED_IN_HAZARDS = re.compile(r"\b(pay|payment|purchase|buy|checkout|check out|subscribe|upgrade|billing|card|"
                               r"verify you are the parent|delete|remove|destroy|deactivate|unsubscribe|cancel subscription|close account|log ?out|"
                               r"sign ?out|change (your )?(email|password)|reset (your )?password|invite|share|send to)\b",
                               re.I)
# A page about money (K-12's card check is a "Continue" under "Verify you are the parent"): moving forward is refused.
# A step list naming the card check as next or done isn't that page: K-12 says "Verify you are the parent, next" on
# the page where kids are added.
MONEY_PAGE = re.compile(r"card number|\bcvc\b|\bcvv\b|payment details|billing address|"
                        r"verify you are the parent(?!,? (next|done)\b)", re.I)
FORWARD = re.compile(r"\b(continue|next|submit|confirm|done|finish|save|verify|start)\b", re.I)


EMAIL_ADDRESS = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def may_open(label, address):
    """A logged-in run opens a page by its address only if neither its label nor its path and query is a hazard
    ("/account/logout", "/account/deleteKid", "?action=destroy"): opening by address never passes Session.act."""
    u = urlparse(unquote(unquote(address or "")))  # "/account/%64elete", "?next=%252Fbilling"
    words = re.sub(r"[^a-zA-Z]+", " ", re.sub(r"([a-z])([A-Z])", r"\1 \2", f"{u.path} {u.query} {u.fragment}"))
    return not hazard(label or "") and not hazard(words)


class HazardStop(Exception):
    """A logged-in run reached a step it never takes (the message is the refused label): the demo stops there."""


def hazard(label, context=""):
    """True if a logged-in run must not take this step: a hazard label, or moving forward on a money page."""
    return bool(LOGGED_IN_HAZARDS.search(label or "")) or (
        bool(MONEY_PAGE.search(context or "")) and bool(FORWARD.search(label or "")))


class DryRunStop(Exception):
    """Raised at the first data-changing action of a dry run, after it is recorded as "would click"."""


def blocked(label, unless=""):
    """True if the label looks destructive or off-site, unless the step asked for exactly that."""
    return bool(BLOCKED.search(label or "")) and not BLOCKED.search(unless or "")


def on_site(url, host):
    h = urlparse(url).hostname or ""
    return h == host or h.endswith("." + host)


def has_secret(value):
    return bool(PLACEHOLDER.search(value or ""))


def password_secret(text):
    """The {{NAME}} in `text` to type into the password field, or None. Password inputs are never observed, so no
    model can pick them; only a placeholder named like a password is sent there."""
    return next((name for name in PLACEHOLDER.findall(text or "") if PASSWORD_NAME.search(name)), None)


def fill_text(value):
    """The text to type: {{NAME}} placeholders are swapped for DEMO_NAME at typing time only."""
    def swap(m):
        v = secret(m.group(1))
        if v is None:
            raise SystemExit(f"{m.group(0)} is in the prompt but DEMO_{m.group(1)} is not set")
        return v
    return PLACEHOLDER.sub(swap, value or "")


def task_goal(prompt):
    return DEMO_FRAMING.sub("", prompt, count=1).strip() or prompt


def stop_if_dry_run(rec, e, s):
    """In a dry run, stop before the first click that would change data, recording it as "would click"."""
    if getattr(rec, "dry_run", False) and would_change(e):
        rec.would_click(e["node"], e["label"], s.observe())
        raise DryRunStop(e["label"][:60])


def would_change(e):
    """True if clicking this element would change data (a submit-like button or a toggle), not just navigate."""
    return e["role"] in TOGGLES or (e["role"] != "link" and bool(CHANGES.search(e["label"] or "")))
