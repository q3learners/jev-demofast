"""End a demo the way a founder would: show off the result. Two or three items the goal is about are scrolled into
view and outlined, and the narration names them."""
from ..browser.elements import words
from .plan import extract

WHAT = "the items this page lists that the goal is about, each with its price"


def _on_screen(s, item):
    want = {w for w in words(item) if not w.isdigit()} or words(item)
    return next((e for e in s.elements() if e["role"] in ("link", "button") and want and want <= words(e["label"])),
                None)


def showcase(cf, s, rec, goal, log=print, count=3):
    """Highlight up to `count` items, then commit one "read" segment listing them. Returns the items."""
    for kind in ("keyDown", "keyUp"):  # close a filter panel or drawer still open over the results
        s.browser.call("Input.dispatchKeyEvent", type=kind, key="Escape", code="Escape", windowsVirtualKeyCode=27)
    s.wait_for_page()
    page = s.observe()
    items = extract(cf, WHAT, page["url"], s.full_text())
    for item in items[:count]:
        e = _on_screen(s, item)
        if e is not None:
            rec.snap(1.5, node=e["node"])
    rec.commit({"do": "read", "target": "showcase", "items": items}, s.observe())
    log(f"  showcase: {items[:count]}")
    return items
