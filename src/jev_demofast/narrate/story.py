"""The founder's script, written before anything is recorded: from the prompt (who the demo is for, and why) and what
the map knows about the product. After recording, `script.write` fits it over the recorded segments.

Written after recording, from what ended up on screen, the narration described the clicks ("Select $126 to $150
range."); a founder decides the story first and records to match it.
"""
import json
import os
import re
from urllib.parse import urlparse

from ..index import summary

SYSTEM = """You are the founder of the product on this website. You are planning the voice-over for a screen-recorded demo, and
the brief says who will watch it and what they should come away believing. You get the brief and what we know about
the product: its menus and what they hold, its listings and the filters on them, and what the home page says.

Write the voice-over you will speak, as one flowing script in plain text: no headings, no bullet points, no stage
directions, no markdown. 60-100 words: about one sentence for each moment of the demo: the promise, said over the home page;
the menu; the listing; each filter; the results and the payoff, together. The viewer will watch every step on screen, so don't narrate the
route ("we open the menu, then choose..."); talk about the product while it happens: what's thoughtful about how it's
organised, what each moment saves the shopper, and why that matters to this audience. Open on the promise or the
problem in one breath, follow the order the demo will go, and land the payoff. Then stop. Talk only about what the demo will show: the menu, the listing and the filters the brief
needs; no sorting, tabs or features it won't use.

How you sound:
- Spoken sentences, each with a subject and a verb. Never captions or instructions.
- "We" and "our" for the product, "you" for the viewer. Contractions. Warm, confident, specific.
- Name only menus, pages, features and values that appear in what we know, and never claim what a filter value
  covers beyond its label. The results aren't known until the demo is recorded: speak about them generally, never with
  names, counts or prices.
- You may frame the product against the usual way of doing this ("no hunting through tabs"), but never state a fact
  about a named competitor. Ignore cart counts, banners and shipping notices.
- Never say "AI", "automation", "agent", "click", "hover", "select", or "segment". Never introduce yourself by name.

To hear the register (an unrelated product; never reuse its words): "{sample}"
"""
# The one sample is about another kind of product on purpose: Nemotron copied example lines word for word.
SAMPLE = ("Every team says planning takes too long. Here's how we fixed that. Everything starts from your backlog, so "
          "nothing gets lost. Drag the work you want into the week, and we flag what won't fit before you commit. "
          "That's a sprint planned in under a minute.")

MENU_ITEMS, FILTER_VALUES, HOME_TEXTS = 12, 10, 6


def context(index):
    """What the map knows, small enough for one prompt: menus with their items, listings with their filters and values,
    and the home page's headline texts. Not the routes' links."""
    site = index.get("_site") or {}
    listings = [{"route": route, "shows": e.get("texts", [])[:3],
                 "filters": {f["group"]: f.get("values", [])[:FILTER_VALUES] for f in e["filters"]},
                 **({"sort": e["sort"]} if e.get("sort") else {})}
                for route, e in index.items() if not route.startswith("_") and e.get("filters")]
    home = index.get("/") or {}
    return {"site": urlparse(site.get("start", "")).hostname or "",
            "home_page_says": [t[:80] for t in home.get("texts", [])[:HOME_TEXTS]],
            "menus": [{"menu": m["opener"], "holds": [i["label"] for i in m["items"][:MENU_ITEMS]]}
                      for m in site.get("menus", [])],
            "listings": listings,
            "screens": {route: summary(route, index, 3) for route in list(index)[:12]
                        if not route.startswith("_") and route != "/" and not index[route].get("filters")}}


def knows_nothing(index):
    """True when the map holds nothing to speak about: no menus, no listings, no text on any page. A site drawn on a
    canvas (Flutter) maps like this, and a script written from it is invented."""
    known = context(index)
    return not (known["menus"] or known["listings"] or known["home_page_says"]
                or any(index[r].get("texts") for r in index if not r.startswith("_")))


def write(cf, prompt, index, work, product="", log=print):
    """Write the founder's script to <work>/story.txt and return it. Secrets in the prompt are masked."""
    brief = re.sub(r"\{\{\w+\}\}", "(secret)", prompt)
    asked = json.dumps({"brief": brief, "product": product, "what_we_know": context(index)})
    text = cf.chat(cf.s.script_model, SYSTEM.format(sample=SAMPLE), asked,
                   cf.s.script_extra).strip()
    os.makedirs(work, exist_ok=True)
    with open(os.path.join(work, "story.txt"), "w") as f:
        f.write(text + "\n")
    log(f"founder's script:\n{text}")
    return text
