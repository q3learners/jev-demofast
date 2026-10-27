"""Menus are found the way a visitor finds them: hovering the top navigation, or clicking a menu button. A link is
never clicked while looking for menus (that would navigate away)."""
from jev_demofast.explore.menus import discover_menus, new_links

HOME = [{"label": "Help", "to": "/pages/help"}]
MEN = [{"label": "Shoes", "to": "/collections/mens"}, {"label": "Running", "to": "/collections/mens-running"},
       {"label": "Sale", "to": "/collections/mens-sale"}]


def action(node, role, label, y=40):
    return {"kind": "click", "node": node, "id": f"e{node}", "role": role, "label": label,
            "rect": {"x": 100 * node, "y": y, "w": 60, "h": 20}}


class MenuSite:
    """reveal: {label: (how, links)}: what hovering or clicking a top-bar control shows."""
    def __init__(self, actions, reveal):
        self.page = {"url": "https://shop.test/", "title": "Shop", "text": "", "actions": actions}
        self.reveal, self.showing, self.clicked, self.hovered, self.keys = reveal, [], [], [], []
        outer = self

        class B:
            def evaluate(self, js, **k):
                return HOME + outer.showing

            def call(self, method, **params):
                if method == "Input.dispatchKeyEvent" and params.get("type") == "keyDown":
                    outer.keys.append(params["key"])
                    outer.showing = []
                if method == "Input.dispatchMouseEvent" and params.get("type") == "mouseMoved":
                    outer.showing = []  # moving the mouse away closes a hover menu
        self.browser = B()

    def elements(self):
        from jev_demofast.browser.elements import observed
        return observed(self.page)

    def observe(self): return self.page
    def wait_for_page(self): return "settled"

    def hover(self, e):
        self.hovered.append(e["label"])
        how, links = self.reveal.get(e["label"], (None, []))
        self.showing = links if how == "hover" else []

    def act(self, e, kind, text=None):
        self.clicked.append(e["label"])
        how, links = self.reveal.get(e["label"], (None, []))
        self.showing = links if how == "click" else []


def test_new_links_only_lists_revealed_destinations():
    assert new_links(HOME, HOME + MEN + MEN[:1]) == MEN


def test_a_hover_menu_is_recorded_as_hover():
    s = MenuSite([action(1, "link", "Men")], {"Men": ("hover", MEN)})
    assert discover_menus(s, log=lambda m: None) == [{"opener": "Men", "opens_on": "hover", "items": MEN}]


def test_a_link_opener_is_hovered_not_clicked():
    s = MenuSite([action(1, "link", "Men")], {"Men": ("click", MEN)})
    assert discover_menus(s, log=lambda m: None) == [] and s.clicked == []


def test_a_button_menu_is_recorded_as_click():
    s = MenuSite([action(1, "button", "Shop")], {"Shop": ("click", MEN)})
    menus = discover_menus(s, log=lambda m: None)
    assert menus == [{"opener": "Shop", "opens_on": "click", "items": MEN}] and "Escape" in s.keys


def test_only_the_top_navigation_is_tried():
    s = MenuSite([action(1, "link", "Men", y=600)], {"Men": ("hover", MEN)})
    assert discover_menus(s, log=lambda m: None) == [] and s.hovered == []


def test_a_menu_that_fades_in_is_still_found(monkeypatch):
    """Allbirds' menu fades in: its links count as invisible for the first moments after the click."""
    import jev_demofast.explore.menus as menus
    monkeypatch.setattr(menus.time, "sleep", lambda s: None)
    s = MenuSite([action(1, "button", "Men")], {"Men": ("click", MEN)})
    looks = {"n": 0}
    real = s.browser.evaluate

    def fading(js, **k):
        looks["n"] += 1
        links = real(js)
        return links if looks["n"] >= 4 else HOME  # visible only from the fourth look
    s.browser.evaluate = fading
    assert discover_menus(s, log=lambda m: None)[0]["items"] == MEN


def test_a_menu_left_open_is_not_credited_to_the_next_opener():
    """Allbirds' Men menu stayed open after the mouse moved away; Women must not inherit its links."""
    s = MenuSite([action(1, "button", "Men"), action(2, "button", "Women")], {"Men": ("hover", MEN)})
    s.browser.call = lambda method, **params: None  # nothing closes the menu
    opened = s.hover

    def hover(e):  # hovering Women reveals nothing of its own and leaves the Men menu showing
        if e["label"] == "Men":
            opened(e)
    s.hover, s.act = hover, lambda e, kind, text=None: None
    menus = discover_menus(s, log=lambda m: None)
    assert [m["opener"] for m in menus] == ["Men"]


def test_search_and_cart_are_not_menus():
    s = MenuSite([action(1, "button", "Search"), action(2, "button", "View Cart")],
                 {"Search": ("hover", MEN), "View Cart": ("click", MEN)})
    assert discover_menus(s, log=lambda m: None) == [] and s.hovered == []
