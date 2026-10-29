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
and what they hold, its listings with the filters on them, and behind_login: pages that need an account, which the
demo can't show. When there is a readme, it is the product's README
from its code repository, in the makers' own words: take what the product is, who it's for and why it's different from
it, but leave out install steps, code and anything for developers unless the brief is for developers.

Reply with JSON only: {{"script": "...", "shots": [...]}}.

shots are the screens of the demo, in order. The demo always opens on the home page, so start with
{{"page": "/", "show": "..."}}, then up to {max_shots} more: {{"page": "<a key of pages>", "show": "..."}} (or with "items": true), where
show says in a few words why this screen is in the demo. Add "items": true to a page shot whose point is what it lists
(products, plans, courses): the demo ends that shot by pointing out a few of them. Pick the pages that tell the brief's story, never pages the
brief doesn't need. Only when the brief asks for something specific that a listing's filters or a form can do (men's
running shoes under $150; book a table for two), end with {{"task": "<what to do, in one sentence>", "show": "..."}};
it counts as one of the {max_shots}. A brief to look around or see what's popular is not a task: end on the page that
lists it, with "items": true.

script is the voice-over you will speak over those screens, in their order, as one flowing piece of plain text: no
headings, no bullet points, no stage directions, no markdown. About 20 words per shot. The viewer will watch every
screen, so don't narrate the route ("we open the menu, then choose..."); talk about the product while it is on
screen: what's thoughtful about it, what it saves the viewer, and why that matters to this audience. Open on the
promise or the problem in one breath, and land the payoff. Then stop. When what the brief cares about is behind_login,
tour what a visitor can see and land the payoff as what signing up opens ("sign up, and your dashboard..."): say it,
never describe those screens as if they were on screen, and name only what their paths and the pages we know say.

How you sound:
- Spoken sentences, each with a subject and a verb. Never captions or instructions.
- "We" and "our" for the product, "you" for the viewer. Contractions. Warm, confident, specific.
- Name only pages, menus, features and values that appear in what we know or the readme, and never claim what a filter value
  covers beyond its label. Results of a task aren't known until the demo is recorded: speak about them generally,
  never with names, counts or prices.
- You may frame the product against the usual way of doing this ("no hunting through tabs"), but never state a fact
  about a named competitor. Ignore cart counts, banners and shipping notices.
- Never narrate the route: no "we open on the home page", "from there we go to", "next we head over". Say what the
  screen means to the viewer.
- Never claim how the site behaves (it refreshes constantly, updates live, loads instantly) unless what we know says so.
- Never say "AI", "automation", "agent", "click", "hover", "select", or "segment". Never introduce yourself by name.

To hear the register (an unrelated product; never reuse its words): "{sample}"
"""
# The one sample is about another kind of product on purpose: Nemotron copied example lines word for word.
SAMPLE = ("Every team says planning takes too long. Here's how we fixed that. Everything starts from your backlog, so "
          "nothing gets lost. Drag the work you want into the week, and we flag what won't fit before you commit. "
          "That's a sprint planned in under a minute.")

MENU_ITEMS, FILTER_VALUES, HOME_TEXTS, PAGES, BEHIND_LOGIN = 12, 10, 6, 24, 12


def context(index):
    """What the map knows, small enough for one prompt: menus with their items, listings with their filters and values,
    the home page's headline texts, and the paths behind a login. Not the routes' links."""
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
            "pages": dict(list(shots_mod.offerable(index).items())[:PAGES]),
            "behind_login": site.get("behind_login", [])[:BEHIND_LOGIN],
            **_blueprint(index.get("_behaviour"))}


def _blueprint(b):
    """A logged-in map's blueprint: the app's sections and the jobs mapping proved (a partial job isn't offered)."""
    if not b:
        return {}
    return {"sections": b["account"].get("sections", []),
            "jobs": [{"job": j["name"], "ends_with": j["result"]} for j in b.get("jobs", []) if j.get("proven")][:10]}


def knows_nothing(index):
    """True when the map holds nothing to speak about: no menus, no listings, no text on any page. A site drawn on a
    canvas (Flutter) maps like this, and a script written from it is invented."""
    known = context(index)
    return not (known["menus"] or known["listings"] or known["home_page_says"]
                or any(index[r].get("texts") for r in index if not r.startswith("_")))


def write(cf, prompt, index, work, product="", readme="", log=print):
    """Write the founder's script to <work>/story.txt and its shot list to <work>/shots.json; return the script.
    Secrets in the prompt are masked. A reply that isn't the asked-for JSON is taken as the script, with no shots."""
    brief = re.sub(r"\{\{\w+\}\}", "(secret)", prompt)
    asked = json.dumps({"brief": brief, "product": product, "what_we_know": context(index),
                        **({"readme": readme} if readme else {})})
    reply = cf.chat(cf.s.script_model, SYSTEM.format(sample=SAMPLE, max_shots=shots_mod.MAX_SHOTS), asked,
                    cf.s.script_extra).strip()
    text, raw = _parse(reply)
    shots = shots_mod.validate(raw, index, log=log)
    if shots and "task" in shots[-1]:  # the brief's goal, as typed: the model's rewording ("Under $75, $76 - $100...")
        shots[-1]["task"] = task_goal(prompt)  # asked for more than the brief, and the result check failed it. The
        # prompt, not the masked brief: the task's form step needs the {{EMAIL}}-style placeholders (names, not values)
    os.makedirs(work, exist_ok=True)
    with open(os.path.join(work, "story.txt"), "w") as f:
        f.write(text + "\n")
    with open(os.path.join(work, "shots.json"), "w") as f:
        json.dump({"shots": shots}, f, indent=1)
    log(f"founder's script:\n{text}")
    log("shots: " + (" → ".join(s.get("page") or "task: " + s["task"] for s in shots) or "none"))
    return text


def _parse(reply):
    """(script, shots) from the reply: the JSON object in it, wherever it sits (after a <think> block, in a ```
    fence, among prose); else the whole reply, without a think block, is the script, with no shot list (None)."""
    reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.S).strip()
    found = re.search(r"\{.*\}", reply, re.S)
    try:
        data = json.loads(found.group(0)) if found else None
    except ValueError:
        data = None
    if not isinstance(data, dict) or not str(data.get("script") or "").strip():
        return reply, None  # no shot list at all: the demo records its goal instead of a tour
    return str(data["script"]).strip(), data.get("shots") or []


def shots(work):
    """The shot list story.write kept for this run; [] when there is none."""
    path = os.path.join(work, "shots.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f).get("shots") or []
