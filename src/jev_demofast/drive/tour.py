"""The tour: the recorder plays the founder's shot list. Each page is reached the way a person would (its link on
screen, else straight there), shown with a scroll or two, and the brief's task, when there is one, ends the demo.

Given only a goal, the recorder took the shortest path and stopped: one click to tutorq.ai/sat for a script about
four products. The shots come from the founder's script (narrate/story.py), checked against the map.
"""
import time
from urllib.parse import urlparse

from ..record.recorder import Recorder
from .guards import DryRunStop, on_site
from .jev_drive import click_on_camera, drive_goal
from .menus import LEFT_SITE
from .popups import clear_popups, covered, first_screen
from .session import Session, origin

SCROLL_STEPS = 1  # about one screen: the viewer sees past the top banner (two per page made tutorq.ai 89 s long)
TASK_STEPS = 12
CAN_SCROLL = "scrollY + innerHeight < document.documentElement.scrollHeight - 40"
SCROLL = "window.scrollBy(0, Math.round(innerHeight * 0.8))"
TO_TOP = "window.scrollTo(0, 0)"
HEADINGS = ("[...document.querySelectorAll('h1,h2,h3')].filter(h => { const r = h.getBoundingClientRect(); "
            "return r.bottom > 0 && r.top < innerHeight && h.innerText.trim(); })"
            ".slice(0, 4).map(h => h.innerText.trim().slice(0, 80))")


def run(cf, url, shots, index, out=None, fresh=False, dry_run=False, log=print, session=Session, recorder=Recorder):
    """Record the shots in order. The result is jev_drive.run's, plus "skipped": the pages that couldn't be shown."""
    t0 = time.perf_counter()
    ms = lambda: round((time.perf_counter() - t0) * 1000)
    task = next((shot["task"] for shot in shots if "task" in shot), None)
    goal = task or "tour: " + " → ".join(shot["page"] for shot in shots if "page" in shot)
    s = session(url, fresh=fresh)
    rec = recorder(out, s)
    rec.dry_run = dry_run
    log = rec.tee(log)
    result = {"goal": goal, "verified": False, "dry_run": dry_run, "skipped": []}
    steps, task_ok, why = [0], True, ""
    try:
        first_screen(cf, s, log)  # the opening frame is the product, never a pop-up (as jev_drive.run)
        rec.snap(1.5)
        if covered(s):
            clear_popups(cf, s, log)
            rec.discard()
            rec.snap(1.5)
        rec.commit({"do": "open", "shot": 0, "show": shots[0]["show"]}, s.observe())
        _show(s, rec, 0, shots[0]["show"])
        for i, shot in enumerate(shots[1:], 1):
            clear_popups(cf, s, log)
            if "task" in shot:
                _to_top(s)  # the task starts where its controls are (Allbirds' filters were scrolled away)
                before = len(rec.actions)
                task_ok, why = drive_goal(cf, s, rec, shot["task"], index, TASK_STEPS, log, ms, steps)
                for action in rec.actions[before:]:
                    action.update(shot=i, show=shot["show"])
                continue
            problem = _reach(s, rec, shot["page"], i, shot["show"])
            if problem:
                rec.discard()
                result["skipped"].append(shot["page"])
                log(f"{ms():>6} ms  skipped shot {shot['page']}: {problem}")
                continue
            log(f"{ms():>6} ms  shot {i}: {shot['page']} ({rec.actions[-1]['do']})")
            _show(s, rec, i, shot["show"])
        if result["skipped"]:
            why = "couldn't show " + ", ".join(result["skipped"])
        result["verified"] = task_ok and not result["skipped"]
        if not result["verified"]:
            rec.unconfirmed(why)
    except DryRunStop as stop:
        result["would_click"] = str(stop)
        log(f"{ms():>6} ms  DRY RUN: stopped before {str(stop)!r}; nothing was changed")
    finally:
        rec.save(goal, cf.decisions)
        s.close()
    result.update(seconds=round(time.perf_counter() - t0, 1), decisions=steps[0], **cf.stats)
    log(f"done in {result['seconds']} s | {len(shots)} shots, {len(result['skipped'])} skipped | "
        f"Jev {cf.stats['jev_calls']} calls, {cf.stats['jev_seconds']:.1f} s")
    return result


def _path(url):
    return urlparse(url).path.rstrip("/") or "/"


def arrived(url, page, host):
    """On the shot's page: its path, or a redirect to another host of the site (tutorq.ai/campus → campus.tutorq.ai)."""
    return on_site(url, host) and (_path(url) == _path(page) or urlparse(url).hostname != host)


def _reach(s, rec, page, i, show):
    """Go to the shot's page on camera. Returns why it couldn't, or None once there."""
    if _path(s.page["url"]) == _path(page) and urlparse(s.page["url"]).hostname == s.host:
        return None
    _to_top(s)  # the navigation is at the top, where a person would scroll back to
    action = {"shot": i, "show": show}
    link = next((e for e in s.elements() if "click" in e["actions"] and _leads_to(s, e, page)), None)
    try:
        if link:
            got = click_on_camera(s, rec, link, {"do": "click", "target": link["label"], **action})
            if got is None:
                return "the page changed under the click"
        else:
            s.browser.call("Page.navigate", url=origin(s.start_url) + page)  # a cut, for a page with no link here
            s.wait_loaded()
            s.wait_for_page()
            got = s.observe()
            if not on_site(got["url"], s.host):
                got = LEFT_SITE
            else:
                rec.snap(1.0)
                rec.commit({"do": "go", "target": page, **action}, got)
    except TimeoutError:
        return "it didn't load"
    if got is LEFT_SITE:
        return "it led off the site"
    if not arrived(s.page["url"], page, s.host):
        rec.actions[-1]["outcome"] = f"not confirmed: it opened {s.page['url']} instead of {page}"
        return f"it opened {s.page['url']}"
    return None


def _to_top(s):
    s.browser.evaluate(TO_TOP)
    s.next_frame()
    s.observe()


def _leads_to(s, e, page):
    href = s.href(e["node"])
    return bool(href) and urlparse(href).hostname == s.host and _path(href) == _path(page)


def _show(s, rec, i, show):
    """Scroll through the page, a screen at a time, so the viewer sees it; a page that fits on screen isn't moved."""
    for _ in range(SCROLL_STEPS):
        if not s.browser.evaluate(CAN_SCROLL):
            return
        s.browser.evaluate(SCROLL)
        s.next_frame()
        s.wait_for_page()
        rec.snap(1.5)
        rec.commit({"do": "look", "shot": i, "show": show, "headings": s.browser.evaluate(HEADINGS) or []},
                   s.observe())
