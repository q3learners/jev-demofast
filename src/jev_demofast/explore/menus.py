"""Find a site's menus the way a visitor does: hover each control in the top navigation, or click it if it's a menu
button. A link is never clicked here (that navigates away). Menus didn't announce themselves (aria-expanded) on any
of the four shops in the recon, so a menu is whatever reveals new links."""
import time

from ..drive.guards import blocked

import re

TOP_PX = 220  # the navigation bar's band, from the top of the page
# Top-bar controls that open a drawer or overlay, not navigation (a cart drawer lists products, not sections).
NOT_NAVIGATION = re.compile(r"search|cart|bag|basket|account|sign ?in|log ?in|wish ?list|favou?rites|close", re.I)
VISIBLE_LINKS_JS = r"""(() => [...document.querySelectorAll('a[href]')].filter(a => {
    const r = a.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && a.checkVisibility({checkOpacity: true, checkVisibilityCSS: true});
  }).map(a => { let u; try { u = new URL(a.href); } catch { return null; }
    return u.host === location.host ? {label: a.innerText.replace(/\s+/g, ' ').trim().slice(0, 60), to: u.pathname} : null;
  }).filter(l => l && l.label))()"""


def new_links(before, after):
    """Links in `after` whose destination wasn't in `before`, once each, in `after` order."""
    known, out = {l["to"] for l in before}, []
    for l in after:
        if l["to"] not in known:
            known.add(l["to"])
            out.append(l)
    return out


def _links(s):
    return s.browser.evaluate(VISIBLE_LINKS_JS) or []


def _revealed(s, base, looks=4, every_s=0.4):
    """New links after opening a menu. Menus fade in: Allbirds' links stay invisible (opacity) for a moment after the
    page stops changing, so look a few times before deciding nothing opened."""
    for n in range(looks):
        items = new_links(base, _links(s))
        if len(items) >= 2 or n == looks - 1:
            return items
        time.sleep(every_s)


def _openers(s, max_openers):
    top = {a["node"] for a in s.page.get("actions", []) if a.get("rect", {}).get("y", TOP_PX) < TOP_PX}
    return [e for e in s.elements() if e["node"] in top and e["role"] in ("button", "link") and e["label"]
            and "click" in e["actions"] and not blocked(e["label"]) and not NOT_NAVIGATION.search(e["label"])
            ][:max_openers]


def _close(s, how):
    if how == "click":
        for kind in ("keyDown", "keyUp"):
            s.browser.call("Input.dispatchKeyEvent", type=kind, key="Escape", code="Escape", windowsVirtualKeyCode=27)
    s.browser.call("Input.dispatchMouseEvent", type="mouseMoved", x=5, y=s.page.get("h", 780) - 5)
    s.wait_for_page()


def discover_menus(s, log=print, max_openers=12):
    """[{"opener", "opens_on": "hover"|"click", "items": [{"label", "to"}]}] for top-bar controls revealing 2+ links."""
    s.observe()
    menus = []
    for e in _openers(s, max_openers):
        base = _links(s)  # fresh each time: a menu that didn't close (Allbirds') isn't credited to the next opener
        for how in ("hover", "click"):
            if how == "click" and e["role"] != "button":
                break
            try:
                s.hover(e) if how == "hover" else s.act(e, "click")
            except Exception as error:  # moved or covered: skip this opener
                log(f"menu: {e['label'][:24]!r} {how} failed ({type(error).__name__})")
                break
            s.wait_for_page()
            items = _revealed(s, base)
            _close(s, how)
            if len(items) >= 2:
                menus.append({"opener": e["label"], "opens_on": how, "items": items})
                log(f"menu: {e['label'][:24]!r} opens on {how}: {len(items)} links")
                break
    return menus
