"""Observed page elements and cheap text matching.

`observed`, `describe`, `is_field`, `fold`, `words`, `month_day`, `relevance` and `shortlist` are adapted from
laya-ultrafast's laya.py (MIT, Copyright (c) 2026 Browser Use; see NOTICE).
"""
import re
import unicodedata

FIELD_ROLES = {"combobox", "textbox", "searchbox", "spinbutton", "checkbox", "radio", "switch"}
TOGGLES = {"checkbox", "radio", "switch"}
STOP_WORDS = {"the", "and", "for", "with", "from", "find", "open", "stop", "when", "visib", "page", "are", "this"}
MONTH_DAY = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)(?:uary|ruary|ch|il|e|y|ust|t|tember|ober|ember)?"
    r"\s+(\d{1,2})\b|\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
)


def fold(text):
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def words(text):
    """Meaningful word stems (first 5 letters), for cheap label matching."""
    return {w[:5] for w in fold(text).split() if (len(w) > 2 or w.isdigit()) and w[:5] not in STOP_WORDS}


def month_day(text):
    m = MONTH_DAY.search(fold(text))
    return (m[1] or m[4], int(m[2] or m[3])) if m else None


def is_field(e):
    counter = e["role"] == "button" and re.search(r"\d", e["label"]) and not month_day(e["label"])
    return e["role"] in FIELD_ROLES or bool(e["options"]) or bool(counter)


def observed(page):
    """One entry per DOM node the page offers an action on (click / fill / select)."""
    elements, nodes = [], {}
    for action in page["actions"]:
        if action["kind"] not in {"click", "fill", "select"}:
            continue
        e = nodes.get(action["node"])
        if e is None:
            e = nodes[action["node"]] = {
                "node": action["node"],
                "role": action.get("role", ""),
                "label": action["label"].split(" → ")[0].strip(),
                "value": action.get("current_value", action.get("value", "")) or "",
                "checked": action.get("checked"),
                "expanded": action.get("expanded"),
                "hint": action.get("hint", ""),
                "actions": {},
                "options": [],
            }
            elements.append(e)
        if action["kind"] == "select":
            e["options"].append(action)
        else:
            e["actions"].setdefault(action["kind"], action)
    for e in elements:
        if e["role"] in TOGGLES:
            e["current"] = "checked" if e["checked"] in {"true", True} else "unchecked"
        elif e["value"] or (is_field(e) and e["role"] != "button"):
            e["current"] = e["value"]
        else:
            e["current"] = e["label"]
    return elements


def describe(e):
    """One line a decision model can read: role, label, hint, current value, options."""
    text = f"{e['role']} {e['label'][:70]}"
    if e.get("hint"):
        text += f" ({e['hint'][:50]})"
    if is_field(e) and e["current"] != e["label"]:
        text += f" = {e['current'][:40] or '(empty)'}"
    if e["options"]:
        text += " (options: " + ", ".join(o["label"].split(" → ")[-1] for o in e["options"][:6]) + ")"
    return text


def relevance(e, text):
    """How many of `text`'s word stems the element shares (a date match counts extra)."""
    s = len(words(f"{e['label']} {e.get('hint', '')} {e['current']}") & words(text))
    date = month_day(text)
    return s + 5 if date and month_day(e["label"]) == date else s


def shortlist(candidates, text, limit):
    """The `limit` most relevant candidates, kept in document order."""
    scores = {e["node"]: relevance(e, text) for e in candidates}
    kept = {e["node"] for e in sorted(candidates, key=lambda e: -scores[e["node"]])[:limit]}
    return [e for e in candidates if e["node"] in kept]
