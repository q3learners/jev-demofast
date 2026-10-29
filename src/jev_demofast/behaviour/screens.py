"""Reading the screen the session is on, for the blueprint: its kind (page, dialog, wizard step), title, key, controls
and fields; and the app's sections, which are what stays on screen as you move between them.

A dialog is found by its box, not by checkVisibility: Flutter's semantics tree is drawn with opacity 0, so a visible
K-12 dialog reads as invisible. After K-12's "Continue" the page text was only "Skip Add" (29 October, live)."""
import json

from ..drive.guards import blocked
from .model import screen_key

DIALOG_JS = r"""(() => {
  const d = [...document.querySelectorAll('[role=dialog],[role=alertdialog],dialog[open],[aria-modal=true]')]
    .find(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
  if (!d) return null;
  return (d.getAttribute('aria-label') || d.innerText || '').trim().split('\n')[0].trim() || 'dialog';
})()"""
# Which of the given elements sit inside the open dialog. In a real page the element list still holds the page behind
# a dialog (live, 29 October: the background "Continue" was chosen 40 times instead of the dialog's "Add").
DIALOG_NODES_MARK = "/*dialog-nodes*/"
_DIALOG_NODES_JS = DIALOG_NODES_MARK + r"""(() => {
  const d = [...document.querySelectorAll('[role=dialog],[role=alertdialog],dialog[open],[aria-modal=true]')]
    .find(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
  if (!d) return null;
  return %s.filter(id => { const e = window.__jevFast?.nodes.get(id); return !!e && d.contains(e); });
})()"""
NAV_ROLES = {"tab", "link", "button"}
TEXTS = 10


def _first_line(label):
    return (label or "").strip().split("\n")[0].strip()


def in_dialog(s, els):
    """The elements inside the open dialog; all of them when there's no dialog or the page can't say."""
    inside = s.browser.evaluate(_DIALOG_NODES_JS % json.dumps([e["node"] for e in els]))
    return els if inside is None else [e for e in els if e["node"] in set(inside)]


def read_screen(s, wizard=False):
    """(key, screen) for the screen the session is on. screen: {kind, title, url, texts, fields, controls}."""
    page = s.observe()
    dialog = s.browser.evaluate(DIALOG_JS)
    els = in_dialog(s, s.elements()) if dialog else s.elements()
    controls = list(dict.fromkeys(_first_line(e["label"]) for e in els
                                  if "click" in e["actions"] and _first_line(e["label"])))
    fields = [_first_line(e["label"]) for e in els if "fill" in e["actions"] and _first_line(e["label"])]
    labels = set(controls) | set(fields)
    texts = list(dict.fromkeys(t.strip() for t in (page.get("text") or "").split("\n")
                               if 2 < len(t.strip()) < 120 and t.strip() not in labels))[:TEXTS]
    kind = "dialog" if dialog else "wizard-step" if wizard else "page"
    title = dialog or (texts[0] if texts else "")
    return screen_key(page["url"], title, kind), {"kind": kind, "title": title, "url": page["url"], "texts": texts,
                                                  "fields": fields, "controls": controls}


def nav_labels(s):
    """The labels that could be the app's navigation: tabs, links and buttons that aren't fields or never-press."""
    return list(dict.fromkeys(_first_line(e["label"]) for e in s.elements()
                              if e["role"] in NAV_ROLES and "click" in e["actions"] and "fill" not in e["actions"]
                              and _first_line(e["label"]) and not blocked(e["label"])))


def sections(first, second):
    """The labels on both screens, in the first's order: the navigation that stays."""
    return [label for label in first if label in second]
