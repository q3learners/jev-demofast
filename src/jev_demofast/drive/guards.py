"""Safety rules every run follows, whichever driver decides the steps."""
import re
from urllib.parse import urlparse

from ..config import secret

# Never clicked unless the step itself explicitly names such an action.
BLOCKED = re.compile(r"sign ?up|register|create (an )?account|google|apple|microsoft|github login|facebook|"
                     r"continue with|delete|remove|log ?out|sign ?out", re.I)
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


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
