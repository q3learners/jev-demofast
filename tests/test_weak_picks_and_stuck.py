"""A weak plan target can't force a click, and a run that gets stuck says so to the narrator."""
import base64
import json

from jev_demofast.browser.elements import observed
from jev_demofast.drive import navigator
from jev_demofast.drive.pick import Picker

PAGE = {"url": "https://github.com/trending", "title": "Trending", "actions": [
    {"kind": "click", "node": 1, "id": "c1", "label": "Open Source", "role": "button"},
    {"kind": "click", "node": 2, "id": "c2", "label": "Star 1,204", "role": "button"},
    {"kind": "click", "node": 3, "id": "c3", "label": "Date range: Today", "role": "button"},
]}


class UnsureJev:
    """Picks the first option, barely sure: a full word match where the words say little ("1")."""
    def choose(self, instructions, options, state, allow_none=False):
        return next(iter(options)), 0.37


class FakeSession:
    def __init__(self, page):
        self.page = page

    def elements(self): return observed(self.page)
    def observe(self): return self.page


def test_a_full_word_match_still_needs_jev_to_be_sure():
    els = observed(PAGE)
    chosen, conf, how = Picker(UnsureJev(), "jev").pick("1", "click", els, PAGE, "goal")
    assert chosen is None and how == "none"   # → reveal or re-plan, not a click on whatever contains "1"


def test_a_bare_number_in_a_later_step_doesnt_skip_the_steps_before_it():
    steps = [{"do": "click", "target": "Trending"}, {"do": "click", "target": "This week"},
             {"do": "click", "target": "1"}]

    class NoJev:
        def choose(self, instructions, options, state, allow_none=False):
            return None, 0.0
    reached = Picker(NoJev(), "jev").lookahead(FakeSession(PAGE), steps, 0, "goal", polls=1)
    assert reached is None  # "This week" isn't here yet; "1" matching a star count is no reason to skip it


class StuckSession:
    """No element on the page matches the plan, so the run ends STUCK."""
    host = "github.com"
    page = {"url": "https://github.com/", "title": "GitHub", "text": "Build and ship software", "actions": [],
            "scroll": 0}

    def __init__(self, url, fresh=False): pass

    class browser:
        evaluate = staticmethod(lambda js, **k: None)
        call = staticmethod(lambda method, **params: {"data": base64.b64encode(b"\xff\xd8 frame").decode()})

    def elements(self): return []
    def observe(self): return self.page
    def next_frame(self): pass
    def close(self): pass


def test_a_stuck_run_tells_the_narrator_it_did_not_finish(monkeypatch, tmp_path):
    monkeypatch.setattr(navigator, "Session", StuckSession)
    monkeypatch.setattr(navigator, "make_plan", lambda cf, goal, page, done=None: {
        "steps": [{"do": "click", "target": "Pricing"}], "done_text": ""})

    class Cf:
        stats = {"jev_calls": 0, "jev_seconds": 0.0, "llm_calls": 0, "llm_seconds": 0.0}
        decisions = []
    result = navigator.run(Cf(), "https://github.com/", "show pricing", out=str(tmp_path), picker="keyword",
                           log=lambda m: None)
    assert result["verified"] is False
    last = json.loads((tmp_path / "actions.json").read_text())["actions"][-1]
    assert last["outcome"].startswith("not confirmed") and "Pricing" in last["outcome"]
