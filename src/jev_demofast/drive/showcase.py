"""End a demo the way a founder would: show off the result. Two or three items the goal is about are scrolled into
view and outlined, and the narration names them."""
import re

from ..browser.elements import words
from .guards import blocked
from .plan import extract
from .session import StalePage

WHAT = "the items this page lists that the goal is about, each with its price"
# A filter panel's own close control, for panels that ignore Escape. Closing, never applying or clearing: the filters
# are already applied. Allbirds' is one toggle labelled "Filter Collapse filters (20 products)" whether open or not.
CLOSE_PANEL = re.compile(r"\b(close|collapse|hide)( the)? filters?\b|^close$", re.I)
OPTION = ("checkbox", "radio", "switch")  # filter values on screen: the panel is open


def _on_screen(s, item):
    want = {w for w in words(item) if not w.isdigit()} or words(item)
    return next((e for e in s.elements() if e["role"] in ("link", "button") and want and want <= words(e["label"])),
                None)


def reveal_results(s):
    """Close a filter panel or drawer still open over the results: Escape, else the panel's own close control.
    Before the results are checked, and again before they're shown (Allbirds' panel hid every result from both)."""
    for kind in ("keyDown", "keyUp"):  # close a filter panel or drawer still open over the results
        s.browser.call("Input.dispatchKeyEvent", type=kind, key="Escape", code="Escape", windowsVirtualKeyCode=27)
    s.wait_for_page()
    s.observe()
    open_panel = any(e["role"] in OPTION for e in s.elements())  # a toggle clicked when closed would open it
    closer = next((e for e in s.elements() if e["role"] in ("button", "link") and CLOSE_PANEL.search(e["label"] or "")
                   and not blocked(e["label"])), None) if open_panel else None
    if closer is not None:  # the panel ignored Escape: close it with its own control, so the results are on screen
        try:
            s.act(closer, "click")
            s.wait_for_page()
        except StalePage:  # it closed on its own meanwhile
            pass


def showcase(cf, s, rec, goal, log=print, count=3):
    """Highlight up to `count` items, then commit one "read" segment listing them. Returns the items."""
    reveal_results(s)
    page = s.observe()
    items = extract(cf, WHAT, page["url"], s.full_text())
    if not items:  # nothing listed to show: no empty "read" moment for the narrator to fill
        log("  showcase: no items on this page")
        return []
    shown = []
    for item in items[:count]:
        e = _on_screen(s, item)
        if e is not None:
            rec.snap(1.5, node=e["node"])
            shown.append(item)
    # The narrator names only what the viewer saw outlined (it once named a shoe further down the page).
    rec.commit({"do": "read", "target": "showcase", "items": shown or items[:count]}, s.observe())
    log(f"  showcase: {items[:count]}")
    return items
