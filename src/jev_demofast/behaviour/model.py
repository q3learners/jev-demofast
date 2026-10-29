"""The behaviour map's shape: the product's blueprint. Screens (pages, tabs, dialogs, wizard steps), the actions
mapping tried with what each did, the jobs those actions add up to, and the account's state.

It's stored under "_behaviour" next to today's route entries; every reader of a map skips keys that start with "_",
so the story and the recording keep working on legacy_routes() until they read the blueprint itself."""
from ..drive.session import address

KINDS = {"dialog": "dialog", "wizard-step": "step"}


def empty():
    return {"account": {"state": None, "sections": []}, "screens": {}, "actions": [], "jobs": [], "left": [],
            "chains": []}


def screen_key(url, title=None, kind="page"):
    """Stable across visits: the address as the explorer keeps it, plus the title of a dialog or a wizard step
    ("/setup/kids" and "/setup/kids · dialog: Add Maya first?" are two screens)."""
    key = address(url)
    return f"{key} · {KINDS[kind]}: {title}" if kind in KINDS and title else key


def add_screen(m, key, screen, now):
    m["screens"][key] = {**m["screens"].get(key, {}), **screen, "last_seen": now}
    m["screens"][key].pop("gone", None)


def add_action(m, screen_key_, control, did, outcome, now, values=None):
    """The action's index; the same control tried the same way again updates its entry."""
    for i, a in enumerate(m["actions"]):
        if (a["screen"], a["control"], a["did"]) == (screen_key_, control, did):
            a.update(outcome=outcome, tried_at=now, **({"values": values} if values else {}))
            return i
    m["actions"].append({"screen": screen_key_, "control": control, "did": did, "outcome": outcome, "tried_at": now,
                         **({"values": values} if values else {})})
    return len(m["actions"]) - 1


def merge(saved, fresh, seen_sections, now):
    """A new crawl folded into a saved map. What the crawl saw wins; a saved screen of a section the crawl walked
    again, but didn't see, is marked gone (kept: a job may still name it). Other sections stay as they were."""
    if not saved:
        return fresh
    m = {**saved, "account": fresh["account"], "left": fresh["left"]}
    m["screens"] = dict(saved["screens"])
    for key, screen in m["screens"].items():
        if screen.get("section") in seen_sections and key not in fresh["screens"]:
            m["screens"][key] = {**screen, "gone": True}
    m["screens"].update(fresh["screens"])
    m["actions"] = [dict(a) for a in saved["actions"]]
    moved = [add_action(m, a["screen"], a["control"], a["did"], a["outcome"], a["tried_at"], a.get("values"))
             for a in fresh["actions"]]  # a fresh action's index in the merged list
    chains = [list(c) for c in saved.get("chains", [])] + [[moved[i] for i in c] for c in fresh.get("chains", [])]
    m["chains"] = [c for n, c in enumerate(chains) if c not in chains[:n]]
    m["jobs"] = fresh["jobs"] or saved["jobs"]
    return m


def typed_by_mapping(m):
    """Every value mapping typed: what it added (a kid called Maya) isn't a change in the product."""
    return {v for a in m.get("actions", []) for v in (a.get("values") or {}).values()}


def legacy_routes(m, origin):
    """Today's route entries, one per page or tab address (a dialog or a step belongs to its page)."""
    routes = {}
    for key, s in m["screens"].items():
        if s.get("kind") in KINDS or s.get("gone"):
            continue
        entry = routes.setdefault(key, {"file": f"explored: {s.get('url') or origin + key}", "submits": False,
                                        "examples": [key], "links": [], "buttons": [], "fields": [], "texts": [],
                                        "kind": "page", "filters": [], "sort": None, "sign_in": False})
        entry["buttons"] += [{"label": c, "submit": False} for c in s.get("controls", [])
                             if {"label": c, "submit": False} not in entry["buttons"]]
        entry["fields"] += [f for f in s.get("fields", []) if f not in entry["fields"]]
        entry["texts"] += [t for t in s.get("texts", []) if t not in entry["texts"]]
    return routes
