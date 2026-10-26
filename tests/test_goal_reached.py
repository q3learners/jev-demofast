"""A run that reaches the goal's page is verified even if the planner's guessed finish phrase isn't on it word for
word; one that doesn't reach it is not, whatever the phrase."""
import base64
import json

import pytest

from jev_demofast.drive import check, navigator

TRENDING = {"url": "https://github.com/trending?since=weekly", "title": "Trending", "scroll": 0,
            "text": "Trending. See what the GitHub community is most excited about this week.", "actions": []}
HOME = {"url": "https://github.com/", "title": "GitHub", "scroll": 0, "text": "Build and ship software",
        "actions": [{"kind": "click", "node": 1, "id": "c1", "label": "Trending", "role": "link"}]}


class FakeCf:
    def __init__(self, score):
        self.score, self.asked = score, []
        self.s = type("S", (), {"check_model": "typesafe/jev"})

    def yes(self, instructions, state, true="yes", false="no", model=None, images=None):
        self.asked.append(state)
        return self.score


def test_goal_reached_asks_about_the_final_screen():
    cf = FakeCf(0.84)
    ok, score = check.goal_reached(cf, "find trending projects this week", TRENDING)
    assert ok and score == 0.84 and cf.asked[0]["url"] == TRENDING["url"]
    assert check.goal_reached(FakeCf(0.2), "find trending projects this week", HOME) == (False, 0.2)


class ClickSession:
    """Home page with a 'Trending' link; clicking it lands on the weekly trending page."""
    host = "github.com"

    def __init__(self, url, fresh=False):
        self.page = HOME

    class browser:
        evaluate = staticmethod(lambda js, **k: None)
        call = staticmethod(lambda method, **params: {"data": base64.b64encode(b"\xff\xd8 frame").decode()})

    def elements(self):
        from jev_demofast.browser.elements import observed
        return observed(self.page)

    def observe(self): return self.page
    def act(self, element, kind, text=None): self.page = TRENDING
    def wait_for_page(self): return "navigated"
    def next_frame(self): pass
    def settle(self, before, max_s=6.0): raise AssertionError("no blind 6 s wait at the end")
    def close(self): pass


@pytest.mark.parametrize("score,verified", [(0.86, True), (0.12, False)])
def test_the_final_screen_decides_when_the_finish_phrase_is_missing(monkeypatch, tmp_path, score, verified):
    monkeypatch.setattr(navigator, "Session", ClickSession)
    monkeypatch.setattr(navigator, "make_plan", lambda cf, goal, page, done=None: {
        "steps": [{"do": "click", "target": "Trending"}], "done_text": "trending repositories this week"})

    class Cf(FakeCf):
        stats = {"jev_calls": 0, "jev_seconds": 0.0, "llm_calls": 0, "llm_seconds": 0.0}
        decisions = []
    result = navigator.run(Cf(score), "https://github.com/", "find trending projects this week", out=str(tmp_path),
                           picker="keyword", log=lambda m: None)
    assert result["verified"] is verified
    last = json.loads((tmp_path / "actions.json").read_text())["actions"][-1]
    assert last.get("outcome", "") == ("" if verified else "not confirmed: the screen didn't show the goal accomplished")


def test_the_finish_phrase_on_the_page_still_verifies_without_a_model_call(monkeypatch, tmp_path):
    monkeypatch.setattr(navigator, "Session", ClickSession)
    monkeypatch.setattr(navigator, "make_plan", lambda cf, goal, page, done=None: {
        "steps": [{"do": "click", "target": "Trending"}], "done_text": "most excited about this week"})

    class Cf(FakeCf):
        stats = {"jev_calls": 0, "jev_seconds": 0.0, "llm_calls": 0, "llm_seconds": 0.0}
        decisions = []
    cf = Cf(0.0)
    result = navigator.run(cf, "https://github.com/", "find trending projects this week", out=str(tmp_path),
                           picker="keyword", log=lambda m: None)
    assert result["verified"] is True and cf.asked == []
