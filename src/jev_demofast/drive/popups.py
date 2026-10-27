"""Pages the tool can't use as they are: a bot block, and a pop-up covering the page.

A block is reported, never worked around. A pop-up is cleared the way a person would: Escape, else its close or
"no thanks" control. Never by typing into it or signing up. Measured on 4 shops: Everlane's pop-up (in a third-party
frame) hid the whole page from the tool and closed on Escape; Allbirds' didn't, but its close button was visible.
"""
import re

from ..browser.elements import describe
from .guards import blocked, on_site, would_change

BOT_CHECK = re.compile(r"access denied|captcha|verify you are (a )?human|are you a robot|press (&|and) hold|"
                       r"just a moment|unusual (traffic|activity)|request blocked|pardon our interruption", re.I)
# Controls on a marketing pop-up that sign the viewer up: never the way to close it.
SIGN_UP = re.compile(r"sign ?up|subscribe|continue|submit|join|get .*off|unlock|claim", re.I)
COVERED_JS = """(() => {
  const cx = innerWidth / 2, cy = innerHeight / 2;
  const dialog = [...document.querySelectorAll('[role=dialog],dialog[open],[aria-modal=true]')].some(d => {
    const r = d.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && d.checkVisibility({checkOpacity: true, checkVisibilityCSS: true}) &&
      r.left <= cx && r.right >= cx && r.top <= cy && r.bottom >= cy;
  });
  const hidden_roots = [...document.body.children].filter(e => e.getAttribute('aria-hidden') === 'true' || e.inert).length;
  return {dialog, hidden_roots};
})()"""


def bot_check(page):
    """The phrase that marks this page as a bot block, or None."""
    m = BOT_CHECK.search(f"{page.get('title', '')}\n{(page.get('text') or '')[:3000]}")
    return m.group(0) if m else None


def covered(s):
    """A pop-up covers the page: a visible dialog over the middle of the viewport, or the page hidden from assistive
    technology (aria-hidden or inert) with almost nothing left to act on."""
    try:
        probe = s.browser.evaluate(COVERED_JS) or {}
    except Exception:  # mid-navigation: read again on the next screen
        return False
    return bool(probe.get("dialog")) or (probe.get("hidden_roots", 0) > 3 and len(s.elements()) < 5)


def _press_escape(s):
    for kind in ("keyDown", "keyUp"):
        s.browser.call("Input.dispatchKeyEvent", type=kind, key="Escape", code="Escape", windowsVirtualKeyCode=27)


def clear_popups(cf, s, log=print):
    """Clear a pop-up covering the page. Returns "escape", "close: <label>", or None (nothing covered, or it couldn't
    be cleared without signing up). Never fills a field."""
    if not covered(s):
        return None
    _press_escape(s)
    s.wait_for_page()
    s.observe()
    if not covered(s):
        log("pop-up: closed with Escape")
        return "escape"
    href = getattr(s, "href", lambda node: None)
    closers = [e for e in s.elements() if "click" in e["actions"] and e["role"] in ("button", "link")
               and not blocked(e["label"]) and not SIGN_UP.search(e["label"] or "") and not would_change(e)
               and (not href(e["node"]) or on_site(href(e["node"]), s.host if hasattr(s, "host") else ""))]
    if not closers or cf is None:
        log("pop-up: still covering the page; no safe control to close it")
        return None
    key, conf = cf.choose("A pop-up covers the page. Which control closes it without signing up or giving any "
                          "details? 'none' if none.", {str(e["node"]): describe(e) for e in closers[:20]},
                          {"url": s.page["url"], "text": " ".join((s.page.get("text") or "").split())[:500]},
                          allow_none=True)
    e = next((c for c in closers if str(c["node"]) == key), None)
    if e is None or conf < 0.5:
        log(f"pop-up: no control clearly closes it ({conf:.2f}); left as is")
        return None
    before = s.page["url"]
    s.act(e, "click")
    s.wait_for_page()
    s.observe()
    if s.page["url"] != before:  # it navigated: that wasn't a close button; go back to where the demo was
        s.browser.call("Page.navigate", url=before)
        getattr(s, "wait_loaded", lambda: None)()
        s.observe()
        log(f"pop-up: {e['label'][:30]!r} navigated away; went back")
        return None
    if covered(s):
        log(f"pop-up: clicking {e['label'][:30]!r} didn't close it")
        return None
    log(f"pop-up: closed with {e['label'][:30]!r} ({conf:.2f})")
    return f"close: {e['label']}"
