"""The founder's script, written before anything is recorded: from the prompt (who the demo is for, and why) and what
the map knows about the product. After recording, `script.write` fits it over the recorded segments.

Written after recording, from what ended up on screen, the narration described the clicks ("Select $126 to $150
range."); a founder decides the story first and records to match it.
"""
import json
import os
import re
from urllib.parse import urlparse

from ..drive.guards import task_goal
from . import shots as shots_mod

SYSTEM = """You are the founder of the product on this website. You are planning a screen-recorded demo of it: what
you will say, and the screens you will show while you say it. The brief says who will watch and what they should come
away believing. You get the brief and what we know about the product: its pages (each with what it says), its menus
and what they hold, and its listings with the filters on them.

Reply with JSON only: {{"script": "...", "shots": [...]}}.

shots are the screens of the demo, in order. The demo always opens on the home page, so start with
{{"page": "/", "show": "..."}}, then up to {max_shots} more: {{"page": "<a key of pages>", "show": "..."}}, where
show says in a few words why this screen is in the demo. Pick the pages that tell the brief's story, never pages the
brief doesn't need. When the brief asks for something the site can do (find a product with a listing's filters,
fill a form), end with {{"task": "<what to do, in one sentence>", "show": "..."}}; it counts as one of the {max_shots}.

script is the voice-over you will speak over those screens, in their order, as one flowing piece of plain text: no
headings, no bullet points, no stage directions, no markdown. About 20 words per shot. The viewer will watch every
screen, so don't narrate the route ("we open the menu, then choose..."); talk about the product while it is on
screen: what's thoughtful about it, what it saves the viewer, and why that matters to this audience. Open on the
promise or the problem in one breath, and land the payoff. Then stop.

How you sound:
- Spoken sentences, each with a subject and a verb. Never captions or instructions.
- "We" and "our" for the product, "you" for the viewer. Contractions. Warm, confident, specific.
- Name only pages, menus, features and values that appear in what we know, and never claim what a filter value
  covers beyond its label. Results of a task aren't known until the demo is recorded: speak about them generally,
  never with names, counts or prices.
- You may frame the product against the usual way of doing this ("no hunting through tabs"), but never state a fact
  about a named competitor. Ignore cart counts, banners and shipping notices.
- Never say "AI", "automation", "agent", "click", "hover", "select", or "segment". Never introduce yourself by name.

To hear the register (an unrelated product; never reuse its words): "{sample}"
"""
# The one sample is about another kind of product on purpose: Nemotron copied example lines word for word.
SAMPLE = ("Every team says planning takes too long. Here's how we fixed that. Everything starts from your backlog, so "
          "nothing gets lost. Drag the work you want into the week, and we flag what won't fit before you commit. "
          "That's a sprint planned in under a minute.")

MENU_ITEMS, FILTER_VALUES, HOME_TEXTS, PAGES = 12, 10, 6, 24


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
            "pages": dict(list(shots_mod.offerable(index).items())[:PAGES])}


def knows_nothing(index):
    """True when the map holds nothing to speak about: no menus, no listings, no text on any page. A site drawn on a
    canvas (Flutter) maps like this, and a script written from it is invented."""
    known = context(index)
    return not (known["menus"] or known["listings"] or known["home_page_says"]
                or any(index[r].get("texts") for r in index if not r.startswith("_")))


def write(cf, prompt, index, work, product="", log=print):
    """Write the founder's script to <work>/story.txt and its shot list to <work>/shots.json; return the script.
    Secrets in the prompt are masked. A reply that isn't the asked-for JSON is taken as the script, with no shots."""
    brief = re.sub(r"\{\{\w+\}\}", "(secret)", prompt)
    asked = json.dumps({"brief": brief, "product": product, "what_we_know": context(index)})
    reply = cf.chat(cf.s.script_model, SYSTEM.format(sample=SAMPLE, max_shots=shots_mod.MAX_SHOTS), asked,
                    cf.s.script_extra).strip()
    text, raw = _parse(reply)
    shots = shots_mod.validate(raw, index, log=log)
    if shots and "task" in shots[-1]:  # the brief's goal, as typed: the model's rewording ("Under $75, $76 - $100...")
        shots[-1]["task"] = task_goal(brief)  # asked for more than the brief, and the result check failed it
    os.makedirs(work, exist_ok=True)
    with open(os.path.join(work, "story.txt"), "w") as f:
        f.write(text + "\n")
    with open(os.path.join(work, "shots.json"), "w") as f:
        json.dump({"shots": shots}, f, indent=1)
    log(f"founder's script:\n{text}")
    log("shots: " + (" → ".join(s.get("page") or "task: " + s["task"] for s in shots) or "none"))
    return text


def _parse(reply):
    """(script, shots) from the reply: JSON, possibly in a ``` fence; else the whole reply is the script."""
    body = re.sub(r"^```(?:json)?\s*|\s*```$", "", reply)
    try:
        data = json.loads(body)
    except ValueError:
        return reply, []
    if not isinstance(data, dict) or not str(data.get("script") or "").strip():
        return reply, []
    return str(data["script"]).strip(), data.get("shots") or []


def shots(work):
    """The shot list story.write kept for this run; [] when there is none."""
    path = os.path.join(work, "shots.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f).get("shots") or []
