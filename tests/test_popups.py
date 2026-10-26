"""A bot block is recognised (and never worked around); a pop-up covering the page is cleared by Escape or its close
control, never by typing into it or signing up."""
from jev_demofast.drive import popups


def el(node, role, label, kind="click"):
    return {"node": node, "role": role, "label": label, "actions": {kind: {}}, "current": label, "options": [],
            "hint": ""}


class PopupSession:
    """A page whose pop-up goes away on Escape (escape_clears) or when its close control is clicked."""
    def __init__(self, els, escape_clears=False, close_label="Close"):
        self.els, self.escape_clears, self.close_label = els, escape_clears, close_label
        self.covered, self.acted, self.keys = True, [], []
        self.page = {"url": "https://shop.test/", "title": "Shop", "text": "Unlock 10% off"}
        outer = self

        class B:
            def evaluate(self, js, **k):
                return {"dialog": outer.covered, "hidden_roots": 0}

            def call(self, method, **params):
                if method == "Input.dispatchKeyEvent" and params.get("type") == "keyDown":
                    outer.keys.append(params["key"])
                    if outer.escape_clears and params["key"] == "Escape":
                        outer.covered = False
        self.browser = B()

    def elements(self): return self.els
    def observe(self): return self.page
    def wait_for_page(self): return "settled"

    def act(self, element, kind, text=None):
        self.acted.append((element["label"], kind))
        if kind == "click" and element["label"] == self.close_label:
            self.covered = False


class Cf:
    def __init__(self, pick=None, conf=0.9):
        self.pick, self.conf, self.offered = pick, conf, None

    def choose(self, instructions, options, state, allow_none=False):
        self.offered = options
        return next((k for k, v in options.items() if self.pick and self.pick in v), None), self.conf


def test_bot_check_reads_a_block_page():
    assert popups.bot_check({"title": "Access Denied", "text": "You don't have permission to access this"}) == "Access Denied"
    assert popups.bot_check({"title": "Allbirds", "text": "Men Women New Arrivals Free shipping"}) is None


def test_escape_clears_a_popup():
    s, cf = PopupSession([el(1, "button", "Close")], escape_clears=True), Cf("Close")
    assert popups.clear_popups(cf, s, log=lambda m: None) == "escape"
    assert cf.offered is None and s.acted == []


def test_a_close_button_clears_a_popup_escape_cannot():
    s = PopupSession([el(1, "textbox", "Email Address", "fill"), el(2, "button", "Continue"), el(3, "button", "Close")])
    assert popups.clear_popups(Cf("Close"), s, log=lambda m: None) == "close: Close"
    assert s.acted == [("Close", "click")]


def test_never_types_or_signs_up_to_clear_a_popup():
    s, cf = PopupSession([el(1, "textbox", "Email Address", "fill"), el(2, "button", "Continue")]), Cf("Continue")
    assert popups.clear_popups(cf, s, log=lambda m: None) is None
    assert s.acted == [] and not any("Continue" in v for v in (cf.offered or {}).values())


def test_an_uncovered_page_needs_nothing():
    s = PopupSession([el(1, "link", "Men")])
    s.covered = False
    assert popups.clear_popups(Cf(), s, log=lambda m: None) is None and s.keys == []
