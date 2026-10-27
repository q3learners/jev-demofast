"""Site explorer: browse a live site once, ahead of time, and write a map demos can drive from.

The map has the source-code map's shape ({route: {file, links, buttons, fields, texts, submits}}) plus, per route,
kind/filters/sort/examples, and a "_site" record: menus (and how they open), pop-ups, and a bot block if one stopped it.
Exploring only navigates, opens menus and reads; it never submits, signs up or types into a pop-up.
"""
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from ..drive.guards import blocked, on_site
from ..drive.popups import bot_check, clear_popups
from ..drive.session import Session
from . import menus
from .listing import read_listing
from .menus import VISIBLE_LINKS_JS, discover_menus
from .templates import pick_examples, templates

HEADINGS_JS = r"""[...document.querySelectorAll('h1,h2,h3')].filter(h => h.checkVisibility())
  .map(h => h.innerText.replace(/\s+/g, ' ').trim()).filter(t => t && t.length < 120).slice(0, 10)"""
EXAMPLES_PER_ROUTE = 2
LINKS_PER_ROUTE = 80  # as the source-code map caps them
# Marketing pop-ups open on a timer (Allbirds' a few seconds in); exploring is ahead of time, so the first page gets
# a one-time settle before menus are looked for. Demos never pause for this: they clear pop-ups on every screen.
FIRST_PAGE_SETTLE_S = 4


def _read_page(s):
    """What the map records about the screen the session is on."""
    els = s.elements()
    listing = read_listing(s)
    return {"links": s.browser.evaluate(VISIBLE_LINKS_JS) or [],
            "buttons": [{"label": e["label"][:80], "submit": False} for e in els if e["role"] == "button"
                        and e["label"]][:60],
            "fields": [e["label"][:60] for e in els if "fill" in e["actions"] and e["label"]][:30],
            "texts": s.browser.evaluate(HEADINGS_JS) or [], **listing}


def _merge(entry, page, path, url):
    """Fold one example page into its route's entry: lists unioned in order, filter values merged per group."""
    if not entry:
        return {"file": f"explored: {url}", "submits": False, "examples": [path], **page}
    entry["examples"].append(path)
    for key in ("links", "buttons", "fields", "texts"):
        seen = {json.dumps(x, sort_keys=True) for x in entry[key]}
        entry[key] += [x for x in page[key] if json.dumps(x, sort_keys=True) not in seen]
    groups = {f["group"]: f for f in entry["filters"]}
    for f in page["filters"]:
        if f["group"] in groups:
            groups[f["group"]]["values"] = list(dict.fromkeys(groups[f["group"]]["values"] + f["values"]))
            if f.get("url_values"):
                groups[f["group"]]["url_values"] = {**groups[f["group"]].get("url_values", {}), **f["url_values"]}
        else:
            entry["filters"].append(f)
    if page["kind"] == "listing":
        entry["kind"] = "listing"
    entry["sort"] = entry["sort"] or page["sort"]
    return entry


def explore(url, out=None, max_pages=40, max_minutes=5, cf=None, log=print, session=Session):
    """Map the site at `url`. Returns the map, and writes it as JSON to `out` when given."""
    started, origin = time.monotonic(), "{0.scheme}://{0.netloc}".format(urlparse(url))
    site = {"start": url, "explored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "menus": [], "popups": [], "blocked": None}
    found, s = {"_site": site}, session(url, isolated=True)
    try:
        site["blocked"] = bot_check(s.page)
        if site["blocked"]:
            log(f"blocked: {site['blocked']!r} on {url}; nothing explored (bot protection is never worked around)")
            return _write(found, out)
        queue, visited, entries = [], [], {}

        def visit(path):
            how = clear_popups(cf, s, log)
            if how:
                site["popups"].append({"seen_on": path, "cleared_by": how})
            page = _read_page(s)
            visited.append(path)
            for link in page["links"]:
                if link["to"] not in queue and not blocked(link["label"]):
                    queue.append(link["to"])
            return page

        home = urlparse(s.page["url"]).path or "/"
        pages = {home: visit(home)}
        time.sleep(FIRST_PAGE_SETTLE_S)
        s.observe()
        how = clear_popups(cf, s, log)  # a pop-up that arrived late would hide the navigation
        if how:
            site["popups"].append({"seen_on": home, "cleared_by": how})
        site["menus"] = discover_menus(s, log)
        menu_paths = [i["to"] for m in site["menus"] for i in m["items"]]
        queue[:0] = [p for p in dict.fromkeys(menu_paths) if p not in queue]  # menu destinations first
        while queue and len(visited) < max_pages and time.monotonic() - started < max_minutes * 60:
            routes = templates(list(dict.fromkeys([home] + queue + visited)))
            todo = [p for p in pick_examples(list(dict.fromkeys(visited + queue)), routes, EXAMPLES_PER_ROUTE)
                    if p not in visited]
            if not todo:
                break
            path = todo[0]
            queue.remove(path)
            try:
                s.browser.call("Page.navigate", url=origin + path)
            except TimeoutError as e:  # one page that won't load costs that page, not the map
                log(f"  skipped {path}: {e}")
                visited.append(path)
                continue
            s.wait_loaded()
            s.observe()
            if not on_site(s.page["url"], urlparse(url).hostname) or bot_check(s.page):
                visited.append(path)
                continue
            pages[path] = visit(path)
        routes = templates(list(pages))
        for path, page in pages.items():
            entries[routes[path]] = _merge(entries.get(routes[path]), page, path, origin + path)
        for entry in entries.values():
            entry["links"] = entry["links"][:LINKS_PER_ROUTE]
        found.update(entries)
        log(f"explored {len(pages)} pages in {time.monotonic() - started:.0f} s: {len(entries)} routes, "
            f"{sum(e['kind'] == 'listing' for e in entries.values())} listings, {len(site['menus'])} menus")
        return _write(found, out)
    finally:
        s.close()


def _write(found, out):
    if out:
        with open(out, "w") as f:
            json.dump(found, f, indent=1)
    return found
