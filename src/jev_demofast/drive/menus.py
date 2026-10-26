"""Menus in a demo: open the menu on camera (hover or click, as the explored map says), then click the item.

A founder showing their product opens the menu so the viewer learns where things are; the demo never jumps straight
to a page to skip that. The map's menus (_site.menus) tell Jev what each opener holds before it is opened.
"""
import time

from ..browser.elements import words
from .guards import blocked, on_site, stop_if_dry_run
from .session import StalePage, fingerprint

LEFT_SITE = object()  # open_menu's answer when a menu item led off the site: the run stops, as for any click
LOOKS, EVERY_S = 4, 0.4  # menus fade in (Allbirds'): their items appear a moment after the page stops changing


def menu_options(index, els):
    """{opener node: menu} for the map's menus whose opener is on screen."""
    found = {}
    for menu in (index.get("_site") or {}).get("menus", []):
        e = next((e for e in els if "click" in e["actions"] and words(e["label"]) == words(menu["opener"])), None)
        if e is not None:
            found[e["node"]] = menu
    return found


def describe_menu(menu, limit=8):
    return "→ opens a menu: " + ", ".join(i["label"][:24] for i in menu["items"][:limit])


def _items_on_screen(s, menu):
    wanted = [words(i["label"]) for i in menu["items"]]
    for n in range(LOOKS):
        s.observe()
        items = [e for e in s.elements() if "click" in e["actions"] and words(e["label"]) in wanted
                 and not blocked(e["label"]) and _stays_on_site(s, e)]
        if items or n == LOOKS - 1:
            return items
        time.sleep(EVERY_S)


def _stays_on_site(s, e):
    href = s.href(e["node"])
    return not href or on_site(href, s.host)


def open_menu(cf, s, rec, opener, menu, goal, state, log):
    """Open the menu on camera and click the item Jev picks. Returns the clicked item's label; None if the menu showed
    none of its items; LEFT_SITE if the item led off the site. Items get the same guards as any click: blocked labels
    and off-site links are never offered, and a dry run stops before one that would change data."""
    rec.snap(1.0, node=opener["node"])
    how = menu.get("opens_on", "click")
    if how == "click":
        stop_if_dry_run(rec, opener, s)
    s.hover(opener) if how == "hover" else s.act(opener, "click")
    s.wait_for_page()
    items = _items_on_screen(s, menu)
    if not items and how == "hover" and opener["role"] == "button":  # recorded as hover, but it may only open on click
        how = "click"
        stop_if_dry_run(rec, opener, s)
        s.act(opener, "click")
        s.wait_for_page()
        items = _items_on_screen(s, menu)
    if not items:
        rec.discard()
        log(f"menu {opener['label'][:24]!r}: none of its items appeared")
        return None
    rec.snap(0.8)
    rec.commit({"do": how, "target": f"open the {opener['label']} menu"}, s.page)
    key, conf = cf.choose("Which menu item moves toward the goal?", {str(e["node"]): e["label"][:60] for e in items},
                          state)
    item = next(e for e in items if str(e["node"]) == key)
    stop_if_dry_run(rec, item, s)
    rec.snap(1.2, node=item["node"])
    before = fingerprint(s.observe())
    try:
        s.act(item, "click")
    except StalePage:
        rec.discard()
        s.observe()
        return None
    s.wait_for_page()
    page = s.observe()
    rec.snap(0.8)
    if not on_site(page["url"], s.host):
        rec.discard()
        return LEFT_SITE
    rec.commit({"do": "click", "target": item["label"]}, page)
    log(f"  menu {opener['label'][:20]!r} ({how}) → {item['label'][:30]!r} ({conf:.2f})"
        f"{'' if fingerprint(page) != before else '  [no change]'}")
    return item["label"]
