"""Jev drives from an app index. No LLM route plan.

Each screen, Jev decides: done, act here (the goal's form is on this screen), or navigate. Navigating, every
clickable option is annotated with where it leads (live href, else the code's router.push) and what that screen
contains (from the index). Acting, an LLM supplies only the words to type; Jev picks the submit button and then
confirms "done" once the page has settled. Rules from measurements: act on a form only when Jev is ≥ 0.5 sure.
"""
import base64
import time
from urllib.parse import urlparse

from ..browser.elements import describe, words
from ..index import route_for, summary
from ..record.recorder import Recorder
from .check import goal_reached
from .filters import apply_filters, url_agrees
from .guards import DryRunStop, blocked, fill_text, on_site, password_secret, stop_if_dry_run
from .menus import LEFT_SITE, describe_menu, menu_options, open_menu
from .popups import clear_popups, covered, first_screen
from .showcase import reveal_results, showcase
from .session import Session, StalePage, fingerprint

CONFIDENT = 0.5
VALUES = """Fill ONE web form for the user's goal. Return JSON {"values": {"<field description>": "<text to type>"}} for
the fields the goal gives values for, using the field descriptions exactly as listed. Omit fields the goal doesn't cover.
A goal can span several forms (e.g. sign in, then invite someone): use the screen and what's already done to tell which
part of the goal THIS form serves, and give only the values meant for this form (an invite form gets the invitee's
email, not the signed-in user's). Secrets appear as placeholders like {{PASSWORD}}: copy them verbatim."""


def run(cf, url, goal, index, out=None, fresh=False, max_steps=12, blur_typed=True, dry_run=False, log=print):
    t0 = time.perf_counter()
    ms = lambda: round((time.perf_counter() - t0) * 1000)
    s = Session(url, fresh=fresh)
    rec = Recorder(out, s, blur_typed=blur_typed)
    rec.dry_run = dry_run
    log = rec.tee(log)
    result = {"goal": goal, "verified": False, "dry_run": dry_run}
    decisions = [0]
    try:
        # The opening frame is the product, never a marketing pop-up ("Unlock 10% Off" opened two videos): watch for a
        # first-visit pop-up and clear it, and retake the frame if one lands just as it's taken.
        first_screen(cf, s, log)
        rec.snap(1.5)
        if covered(s):
            clear_popups(cf, s, log)
            rec.discard()
            rec.snap(1.5)
        rec.commit({"do": "open"}, s.observe())
        result["verified"], why = drive_goal(cf, s, rec, goal, index, max_steps, log, ms, decisions)
        if not result["verified"]:
            rec.unconfirmed(why)
    except DryRunStop as stop:
        result["would_click"] = str(stop)
        log(f"{ms():>6} ms  DRY RUN: stopped before {str(stop)!r}; nothing was changed")
    finally:
        rec.save(goal, cf.decisions)
        s.close()
    result.update(seconds=round(time.perf_counter() - t0, 1), decisions=decisions[0], **cf.stats)
    log(f"done in {result['seconds']} s | {decisions[0]} decisions | Jev {cf.stats['jev_calls']} calls, "
        f"{cf.stats['jev_seconds']:.1f} s")
    return result


def drive_goal(cf, s, rec, goal, index, max_steps, log, ms, steps=None):
    """From the screen the session is on, drive to the goal: done, act here, or navigate, screen by screen. Returns
    (verified, why not); `steps` (a one-item list) counts the decisions, even when a dry run stops it."""
    steps = steps if steps is not None else [0]
    verified = False
    tried, filled, history = set(), set(), []
    explored, expected = "_site" in index, []  # an explored map: screenshot check, filters, a showcase ending
    why = "it ran out of steps"  # what the narration says if the goal isn't reached
    while steps[0] < max_steps:
        steps[0] += 1
        clear_popups(cf, s, log)  # marketing pop-ups open on timers, on any screen
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
        entry = index.get(route or "", {})
        filterable = explored and entry.get("kind") == "listing" and entry.get("filters") and path not in filled
        if explored and mode == "done":
            ok, score = _explored_verdict(cf, goal, s, expected)
            if ok or not filterable:
                log(f"{ms():>6} ms  {'VERIFIED' if ok else 'NOT REACHED'}: the screen shows the goal? {score:.2f}")
                verified = ok
                if ok:
                    showcase(cf, s, rec, goal, log)
                why = "the screen didn't show the goal accomplished"
                break
            mode = "act_here"  # Jev thought this listing was enough, but it isn't filtered as the goal asks yet
        if mode == "act_here" and filterable:
            unavailable = []
            expected = apply_filters(cf, s, rec, goal, entry, log, unavailable=unavailable)
            filled.add(path)
            rec.note_unavailable(unavailable)
            if expected is None:
                log(f"GUARD: left {s.host}; stopped")
                why = f"a click led away from {s.host}"
                break
            reveal_results(s)  # the check looks at the results, not the panel still open over them
            ok, score = _explored_verdict(cf, goal, s, expected)
            log(f"{ms():>6} ms  {'VERIFIED' if ok else 'NOT REACHED'}: filtered listing shows the goal? {score:.2f}"
                f"{'' if url_agrees(s.page['url'], expected) else ' (the URL lacks the filters)'}")
            verified = ok
            if ok:
                showcase(cf, s, rec, goal, log)
            why = ("the site has no results for " + " and ".join(unavailable) + " with the other filters"
                   if unavailable else "the filtered listing didn't show what the goal asks for")
            break
        if mode == "done":
            # "done" counts only if the screen itself confirms it: after a refused invite, Jev once chose "done"
            # (0.70) on a page saying "User is already a member of this team" while the page check said 0.25.
            verified = confirmed(cf, goal, page)
            if not verified:
                log(f"{ms():>6} ms  NOT CONFIRMED: the screen doesn't show the goal accomplished; stopping")
                why = "the screen didn't show the goal accomplished"
            break
        if mode == "act_here" and fields and path not in filled and explored:
            # An explored map never verifies through the text check: a search box's results page reading "results
            # for running shoes under $100" fooled it. The form goes through the screenshot check like the rest.
            _fill_and_submit(cf, s, rec, goal, fields, state, history, log, ms, need_values=True)
            filled.add(path)
            ok, score = _explored_verdict(cf, goal, s, expected)
            log(f"{ms():>6} ms  {'VERIFIED' if ok else 'NOT REACHED'}: the screen shows the goal? {score:.2f}")
            if ok:
                verified = True
                showcase(cf, s, rec, goal, log)
                break
            continue
        if mode == "act_here" and fields and path not in filled:
            if _fill_and_submit(cf, s, rec, goal, fields, state, history, log, ms):
                verified = True
                break
            filled.add(path)
            continue
        if not _navigate(cf, s, rec, goal, index, route, path, els, state, tried, history, log, ms):
            why = "it found no way to the screen where the goal is done"
            break
    return verified, why

def _fill_and_submit(cf, s, rec, goal, fields, state, history, log, ms, need_values=False):
    """Fill the fields the goal gives values for, submit, settle, and ask Jev whether it's done."""
    values = cf.chat_json(cf.s.read_model, VALUES, {
        "goal": goal, "already_done": history[-6:], "fields": [e["label"] for e in fields],
        "screen": {"title": state["screen"]["title"], "text": state["screen"]["visible_text"][:500]}}).get("values", {})
    for e in fields:
        v = values.get(e["label"])
        if not v:
            continue
        rec.snap(1.0, node=e["node"])
        s.act(e, "fill", text=fill_text(v))
        rec.blur(e["node"])
        s.next_frame()
        rec.snap(0.8)
        rec.commit({"do": "fill", "target": e["label"]}, s.observe())
        log(f"{ms():>6} ms    fill {e['label'][:30]!r}")
        history.append(f"filled {e['label'][:40]} on {state['screen']['url']}")
    if need_values and not any(values.get(e["label"]) for e in fields):  # nothing to type: don't press submit blindly
        return False
    # Passwords are hidden from observation by design: type a {{NAME}} secret from the goal straight into the field.
    secret = password_secret(goal)
    if secret and s.type_secret_into_password(fill_text("{{" + secret + "}}")):
        s.next_frame()
        rec.snap(0.8)
        rec.commit({"do": "fill", "target": "password (typed directly; never shown)"}, s.observe())
        log(f"{ms():>6} ms    fill password (typed directly; value never shown)")
    _choose_options(cf, s, rec, goal, state, log, ms)
    buttons = [e for e in s.elements() if "click" in e["actions"] and e["role"] == "button" and not blocked(e["label"])]
    if not buttons:
        return False
    key, conf = cf.choose("Which button submits this form toward the goal?",
                          {str(e["node"]): describe(e) for e in buttons[:20]}, state)
    b = next(e for e in buttons if str(e["node"]) == key)
    _stop_if_dry_run(rec, b, s)
    rec.snap(1.0, node=b["node"])
    before_url = s.page["url"]
    before = s.observe().get("text") or ""
    s.act(b, "click")
    page = s.settle(before)
    rec.snap(1.5)
    rec.commit({"do": "click", "target": b["label"]}, page)
    log(f"{ms():>6} ms    submit {b['label'][:30]!r} ({conf:.2f})")
    history.append(f"submitted '{b['label'][:40]}' on {state['screen']['url']}")
    for attempt in range(2):  # not confirmed yet? let the page settle once more and ask again before moving on
        done = confirm_score(cf, goal, page, f"submitted the form with '{b['label']}'")
        log(f"{ms():>6} ms  Jev: done? {done:.2f}")
        if done >= CONFIDENT or attempt or page["url"] != before_url:
            break  # moved to another page: that was a step of the goal, not its end, so no second wait
        page = s.settle(page.get("text") or "", max_s=4)
    if done >= CONFIDENT and rec.out:  # the confirmation screen is the demo's last frame
        rec.snap(2.0)
        rec.commit({"do": "confirm", "target": "confirmation"}, page)
    elif page["url"] == before_url and rec.actions:
        # Still on the form's page and not confirmed: the submit failed or was refused. Tell the narrator, so the
        # voice-over says what went wrong instead of describing a success. (A sign-in that moves to another page is
        # a step of the goal, not a failure.)
        rec.actions[-1]["outcome"] = "not confirmed: the page did not show success"
    return done >= CONFIDENT


def _explored_verdict(cf, goal, s, expected):
    """Explored maps: the screen must show the goal (Clef + screenshot, 0.75) and the URL must carry the filters the
    map knows the URL form of."""
    clear_popups(cf, s, lambda m: None)  # a timed pop-up in the screenshot would spoil the verdict
    shot = lambda: base64.b64decode(s.browser.call("Page.captureScreenshot", format="jpeg", quality=80)["data"])
    ok, score = goal_reached(cf, goal, s.observe(), shot)
    return ok and url_agrees(s.page["url"], expected), score


def confirm_score(cf, goal, page, just_did=None):
    """Jev's probability that this screen confirms the goal was accomplished."""
    state = {"goal": goal, "visible_text": " ".join((page.get("text") or "").split())[:800]}
    if just_did:
        state["just_did"] = just_did
    return cf.yes("Does this screen confirm the goal was accomplished?", state,
                  true="the page confirms success", false="not confirmed yet, or an error")


def confirmed(cf, goal, page):
    return confirm_score(cf, goal, page) >= CONFIDENT


def _choose_options(cf, s, rec, goal, state, log, ms):
    """Radio buttons / checkboxes on the form: Jev picks the one the goal calls for; clicked only if not already set."""
    opts = [e for e in s.elements() if e["role"] in ("radio", "checkbox") and "click" in e["actions"] and not blocked(e["label"])]
    if not opts:
        return
    key, conf = cf.choose("Which option does the goal call for on this form? 'none' if the goal doesn't mention any.",
                          {str(e["node"]): f"{e['role']} {e['label'][:60]} ({e['current']})" for e in opts[:20]},
                          state, allow_none=True)
    e = next((o for o in opts if str(o["node"]) == key), None)
    if e is None or conf < CONFIDENT:
        log(f"{ms():>6} ms    options: leave as they are ({conf:.2f})")
        return
    if e["current"] == "checked":
        log(f"{ms():>6} ms    option {e['label'][:30]!r} already selected ({conf:.2f})")
        return
    _stop_if_dry_run(rec, e, s)
    rec.snap(1.0, node=e["node"])
    s.act(e, "click")
    s.next_frame()
    rec.snap(0.8)
    rec.commit({"do": "click", "target": e["label"]}, s.observe())
    log(f"{ms():>6} ms    select {e['label'][:30]!r} ({conf:.2f})")


def _navigate(cf, s, rec, goal, index, route, path, els, state, tried, history, log, ms):
    """Annotate each option with where it leads, per the index; Jev picks one; click it."""
    # a menu that didn't open earlier is offered as the plain control it is (Nike's "Men" is also a link)
    menus = {n: m for n, m in menu_options(index, els, s.page.get("actions")).items() if ("menu", path, n) not in tried}
    options = []
    for e in els:
        if "click" not in e["actions"] or blocked(e["label"]) or (path, e["node"]) in tried:
            continue
        if e["node"] in menus:  # the map knows what this opener holds: offer the menu, opened on camera
            options.append((e, describe_menu(menus[e["node"]])))
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
    if e["node"] in menus:
        item = open_menu(cf, s, rec, e, menus[e["node"]], goal, state, log, index)
        if item is None:
            tried.discard((path, e["node"]))
            tried.add(("menu", path, e["node"]))
        if item is LEFT_SITE:
            log(f"GUARD: left {s.host}; stopped")
            return False
        if item:
            history.append(f"opened the {e['label'][:30]} menu and clicked '{item[:40]}' on {path}")
        return True
    before = fingerprint(s.observe())
    page = click_on_camera(s, rec, e, {"do": "click", "target": e["label"]})
    if page is None:
        return True
    if page is LEFT_SITE:
        log(f"GUARD: left {s.host}; stopped")
        return False
    history.append(f"clicked '{e['label'][:40]}' on {path}")
    log(f"{ms():>6} ms    click {e['label'][:34]!r} {where[:70]} ({conf:.2f})"
        f"{'' if fingerprint(page) != before else '  [no change]'}")
    return True


def click_on_camera(s, rec, e, action):
    """Click `e` with the viewer watching: outlined, clicked, the next screen settled, then kept as one segment with
    `action`. Returns the new page; None if the page changed under the click (nothing kept); LEFT_SITE if the click
    led off the site (nothing kept). A dry run stops before a click that would change data."""
    _stop_if_dry_run(rec, e, s)
    rec.snap(1.2, node=e["node"])
    try:
        s.act(e, "click")
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
    rec.commit(action, page)
    return page


_stop_if_dry_run = stop_if_dry_run
