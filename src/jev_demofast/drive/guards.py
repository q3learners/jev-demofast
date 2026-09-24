"""Safety rules every run follows, whichever driver decides the steps."""
import re
from urllib.parse import urlparse

from ..config import secret

# Never clicked unless the step itself explicitly names such an action.
BLOCKED = re.compile(r"sign ?up|register|create (an )?account|google|apple|microsoft|github login|facebook|"
                     r"continue with|delete|remove|log ?out|sign ?out", re.I)
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
# "Create a demo of how to X" / "Show me how to X" asks for X: the framing is about the video, not the task.
DEMO_FRAMING = re.compile(r"^\s*(?:(?:create|make|record|build|generate)\s+(?:a|an|the)?\s*(?:product\s+)?"
                          r"(?:demo|video|walkthrough)(?:\s+video)?(?:\s*[:\-]\s*|\s+(?:of|showing|on|for)\s+)"
                          r"(?:how\s+to\s+)?|show\s+(?:me\s+|us\s+)?how\s+to\s+)", re.I)
# In a dry run, the tool stops before any of these: submits and toggles change data, links only navigate.
CHANGES = re.compile(r"\b(save|submit|send|invite|update|confirm|apply|pay|subscribe|purchase|buy|unsubscribe|"
                     r"unwatch|watch|ignore|turn (on|off)|disable|enable|add|create|delete|remove)\b", re.I)
TOGGLES = {"checkbox", "switch", "radio", "menuitemcheckbox", "menuitemradio"}


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


def would_change(e):
    """True if clicking this element would change data (a submit-like button or a toggle), not just navigate."""
    return e["role"] in TOGGLES or (e["role"] != "link" and bool(CHANGES.search(e["label"] or "")))
