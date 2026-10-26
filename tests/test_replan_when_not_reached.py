"""A plan that runs to its end without reaching the goal gets one more plan, from the page the run is on."""
import base64
import json

from jev_demofast.browser.elements import observed
from jev_demofast.drive import navigator

HOME = {"url": "https://github.com/", "title": "GitHub", "scroll": 0, "text": "Build and ship software",
        "actions": [{"kind": "click", "node": 1, "id": "c1", "label": "Open Source", "role": "button"}]}
MENU = {**HOME, "text": "Build and ship software. Open Source menu: Trending",
        "actions": HOME["actions"] + [{"kind": "click", "node": 2, "id": "c2", "label": "Trending", "role": "link"}]}
TRENDING = {"url": "https://github.com/trending?since=weekly", "title": "Trending", "scroll": 0,
            "text": "See what the GitHub community is most excited about this week.", "actions": []}


class MenuSession:
    host = "github.com"

    def __init__(self, url, fresh=False):
        self.page = HOME

    class browser:
        evaluate = staticmethod(lambda js, **k: None)
        call = staticmethod(lambda method, **params: {"data": base64.b64encode(b"\xff\xd8 frame").decode()})

    def elements(self): return observed(self.page)
    def observe(self): return self.page
    def act(self, element, kind, text=None): self.page = MENU if element["label"] == "Open Source" else TRENDING
    def wait_for_page(self): return "settled"
    def next_frame(self): pass
    def close(self): pass


def run(monkeypatch, tmp_path, scores):
    plans, planned_from = [[{"do": "click", "target": "Open Source"}], [{"do": "click", "target": "Trending"}]], []

    def make_plan(cf, goal, page, done=None):
        planned_from.append((page["url"], page["text"], list(done or [])))
        return {"steps": plans[min(len(planned_from), 2) - 1], "done_text": ""}
    monkeypatch.setattr(navigator, "Session", MenuSession)
    monkeypatch.setattr(navigator, "make_plan", make_plan)

    class Cf:
        stats = {"jev_calls": 0, "jev_seconds": 0.0, "llm_calls": 0, "llm_seconds": 0.0}
        decisions = []
        s = type("S", (), {"check_model": "typesafe/jev"})

        def yes(self, instructions, state, true="yes", false="no", model=None, images=None):
            return scores.pop(0)
    result = navigator.run(Cf(), "https://github.com/", "find trending projects this week", out=str(tmp_path),
                           picker="keyword", log=lambda m: None)
    return result, planned_from


def test_a_plan_that_falls_short_is_replanned_once_from_where_the_run_is(monkeypatch, tmp_path):
    result, planned_from = run(monkeypatch, tmp_path, [0.04, 0.96])
    assert result["verified"] is True and len(planned_from) == 2
    url, text, done = planned_from[1]
    assert "Trending" in text                                    # planned from the open menu, not the start page
    assert any("not" in d and "goal" in d for d in done)          # told the first plan didn't get there


def test_at_most_two_extra_plans(monkeypatch, tmp_path):
    result, planned_from = run(monkeypatch, tmp_path, [0.04, 0.10, 0.10, 0.10])
    not_reached = [done for _, _, done in planned_from if any("did not reach the goal" in d for d in done)]
    assert result["verified"] is False and len(not_reached) == 2
    assert len(planned_from) <= 1 + 2 + 2  # first plan, two after "not reached", two after "target not found"
    last = json.loads((tmp_path / "actions.json").read_text())["actions"][-1]
    assert last["outcome"].startswith("not confirmed: ")  # the latest reason, here the last plan's missing target


def test_a_new_plan_may_open_menus_again(monkeypatch, tmp_path):
    """The 'open a menu to find it' allowance is per step of a plan; a re-plan starts with a fresh one."""
    page = {"url": "https://example.com/", "title": "Home", "scroll": 0, "text": "Home",
            "actions": [{"kind": "click", "node": 2, "id": "c2", "label": "More", "role": "button"}]}

    class S(MenuSession):
        opened = 0
        def __init__(self, url, fresh=False): self.page = page
        def act(self, element, kind, text=None): S.opened += 1

    class Cf:
        stats = {"jev_calls": 0, "jev_seconds": 0.0, "llm_calls": 0, "llm_seconds": 0.0}
        decisions = []
        s = type("S", (), {"check_model": "typesafe/jev"})
        def choose(self, instructions, options, state, allow_none=False):
            return ("2", 0.9) if "is not visible" in instructions else (None, 0.0)
    monkeypatch.setattr(navigator, "Session", S)
    monkeypatch.setattr(navigator, "make_plan", lambda cf, goal, page, done=None: {
        "steps": [{"do": "click", "target": "Pricing"}], "done_text": ""})
    navigator.run(Cf(), "https://example.com/", "show pricing", picker="jev", log=lambda m: None)
    assert S.opened == 2 * 3  # two menu opens for each of the three plans (the first and two re-plans)
