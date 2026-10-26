"""A listing page's filters and sort, read from the page itself (controls in closed filter panels included).

Shopify names its filter inputs after the URL parameter (filter.v.price.lte, filter.p.m.<ns>.<key>), so the map knows
how each filter appears in the URL. Sites that don't keep the group and values, with param None.
"""
import re

READ_LISTING_JS = r"""(() => {
  const clean = s => (s || '').replace(/\s+/g, ' ').trim().slice(0, 60);
  const heading = e => {
    const d = e.closest('details'); if (d && d.querySelector('summary')) return clean(d.querySelector('summary').innerText);
    const f = e.closest('fieldset'); if (f && f.querySelector('legend')) return clean(f.querySelector('legend').innerText);
    const g = e.closest('[role=group][aria-label],[aria-labelledby]');
    if (g) return clean(g.getAttribute('aria-label') || document.getElementById(g.getAttribute('aria-labelledby'))?.innerText);
    return clean(e.name);
  };
  const label = e => clean(e.labels?.[0]?.innerText || e.getAttribute('aria-label') || e.value);
  const groups = new Map();
  for (const e of document.querySelectorAll('input[type=checkbox],input[type=radio],input[type=number],input[type=text],select')) {
    if (e.closest('header nav,[role=dialog],dialog') || /search|email|newsletter|quantity|qty/i.test(e.name + ' ' + e.id)) continue;
    const h = heading(e); if (!h) continue;
    if (!groups.has(h)) groups.set(h, []);
    if (e.tagName === 'SELECT') for (const o of e.options) groups.get(h).push({type: 'select', name: e.name || '', label: clean(o.text)});
    else groups.get(h).push({type: e.type, name: e.name || '', label: label(e), value: e.value || ''});
  }
  const prefixes = {};
  for (const a of document.querySelectorAll('a[href]')) {
    let u; try { u = new URL(a.href); } catch { continue; }
    if (u.host !== location.host) continue;
    const parts = u.pathname.split('/').filter(Boolean);
    if (parts.length < 2) continue;
    const key = '/' + parts[0];
    (prefixes[key] ||= new Set()).add(u.pathname);
  }
  const item_links = Math.max(0, ...Object.values(prefixes).map(s => s.size));
  const add_to_cart = [...document.querySelectorAll('button,input[type=submit]')].some(b =>
    /add to (bag|cart|basket)/i.test(b.innerText || b.value || '') && b.checkVisibility());
  return {item_links, add_to_cart, groups: [...groups].map(([heading, controls]) => ({heading, controls}))};
})()"""

SORT = re.compile(r"\bsort", re.I)
COUNT = re.compile(r"\s*\(\d+\)\s*$")  # "Running Shoes (12)": the count changes as filters apply
LOW = re.compile(r"gte|min|from|low", re.I)
HIGH = re.compile(r"lte|max|to\b|high", re.I)


def _param(names):
    """The controls' shared name, when it looks like a URL key; None otherwise."""
    names = {n for n in names if n}
    if len(names) != 1:
        return None
    (name,) = names
    return name if re.search(r"[._\[]", name) else None


def _range(controls):
    boxes = [c for c in controls if c["type"] in ("number", "text")]
    if len(boxes) != 2:
        return None
    low = next((c for c in boxes if LOW.search(f"{c['name']} {c['label']}")), None)
    high = next((c for c in boxes if c is not low and HIGH.search(f"{c['name']} {c['label']}")), None)
    if not (low and high):
        return None
    return [low["name"] or None, high["name"] or None] if low["name"] and high["name"] else None


def parse_listing(raw):
    """{"kind": "listing"|"page", "filters": [...], "sort": {...}|None} from READ_LISTING_JS's result."""
    filters, sort = [], None
    for g in raw.get("groups", []):
        controls = g["controls"]
        if not controls:
            continue
        if SORT.search(g["heading"]) or SORT.search(controls[0]["name"]):
            sort = {"param": _param(c["name"] for c in controls),
                    "options": list(dict.fromkeys(c["label"] for c in controls if c["label"]))}
            continue
        rng = _range(controls)
        if rng is not None or (len(controls) == 2 and all(c["type"] in ("number", "text") for c in controls)):
            filters.append({"group": g["heading"], "kind": "range", "param": rng, "values": []})
            continue
        values = list(dict.fromkeys(COUNT.sub("", c["label"]) for c in controls if c["label"]))
        if len(values) < 2:  # a filter offers a choice; one value is a product card's control (a colour swatch)
            continue
        kind = "radio" if all(c["type"] == "radio" for c in controls) else "checkbox"
        entry = {"group": g["heading"], "kind": kind, "param": _param(c["name"] for c in controls), "values": values}
        url_values = {COUNT.sub("", c["label"]): c["value"] for c in controls
                      if c.get("value") and c["value"] not in ("on", COUNT.sub("", c["label"]))}
        if entry["param"] and url_values:  # what the URL carries (Shopify's taxonomy filters put an id there)
            entry["url_values"] = url_values
        filters.append(entry)
    if raw.get("add_to_cart"):  # its size and colour pickers aren't listing filters (Nike's product pages)
        return {"kind": "product", "filters": [], "sort": None}
    listing = raw.get("item_links", 0) >= 8 and bool(filters or sort)
    return {"kind": "listing" if listing else "page", "filters": filters, "sort": sort}


def read_listing(s):
    return parse_listing(s.browser.evaluate(READ_LISTING_JS) or {})
