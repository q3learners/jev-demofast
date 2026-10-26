"""In a demo, a menu opens on camera before its item is clicked, and a pop-up is cleared on whichever screen it
appears."""
import base64
import json

from jev_demofast.browser.elements import observed
from jev_demofast.drive import jev_drive
from jev_demofast.drive.popups import COVERED_JS

MAP = {"_site": {"menus": [{"opener": "Men", "opens_on": "hover",
                            "items": [{"label": "Running", "to": "/collections/mens-running"}]}]},
       "/": {"links": [], "fields": [], "texts": ["Welcome"]},
       "/collections/:handle": {"links": [], "fields": [], "texts": ["Running shoes"], "kind": "listing"}}
HOME = [{"kind": "click", "node": 1, "id": "e1", "role": "button", "label": "Men"},
        {"kind": "click", "node": 2, "id": "e2", "role": "link", "label": "Help"}]
RUNNING = {"kind": "click", "node": 3, "id": "e3", "role": "link", "label": "Running"}


class Shop:
    def __init__(self, url, fresh=False, isolated=False):
        self.host, self.path, self.menu, self.covered = "shop.test", "/", False, False
        self.events, self.popup_on_listing = [], Shop.popup_on_listing
        self.observe()

    popup_on_listing = False

    @property
    def browser(self):
        outer = self

        class B:
            def evaluate(self, js, **k):
                return {"dialog": outer.covered, "hidden_roots": 0} if js == COVERED_JS else None

            def call(self, method, **params):
                if method == "Page.captureScreenshot":
                    return {"data": base64.b64encode(b"\xff\xd8 frame").decode()}
                if method == "Input.dispatchKeyEvent" and params.get("type") == "keyDown":
                    outer.events.append(("key", params["key"]))
                    outer.covered = False
                return {}
        return B()

    def observe(self):
        actions = (HOME + ([RUNNING] if self.menu else [])) if self.path == "/" else []
        self.page = {"url": "https://shop.test" + self.path, "title": "Shop", "scroll": 0, "actions": actions,
                     "text": "Running shoes" if self.path != "/" else "Welcome"}
        return self.page

    def elements(self): return observed(self.page)
    def full_text(self): return self.page["text"]
    def href(self, node): return None
    def wait_for_page(self): return "settled"
    def next_frame(self): pass
    def close(self): pass

    def hover(self, e):
        self.events.append(("hover", e["label"]))
        self.menu = e["label"] == "Men"

    def act(self, e, kind, text=None):
        self.events.append(("click", e["label"]))
        if e["label"] == "Running":
            self.path, self.menu, self.covered = "/collections/mens-running", False, self.popup_on_listing


class Cf:
    stats = {"jev_calls": 0, "jev_seconds": 0.0, "llm_calls": 0, "llm_seconds": 0.0}
    decisions = []
    s = type("S", (), {"check_model": "typesafe/jev", "read_model": "nemotron"})

    def __init__(self):
        self.asked = []

    def choose(self, instructions, options, state, allow_none=False):
        self.asked.append(instructions)
        if instructions.startswith("Given the goal"):
            return ("done", 0.9) if "Running" in state["screen"]["visible_text"] else ("navigate", 0.9)
        if instructions.startswith("Which option moves"):
            return next(k for k, v in options.items() if "opens a menu" in v), 0.9
        if instructions.startswith("Which menu item"):
            return next(k for k, v in options.items() if "Running" in v), 0.9
        return None, 0.0

    def yes(self, instructions, state, true="yes", false="no", model=None, images=None):
        return 0.95

    def chat_json(self, model, system, context, extra=None):  # the showcase reads the items off the final screen
        return {"items": []}


def run(monkeypatch, tmp_path):
    shops = []
    monkeypatch.setattr(jev_drive, "Session", lambda url, fresh=False: shops.append(Shop(url)) or shops[-1])
    result = jev_drive.run(Cf(), "https://shop.test/", "find men's running shoes", MAP, out=str(tmp_path),
                           log=lambda m: None)
    return result, shops[0]


def test_a_menu_opens_on_camera_then_its_item_is_clicked(monkeypatch, tmp_path):
    result, shop = run(monkeypatch, tmp_path)
    assert result["verified"] is True
    assert shop.events == [("hover", "Men"), ("click", "Running")]
    segments = [(a["do"], a.get("target")) for a in json.loads((tmp_path / "actions.json").read_text())["actions"]]
    assert ("hover", "open the Men menu") in segments and ("click", "Running") in segments
    assert segments.index(("hover", "open the Men menu")) < segments.index(("click", "Running"))


def test_a_popup_that_appears_mid_run_is_cleared(monkeypatch, tmp_path):
    monkeypatch.setattr(Shop, "popup_on_listing", True)
    result, shop = run(monkeypatch, tmp_path)
    assert shop.events == [("hover", "Men"), ("click", "Running"), ("key", "Escape")] and result["verified"] is True


def test_menu_items_that_are_blocked_or_off_site_are_not_offered(monkeypatch, tmp_path):
    menu = {"opener": "Men", "opens_on": "hover", "items": [{"label": "Running", "to": "/collections/mens-running"},
                                                            {"label": "Sign up", "to": "/account/register"},
                                                            {"label": "Partner store", "to": "/partner"}]}
    extra = [{"kind": "click", "node": 4, "id": "e4", "role": "link", "label": "Sign up"},
             {"kind": "click", "node": 5, "id": "e5", "role": "link", "label": "Partner store"}]

    class Guarded(Shop):
        def observe(self):
            page = super().observe()
            if self.menu:
                page["actions"] += extra
            return page

        def href(self, node):
            return "https://elsewhere.test/" if node == 5 else None
    offered = []

    class Watch(Cf):
        def choose(self, instructions, options, state, allow_none=False):
            if instructions.startswith("Which menu item"):
                offered.extend(options.values())
            return super().choose(instructions, options, state, allow_none)
    monkeypatch.setattr(jev_drive, "Session", lambda url, fresh=False: Guarded(url))
    jev_drive.run(Watch(), "https://shop.test/", "find running shoes", {**MAP, "_site": {"menus": [menu]}},
                  out=str(tmp_path), log=lambda m: None)
    assert offered == ["Running"]


def test_a_menu_item_that_leaves_the_site_stops_the_run(monkeypatch, tmp_path):
    class Leaves(Shop):
        def act(self, e, kind, text=None):
            super().act(e, kind, text)
            if e["label"] == "Running":
                self.host_left = True

        def observe(self):
            page = super().observe()
            if getattr(self, "host_left", False):
                page["url"] = "https://elsewhere.test/landing"
            return page
    monkeypatch.setattr(jev_drive, "Session", lambda url, fresh=False: Leaves(url))
    result = jev_drive.run(Cf(), "https://shop.test/", "find running shoes", MAP, out=str(tmp_path), log=lambda m: None)
    assert result["verified"] is False
    last = json.loads((tmp_path / "actions.json").read_text())["actions"][-1]
    assert "away from" in last["outcome"] or "no way" in last["outcome"]


def test_a_dry_run_stops_before_a_data_changing_menu_item(monkeypatch, tmp_path):
    menu = {"opener": "Men", "opens_on": "hover", "items": [{"label": "Add to bag", "to": "/cart/add"}]}

    class Bag(Shop):
        def observe(self):
            page = super().observe()
            if self.menu:
                page["actions"] = HOME + [{"kind": "click", "node": 6, "id": "e6", "role": "button", "label": "Add to bag"}]
            return page

    class PickBag(Cf):
        def choose(self, instructions, options, state, allow_none=False):
            if instructions.startswith("Which menu item"):
                return next(iter(options)), 0.9
            return super().choose(instructions, options, state, allow_none)
    monkeypatch.setattr(jev_drive, "Session", lambda url, fresh=False: Bag(url))
    result = jev_drive.run(PickBag(), "https://shop.test/", "add shoes to the bag", {**MAP, "_site": {"menus": [menu]}},
                           out=str(tmp_path), dry_run=True, log=lambda m: None)
    assert result.get("would_click") == "Add to bag"


def test_a_menu_opener_that_goes_stale_doesnt_crash_the_run(monkeypatch, tmp_path):
    from jev_demofast.browser.cdp import StalePage

    class Stale(Shop):
        def hover(self, e):
            self.events.append(("hover", e["label"]))  # hovering shows nothing

        def act(self, e, kind, text=None):
            if e["label"] == "Men":
                raise StalePage("Target changed or is covered. Observe again.")
            super().act(e, kind, text)
    class AnyOption(Cf):  # once the menu has failed, the driver moves on to the other options
        def choose(self, instructions, options, state, allow_none=False):
            if instructions.startswith("Which option moves"):
                return next((k for k, v in options.items() if "opens a menu" in v), next(iter(options))), 0.9
            return super().choose(instructions, options, state, allow_none)
    monkeypatch.setattr(jev_drive, "Session", lambda url, fresh=False: Stale(url))
    result = jev_drive.run(AnyOption(), "https://shop.test/", "find running shoes", MAP, out=str(tmp_path),
                           log=lambda m: None)
    assert result["verified"] is False  # no crash: the menu simply didn't open, and the run ended honestly


def test_a_menu_hidden_by_a_late_popup_is_tried_again(monkeypatch, tmp_path):
    """Live: Allbirds' pop-up arrived just as Men was hovered, so the menu showed nothing."""
    class LatePopup(Shop):
        def hover(self, e):
            super().hover(e)
            if not any(k == "key" for k, _ in self.events):
                self.covered = True  # the pop-up lands now and hides the menu

        def observe(self):
            page = super().observe()
            if self.covered:
                page["actions"] = []
            return page
    shops = []
    monkeypatch.setattr(jev_drive, "Session", lambda url, fresh=False: shops.append(LatePopup(url)) or shops[-1])
    result = jev_drive.run(Cf(), "https://shop.test/", "find men's running shoes", MAP, out=str(tmp_path),
                           log=lambda m: None)
    assert result["verified"] is True
    assert shops[0].events == [("hover", "Men"), ("key", "Escape"), ("hover", "Men"), ("click", "Running")]
