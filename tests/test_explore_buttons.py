"""A Flutter app navigates with buttons, not links: the explorer clicks the safe ones and records where they lead.
On a page with fields, Clef must say a button only navigates (K-12: navigation 0.93-0.98, submit 0.02-0.03)."""
import base64

import pytest

from jev_demofast.explore import buttons
from jev_demofast.explore.buttons import discover, only_navigates

ORIGIN = "https://k12.test"
# path → (has_fields, {button label: where it leads, or None to stay})
SITE = {
    "/setup/who": (False, {"Sign in": "/setup/account?mode=signin", "I'm a parent\nI'm setting it up": "/setup/account?mode=signup",
                           "I'm a student": "/setup/student", "Sign up now": "/setup/account?mode=signup",
                           "Delete everything": "/gone", "Save": "/saved", "Help": "https://other.test/help"}),
    "/setup/account?mode=signin": (True, {"I need an account": "/setup/account?mode=signup", "Back": "/setup/who",
                                          "Show password": None, "Sign in": "/today"}),
}


class FakeClef:
    def __init__(self, scores, check_model="@cf/cloudflare/clef", fail=False):
        self.scores, self.fail, self.asked = scores, fail, []
        self.s = type("S", (), {"check_model": check_model})()

    def yes(self, instructions, state, true="yes", false="no", model=None, images=None):
        self.asked.append(state["button"])
        assert instructions == buttons.QUESTION and true == buttons.TRUE and false == buttons.FALSE and images
        if self.fail:
            raise RuntimeError("model down")
        return self.scores.get(state["button"], 0.0)


class FakeSession:
    def __init__(self, path, extra_labels=()):
        self.path, self.clicked, self.navigations = path, [], []
        self.extra = list(extra_labels)
        self.observe()
        outer = self

        class B:
            def evaluate(self, js, **k):
                if js == buttons.SIGN_IN_FORM_JS:
                    return SITE[outer.path.split("#")[0]][0] if outer.path in SITE else False
                return None

            def call(self, method, **params):
                if method == "Page.navigate":
                    outer.navigations.append(params["url"])
                    outer.path = params["url"].removeprefix(ORIGIN)
                    outer.observe()
                if method == "Page.captureScreenshot":
                    return {"data": base64.b64encode(b"jpeg").decode()}
                return {}
        self.browser = B()

    def observe(self):
        fields, btns = SITE.get(self.path, (False, {}))
        url = self.path if self.path.startswith("http") else ORIGIN + self.path
        self.page = {"url": url, "text": "page " + self.path}
        labels = list(btns) + self.extra
        self._els = [{"node": i, "role": "button", "label": l, "actions": {"click": {}}} for i, l in enumerate(labels)]
        if fields:
            self._els.append({"node": 99, "role": "textbox", "label": "Email", "actions": {"fill": {}, "click": {}}})
        return self.page

    def elements(self):
        return self._els

    def act(self, e, kind):
        self.clicked.append(e["label"])
        to = SITE[self.path][1][e["label"]]
        if to:
            self.path = to.removeprefix(ORIGIN)
        self.observe()

    def wait_for_page(self):
        return "settled"

    def wait_loaded(self):
        pass


def test_a_button_that_leads_elsewhere_becomes_a_link():
    s = FakeSession("/setup/who")
    links = discover(s, ORIGIN, "/setup/who", None, log=lambda m: None)
    assert {"label": "I'm a student", "to": "/setup/student", "via": "button"} in links


def test_the_query_is_kept_in_the_link():
    s = FakeSession("/setup/who")
    links = discover(s, ORIGIN, "/setup/who", None, log=lambda m: None)
    assert {"label": "Sign in", "to": "/setup/account?mode=signin", "via": "button"} in links
    assert {"label": "I'm a parent", "to": "/setup/account?mode=signup", "via": "button"} in links  # first line only


def test_blocked_and_changing_buttons_are_never_clicked():
    s = FakeSession("/setup/who")
    discover(s, ORIGIN, "/setup/who", None, log=lambda m: None)
    assert not {"Sign up now", "Delete everything", "Save"} & set(s.clicked)


def test_on_a_page_with_fields_clef_decides():
    s = FakeSession("/setup/account?mode=signin")
    cf = FakeClef({"I need an account": 0.93, "Back": 0.98, "Show password": 0.09, "Sign in": 0.03})
    links = discover(s, ORIGIN, "/setup/account?mode=signin", cf, log=lambda m: None)
    assert set(s.clicked) == {"I need an account", "Back"}
    assert [l["to"] for l in links] == ["/setup/account?mode=signup", "/setup/who"]


@pytest.mark.parametrize("cf", [None, FakeClef({"Back": 0.98}, check_model="@cf/jev/jev-small")])
def test_no_check_model_means_no_clicks_on_pages_with_fields(cf):
    s = FakeSession("/setup/account?mode=signin")
    assert discover(s, ORIGIN, "/setup/account?mode=signin", cf, log=lambda m: None) == []
    assert s.clicked == []


def test_a_clef_error_means_no_click():
    s = FakeSession("/setup/account?mode=signin")
    cf = FakeClef({}, fail=True)
    assert discover(s, ORIGIN, "/setup/account?mode=signin", cf, log=lambda m: None) == []
    assert s.clicked == [] and len(cf.asked) == 4  # every button asked, none clicked, discovery went on


def test_a_button_that_stays_adds_no_link_and_the_page_is_reloaded():
    s = FakeSession("/setup/account?mode=signin")
    cf = FakeClef({"Show password": 0.95})  # even if Clef got it wrong, staying put adds no link
    links = discover(s, ORIGIN, "/setup/account?mode=signin", cf, log=lambda m: None)
    assert s.clicked == ["Show password"] and links == []
    assert s.navigations[-1] == ORIGIN + "/setup/account?mode=signin"


def test_same_label_is_tried_once():
    s = FakeSession("/setup/who", extra_labels=["Sign in"])
    discover(s, ORIGIN, "/setup/who", None, log=lambda m: None)
    assert s.clicked.count("Sign in") == 1


def test_a_button_that_leaves_the_site_adds_no_link():
    s = FakeSession("/setup/who")
    links = discover(s, ORIGIN, "/setup/who", None, log=lambda m: None)
    assert "Help" in s.clicked and all(l["label"] != "Help" for l in links)


def test_ends_on_the_page_it_started_from():
    s = FakeSession("/setup/who")
    discover(s, ORIGIN, "/setup/who", None, log=lambda m: None)
    assert s.navigations[-1] == ORIGIN + "/setup/who" and s.path == "/setup/who"


def test_only_navigates_needs_images():
    cf = FakeClef({"Back": 0.98}, check_model="@cf/jev/jev-small")
    assert only_navigates(cf, "Back", {"url": ORIGIN, "text": ""}, ["Email"], ["Back"], lambda: b"x") is False
