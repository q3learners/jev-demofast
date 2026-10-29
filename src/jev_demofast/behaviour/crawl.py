"""The walk through the signed-in app that writes the blueprint: the account's state, every section, every control
mapping may press, back to where it started each time, within budget. Every press goes through Session.act, so the
login branch's safety rules (hazard labels, the money judge, the own-email rule) apply unchanged."""
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

from ..drive.guards import HazardStop, on_site
from ..drive.session import StalePage
from . import forms, jobs
from .model import add_action, add_screen, empty, merge, typed_by_mapping
from .rules import ADDS, may_press, outcome
from .screens import nav_labels, read_screen, sections

ACCOUNT = """You see the first screen of a web app right after signing in. Is the account still partway through a setup
or onboarding flow it hasn't finished (a step list with a "current step", a "finish setting up" screen)? Reply with
JSON only: {"setup_unfinished": true|false, "current_step": "<the current step's name as shown, or empty>"}."""


def account_state(cf, screen, log=print):
    """"set up", "partway: <step>", or "unknown" when the model can't say (never guessed)."""
    try:
        ans = cf.chat_json(cf.s.read_model, ACCOUNT, {"texts": screen.get("texts", []),
                                                      "controls": screen.get("controls", [])[:30]})
    except Exception as err:
        log(f"blueprint: couldn't read the account's state ({type(err).__name__})")
        return "unknown"
    if not isinstance(ans, dict) or "setup_unfinished" not in ans:
        return "unknown"
    step = str(ans.get("current_step") or "").strip()
    return f"partway: {step}" if ans["setup_unfinished"] else "set up"





@dataclass
class Budget:
    total_s: float = 1200  # the founder: 10-20 minutes for a first map is fine, because it's reused
    steps_per_section: int = 40
    items_per_list: int = 2  # one or two subjects, not all forty


@dataclass
class _Walk:
    """One crawl's moving parts: the session (replaced when the way back is lost), the map, the clock."""
    s: object
    new_session: object
    cf: object
    m: dict
    budget: Budget
    started: float
    now: str
    log: object
    nav: list = field(default_factory=list)
    host: str = ""

    def out_of_time(self):
        return time.monotonic() - self.started >= self.budget.total_s


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _first_line(e):
    return (e.get("label") or "").strip().split("\n")[0]


def _press(w, e):
    """Press this element, the one the rules judged, through Session.act. False if the rules don't allow it."""
    if "click" not in e["actions"] or not may_press(e, filled_here=False):
        return False
    w.s.act(e, "click")
    w.s.wait_for_page()
    return True


def _press_label(w, label):
    """Press the first element labelled `label` that the rules allow (a switch of the same name is never it)."""
    e = next((e for e in w.s.elements() if "click" in e["actions"] and _first_line(e) == label
              and may_press(e, filled_here=False)), None)
    return e is not None and _press(w, e)


def _left_the_app(w):
    """The host the session is on now, when it isn't the app's; else None."""
    url = w.s.observe().get("url") or ""  # the page as it is now, not as it was before the click
    return None if on_site(url, w.host) else (urlparse(url).hostname or url)


def _find_sections(w, first_key):
    """Press the first navigation label that leads elsewhere; the labels on both screens are the app's sections."""
    allowed = {_first_line(e) for e in w.s.elements() if "click" in e["actions"] and may_press(e, filled_here=False)}
    home = [label for label in nav_labels(w.s) if label in allowed]
    for label in home:
        try:
            if not _press_label(w, label):
                continue
        except (HazardStop, StalePage):
            continue
        key, _ = read_screen(w.s)
        if _left_the_app(w):
            _back_to(w, None, w.m["screens"][first_key]["url"], first_key)
            continue
        if key != first_key:
            found = sections(home, nav_labels(w.s))
            _back_to(w, None, w.m["screens"][first_key]["url"], first_key)
            return found
    return []


def _back_to(w, section, url, key):
    """Back on screen `key`: reopen its address, else press the section's tab, else a new session and the tab.
    False when the way back is lost."""
    if not on_site(url, w.host):  # never navigates off the app
        return False
    for attempt in ("address", "tab", "new session"):
        try:
            if attempt == "new session":
                w.s.close()
                w.s = w.new_session(url)
            if attempt in ("address", "new session"):
                w.s.browser.call("Page.navigate", url=url)
                w.s.wait_loaded()
            if attempt in ("tab", "new session") and section and read_screen(w.s)[0] != key:
                _press_label(w, section)
            if read_screen(w.s)[0] == key:
                return True
        except Exception:  # a refused tab, a page that moved, a sign-in that failed: try the next way
            continue
    return False


def _list_group(label, landed):
    """A press in a list: its landing path's parent ("/subjects/7" → "/subjects/*"), else None."""
    path = landed.split(" · ")[0]
    return re.sub(r"/[^/]+$", "/*", path) if path.count("/") >= 2 else None


def _walk_section(w, section, start_key):
    """Every screen reached in this section, every control mapping may press on it, back each time."""
    queue, done, steps = [start_key], set(), 0
    while queue:
        key = queue.pop(0)
        if key in done:
            continue
        done.add(key)
        url = w.m["screens"][key]["url"]
        if not _back_to(w, section, url, key):
            w.m["left"].append(f"{section}: way back lost")
            return
        _, screen = read_screen(w.s)
        if screen["fields"]:  # the form first; then the screen's other controls (a search box isn't the whole tab)
            forms.handle(w.s, w.cf, w.m, key, screen, w.m["account"]["state"], w.budget, w.log, w.now, section)
            if not _back_to(w, section, url, key):
                w.m["left"].append(f"{section}: way back lost")
                return
        tried = {a["control"] for a in w.m["actions"] if a["screen"] == key}
        groups, skipped, run_role = {}, {}, None
        for label in screen["controls"]:
            if label in w.nav or label in tried:
                continue
            if screen["fields"] and not any(_first_line(x) == label and x["role"] in ("link", "tab")
                                            for x in w.s.elements()):
                continue  # beside a form only links are followed: its buttons belong to the form (never sent empty)
            if steps >= w.budget.steps_per_section or w.out_of_time():
                w.m["left"].append(f"{section}: out of steps")
                return
            e = next((e for e in w.s.elements() if _first_line(e) == label and may_press(e, filled_here=False)),
                     None) or next((e for e in w.s.elements() if _first_line(e) == label), None)
            if e is None or not may_press(e, filled_here=False):
                if e is not None and e.get("role") not in ("switch", "checkbox", "radio"):
                    add_action(w.m, key, label, "click", f"refused: {label}", w.now)
                continue
            if e["role"] != run_role:  # a list is a run of same-role controls: a different role ends it
                groups, run_role = {}, e["role"]
            last = groups.get(e["role"])
            if last and last[1] >= w.budget.items_per_list and not ADDS.search(label):  # never an add
                skipped[last[0]] = skipped.get(last[0], 0) + 1
                continue
            steps += 1
            before = w.s.page.get("text", "")
            try:
                _press(w, e)
            except HazardStop:
                add_action(w.m, key, label, "click", f"refused: {label}", w.now)
                continue
            except StalePage:
                continue
            gone_to = _left_the_app(w)
            if gone_to:
                add_action(w.m, key, label, "click", f"refused: leaves the app → {gone_to}", w.now)
                if not _back_to(w, section, url, key):
                    w.m["left"].append(f"{section}: way back lost")
                    return
                continue
            after_key, after = read_screen(w.s)
            add_action(w.m, key, label, "click", outcome(key, before, after_key, after["kind"], w.s.page.get("text"),
                                                         []), w.now)
            if after["kind"] == "dialog":  # answered like any dialog, then back; a dialog is never queued
                add_screen(w.m, after_key, {**after, "section": section}, w.now)
                forms.handle(w.s, w.cf, w.m, after_key, after, w.m["account"]["state"], w.budget, w.log, w.now,
                             section)
                if not _back_to(w, section, url, key):
                    w.m["left"].append(f"{section}: way back lost")
                    return
                continue
            if after_key != key:
                if after_key not in w.m["screens"]:
                    add_screen(w.m, after_key, {**after, "section": section}, w.now)
                    queue.append(after_key)
                group = _list_group(label, after_key)
                if group and last and last[0] == group:
                    groups[e["role"]] = (group, last[1] + 1)
                elif group:
                    groups[e["role"]] = (group, 1)
                if not _back_to(w, section, url, key):
                    w.m["left"].append(f"{section}: way back lost")
                    return
        for group, n in skipped.items():
            w.m["left"].append(f"{key}: {n} more items")


def crawl(new_session, cf, origin, saved=None, budget=None, log=print, now=None):
    """The blueprint of the signed-in app at `origin`, merged into `saved`. new_session(url) is a signed-in session
    (Login.session)."""
    w = _Walk(new_session(origin + "/"), new_session, cf, empty(), budget or Budget(), time.monotonic(),
              now or _now(), log, host=urlparse(origin).hostname)
    try:
        first_key, first = read_screen(w.s)
        w.m["account"]["state"] = account_state(cf, first, log)
        add_screen(w.m, first_key, first, w.now)
        if w.m["account"]["state"].startswith("partway"):  # a setup step: walked up to its finishing click only
            add_screen(w.m, first_key, {**first, "kind": "wizard-step", "section": "Setup"}, w.now)
            forms.handle(w.s, cf, w.m, first_key, first, w.m["account"]["state"], w.budget, log, w.now, "Setup")
            return _with_jobs(cf, merge(saved, w.m, {"Setup"}, w.now), log)
        w.nav = _find_sections(w, first_key)
        w.m["account"]["sections"] = list(w.nav)
        seen = set()
        for section in w.nav:
            if w.out_of_time():
                w.m["left"].append(f"{section}: not walked (out of time)")
                continue
            if not _back_to(w, None, w.m["screens"][first_key]["url"], first_key) or not _press_label(w, section):
                w.m["left"].append(f"{section}: couldn't open it")
                continue
            key, screen = read_screen(w.s)
            seen.add(section)
            if _unchanged(w, saved, section, key, screen):
                continue
            add_screen(w.m, key, {**screen, "kind": "tab", "section": section}, w.now)
            try:
                _walk_section(w, section, key)
            except Exception as err:  # costs this section, never the map (and what was already added is kept)
                w.m["left"].append(f"{section}: stopped ({type(err).__name__})")
                log(f"blueprint: {section} stopped ({type(err).__name__})")
                continue
            log(f"blueprint: {section} walked")
    finally:
        w.s.close()
    return _with_jobs(cf, merge(saved, w.m, seen, w.now), log)


def _unchanged(w, saved, section, key, screen):
    """A saved section whose tab shows what it showed before (leaving out the navigation and what mapping itself
    added) isn't walked again: its screens are kept, seen now. A different account state walks everything."""
    if not saved or saved["account"].get("state") != w.m["account"]["state"]:
        return False
    old = saved["screens"].get(key)
    ignore = set(w.nav) | typed_by_mapping(saved)
    if not old or old.get("gone") or {c for c in old.get("controls", []) if c not in ignore} != \
            {c for c in screen["controls"] if c not in ignore}:
        return False
    for k, s in saved["screens"].items():
        if s.get("section") == section:
            w.m["screens"][k] = s if s.get("gone") else {**s, "last_seen": w.now}
    w.log(f"blueprint: {section} unchanged since {old.get('last_seen')}")
    return True


def _with_jobs(cf, m, log):
    m["jobs"] = jobs.find(cf, m, log)
    return m
