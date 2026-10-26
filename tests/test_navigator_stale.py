"""A click on an element that stays covered or stale must not loop forever or crash the run."""
from jev_demofast.browser.cdp import StalePage
from jev_demofast.drive import navigator

TRENDING = {"node": 1, "role": "link", "label": "Trending", "actions": {"click": {}}, "current": "Trending",
            "options": [], "hint": ""}
DATE_MENU = {"node": 2, "role": "button", "label": "Date range: Today", "actions": {"click": {}},
             "current": "Date range: Today", "options": [], "hint": ""}


class StaleSession:
    """Every click raises StalePage, as when an open menu covers the target."""
    host = "github.com"
    page = {"url": "https://github.com/trending", "title": "Trending", "text": "Trending", "actions": [],
            "scroll": 0}

    def __init__(self, url, fresh=False, elements=()):
        self.els, self.clicks = list(elements), 0

    class browser:
        evaluate = staticmethod(lambda js: None)
        call = staticmethod(lambda *a, **k: {})

    def elements(self): return self.els
    def observe(self): return self.page
    def close(self): pass

    def act(self, element, kind, text=None):
        self.clicks += 1
        assert self.clicks < 50, "retried a stale click without limit"
        raise StalePage("Target changed or is covered. Observe again.")


class FakeCf:
    stats = {"jev_calls": 0, "jev_seconds": 0.0, "llm_calls": 0, "llm_seconds": 0.0}
    decisions = []

    def choose(self, instructions, options, state, allow_none=False):
        if "is not visible" in instructions:  # reveal: open the menu
            return "2", 0.9
        return None, 0.0  # no visible element is the target


def run(monkeypatch, elements, picker):
    sessions = []

    def session(url, fresh=False):
        sessions.append(StaleSession(url, fresh, elements))
        return sessions[-1]
    monkeypatch.setattr(navigator, "Session", session)
    monkeypatch.setattr(navigator, "make_plan", lambda cf, goal, page, done=None: {
        "steps": [{"do": "click", "target": "Trending" if picker == "keyword" else "This week"}], "done_text": ""})
    monkeypatch.setattr(navigator.time, "sleep", lambda s: None)
    result = navigator.run(FakeCf(), "https://github.com/", "find trending repos", picker=picker, log=lambda m: None)
    return result, sessions[0]


def test_a_click_that_stays_stale_is_given_up_not_retried_forever(monkeypatch):
    result, s = run(monkeypatch, [TRENDING], "keyword")
    assert result["verified"] is False
    assert s.clicks <= 3 * 3  # a few tries per plan (first plan + two re-plans), then stuck


def test_a_stale_menu_opener_does_not_crash_the_run(monkeypatch):
    result, s = run(monkeypatch, [DATE_MENU], "jev")
    assert result["verified"] is False and s.clicks >= 1
