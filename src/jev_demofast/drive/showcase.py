"""End a demo the way a founder would: show off the result. Two or three items the goal is about are scrolled into
view and outlined, and the narration names them."""
import re

from ..browser.elements import words
from .guards import blocked
from .plan import extract
from .session import StalePage

WHAT = "the items this page lists that the goal is about, each with its price"
# A filter panel's own close control, for panels that ignore Escape (Allbirds' "Collapse filters"). Closing, never
# applying or clearing: the filters are already applied.
CLOSE_PANEL = re.compile(r"^(close|collapse|hide)( the)? filters?\b|^close$", re.I)


def _on_screen(s, item):
    want = {w for w in words(item) if not w.isdigit()} or words(item)
    return next((e for e in s.elements() if e["role"] in ("link", "button") and want and want <= words(e["label"])),
                None)


def showcase(cf, s, rec, goal, log=print, count=3):
    """Highlight up to `count` items, then commit one "read" segment listing them. Returns the items."""
    for kind in ("keyDown", "keyUp"):  # close a filter panel or drawer still open over the results
        s.browser.call("Input.dispatchKeyEvent", type=kind, key="Escape", code="Escape", windowsVirtualKeyCode=27)
    s.wait_for_page()
    s.observe()
    closer = next((e for e in s.elements() if e["role"] in ("button", "link") and CLOSE_PANEL.search(e["label"] or "")
                   and not blocked(e["label"])), None)
    if closer is not None:  # the panel ignored Escape: close it with its own control, so the results are on screen
        try:
            s.act(closer, "click")
            s.wait_for_page()
        except StalePage:  # it closed on its own meanwhile
            pass
    page = s.observe()
    items = extract(cf, WHAT, page["url"], s.full_text())
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
