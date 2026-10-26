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
    s = type("S", (), {"check_model": "typesafe/jev"})

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
