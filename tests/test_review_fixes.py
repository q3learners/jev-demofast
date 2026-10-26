"""Findings from the whole-branch review of the site explorer, each pinned by a test."""
import base64
import json

from jev_demofast.browser.elements import observed
from jev_demofast.drive import filters, jev_drive, popups
from jev_demofast.drive.menus import menu_options
from jev_demofast.explore import listing
from jev_demofast.explore.templates import templates as make_templates
from jev_demofast.explore import menus as explore_menus

from test_drive_filters_showcase import MAP, UNDER_100, Cf, Listing, Rec
from test_drive_menus_popups import Shop
from test_drive_menus_popups import Cf as MenuCf
from test_drive_menus_popups import MAP as MENU_MAP
from test_explore_menus import MenuSite, action
from test_popups import Cf as PopupCf
from test_popups import PopupSession, el


# 1. An explored map never verifies through the old text-only form check.
def test_an_explored_map_never_verifies_with_the_text_only_form_check(monkeypatch, tmp_path):
    class Home(Listing):
        def observe(self):
            page = super().observe()
            page["url"] = "https://shop.test/"
            page["actions"] = [{"kind": "fill", "node": 30, "id": "e30", "role": "searchbox", "label": "Search"},
                               {"kind": "click", "node": 31, "id": "e31", "role": "button", "label": "Search"}]
            page["text"] = "Results for men's running shoes under $100"
            return page

        def settle(self, before, max_s=6.0):
            return self.observe()

    class TextFooled(Cf):
        def choose(self, instructions, options, state, allow_none=False):
            if "button" in instructions:
                return "31", 0.9
            return super().choose(instructions, options, state, allow_none)

        def chat_json(self, model, system, context, extra=None):
            return {"values": {"Search": "men's running shoes under $100"}}

        def yes(self, instructions, state, true="yes", false="no", model=None, images=None):
            return 0.95 if model is None else 0.2  # the text check is fooled; the screenshot check isn't
    monkeypatch.setattr(jev_drive, "Session", lambda url, fresh=False: Home())
    explored = {"_site": {"menus": []}, "/": {"links": [], "fields": ["Search"], "texts": []}}
    result = jev_drive.run(TextFooled(UNDER_100), "https://shop.test/", "men's running shoes under $100", explored,
                           out=str(tmp_path), max_steps=1, log=lambda m: None)
    assert result["verified"] is False


# 2. A pop-up "closer" that navigates (off-site or anywhere) isn't a close.
def test_a_popup_closer_link_off_the_site_is_never_offered():
    s, cf = PopupSession([el(1, "link", "Privacy policy"), el(2, "button", "Close")]), PopupCf("Close")
    s.href = lambda node: "https://elsewhere.test/privacy" if node == 1 else None
    popups.clear_popups(cf, s, log=lambda m: None)
    assert not any("Privacy" in v for v in cf.offered.values())


def test_a_closer_that_navigates_is_undone():
    s, cf = PopupSession([el(1, "link", "Shop now")], close_label="Shop now"), PopupCf("Shop now")
    s.href = lambda node: None
    moved = {"to": None}
    real_act = s.act

    def act(e, kind, text=None):
        real_act(e, kind, text)
        s.page = {**s.page, "url": "https://shop.test/collections/sale"}
    s.act = act
    real_call = s.browser.call
    s.browser.call = lambda method, **p: moved.update(to=p.get("url")) if method == "Page.navigate" else real_call(method, **p)
    assert popups.clear_popups(cf, s, log=lambda m: None) is None and moved["to"] == "https://shop.test/"


# 3. Single-segment pages aren't one template.
def test_top_level_pages_are_not_one_template():
    routes = make_templates(["/men", "/women", "/about", "/stores"])
    assert routes == {"/men": "/men", "/women": "/women", "/about": "/about", "/stores": "/stores"}


# 4. Price boxes labelled From / To are found and filled, with the URL check.
def test_from_and_to_price_boxes_are_filled():
    class Boxes(Listing):
        def observe(self):
            page = super().observe()
            page["actions"] += [{"kind": "fill", "node": 50, "id": "e50", "role": "spinbutton", "label": "From"},
                                {"kind": "fill", "node": 51, "id": "e51", "role": "spinbutton", "label": "To"}]
            return page

        def act(self, e, kind, text=None):
            super().act(e, kind, text)
            if e["label"] == "To":
                self.query = "?filter.v.price.lte=100"
    entry = {"filters": [{"group": "Price", "kind": "range", "param": ["filter.v.price.gte", "filter.v.price.lte"],
                          "values": []}]}
    picks = {"checks": [], "ranges": [{"group": "Price", "min": None, "max": "100"}], "sort": None}
    s = Boxes()
    expected = filters.apply_filters(Cf(picks), s, Rec(), "goal", entry, log=lambda m: None)
    assert s.events == ["To"] and expected == ["filter.v.price.lte=100"] and filters.url_agrees(s.page["url"], expected)


# 5. Labels lose their counts; the URL check uses the input's value.
def test_filter_values_drop_counts_and_keep_the_url_value():
    raw = {"item_links": 20, "groups": [{"heading": "Product Type", "controls": [
        {"type": "checkbox", "name": "filter.p.m.standard.type", "label": "Running Shoes (12)",
         "value": "gid://shopify/Metaobject/123"},
        {"type": "checkbox", "name": "filter.p.m.standard.type", "label": "Slip Ons (4)",
         "value": "gid://shopify/Metaobject/456"}]}]}
    (f,) = listing.parse_listing(raw)["filters"]
    assert f["values"] == ["Running Shoes", "Slip Ons"]
    assert f["url_values"] == {"Running Shoes": "gid://shopify/Metaobject/123", "Slip Ons": "gid://shopify/Metaobject/456"}
    assert filters.url_agrees("https://shop.test/c?filter.p.m.standard.type=gid%3A%2F%2Fshopify%2FMetaobject%2F123",
                              ["filter.p.m.standard.type=gid://shopify/Metaobject/123"])


# 6. A pop-up landing during filtering is cleared before the next filter and before the verdict.
def test_a_popup_during_filtering_is_cleared(monkeypatch):
    calls = []
    monkeypatch.setattr(filters, "clear_popups", lambda cf, s, log=print: calls.append("clear"))
    filters.apply_filters(Cf(UNDER_100), Listing(), Rec(), "goal", MAP["/collections/:handle"], log=lambda m: None)
    assert len(calls) >= 3  # before each of the three filters


# 7. A menu that didn't open stays reachable as a plain click; the top-bar opener wins over a footer link.
def test_a_menu_that_did_not_open_is_offered_as_a_plain_click_next(monkeypatch, tmp_path):
    asked = []

    class Dead(Shop):
        def hover(self, e):
            self.events.append(("hover", e["label"]))  # the menu never opens

    class Watch(MenuCf):
        def choose(self, instructions, options, state, allow_none=False):
            if instructions.startswith("Which option moves"):
                asked.append(list(options.values()))
                return next((k for k, v in options.items() if "Men" in v), next(iter(options))), 0.9
            return super().choose(instructions, options, state, allow_none)
    monkeypatch.setattr(jev_drive, "Session", lambda url, fresh=False: Dead(url))
    jev_drive.run(Watch(), "https://shop.test/", "find running shoes", MENU_MAP, out=str(tmp_path), max_steps=2,
                  log=lambda m: None)
    assert any(o.startswith("Men") and "opens a menu" not in o for o in asked[1])


def test_menu_options_prefer_the_top_bar_opener():
    page = {"actions": [{"kind": "click", "node": 1, "id": "e1", "role": "link", "label": "Men",
                         "rect": {"x": 0, "y": 900, "w": 40, "h": 20}},
                        {"kind": "click", "node": 2, "id": "e2", "role": "button", "label": "Men",
                         "rect": {"x": 0, "y": 40, "w": 40, "h": 20}},
                        {"id": "scroll_down", "kind": "scroll", "label": "Scroll down", "delta": 560}]}  # no node
    found = menu_options({"_site": {"menus": [{"opener": "Men", "opens_on": "hover", "items": []}]}}, observed(page),
                         page["actions"])
    assert list(found) == [2]


# 8. Exploring never clicks a top-bar button that would change data.
def test_explore_never_clicks_a_data_changing_top_bar_button():
    s = MenuSite([action(1, "button", "Update location")], {"Update location": ("click", [{"label": "a", "to": "/a"},
                                                                                          {"label": "b", "to": "/b"}])})
    explore_menus.discover_menus(s, log=lambda m: None)
    assert s.clicked == []
