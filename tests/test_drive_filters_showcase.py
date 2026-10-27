"""On an explored listing, a demo applies the filters the goal asks for, on camera, checks the result on screen and in
the URL, and ends by showcasing a few items."""
import base64
import json

from jev_demofast.browser.elements import observed
from jev_demofast.drive import filters, jev_drive, showcase
from jev_demofast.drive.popups import COVERED_JS

FILTERS = [{"group": "Product Type", "kind": "checkbox", "param": "filter.p.type", "values": ["Running Shoes", "Slip Ons"]},
           {"group": "Price", "kind": "checkbox", "param": None, "values": ["Under $75", "$76 - $100", "$101 - $125"]}]
MAP = {"_site": {"menus": []}, "/collections/:handle": {
    "links": [], "fields": [], "texts": ["Men's shoes"], "kind": "listing", "filters": FILTERS}}
SHOES = [("Tree Runner", "$98"), ("Dasher NZ", "$95"), ("Wool Runner", "$90"), ("Trail Runner", "$99")]


class Listing:
    """/collections/mens. 'Running Shoes' sits in the closed Product Type panel; ticking it sets the URL query."""
    url_on_running = "?filter.p.type=Running+Shoes"

    def __init__(self, url="https://shop.test/collections/mens", fresh=False, isolated=False):
        self.host, self.query, self.panel, self.checked, self.events = "shop.test", "", False, set(), []
        self.observe()

    @property
    def browser(self):
        outer = self

        class B:
            def evaluate(self, js, **k):
                return {"dialog": False, "hidden_roots": 0} if js == COVERED_JS else None

            def call(self, method, **params):
                if method == "Page.captureScreenshot":
                    return {"data": base64.b64encode(b"\xff\xd8 frame").decode()}
                return {}
        return B()

    def observe(self):
        acts = [{"kind": "click", "node": 10, "id": "e10", "role": "button", "label": "Product Type"},
                {"kind": "click", "node": 11, "id": "e11", "role": "checkbox", "label": "Under $75 (3)"},
                {"kind": "click", "node": 12, "id": "e12", "role": "checkbox", "label": "$76 - $100 (9)"}]
        if self.panel:
            acts.append({"kind": "click", "node": 13, "id": "e13", "role": "checkbox", "label": "Running Shoes (12)"})
        acts += [{"kind": "click", "node": 20 + n, "id": f"p{n}", "role": "link", "label": f"{name} {price}"}
                 for n, (name, price) in enumerate(SHOES)]
        self.page = {"url": "https://shop.test/collections/mens" + self.query, "title": "Men's shoes", "scroll": 0,
                     "actions": acts, "text": "Men's shoes " + " ".join(f"{a} {b}" for a, b in SHOES)}
        return self.page

    def elements(self): return observed(self.page)
    def full_text(self): return self.page["text"]
    def wait_for_page(self): return "settled"
    def next_frame(self): pass
    def href(self, node): return None
    def close(self): pass

    def act(self, e, kind, text=None):
        self.events.append(e["label"])
        if e["label"] == "Product Type":
            self.panel = True
        if e["label"].startswith("Running Shoes"):
            self.query = self.url_on_running


class Cf:
    stats = {"jev_calls": 0, "jev_seconds": 0.0, "llm_calls": 0, "llm_seconds": 0.0}
    decisions = []
    s = type("S", (), {"check_model": "@cf/cloudflare/clef", "read_model": "nemotron"})

    def __init__(self, picks, screen=0.95, items=("Tree Runner", "Dasher NZ", "Wool Runner")):
        self.picks, self.screen, self.items, self.asked = picks, screen, list(items), []

    def chat_json(self, model, system, context, extra=None):
        return {"items": self.items} if "Extract" in system else self.picks

    def choose(self, instructions, options, state, allow_none=False):
        self.asked.append(instructions)
        return "act_here", 0.9

    def yes(self, instructions, state, true="yes", false="no", model=None, images=None):
        return self.screen


UNDER_100 = {"checks": [{"group": "Product Type", "value": "Running Shoes"}, {"group": "Price", "value": "Under $75"},
                        {"group": "Price", "value": "$76 - $100"}], "ranges": [], "sort": None}


def test_invented_filter_values_are_dropped():
    picks = {"checks": [{"group": "Product Type", "value": "Trail Shoes"}, {"group": "Colour", "value": "Red"},
                        {"group": "Price", "value": "Under $75"}], "ranges": [], "sort": None}
    assert filters.choose_filters(Cf(picks), "goal", FILTERS)["checks"] == [{"group": "Price", "value": "Under $75"}]


class Rec:
    def __init__(self): self.commits, self.snaps = [], []
    def snap(self, hold, node=None, badge=None): self.snaps.append(node)
    def commit(self, action, page=None): self.commits.append(action)
    def discard(self): pass


def test_filters_apply_on_camera_and_the_url_must_agree():
    s, rec = Listing(), Rec()
    expected = filters.apply_filters(Cf(UNDER_100), s, rec, "men's running shoes under $100", MAP["/collections/:handle"],
                                     log=lambda m: None)
    assert expected == ["filter.p.type=Running Shoes"]
    assert s.events == ["Product Type", "Running Shoes (12)", "Under $75 (3)", "$76 - $100 (9)"]
    assert [c["target"] for c in rec.commits if c["do"] == "filter"] == [
        "Product Type: Running Shoes", "Price: Under $75", "Price: $76 - $100"]
    assert filters.url_agrees(s.page["url"], expected)
    assert not filters.url_agrees("https://shop.test/collections/mens", expected)


def test_showcase_highlights_three_items():
    s, rec = Listing(), Rec()
    items = showcase.showcase(Cf(UNDER_100), s, rec, "goal", log=lambda m: None)
    assert items[:3] == ["Tree Runner", "Dasher NZ", "Wool Runner"] and rec.snaps == [20, 21, 22]
    assert rec.commits[-1]["do"] == "read" and rec.commits[-1]["items"] == items


def run(monkeypatch, tmp_path, cf, listing=Listing, index=MAP):
    monkeypatch.setattr(jev_drive, "Session", lambda url, fresh=False: listing())
    return jev_drive.run(cf, "https://shop.test/collections/mens", "men's running shoes under $100", index,
                         out=str(tmp_path), log=lambda m: None)


def test_a_demo_on_an_explored_listing_filters_verifies_and_showcases(monkeypatch, tmp_path):
    result = run(monkeypatch, tmp_path, Cf(UNDER_100))
    assert result["verified"] is True
    segments = [a["do"] for a in json.loads((tmp_path / "actions.json").read_text())["actions"]]
    assert segments.count("filter") == 3 and segments[-1] == "read"


def test_a_wrong_url_fails_verification_even_if_the_screen_check_passes(monkeypatch, tmp_path):
    class WrongQuery(Listing):
        url_on_running = "?filter.p.type=Slip+Ons"
    assert run(monkeypatch, tmp_path, Cf(UNDER_100, screen=0.95), listing=WrongQuery)["verified"] is False


def test_a_map_without_site_or_filters_still_drives(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(jev_drive, "_fill_and_submit", lambda *a: called.append("form") or True)
    monkeypatch.setattr(filters, "apply_filters", lambda *a, **k: called.append("filters") or [])

    class WithField(Listing):
        def observe(self):
            page = super().observe()
            page["actions"].append({"kind": "fill", "node": 30, "id": "e30", "role": "textbox", "label": "Email"})
            return page
    source_map = {"/collections/:handle": {"links": [], "fields": ["Email"], "texts": []}}
    assert run(monkeypatch, tmp_path, Cf(UNDER_100), listing=WithField, index=source_map)["verified"] is True
    assert called == ["form"]


def test_blocked_labels_are_never_clicked_as_filters():
    picks = {"checks": [{"group": "Account", "value": "Delete account"}], "ranges": [], "sort": None}
    entry = {"filters": [{"group": "Account", "kind": "checkbox", "param": None, "values": ["Delete account", "Keep"]}]}

    class WithDanger(Listing):
        def observe(self):
            page = super().observe()
            page["actions"].append({"kind": "click", "node": 40, "id": "e40", "role": "checkbox", "label": "Delete account"})
            return page
    s = WithDanger()
    assert filters.apply_filters(Cf(picks), s, Rec(), "goal", entry, log=lambda m: None) == [] and s.events == []


def test_a_filter_click_that_leaves_the_site_stops():
    class Leaves(Listing):
        def act(self, e, kind, text=None):
            super().act(e, kind, text)
            self.gone = True

        def observe(self):
            page = super().observe()
            if getattr(self, "gone", False):
                page["url"] = "https://elsewhere.test/"
            return page
    s = Leaves()
    assert filters.apply_filters(Cf(UNDER_100), s, Rec(), "goal", MAP["/collections/:handle"], log=lambda m: None) is None
    assert len(s.events) == 1


def test_price_boxes_only_take_numbers():
    entry = {"filters": [{"group": "Price", "kind": "range", "param": ["p.gte", "p.lte"], "values": []}]}
    picks = {"checks": [], "ranges": [{"group": "Price", "min": None, "max": "100; drop table"}], "sort": None}
    assert filters.choose_filters(Cf(picks), "goal", entry["filters"])["ranges"] == []
    picks["ranges"][0]["max"] = "$100"
    assert filters.choose_filters(Cf(picks), "goal", entry["filters"])["ranges"] == [{"group": "Price", "min": None, "max": "100"}]


def test_a_collapsed_filter_panel_is_opened_first():
    """Allbirds keeps every filter group behind one "Filter" button: open it, then the group, then the value."""
    class Collapsed(Listing):
        opened = False

        def observe(self):
            page = super().observe()
            if not self.opened:
                page["actions"] = [{"kind": "click", "node": 9, "id": "e9", "role": "button",
                                    "label": "Filter Collapse filter"}] + [a for a in page["actions"] if a["role"] == "link"]
            return page

        def act(self, e, kind, text=None):
            if e["label"].startswith("Filter"):
                self.opened = True
            super().act(e, kind, text)
    s, rec = Collapsed(), Rec()
    expected = filters.apply_filters(Cf(UNDER_100), s, rec, "goal", MAP["/collections/:handle"], log=lambda m: None)
    assert s.events[:3] == ["Filter Collapse filter", "Product Type", "Running Shoes (12)"]
    assert expected == ["filter.p.type=Running Shoes"] and rec.commits[0]["target"] == "open the filters"


def test_the_panel_is_reopened_when_a_filter_click_collapses_it():
    """Live: ticking "Under $75" reloaded the listing with the filter panel collapsed again."""
    class Recollapsing(Listing):
        opened = False

        def observe(self):
            page = super().observe()
            if not self.opened:
                page["actions"] = [{"kind": "click", "node": 9, "id": "e9", "role": "button",
                                    "label": "Filter Collapse filter"}] + [a for a in page["actions"] if a["role"] == "link"]
            return page

        def act(self, e, kind, text=None):
            self.opened = e["label"].startswith("Filter") or (self.opened and e["role"] != "checkbox")
            super().act(e, kind, text)
    s = Recollapsing()
    filters.apply_filters(Cf(UNDER_100), s, Rec(), "goal", MAP["/collections/:handle"], log=lambda m: None)
    assert [x for x in s.events if not x.startswith(("Filter", "Product Type"))] == [
        "Running Shoes (12)", "Under $75 (3)", "$76 - $100 (9)"]


def test_a_filter_value_the_site_disabled_is_reported_unavailable():
    """Live: with Running Shoes ticked, Allbirds disables every price band under $126: say so, don't just skip."""
    class Disabled(Listing):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.panel = True

        @property
        def browser(self):
            inner = super().browser

            class B:
                def evaluate(self, js, **k):
                    return ["Under $75", "$76 - $100"] if "disabled" in js else inner.evaluate(js)

                def call(self, method, **params):
                    return inner.call(method, **params)
            return B()

        def observe(self):
            page = super().observe()
            page["actions"] = [a for a in page["actions"] if "$" not in a["label"] or a["role"] == "link"]
            page["actions"].append({"kind": "click", "node": 14, "id": "e14", "role": "button", "label": "Price"})
            return page
    unavailable, s = [], Disabled()
    filters.apply_filters(Cf(UNDER_100), s, Rec(), "goal", MAP["/collections/:handle"],
                          log=lambda m: None, unavailable=unavailable)
    assert unavailable == ["Price: Under $75", "Price: $76 - $100"]
    assert "Price" not in s.events  # a disabled value is known from the page: no heading clicked looking for it


def test_the_showcase_closes_an_open_filter_panel_first():
    """Live: the showcase outlined shoes hidden behind the still-open filter panel."""
    s, keys = Listing(), []
    s.panel = True
    inner = Listing.browser.fget(s)

    class B:
        def evaluate(self, js, **k):
            return inner.evaluate(js)

        def call(self, method, **params):
            if method == "Input.dispatchKeyEvent" and params.get("type") == "keyDown":
                keys.append(params["key"])
                s.panel = False
            return inner.call(method, **params)
    type(s).browser = property(lambda self: B())
    try:
        showcase.showcase(Cf(UNDER_100), s, Rec(), "goal", log=lambda m: None)
    finally:
        type(s).browser = Listing.browser
    assert keys == ["Escape"]


def test_a_value_disabled_only_while_the_listing_reloads_is_still_applied(monkeypatch):
    """Live: right after a filter click Shopify disables every option until the listing reloads; Running Shoes was
    reported unavailable though it existed."""
    monkeypatch.setattr(filters.time, "sleep", lambda s: None)
    looks = {"n": 0}

    class Reloading(Listing):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.panel = True

        @property
        def browser(self):
            inner = super().browser

            class B:
                def evaluate(self, js, **k):
                    return ["Running Shoes"] if "disabled" in js and looks["n"] < 2 else (
                        [] if "disabled" in js else inner.evaluate(js))

                def call(self, method, **params):
                    return inner.call(method, **params)
            return B()

        def observe(self):
            looks["n"] += 1
            page = super().observe()
            if looks["n"] < 3:  # still reloading: the box isn't offered yet
                page["actions"] = [a for a in page["actions"] if not a["label"].startswith("Running")]
            return page
    picks = {"checks": [{"group": "Product Type", "value": "Running Shoes"}], "ranges": [], "sort": None}
    s, unavailable = Reloading(), []
    filters.apply_filters(Cf(picks), s, Rec(), "goal", MAP["/collections/:handle"], log=lambda m: None,
                          unavailable=unavailable)
    assert unavailable == [] and "Running Shoes (12)" in s.events
