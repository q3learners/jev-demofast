"""Site explorer: browse a live site once, ahead of time, and write a map demos can drive from.

The map has the source-code map's shape ({route: {file, links, buttons, fields, texts, submits}}) plus, per route,
kind/filters/sort/examples, and a "_site" record: menus (and how they open), pop-ups, a bot block if one stopped it, and
the pages behind a login (behind_login), which aren't mapped.
Exploring only navigates, opens menus and reads; it never submits, signs up or types into a pop-up.
"""
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from ..drive.guards import blocked, hazard, on_site
from ..drive.popups import bot_check, clear_popups
from ..drive.session import Session, StalePage
from . import menus
from .buttons import SIGN_IN_FORM_JS, discover
from .listing import read_listing
from .menus import VISIBLE_LINKS_JS, discover_menus
from .templates import pick_examples, templates

# Visible to a person, not only to a screen reader: Amazon's only "headings" were its hidden "Skip to" and "Keyboard
# shortcuts" labels (a 1 px box, or placed off the page's side), and the founder's script had nothing true to say.
HEADINGS_JS = r"""[...document.querySelectorAll('h1,h2,h3')].filter(h => {
    if (!h.checkVisibility()) return false;
    const r = h.getBoundingClientRect();
    return r.width > 2 && r.height > 2 && r.right > 0 && r.left < document.documentElement.clientWidth; })
  .map(h => h.innerText.replace(/\s+/g, ' ').trim()).filter(t => t && t.length < 120).slice(0, 10)"""
# A page built in the browser (React, Vue) is "complete" before it has any content: q3learners.ai read as an empty
# <div id="root">, and the map was empty. Each page is read once it shows text, or after CONTENT_WAIT_S without.
HAS_CONTENT_JS = "!!document.body && document.body.innerText.trim().length > 0"
CONTENT_WAIT_S, CONTENT_POLL_S = 10, 0.25
EXAMPLES_PER_ROUTE = 2
LINKS_PER_ROUTE = 80  # as the source-code map caps them
# Marketing pop-ups open on a timer (Allbirds' a few seconds in); exploring is ahead of time, so the first page gets
# a one-time settle before menus are looked for. Demos never pause for this: they clear pop-ups on every screen.
FIRST_PAGE_SETTLE_S = 4


def _wait_for_content(s):
    for _ in range(round(CONTENT_WAIT_S / CONTENT_POLL_S)):
        if s.browser.evaluate(HAS_CONTENT_JS) is not False:  # drawn, or no answer: read what is there
            break
        time.sleep(CONTENT_POLL_S)
    s.observe()


def _flutter_texts(text, els):
    """A Flutter page has no h1-h3 (k12.tutorq.ai had none): its first lines of text that aren't a control's label."""
    controls = {e["label"].strip().split("\n")[0].strip() for e in els}
    lines = [t.strip() for t in (text or "").split("\n")]
    return list(dict.fromkeys(t for t in lines if 3 <= len(t) < 120 and t not in controls))[:10]


def _read_page(s):
    """What the map records about the screen the session is on."""
    els = s.elements()
    listing = read_listing(s)
    texts = s.browser.evaluate(HEADINGS_JS) or []
    if not texts and getattr(s, "is_flutter", False):
        texts = _flutter_texts(s.page.get("text"), els)
    return {"links": s.browser.evaluate(VISIBLE_LINKS_JS) or [],
            "buttons": [{"label": e["label"][:80], "submit": False} for e in els if e["role"] == "button"
                        and e["label"]][:60],
            "fields": [e["label"][:60] for e in els if "fill" in e["actions"] and e["label"]][:30],
            "texts": texts, "sign_in": s.browser.evaluate(SIGN_IN_FORM_JS) is True,
            **listing}


def _logged_in_hazard(s, link):
    """In a logged-in run (--login) a link is opened by its address, which never passes Session.act's check: its
    label and its path ("/account/logout", "/kids/3/delete") are checked here instead."""
    if not getattr(s, "hazards", False):
        return False
    u = urlparse(link["to"])
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", f"{u.path} {u.query}")  # /account/deleteKid, ?action=destroy
    words = re.sub(r"[^a-zA-Z]+", " ", words)
    return hazard(link.get("label") or "") or hazard(words)


def _sent_to_sign_in(s, asked):
    """True when opening `asked` ended somewhere else, on a page with a sign-in form."""
    landed, want = urlparse(s.page["url"]), urlparse(asked)
    moved = (landed.netloc, landed.path.rstrip("/")) != (want.netloc, want.path.rstrip("/"))
    return moved and s.browser.evaluate(SIGN_IN_FORM_JS) is True


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
    entry["sign_in"] = entry.get("sign_in", False) or page["sign_in"]
    return entry


def explore(url, out=None, max_pages=40, max_minutes=5, cf=None, log=print, session=Session):
    """Map the site at `url`. Returns the map, and writes it as JSON to `out` when given."""
    started, origin = time.monotonic(), "{0.scheme}://{0.netloc}".format(urlparse(url))
    site = {"start": url, "explored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "menus": [], "popups": [], "blocked": None, "behind_login": []}
    found, s = {"_site": site}, session(url, isolated=True)
    try:
        site["blocked"] = bot_check(s.page)
        if site["blocked"]:
            log(f"blocked: {site['blocked']!r} on {url}; nothing explored (bot protection is never worked around)")
            return _write(found, out)
        queue, visited, entries, button_paths = [], [], {}, set()

        def visit(path):
            _wait_for_content(s)
            how = clear_popups(cf, s, log)
            if how:
                site["popups"].append({"seen_on": path, "cleared_by": how})
            page = _read_page(s)
            visited.append(path)
            if getattr(s, "is_flutter", False) and time.monotonic() - started < max_minutes * 60:
                found_links = discover(s, origin, path, cf, log,  # Flutter navigates with buttons, not links
                                       deadline=started + max_minutes * 60)
                button_paths.update(link["to"] for link in found_links)
                page["links"] += [link for link in found_links if link not in page["links"]]
            for link in page["links"]:
                if link["to"] not in queue and not blocked(link["label"]) and not _logged_in_hazard(s, link):
                    queue.append(link["to"])
            return page

        home = urlparse(s.page["url"]).path or "/"
        pages = {home: visit(home)}
        time.sleep(FIRST_PAGE_SETTLE_S)
        s.observe()
        how = clear_popups(cf, s, log)  # a pop-up that arrived late would hide the navigation
        if how:
            site["popups"].append({"seen_on": home, "cleared_by": how})
        # A Flutter app has no links to reveal, and its top-bar buttons navigate: its pages come from discover()
        site["menus"] = [] if getattr(s, "is_flutter", False) else discover_menus(s, log)
        menu_paths = [i["to"] for m in site["menus"] for i in m["items"]]
        queue[:0] = [p for p in dict.fromkeys(menu_paths) if p not in queue]  # menu destinations first
        while queue and len(visited) < max_pages and time.monotonic() - started < max_minutes * 60:
            routes = templates(list(dict.fromkeys([home] + queue + visited)), keep=frozenset(button_paths))
            todo = [p for p in pick_examples(list(dict.fromkeys(visited + queue)), routes, EXAMPLES_PER_ROUTE)
                    if p not in visited]
            if not todo:
                break
            path = todo[0]
            queue.remove(path)
            try:
                s.browser.call("Page.navigate", url=origin + path)
                s.wait_loaded()
                _wait_for_content(s)  # a sign-in redirect made in the page's script lands after the load
                if _sent_to_sign_in(s, origin + path):
                    site["behind_login"].append(path)
                    visited.append(path)
                    continue
                if not on_site(s.page["url"], urlparse(url).hostname) or bot_check(s.page):
                    visited.append(path)
                    continue
                pages[path] = visit(path)
            except (TimeoutError, StalePage) as e:  # one page that won't load, or a file that isn't a page (selvage.run
                log(f"  skipped {path}: {e}")       # linked an .svg), costs that link, not the map
                if path not in visited:
                    visited.append(path)
        routes = templates(list(pages), keep=frozenset(button_paths))
        for path, page in pages.items():
            entries[routes[path]] = _merge(entries.get(routes[path]), page, path, origin + path)
        for entry in entries.values():
            entry["links"] = entry["links"][:LINKS_PER_ROUTE]
        found.update(entries)
        log(f"explored {len(pages)} pages in {time.monotonic() - started:.0f} s: {len(entries)} routes, "
            f"{sum(e['kind'] == 'listing' for e in entries.values())} listings, {len(site['menus'])} menus")
        if site["behind_login"]:
            log(f"behind a login: {', '.join(site['behind_login'])}. Not mapped; to show them, log in once with "
                f"`jev-demofast chrome --open <the sign-in page>`, then explore again")
        return _write(found, out)
    finally:
        s.close()


def _write(found, out):
    if out:
        with open(out, "w") as f:
            json.dump(found, f, indent=1)
    return found
