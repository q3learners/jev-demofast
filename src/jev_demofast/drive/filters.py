"""Filters on an explored listing, applied the way a person would on camera: open the filter's panel if it's closed,
tick the values the goal calls for, fill a price box. The map says which groups and values exist, so the language
model only chooses among them; anything it invents is dropped."""
from collections import Counter
import re
import time
from urllib.parse import parse_qsl, urlparse

from ..browser.elements import words
from .guards import blocked, on_site, stop_if_dry_run
from .popups import SIGN_UP, clear_popups
from .session import StalePage

LEFT_SITE = "left the site"
# The control that opens a collapsed filter panel or drawer ("FILTER" on Allbirds): shop vocabulary, not a site rule.
PANEL = re.compile(r"\bfilters?\b|\brefine\b", re.I)
NUMBER = re.compile(r"^\d+(\.\d+)?$")

FILTER_VALUES = """Choose the listing filters a shopper would apply for the goal. You get the filter groups and their
exact values. Return JSON {"checks": [{"group": "...", "value": "..."}], "ranges": [{"group": "...", "min": "...",
"max": "..."}], "sort": "<a sort option, or null>"}. Use values exactly as listed; for a price limit tick every price
band within it (e.g. under $100: "Under $75" and "$76 - $100"). Only what the goal asks for; omit everything else."""
# Shopify disables a filter value that would leave no results; the page reader skips disabled controls.
DISABLED_JS = """[...document.querySelectorAll('input[type=checkbox]:disabled,input[type=radio]:disabled')]
  .map(e => (e.labels?.[0]?.innerText || e.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim())
  .filter(Boolean)"""
# Price boxes say "From"/"To" (Shopify's Dawn), "Min"/"Max", or gte/lte in their names.
LOW = re.compile(r"\b(min(imum)?|from|low(est)?)\b|gte", re.I)
HIGH = re.compile(r"\b(max(imum)?|to|high(est)?)\b|lte", re.I)


def _price_box(e, group):
    """A box for this range: a number input, or one that names the group. Never a sign-up box: typing into "Subscribe
    to our emails" and pressing Enter would sign the viewer up."""
    text = f"{e['label']} {e.get('hint', '')}"
    return ((e["role"] == "spinbutton" or words(group) <= words(text)) and not SIGN_UP.search(text)
            and not blocked(e["label"]))


def choose_filters(cf, goal, filters, sort=None):
    """{"checks", "ranges", "sort"}, keeping only groups and values the map has."""
    raw = cf.chat_json(cf.s.read_model, FILTER_VALUES, {
        "goal": goal, "filters": [{"group": f["group"], "kind": f["kind"], "values": f["values"]} for f in filters],
        "sort_options": (sort or {}).get("options", [])}) or {}
    by_group = {f["group"]: f for f in filters}
    checks = [c for c in raw.get("checks") or [] if c.get("group") in by_group
              and c.get("value") in by_group[c["group"]]["values"]]
    ranges = []
    for r in raw.get("ranges") or []:
        if by_group.get(r.get("group"), {}).get("kind") != "range":
            continue
        bounds = {b: str(r.get(b) or "").replace("$", "").replace(",", "").strip() for b in ("min", "max")}
        bounds = {b: v if NUMBER.match(v) else None for b, v in bounds.items()}  # a price box only ever gets a number
        if bounds["min"] or bounds["max"]:
            ranges.append({"group": r["group"], **bounds})
    chosen_sort = raw.get("sort") if raw.get("sort") in (sort or {}).get("options", []) else None
    return {"checks": checks, "ranges": ranges, "sort": chosen_sort}


def _find(s, text, roles=("checkbox", "radio", "option", "switch", "button", "link")):
    """The visible control whose label holds every word of `text` ("Running Shoes" in "Running Shoes (12)")."""
    s.observe()
    want = words(text)
    found = [e for e in s.elements() if "click" in e["actions"] and e["role"] in roles and want
             and want <= words(e["label"]) and not blocked(e["label"])]
    return min(found, key=lambda e: (roles.index(e["role"]), len(e["label"])), default=None)


def _click(s, rec, e, action, guard=True):
    """Click on camera. guard: dry-run check (opening a panel, sorting); ticking a filter value doesn't change data,
    so a dry run goes through it, by design. Returns True, False (the page moved), or LEFT_SITE."""
    if guard:
        stop_if_dry_run(rec, e, s)
    rec.snap(1.0, node=e["node"])
    try:
        s.act(e, "click")
    except StalePage:
        rec.discard()
        return False
    s.wait_for_page()
    page = s.observe()
    if not on_site(page["url"], s.host):
        rec.discard()
        return LEFT_SITE
    rec.snap(0.8)
    rec.commit(action, page)
    return True


def _disabled(s, value):
    want = words(value)
    return any(want and want <= words(label) for label in s.browser.evaluate(DISABLED_JS) or [])


RELOAD_LOOKS, SETTLED_LOOKS = 8, 2  # up to ~3.5 s for a listing to reload (slower in the cloud), then quick looks


def _settled_find(s, value, looks=RELOAD_LOOKS, every_s=0.5):
    """(control, disabled). Right after a filter click Shopify disables every option until the listing reloads, so a
    value counts as disabled only if it stays disabled over a few looks. In the cloud the reload took longer than 0.8 s
    and a real value ($126 - $150) was reported greyed out."""
    for n in range(looks):
        e = _find(s, value, ("checkbox", "radio", "option", "switch"))
        if e is not None or not _disabled(s, value):
            return e, False
        if n < looks - 1:
            time.sleep(every_s)
    return None, True


def apply_filters(cf, s, rec, goal, entry, log=print, unavailable=None):
    """Apply the filters the goal calls for, on camera. Returns the URL parameters expected afterwards
    ("<param>=<value>"), for filters whose URL form the map knows; None if a click led off the site. Values the site
    has disabled (no results with the other filters) are appended to `unavailable` as "<group>: <value>"."""
    choices = choose_filters(cf, goal, entry.get("filters", []), entry.get("sort"))
    by_group = {f["group"]: f for f in entry.get("filters", [])}
    expected, settled = [], False  # settled: a value was just confirmed disabled, so the listing isn't reloading
    picks = Counter(c["group"] for c in choices["checks"])
    # The narrowest group first: one pick (Running Shoes) before several (four price bands). Allbirds' bestsellers
    # with "Under $75" ticked first had no running shoes left, so the shopper's own choice greyed out.
    for c in sorted(choices["checks"], key=lambda c: picks[c["group"]]):
        clear_popups(cf, s, log)  # filtering takes 10-20 s: a timed pop-up can land between filters
        e, disabled = _settled_find(s, c["value"], looks=SETTLED_LOOKS if settled else RELOAD_LOOKS)
        if disabled:  # known from the page: no panel or heading clicked looking for it
            log(f"  filter {c['group']}: {c['value']!r} is unavailable (the site has no results for it here)")
            if unavailable is not None:
                unavailable.append(f"{c['group']}: {c['value']}")
            settled = True
            continue
        settled = False
        # Each filter click may reload the listing with the panel collapsed again (Allbirds): reopen it when needed.
        if e is None and _find(s, c["group"], ("button", "link", "tab")) is None:
            panel = next((x for x in s.elements() if x["role"] in ("button", "link") and PANEL.search(x["label"])
                          and not blocked(x["label"])), None)
            if panel is not None:  # every filter is behind one collapsed panel: open it on camera first
                if _click(s, rec, panel, {"do": "click", "target": "open the filters"}) is LEFT_SITE:
                    return None
                e = _find(s, c["value"], ("checkbox", "radio", "option", "switch"))
        if e is None:  # its group is closed: open it on camera first
            heading = _find(s, c["group"], ("button", "link", "tab"))
            if heading is not None:
                if _click(s, rec, heading, {"do": "click", "target": f"open the {c['group']} filter"}) is LEFT_SITE:
                    return None
                e = _find(s, c["value"], ("checkbox", "radio", "option", "switch"))
        if e is None:
            if _disabled(s, c["value"]):
                log(f"  filter {c['group']}: {c['value']!r} is unavailable (the site has no results for it here)")
                if unavailable is not None:
                    unavailable.append(f"{c['group']}: {c['value']}")
            else:
                log(f"  filter {c['group']}: {c['value']!r} isn't on screen; skipped")
            continue
        clicked = _click(s, rec, e, {"do": "filter", "target": f"{c['group']}: {c['value']}"}, guard=False)
        if clicked is LEFT_SITE:
            return None
        if clicked:
            log(f"  filter {c['group']}: {c['value']}")
            group = by_group[c["group"]]
            if group["param"]:  # the URL carries the input's value, which may differ from its label
                expected.append(f"{group['param']}={group.get('url_values', {}).get(c['value'], c['value'])}")
    for r in choices["ranges"]:
        clear_popups(cf, s, log)
        s.observe()
        boxes = [e for e in s.elements() if "fill" in e["actions"] and _price_box(e, r["group"])]
        for bound, pattern in (("min", LOW), ("max", HIGH)):
            if not r.get(bound):
                continue
            box = next((e for e in boxes if pattern.search(f"{e['label']} {e.get('hint', '')}")), None)
            if box is None:
                log(f"  filter {r['group']}: no {bound} box on screen; skipped")
                continue
            rec.snap(1.0, node=box["node"])
            try:
                s.act(box, "fill", text=str(r[bound]))
            except StalePage:
                rec.discard()
                log(f"  filter {r['group']}: the {bound} box changed under us; skipped")
                continue
            for kind in ("keyDown", "keyUp"):
                s.browser.call("Input.dispatchKeyEvent", type=kind, key="Enter", code="Enter", windowsVirtualKeyCode=13,
                               **({"text": "\r"} if kind == "keyDown" else {}))
            s.wait_for_page()
            if not on_site(s.observe()["url"], s.host):
                rec.discard()
                return None
            rec.commit({"do": "filter", "target": f"{r['group']}: {bound} {r[bound]}"}, s.page)
            param = by_group[r["group"]]["param"]
            if param:
                expected.append(f"{param[0] if bound == 'min' else param[1]}={r[bound]}")
    if choices["sort"]:
        e = _find(s, choices["sort"], ("radio", "option", "button", "link"))
        if e is not None and _click(s, rec, e, {"do": "click", "target": f"sort: {choices['sort']}"}) is LEFT_SITE:
            return None
    return expected


def url_agrees(url, expected):
    """Every expected "<param>=<value>" is in the URL's query (value words matched, so "Running+Shoes" agrees)."""
    query = parse_qsl(urlparse(url).query)
    for exp in expected:
        param, _, value = exp.partition("=")
        if not any(k == param and words(value) <= words(v) for k, v in query):
            return False
    return True
