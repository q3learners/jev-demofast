"""The tour: the recorder plays the founder's shot list. Each page is reached the way a person would (its link on
screen, else straight there), shown with a glide down it, and the brief's task, when there is one, ends the demo.

Given only a goal, the recorder took the shortest path and stopped: one click to tutorq.ai/sat for a script about
four products. The shots come from the founder's script (narrate/story.py), checked against the map.
"""
import time
from urllib.parse import urlparse

from ..narrate.shots import offerable
from ..record.recorder import Recorder
from .guards import DryRunStop, HazardStop, on_site
from .jev_drive import click_on_camera, drive_goal
from .menus import LEFT_SITE
from .popups import clear_popups, covered, first_screen
from .session import Session, address, origin
from .showcase import showcase

# A page is shown with glides a viewer can follow: a jump between two stills read as a cut, never as a scroll.
GLIDES = 2            # stops per page: past the banner, then into the page (one "look" moment for the voice-over)
SCROLL_FRACTION = 0.8  # of a screen, per glide
GLIDE_FRAMES = 12      # frames per glide, eased: about 0.8 s on screen
FRAME_S = 1 / 15
PAUSE_S, HOLD_S = 1.0, 1.5  # on the screen between glides, and after the last
LONE_PAGE_GLIDES = 6  # a one-page site is shown down its page, each stop a moment of its own for the voice-over
TASK_STEPS = 12
CAN_SCROLL = "scrollY + innerHeight < document.documentElement.scrollHeight - 40"
# "instant", as in each step of a glide: selvage.run's scroll-behavior: smooth turned the jump to the top into an animation,
# and the tour clicked a link it saw near the bottom as it slid away.
TO_TOP = "window.scrollTo({top: 0, behavior: 'instant'})"
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
        landed = urlparse(s.page["url"]).hostname  # "allbirds.com" as typed lands on www.allbirds.com
        known, buttons = offerable(index), button_labels(index)
        if len(shots) == 1:
            _show_down(s, rec, shots[0]["show"])
        else:
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
            problem = _reach(s, rec, shot["page"], i, shot["show"], landed, known.get(shot["page"], []),
                             buttons.get(shot["page"], {}))
            if problem:
                rec.discard()
                result["skipped"].append(shot["page"])
                log(f"{ms():>6} ms  skipped shot {shot['page']}: {problem}")
                continue
            log(f"{ms():>6} ms  shot {i}: {shot['page']} ({rec.actions[-1]['do']})")
            _show(s, rec, i, shot["show"])
            if shot.get("items"):  # the screen's point is what it lists (Amazon's hot new releases): name a few
                before = len(rec.actions)
                showcase(cf, s, rec, shot["show"], log)
                for action in rec.actions[before:]:
                    action.update(shot=i, show=shot["show"])
        result["verified"] = task_ok and not result["skipped"]
        if not task_ok:
            rec.unconfirmed(why)  # the task's own reason, on the task's last moment
        # a skipped page lowers the verdict and is listed on the result page, but isn't a moment to speak about: as
        # an outcome, the voice-over said "We couldn't reach the contact page" in a pitch
    except DryRunStop as stop:
        result["would_click"] = str(stop)
        log(f"{ms():>6} ms  DRY RUN: stopped before {str(stop)!r}; nothing was changed")
    except HazardStop as stop:  # a logged-in run never pays, deletes or logs out: the demo ends before that step
        result["stopped_at"] = str(stop)
        log(f"{ms():>6} ms  the next step is {str(stop)!r}; the demo stops here")
    finally:
        rec.save(goal, cf.decisions, skipped=result["skipped"])
        s.close()
    result.update(seconds=round(time.perf_counter() - t0, 1), decisions=steps[0], **cf.stats)
    log(f"done in {result['seconds']} s | {len(shots)} shots, {len(result['skipped'])} skipped | "
        f"Jev {cf.stats['jev_calls']} calls, {cf.stats['jev_seconds']:.1f} s")
    return result


def _path(url):
    return urlparse(url).path.rstrip("/") or "/"


def arrived(page_now, page, host, landed, texts):
    """On the shot's page: its path on the site's own host, or (a redirect, e.g. tutorq.ai/campus → campus.tutorq.ai)
    a screen showing what the map read on that page. A redirect home or to a login wall shows neither."""
    url = page_now["url"]
    if not on_site(url, host):
        return False
    if urlparse(url).hostname == landed and same_page(url, page):
        return True
    screen = " ".join((page_now.get("text") or "").split())
    return any(" ".join(t.split()) in screen for t in texts if t)


def button_labels(index):
    """{page: {page it was found on: [label, ...]}}: the buttons the explorer found leading to each page (a Flutter
    app has no href links). A label counts only where it was found: K-12's "Sign in" navigates on its who page and
    submits on its kid page."""
    found = {}
    for route, entry in index.items():
        if route.startswith("_"):
            continue
        for link in entry.get("links") or []:
            if link.get("via") != "button":
                continue
            for source in entry.get("examples") or [route]:
                labels = found.setdefault(link["to"], {}).setdefault(source, [])
                if link["label"] not in labels:
                    labels.append(link["label"])
    return found


def same_page(url, page):
    """`url` shows `page`: by path, or for a page known by its query or hash route (found through a button), by both."""
    if "?" in page or "#/" in page:
        return address(url).rstrip("/") == page.rstrip("/")
    return _path(url) == _path(page)


def _first_line(label):
    return (label or "").strip().split("\n")[0].strip()


def _reach(s, rec, page, i, show, landed, texts, found_on=None):
    """Go to the shot's page on camera. Returns why it couldn't, or None once there. `found_on`: {page: [labels]} of
    the buttons that lead there, by the page they were found on."""
    if same_page(s.page["url"], page) and urlparse(s.page["url"]).hostname == landed:
        return None
    labels = (found_on or {}).get(address(s.page["url"]), [])
    _to_top(s)  # the navigation is at the top, where a person would scroll back to
    action = {"shot": i, "show": show}
    link = next((e for e in s.elements() if "click" in e["actions"] and _leads_to(s, e, page, landed)), None)
    if link is None and labels:  # no href leads there: the button the map found leading there, clicked on camera
        link = next((e for e in s.elements() if "click" in e["actions"] and _first_line(e["label"]) in labels), None)
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
    if not arrived(s.page, page, s.host, landed, texts):
        return f"it opened {s.page['url']}"
    return None


def _to_top(s):
    s.browser.evaluate(TO_TOP)
    s.next_frame()
    s.observe()


def _leads_to(s, e, page, landed):
    href = s.href(e["node"])
    return bool(href) and urlparse(href).hostname == landed and same_page(href, page)


def scroll_by(fraction):
    """One step of a glide; "instant", so a site's own smooth scrolling doesn't land between two frames."""
    return f"window.scrollBy({{top: Math.round(innerHeight * {fraction:.4f}), behavior: 'instant'}})"


def _ease(t):
    return t * t * (3 - 2 * t)


GLIDE = [SCROLL_FRACTION * (_ease(k / GLIDE_FRAMES) - _ease((k - 1) / GLIDE_FRAMES)) for k in range(1, GLIDE_FRAMES + 1)]


def _show(s, rec, i, show):
    """Glide down the page, a screen at a time, so the viewer sees it move; a page that fits on screen isn't moved.
    The whole of it is one "look" moment, with the headings seen at each stop."""
    headings, glided = [], 0
    for g in range(GLIDES):
        seen = _glide(s, rec, HOLD_S if g == GLIDES - 1 else PAUSE_S)
        if seen is None:
            break
        headings += [h for h in seen if h not in headings]
        glided += 1
    if glided:
        rec.commit({"do": "look", "shot": i, "show": show, "headings": headings}, s.observe())


def _show_down(s, rec, show):
    """A one-page site: glide down its page, each stop a moment (a shot) of its own."""
    for g in range(1, LONE_PAGE_GLIDES + 1):
        seen = _glide(s, rec, HOLD_S)
        if seen is None:
            return
        rec.commit({"do": "look", "shot": g, "show": show, "headings": seen}, s.observe())


def _glide(s, rec, hold):
    """One glide down, about a screen, recorded frame by frame; the headings then on screen, or None at the page's end."""
    if not s.browser.evaluate(CAN_SCROLL):
        return None
    for step in GLIDE:
        s.browser.evaluate(scroll_by(step))
        s.next_frame()
        rec.snap(FRAME_S)
    s.wait_for_page()  # lazy images fill in before the held frame
    rec.snap(hold)
    return s.browser.evaluate(HEADINGS) or []
