"""Jev drives from an app index. No LLM route plan.

Each screen, Jev decides: done, act here (the goal's form is on this screen), or navigate. Navigating, every
clickable option is annotated with where it leads (live href, else the code's router.push) and what that screen
contains (from the index). Acting, an LLM supplies only the words to type; Jev picks the submit button and then
confirms "done" once the page has settled. Rules from measurements: act on a form only when Jev is ≥ 0.5 sure.
"""
import time
from urllib.parse import urlparse

from ..browser.elements import describe, words
from ..index import route_for, summary
from ..record.recorder import Recorder
from .guards import blocked, fill_text, on_site
from .session import Session, StalePage, fingerprint

CONFIDENT = 0.5
VALUES = """Fill a web form for the user's goal. Return JSON {"values": {"<field description>": "<text to type>"}} for the
fields the goal gives values for, using the field descriptions exactly as listed. Omit fields the goal doesn't cover.
Secrets appear as placeholders like {{PASSWORD}}: copy them verbatim."""


def run(cf, url, goal, index, out=None, fresh=False, max_steps=12, blur_typed=True, log=print):
    t0 = time.perf_counter()
    ms = lambda: round((time.perf_counter() - t0) * 1000)
    s = Session(url, fresh=fresh)
    rec = Recorder(out, s, blur_typed=blur_typed)
    result = {"goal": goal, "verified": False}
    tried, filled, decisions = set(), set(), 0
    try:
        rec.snap(1.5)
        rec.commit({"do": "open"}, s.page)
        while decisions < max_steps:
            decisions += 1
            page = s.page
            path = urlparse(page["url"]).path
            route = route_for(path, index)
            els = s.elements()
            fields = [e for e in els if "fill" in e["actions"]]
            state = {"goal": goal, "screen": {"url": path, "title": page.get("title", ""),
                                              "from_code": summary(route, index),
                                              "visible_fields": [e["label"][:40] for e in fields][:8],
                                              "visible_text": " ".join((page.get("text") or "").split())[:600]}}
            mode, conf = cf.choose("Given the goal, what should happen on this screen?", {
                "done": "the goal is already accomplished; this screen confirms it",
                "act_here": "the form or control that accomplishes the goal is on this screen: fill it and submit",
                "navigate": "the goal is accomplished on a different screen: go there"}, state)
            if mode == "act_here" and conf < CONFIDENT:
                mode = "navigate"  # calibrated confidence: act on a form only when Jev is sure it's the right one
            log(f"{ms():>6} ms  [{path}] Jev: {mode} ({conf:.2f})")
            if mode == "done":
                result["verified"] = True
                break
            if mode == "act_here" and fields and path not in filled:
                if _fill_and_submit(cf, s, rec, goal, fields, state, log, ms):
                    result["verified"] = True
                    break
                filled.add(path)
                continue
            if not _navigate(cf, s, rec, goal, index, route, path, els, state, tried, log, ms):
                break
    finally:
        rec.save(goal)
        s.close()
    result.update(seconds=round(time.perf_counter() - t0, 1), decisions=decisions, **cf.stats)
    log(f"done in {result['seconds']} s | {decisions} decisions | Jev {cf.stats['jev_calls']} calls, "
        f"{cf.stats['jev_seconds']:.1f} s")
    return result


def _fill_and_submit(cf, s, rec, goal, fields, state, log, ms):
    """Fill the fields the goal gives values for, submit, settle, and ask Jev whether it's done."""
    values = cf.chat_json(cf.s.read_model, VALUES, {"goal": goal, "fields": [e["label"] for e in fields]}).get("values", {})
    for e in fields:
        v = values.get(e["label"])
        if not v:
            continue
        rec.snap(1.0, node=e["node"])
        s.act(e, "fill", text=fill_text(v))
        rec.blur(e["node"])
        time.sleep(0.3)
        rec.snap(0.8)
        rec.commit({"do": "fill", "target": e["label"]}, s.observe())
        log(f"{ms():>6} ms    fill {e['label'][:30]!r}")
    buttons = [e for e in s.elements() if "click" in e["actions"] and e["role"] == "button" and not blocked(e["label"])]
    if not buttons:
        return False
    key, conf = cf.choose("Which button submits this form toward the goal?",
                          {str(e["node"]): describe(e) for e in buttons[:20]}, state)
    b = next(e for e in buttons if str(e["node"]) == key)
    rec.snap(1.0, node=b["node"])
    before = s.observe().get("text") or ""
    s.act(b, "click")
    page = s.settle(before)
    rec.snap(1.5)
    rec.commit({"do": "click", "target": b["label"]}, page)
    log(f"{ms():>6} ms    submit {b['label'][:30]!r} ({conf:.2f})")
    for attempt in range(2):  # not confirmed yet? let the page settle once more and ask again before moving on
        done = cf.yes("Does this screen confirm the goal was accomplished?",
                      {"goal": goal, "just_did": f"submitted the form with '{b['label']}'",
                       "visible_text": " ".join((page.get("text") or "").split())[:800]},
                      true="the page confirms success", false="not confirmed yet, or an error")
        log(f"{ms():>6} ms  Jev: done? {done:.2f}")
        if done >= CONFIDENT or attempt:
            break
        page = s.settle(page.get("text") or "", max_s=4)
    if done >= CONFIDENT and rec.out:  # the confirmation screen is the demo's last frame
        rec.snap(2.0)
        rec.commit({"do": "confirm", "target": "confirmation"}, page)
    return done >= CONFIDENT


def _navigate(cf, s, rec, goal, index, route, path, els, state, tried, log, ms):
    """Annotate each option with where it leads, per the index; Jev picks one; click it."""
    options = []
    for e in els:
        if "click" not in e["actions"] or blocked(e["label"]) or (path, e["node"]) in tried:
            continue
        href = s.href(e["node"])
        if href and not on_site(href, s.host):
            continue
        dest = urlparse(href).path if href else None
        if dest is None and route:  # a button: does the code navigate somewhere on click?
            code = next((l for l in index[route]["links"] if words(l["label"]) and words(l["label"]) == words(e["label"])), None)
            dest = code["to"] if code and code["to"].startswith("/") else None
        where = (f"→ {dest}: {summary(route_for(dest, index), index, 4)}" if dest and dest != path
                 else "→ stays on this screen (menu or section)")
        options.append((e, where))
        if len(options) >= 30:
            break
    if not options:
        log("STUCK: no options left")
        return False
    key, conf = cf.choose("Which option moves toward the screen where the goal is accomplished?",
                          {str(e["node"]): f"{e['label'][:50]} {w}"[:300] for e, w in options}, state)
    e, where = next(o for o in options if str(o[0]["node"]) == key)
    tried.add((path, e["node"]))
    rec.snap(1.2, node=e["node"])
    before = fingerprint(s.observe())
    try:
        s.act(e, "click")
    except StalePage:
        rec.discard()
        s.observe()
        return True
    time.sleep(0.6)
    page = s.observe()
    rec.snap(0.8)
    if not on_site(page["url"], s.host):
        log(f"GUARD: left {s.host}; stopped")
        rec.discard()
        return False
    rec.commit({"do": "click", "target": e["label"]}, page)
    log(f"{ms():>6} ms    click {e['label'][:34]!r} {where[:70]} ({conf:.2f})"
        f"{'' if fingerprint(page) != before else '  [no change]'}")
    return True
