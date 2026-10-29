"""The explorer browses a site once and writes a map: menus, listing templates with their filters, other screens."""
import json

from jev_demofast import explore as explore_mod
from jev_demofast.drive.popups import COVERED_JS
from jev_demofast.explore import HEADINGS_JS, explore
from jev_demofast.explore.listing import READ_LISTING_JS
from jev_demofast.explore.menus import VISIBLE_LINKS_JS

LISTING = {"item_links": 30, "groups": [
    {"heading": "Product Type", "controls": [{"type": "checkbox", "name": "filter.p.type", "label": v}
                                             for v in ("Running Shoes", "Slip Ons")]}]}
MEN_MENU = [{"label": "Shoes", "to": "/collections/mens"}, {"label": "Women", "to": "/collections/womens"}]


def site_pages(n_siblings=0):
    pages = {
        "/": {"title": "Shop", "text": "Welcome", "links": [{"label": "About", "to": "/pages/about"}],
              "actions": [{"kind": "click", "node": 1, "id": "e1", "role": "button", "label": "Men",
                           "rect": {"x": 10, "y": 30, "w": 40, "h": 20}}], "headings": ["Welcome"]},
        "/pages/about": {"title": "About", "text": "Our story", "links": [], "actions": [], "headings": ["Our story"]},
    }
    for handle in ["mens", "womens"] + [f"extra{i}" for i in range(n_siblings)]:
        pages[f"/collections/{handle}"] = {"title": handle, "text": "Shoes", "links": [], "actions": [],
                                           "headings": [f"{handle} shoes"], "listing": LISTING}
    return pages


def fake_session(pages, home_title=None):
    visited = []

    class FakeSite:
        host = "shop.test"

        def __init__(self, url, fresh=False, isolated=False):
            assert isolated, "exploring must not touch the demo profile"
            self.path, self.menu_open = "/", False
            self.observe()

        def _p(self):
            return pages[self.path]

        @property
        def browser(self):
            outer = self

            class B:
                def evaluate(self, js, **k):
                    p = outer._p()
                    if js == VISIBLE_LINKS_JS:
                        return p["links"] + (MEN_MENU if outer.menu_open else [])
                    if js == READ_LISTING_JS:
                        return p.get("listing", {"item_links": 2, "groups": []})
                    if js == COVERED_JS:
                        return {"dialog": False, "hidden_roots": 0}
                    if js == HEADINGS_JS:
                        return p["headings"]
                    if js == explore_mod.SIGN_IN_FORM_JS:
                        return p.get("password", False)
                    return None

                def call(self, method, **params):
                    if method == "Page.navigate":
                        outer.path, outer.menu_open = "/" + params["url"].split("/", 3)[3], False
                        outer.path = pages[outer.path].get("redirect", outer.path)  # the site sends you elsewhere
                    if method == "Input.dispatchMouseEvent":
                        outer.menu_open = False
            return B()

        def observe(self):
            visited.append(self.path)
            p = self._p()
            if p.get("unreadable"):  # an image or other file, not a page: there's no document to read
                from jev_demofast.browser.cdp import StalePage
                raise StalePage("Document is navigating")
            self.page = {"url": "https://shop.test" + self.path, "title": home_title if self.path == "/" and home_title
                         else p["title"], "text": p["text"], "actions": p["actions"], "h": 780}
            return self.page

        def elements(self):
            from jev_demofast.browser.elements import observed
            return observed(self.page)

        def hover(self, e): self.menu_open = e["label"] == "Men"
        def act(self, e, kind, text=None): pass
        def wait_loaded(self, timeout=10): pass
        def wait_for_page(self): return "settled"
        def next_frame(self): pass
        def close(self): pass
    return FakeSite, visited


def test_explore_writes_menus_listings_and_templates(tmp_path, monkeypatch):
    monkeypatch.setattr(explore_mod.menus.time, "sleep", lambda s: None)
    monkeypatch.setattr(explore_mod.time, "sleep", lambda s: None)
    session, _ = fake_session(site_pages())
    out = tmp_path / "map.json"
    m = explore("https://shop.test/", out=str(out), cf=None, log=lambda x: None, session=session)
    assert json.loads(out.read_text()) == m
    listing = m["/collections/:handle"]
    assert listing["kind"] == "listing" and listing["filters"][0]["values"] == ["Running Shoes", "Slip Ons"]
    assert listing["examples"] == ["/collections/mens", "/collections/womens"]
    assert "/pages/about" in m and m["/pages/about"]["texts"] == ["Our story"]
    assert m["_site"]["menus"][0]["opener"] == "Men" and m["_site"]["blocked"] is None


def test_explore_stops_on_a_bot_check(monkeypatch):
    session, visited = fake_session(site_pages(), home_title="Access Denied")
    m = explore("https://shop.test/", cf=None, log=lambda x: None, session=session)
    assert m == {"_site": {**m["_site"], "blocked": "Access Denied"}} and set(visited) == {"/"}


def test_explore_respects_the_page_budget(monkeypatch):
    monkeypatch.setattr(explore_mod.menus.time, "sleep", lambda s: None)
    monkeypatch.setattr(explore_mod.time, "sleep", lambda s: None)
    pages = site_pages()
    pages["/"]["links"] += [{"label": f"Page {i}", "to": f"/pages/p{i}"} for i in range(10)]
    for i in range(10):
        pages[f"/pages/p{i}"] = {"title": "p", "text": "p", "links": [], "actions": [], "headings": []}
    session, visited = fake_session(pages)
    explore("https://shop.test/", max_pages=3, cf=None, log=lambda x: None, session=session)
    assert len(set(visited)) <= 3


def test_the_explore_command(monkeypatch, capsys):
    import pytest
    from jev_demofast import cli
    calls = []
    monkeypatch.setattr(cli, "_cf", lambda a=None, require=True: "cf")
    monkeypatch.setattr(explore_mod, "explore", lambda url, **k: calls.append((url, k)) or {
        "_site": {"menus": [{}], "blocked": None}, "/c/:handle": {"kind": "listing"}, "/": {"kind": "page"}})
    assert cli.main(["explore", "https://shop.test/", "--out", "m.json", "--pages", "12"]) == 0
    assert calls[0][0] == "https://shop.test/" and calls[0][1]["max_pages"] == 12 and calls[0][1]["cf"] == "cf"
    assert "2 routes, 1 listings, 1 menus → m.json" in capsys.readouterr().out
    monkeypatch.setattr(explore_mod, "explore", lambda url, **k: {"_site": {"menus": [], "blocked": "Access Denied"}})
    with pytest.raises(SystemExit) as stop:
        cli.main(["explore", "https://shop.test/"])
    assert "blocked: Access Denied" in str(stop.value)


def test_a_late_popup_is_cleared_before_menus_are_looked_for(monkeypatch):
    """Allbirds' newsletter pop-up appears a few seconds in, after the first page is read: it must not hide the menus."""
    monkeypatch.setattr(explore_mod.menus.time, "sleep", lambda s: None)
    monkeypatch.setattr(explore_mod.time, "sleep", lambda s: None)
    session, _ = fake_session(site_pages())
    checks = {"n": 0, "covered": False, "escapes": 0}

    class LatePopup(session):
        @property
        def browser(self):
            inner, outer = super().browser, self

            class B:
                def evaluate(self, js, **k):
                    if js == COVERED_JS:
                        return {"dialog": checks["covered"], "hidden_roots": 0}
                    return inner.evaluate(js)

                def call(self, method, **params):
                    if method == "Input.dispatchKeyEvent" and params.get("key") == "Escape":
                        checks["escapes"] += 1
                        checks["covered"] = False
                    return inner.call(method, **params)
            return B()

        def observe(self):
            checks["n"] += 1
            if checks["n"] == 2 and not checks["escapes"]:
                checks["covered"] = True  # the pop-up arrives after the first page read
            return super().observe()

        def elements(self):
            return [] if checks["covered"] else super().elements()
    m = explore("https://shop.test/", cf=None, log=lambda x: None, session=LatePopup)
    assert m["_site"]["menus"] and m["_site"]["popups"][0]["cleared_by"] == "escape"


def test_links_per_route_are_capped(monkeypatch):
    monkeypatch.setattr(explore_mod.menus.time, "sleep", lambda s: None)
    monkeypatch.setattr(explore_mod.time, "sleep", lambda s: None)
    pages = site_pages()
    pages["/collections/mens"]["links"] = [{"label": f"P{i}", "to": f"/products/p{i}"} for i in range(200)]
    session, _ = fake_session(pages)
    m = explore("https://shop.test/", max_pages=4, cf=None, log=lambda x: None, session=session)
    assert len(m["/collections/:handle"]["links"]) <= 80


def test_explore_chooses_the_browser_before_the_browser_library_loads():
    """browser-harness reads which Chrome to use (BU_NAME) once, when it loads: loaded first, explore went to the
    harness's default connection instead of the tool's own Chrome."""
    import subprocess
    import sys
    probe = (
        "import sys\n"
        "import jev_demofast.cli as cli\n"
        "def _cf(a=None, require=True):\n"
        "    print('loaded' if 'browser_harness.helpers' in sys.modules else 'not loaded')\n"
        "    raise SystemExit(0)\n"
        "cli._cf = _cf\n"
        "cli.main(['explore', 'https://shop.test/'])\n")
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "not loaded"


def test_a_page_that_never_loads_is_skipped_and_the_rest_is_mapped(monkeypatch):
    # In the cloud browser, one move to the next page of tutorq.ai timed out, and the whole map was lost with it.
    monkeypatch.setattr(explore_mod.menus.time, "sleep", lambda s: None)
    monkeypatch.setattr(explore_mod.time, "sleep", lambda s: None)
    session, _ = fake_session(site_pages())
    real_browser = session.browser

    def browser(self):
        b = real_browser.fget(self)
        call = b.call

        def slow(method, **params):
            if method == "Page.navigate" and params["url"].endswith("/pages/about"):
                raise TimeoutError("Page.navigate timed out after 30s waiting for the daemon")
            return call(method, **params)
        b.call = slow
        return b
    session.browser = property(browser)
    said = []
    m = explore("https://shop.test/", cf=None, log=said.append, session=session)
    assert "/pages/about" not in m and "/collections/:handle" in m
    assert any("skipped /pages/about" in line for line in said)


def test_page_loads_get_longer_than_other_browser_calls(monkeypatch):
    from jev_demofast.browser import cdp as cdp_mod
    asked = []
    monkeypatch.setattr(cdp_mod, "cdp", lambda method, session_id=None, **k: asked.append((method, k)) or {})
    b = cdp_mod.Browser.__new__(cdp_mod.Browser)
    b.session = "s"
    b.call("Page.navigate", url="https://shop.test/")
    b.call("Page.reload")
    b.call("Runtime.evaluate", expression="1")
    assert asked[0][1]["_response_timeout"] == asked[1][1]["_response_timeout"] == cdp_mod.PAGE_LOAD_TIMEOUT_S == 30
    assert "_response_timeout" not in asked[2][1]


def test_a_page_that_draws_its_content_after_loading_is_read_once_it_has(monkeypatch):
    # q3learners.ai (React): "complete" with an empty <div id="root">; read then, the map was empty and the demo
    # stopped as if the site were a canvas. Three seconds later it had every heading.
    monkeypatch.setattr(explore_mod.menus.time, "sleep", lambda s: None)
    monkeypatch.setattr(explore_mod.time, "sleep", lambda s: None)
    session, _ = fake_session(site_pages())
    real_browser = session.browser
    polls = []

    def browser(self):
        b = real_browser.fget(self)
        evaluate = b.evaluate

        def drawn_late(js, **k):
            drawn = len(polls) >= 3
            if js == explore_mod.HAS_CONTENT_JS:
                polls.append(js)
                return drawn
            if js == HEADINGS_JS and not drawn:
                return []
            return evaluate(js, **k)
        b.evaluate = drawn_late
        return b
    session.browser = property(browser)
    m = explore("https://shop.test/", cf=None, log=lambda x: None, session=session)
    assert m["/"]["texts"] == ["Welcome"]


def walled_site():
    """A site whose dashboard and portfolio need an account: a visitor lands on its sign-in page instead."""
    pages = site_pages()
    pages["/"]["links"] += [{"label": "Dashboard", "to": "/dashboard"}, {"label": "Portfolio", "to": "/portfolio"},
                            {"label": "Log in", "to": "/login"}]
    pages["/dashboard"] = pages["/portfolio"] = {"redirect": "/login"}
    pages["/login"] = {"title": "Sign in", "text": "Welcome back", "links": [], "actions": [], "password": True,
                       "headings": ["Welcome back"]}
    return pages


def test_pages_behind_a_login_are_skipped_and_listed(monkeypatch):
    """reafi.ai: its app pages sent the explorer to /login, the map kept them with the login page's content, and the
    demo went to the login page and back. Pages behind a login aren't mapped; the site record lists them instead."""
    monkeypatch.setattr(explore_mod.menus.time, "sleep", lambda s: None)
    monkeypatch.setattr(explore_mod.time, "sleep", lambda s: None)
    session, _ = fake_session(walled_site())
    said = []
    m = explore("https://shop.test/", cf=None, log=said.append, session=session)
    assert "/dashboard" not in m and "/portfolio" not in m
    assert m["_site"]["behind_login"] == ["/dashboard", "/portfolio"]
    assert "/pages/about" in m and "/collections/:handle" in m  # the rest of the site is mapped as usual
    assert any("behind a login: /dashboard, /portfolio" in line and "jev-demofast chrome --open" in line
               for line in said)


def test_a_sign_in_page_reached_by_its_own_link_is_not_a_wall(monkeypatch):
    monkeypatch.setattr(explore_mod.menus.time, "sleep", lambda s: None)
    monkeypatch.setattr(explore_mod.time, "sleep", lambda s: None)
    session, _ = fake_session(walled_site())
    m = explore("https://shop.test/", cf=None, log=lambda x: None, session=session)
    assert "/login" not in m["_site"]["behind_login"]


def test_a_redirect_to_a_page_without_a_sign_in_form_is_not_a_wall(monkeypatch):
    monkeypatch.setattr(explore_mod.menus.time, "sleep", lambda s: None)
    monkeypatch.setattr(explore_mod.time, "sleep", lambda s: None)
    pages = site_pages()
    pages["/"]["links"].append({"label": "Old about", "to": "/about-us"})
    pages["/about-us"] = {"redirect": "/pages/about"}
    session, _ = fake_session(pages)
    m = explore("https://shop.test/", cf=None, log=lambda x: None, session=session)
    assert m["_site"]["behind_login"] == []


def test_a_sign_in_page_is_mapped_and_marked(monkeypatch):
    """Kept for a task that signs in with {{EMAIL}}; marked so a tour never shows it."""
    monkeypatch.setattr(explore_mod.menus.time, "sleep", lambda s: None)
    monkeypatch.setattr(explore_mod.time, "sleep", lambda s: None)
    session, _ = fake_session(walled_site())
    m = explore("https://shop.test/", cf=None, log=lambda x: None, session=session)
    assert m["/login"]["sign_in"] is True and m["/pages/about"]["sign_in"] is False


def test_a_link_to_a_file_that_isnt_a_page_is_skipped_and_the_rest_is_mapped(monkeypatch):
    """selvage.run linked a diagram, /visuals/selvage-architecture.svg: opened as a page there was no document to read,
    and the whole map stopped. Like a page that never loads, it costs that link, not the map."""
    monkeypatch.setattr(explore_mod.menus.time, "sleep", lambda s: None)
    monkeypatch.setattr(explore_mod.time, "sleep", lambda s: None)
    pages = site_pages()
    pages["/"]["links"].insert(0, {"label": "Architecture diagram", "to": "/visuals/architecture.svg"})
    pages["/visuals/architecture.svg"] = {"title": "", "text": "", "links": [], "actions": [], "headings": [],
                                          "unreadable": True}
    session, _ = fake_session(pages)
    said = []
    m = explore("https://shop.test/", cf=None, log=said.append, session=session)
    assert "/visuals/architecture.svg" not in m and "/pages/about" in m and "/collections/:handle" in m
    assert any("skipped /visuals/architecture.svg" in line for line in said)


# k12.tutorq.ai as the explorer saw it on 29 October (Flutter, logged out): no links, no headings, buttons that navigate
# and two pages with fields where only Clef may let a button be clicked.
K12 = {
    "/setup/who": {"text": "TutorQ K-12\nParents and students set up differently, so we ask first.\nWho is this?\nSign in\n"
                           "I'm a parent\nI'm a student",
                   "buttons": {"Sign in": "/setup/account?mode=signin", "I'm a parent": "/setup/account?mode=signup",
                               "I'm a student": "/setup/student"}},
    "/setup/student": {"text": "TutorQ K-12\nHow do you get in?\nBack\nMy parent gave me a login",
                       "buttons": {"Back": "/setup/who", "My parent gave me a login": "/setup/kid"}},
    "/setup/account?mode=signin": {"text": "TutorQ K-12\nWelcome back.\nEmail\nPassword", "password": True,
                                   "buttons": {"Back": "/setup/who", "I need an account": "/setup/account?mode=signup",
                                               "Sign in": "/today"}},
    "/setup/account?mode=signup": {"text": "TutorQ K-12\nYour account, current step\nEmail", "password": True,
                                   "buttons": {"Back": "/setup/who", "I already have one": "/setup/account?mode=signin"}},
    "/setup/kid": {"text": "TutorQ K-12\nSign in to your subjects\nYour login ID", "password": True,
                   "buttons": {"Back": "/setup/student", "Sign in": "/today"}},
    "/today": {"text": "Today", "buttons": {}},
}


class K12Clef:
    s = type("S", (), {"check_model": "@cf/cloudflare/clef"})()

    def __init__(self):
        self.asked = []

    def yes(self, q, state, **k):
        self.asked.append(state["button"])
        return {"Back": .98, "I need an account": .93, "I already have one": .95, "Sign in": .02}.get(state["button"], 0)


def fake_flutter_session(pages=K12, clicks=None):
    clicks = [] if clicks is None else clicks

    class FlutterSite:
        host, is_flutter = "k12.test", True

        def __init__(self, url, fresh=False, isolated=False):
            self.path = "/setup/who"  # the app sends a visitor there
            self.observe()

        @property
        def browser(self):
            outer = self

            class B:
                def evaluate(self, js, **k):
                    p = pages[outer.path]
                    if js == READ_LISTING_JS:
                        return {"item_links": 0, "groups": []}
                    if js == COVERED_JS:
                        return {"dialog": False, "hidden_roots": 0}
                    if js in (VISIBLE_LINKS_JS, HEADINGS_JS):
                        return []
                    if js == explore_mod.SIGN_IN_FORM_JS:
                        return p.get("password", False)
                    return None

                def call(self, method, **params):
                    if method == "Page.navigate":
                        outer.path = "/" + params["url"].split("/", 3)[3]
                        outer.path = outer.path if outer.path in pages else "/setup/who"
                        outer.observe()
                    if method == "Page.captureScreenshot":
                        return {"data": ""}
                    return {}
            return B()

        def observe(self):
            p = pages[self.path]
            actions = [{"kind": "click", "node": i, "id": f"e{i}", "role": "button", "label": label,
                        "rect": {"x": 10, "y": 30 * i, "w": 40, "h": 20}} for i, label in enumerate(p["buttons"], 1)]
            if p.get("password"):
                actions.append({"kind": "fill", "node": 90, "id": "e90", "role": "textbox", "label": "Email",
                                "rect": {"x": 10, "y": 300, "w": 200, "h": 20}})
            self.page = {"url": "https://k12.test" + self.path, "title": "TutorQ K-12", "text": p["text"],
                         "actions": actions, "h": 780}
            return self.page

        def elements(self):
            from jev_demofast.browser.elements import observed
            return observed(self.page)

        def act(self, e, kind, text=None):
            clicks.append((self.path, e["label"]))
            self.path = pages[self.path]["buttons"].get(e["label"], self.path)
            self.observe()

        def hover(self, e): pass
        def wait_loaded(self, timeout=10): pass
        def wait_for_page(self): return "settled"
        def next_frame(self): pass
        def close(self): pass
    return FlutterSite


def test_a_flutter_site_is_mapped_through_its_buttons(monkeypatch):
    monkeypatch.setattr(explore_mod.time, "sleep", lambda s: None)
    clicks = []
    m = explore("https://k12.test/", cf=K12Clef(), log=lambda x: None, session=fake_flutter_session(clicks=clicks))
    assert {"/setup/who", "/setup/student", "/setup/account?mode=signin", "/setup/account?mode=signup",
            "/setup/kid"} <= set(m)
    assert {"label": "I'm a student", "to": "/setup/student", "via": "button"} in m["/setup/who"]["links"]
    assert m["/setup/account?mode=signin"]["sign_in"] and m["/setup/kid"]["sign_in"] and not m["/setup/who"]["sign_in"]
    assert ("/setup/kid", "Sign in") not in clicks and ("/setup/account?mode=signin", "Sign in") not in clicks
    assert "/today" not in m  # only a submit leads there, and nothing was submitted


def test_a_flutter_page_without_headings_gets_texts_from_its_text(monkeypatch):
    monkeypatch.setattr(explore_mod.time, "sleep", lambda s: None)
    m = explore("https://k12.test/", cf=K12Clef(), log=lambda x: None, session=fake_flutter_session())
    texts = m["/setup/who"]["texts"]
    assert texts[:3] == ["TutorQ K-12", "Parents and students set up differently, so we ask first.", "Who is this?"]
    assert not {"Sign in", "I'm a parent", "I'm a student"} & set(texts)


def test_button_discovery_respects_the_time_budget(monkeypatch):
    monkeypatch.setattr(explore_mod.time, "sleep", lambda s: None)
    calls = []
    real = explore_mod.discover
    monkeypatch.setattr(explore_mod, "discover", lambda *a, **k: calls.append(1) or real(*a, **k))
    clock = iter([0.0] + [10_000.0] * 1000)  # the budget runs out right after the explorer starts
    monkeypatch.setattr(explore_mod.time, "monotonic", lambda: next(clock))
    m = explore("https://k12.test/", cf=K12Clef(), log=lambda x: None, session=fake_flutter_session())
    assert calls == [] and "/setup/who" in m


def test_a_normal_site_never_runs_button_discovery(monkeypatch):
    monkeypatch.setattr(explore_mod.menus.time, "sleep", lambda s: None)
    monkeypatch.setattr(explore_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(explore_mod, "discover", lambda *a, **k: (_ for _ in ()).throw(AssertionError("discovered")))
    session, _ = fake_session(site_pages())
    m = explore("https://shop.test/", cf=None, log=lambda x: None, session=session)
    assert "/collections/:handle" in m and m["/pages/about"]["texts"] == ["Our story"]


def test_a_logged_in_explore_never_opens_a_hazard_link(monkeypatch):
    """Security review: the explorer opens links by address, which never passes Session.act's check. In a logged-in
    run a link whose label or path is a hazard (/account/logout, /kids/3/delete, "Billing") is never queued."""
    monkeypatch.setattr(explore_mod.menus.time, "sleep", lambda s: None)
    monkeypatch.setattr(explore_mod.time, "sleep", lambda s: None)
    pages = site_pages()
    risky = [{"label": "My account", "to": "/account/logout"}, {"label": "Tidy up", "to": "/kids/3/delete"},
             {"label": "Billing", "to": "/billing"}, {"label": "Kids", "to": "/account/deleteKid"},
             {"label": "Go", "to": "/api/kid?action=destroy"}, {"label": "Emails", "to": "/emails/unsubscribe"},
             {"label": "Account", "to": "/account/deactivate"}]
    pages["/"]["links"] = pages["/"]["links"] + risky
    for link in risky:
        pages[link["to"]] = {"title": "x", "text": "x", "links": [], "actions": [], "headings": ["x"]}
    session, visited = fake_session(pages)

    class LoggedIn(session):
        hazards = True
    explore("https://shop.test/", cf=None, log=lambda x: None, session=LoggedIn)
    assert not {"/account/logout", "/kids/3/delete", "/billing", "/account/deleteKid", "/api/kid?action=destroy",
                "/emails/unsubscribe", "/account/deactivate"} & set(visited)
    session2, visited2 = fake_session(pages)  # not logged in: today's behaviour (only blocked labels are skipped)
    explore("https://shop.test/", cf=None, log=lambda x: None, session=session2)
    assert "/billing" in visited2


def test_a_logged_in_explore_never_opens_a_hazard_menu_item(monkeypatch):
    """Review: menu destinations were queued with no check; an account menu's "Log out" (a GET /logout) would log the
    explore session out."""
    monkeypatch.setattr(explore_mod.menus.time, "sleep", lambda s: None)
    monkeypatch.setattr(explore_mod.time, "sleep", lambda s: None)
    pages = site_pages()
    pages["/logout"] = pages["/profile"] = {"title": "x", "text": "x", "links": [], "actions": [], "headings": ["x"]}
    monkeypatch.setattr(explore_mod, "discover_menus", lambda s, log: [{"opener": "Venkat", "opens_on": "click", "items": [
        {"label": "Log out", "to": "/logout"}, {"label": "Profile", "to": "/profile"}]}])
    session, visited = fake_session(pages)

    class LoggedIn(session):
        hazards = True
    explore("https://shop.test/", cf=None, log=lambda x: None, session=LoggedIn)
    assert "/logout" not in visited and "/profile" in visited


def test_a_hazard_popup_doesnt_stop_a_logged_in_explore(monkeypatch):
    """Review: a pop-up whose only closer is a hazard raised HazardStop out of explore()."""
    from jev_demofast.drive.guards import HazardStop
    monkeypatch.setattr(explore_mod.menus.time, "sleep", lambda s: None)
    monkeypatch.setattr(explore_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(explore_mod, "clear_popups", lambda cf, s, log: (_ for _ in ()).throw(HazardStop("Subscribe")))
    session, _ = fake_session(site_pages())
    m = explore("https://shop.test/", cf=None, log=lambda x: None, session=session)
    assert "/pages/about" in m
