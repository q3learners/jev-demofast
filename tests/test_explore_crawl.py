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
                    return None

                def call(self, method, **params):
                    if method == "Page.navigate":
                        outer.path, outer.menu_open = "/" + params["url"].split("/", 3)[3], False
                    if method == "Input.dispatchMouseEvent":
                        outer.menu_open = False
            return B()

        def observe(self):
            visited.append(self.path)
            p = self._p()
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
