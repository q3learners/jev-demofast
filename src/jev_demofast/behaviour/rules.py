"""What mapping may press, and what a press did.

Mapping adds; it never changes what's there (the founder: "it's a demo account, it can create data"; the design: add,
never edit or toggle). So: never a toggle, never a never-press or hazard label, and a change label ("Save", "Update")
only where mapping itself filled the fields. Session.act's checks (the money judge, the own-email rule) apply on top."""
import re

from ..drive.guards import CHANGES, TOGGLES, blocked, hazard

ADDS = re.compile(r"\b(add|create|new)\b", re.I)


def may_press(e, filled_here):
    label = (e.get("label") or "").strip().split("\n")[0]
    if blocked(label) or hazard(label) or e.get("role") in TOGGLES:
        return False
    return filled_here or not CHANGES.search(label) or bool(ADDS.search(label))


def outcome(before_key, before_text, after_key, after_kind, after_text, typed):
    """"dialog <key>", "→ <key>", "added '<value>'" (a typed value that has appeared) or "no change"."""
    if after_kind == "dialog":
        return f"dialog {after_key}"
    if after_key != before_key:
        return f"→ {after_key}"
    new = next((v for v in typed if v and v in (after_text or "") and v not in (before_text or "")), None)
    return f"added '{new}'" if new else "no change"
