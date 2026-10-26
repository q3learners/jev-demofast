"""An information goal is verified only when the screen shows what was asked, not whenever a read returns text."""
import base64
import json

import pytest

from jev_demofast.cloudflare import Cloudflare
from jev_demofast.config import load
from jev_demofast.drive import check, navigator

CF = {"CLOUDFLARE_ACCOUNT_ID": "acct", "CLOUDFLARE_API_TOKEN": "cf-token"}


def env(monkeypatch, **values):
    for k in ("JDF_LLM_PROVIDER", "JDF_CHECK_MODEL", "JDF_JEV_MODEL"):
        monkeypatch.delenv(k, raising=False)
    for k, v in {**CF, **values}.items():
        monkeypatch.setenv(k, v)


def test_the_checks_use_clef_with_screenshots_unless_another_model_is_set(monkeypatch):
    env(monkeypatch)
    assert load().check_model == "@cf/cloudflare/clef"
    env(monkeypatch, JDF_CHECK_MODEL="typesafe/jev")
    assert load().check_model == "typesafe/jev"


def posts(monkeypatch, cf):
    sent = []
    def fake_post(url, body, token=None):
        sent.append((url, body))
        return {"result": {"answers": {"q": {"type": "noul", "noul": 0.2}}}}
    monkeypatch.setattr(cf, "_post", fake_post)
    return sent


def test_jev_is_asked_with_text_only(monkeypatch):
    env(monkeypatch, JDF_CHECK_MODEL="typesafe/jev")
    cf = Cloudflare(load())
    sent = posts(monkeypatch, cf)
    assert cf.yes("Shown?", {"x": 1}, model=cf.s.check_model, images=[b"\xff\xd8jpeg"]) == 0.2
    url, body = sent[0]
    assert url.endswith("/ai/run") and body["model"] == "typesafe/jev" and "images" not in json.dumps(body)


def test_clef_is_asked_on_its_own_route_with_the_screenshot(monkeypatch):
    env(monkeypatch, JDF_CHECK_MODEL="@cf/cloudflare/clef")
    cf = Cloudflare(load())
    sent = posts(monkeypatch, cf)
    cf.yes("Shown?", {"x": 1}, model=cf.s.check_model, images=[b"\xff\xd8jpeg"])
    url, body = sent[0]
    assert url.endswith("/ai/run/@cf/cloudflare/clef") and body["model"] == "clef"
    assert body["images"] == ["data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8jpeg").decode()]
    assert body["state"] == {"x": 1} and "q" in body["questions"]


class FakeCf:
    def __init__(self, score, sees_images=False):
        self.score, self.asked = score, []
        self.s = type("S", (), {"check_model": "@cf/cloudflare/clef" if sees_images else "typesafe/jev"})

    def yes(self, instructions, state, true="yes", false="no", model=None, images=None):
        self.asked.append((state, images))
        return self.score


def test_items_that_the_screen_doesnt_show_dont_verify():
    page = {"url": "https://github.com/", "text": "Search or jump to... trending this week"}
    ok, score = check.shows_answer(FakeCf(0.1), "find trending repos", "trending repositories", ["trending this week"],
                                   page)
    assert not ok and score == 0.1
    ok, _ = check.shows_answer(FakeCf(0.9), "find trending repos", "trending repositories", ["ruvnet / ruflo"], page)
    assert ok


def test_no_items_means_no_check_and_not_verified():
    cf = FakeCf(0.9)
    assert check.shows_answer(cf, "goal", "what", [], {"url": "u", "text": ""}) == (False, 0.0) and not cf.asked


def test_a_screenshot_goes_only_to_a_model_that_sees_images():
    page = {"url": "u", "text": "t"}
    text_only = FakeCf(0.9)
    check.shows_answer(text_only, "goal", "what", ["a"], page, screenshot=lambda: b"jpeg")
    assert text_only.asked[0][1] is None
    seeing = FakeCf(0.9, sees_images=True)
    check.shows_answer(seeing, "goal", "what", ["a"], page, screenshot=lambda: b"jpeg")
    assert seeing.asked[0][1] == [b"jpeg"]


class ReadSession:
    """The plan is a single read step; the read returns the text the tool itself had typed."""
    host = "github.com"
    page = {"url": "https://github.com/search", "title": "Search", "text": "trending this week", "actions": [],
            "scroll": 0}

    def __init__(self, url, fresh=False): pass

    class browser:
        evaluate = staticmethod(lambda js, **k: None)
        call = staticmethod(lambda method, **params: {"data": base64.b64encode(b"\xff\xd8 frame").decode()})

    def elements(self): return []
    def observe(self): return self.page
    def full_text(self): return self.page["text"]
    def next_frame(self): pass
    def close(self): pass


@pytest.mark.parametrize("score,verified", [(0.12, False), (0.91, True)])
def test_navigator_verifies_a_read_only_when_the_check_agrees(monkeypatch, tmp_path, score, verified):
    monkeypatch.setattr(navigator, "Session", ReadSession)
    monkeypatch.setattr(navigator, "make_plan", lambda cf, goal, page, done=None: {
        "steps": [{"do": "read", "target": "trending repositories"}], "done_text": ""})
    monkeypatch.setattr(navigator, "extract", lambda cf, what, url, text: ["trending this week"])

    class Cf(FakeCf):
        stats = {"jev_calls": 0, "jev_seconds": 0.0, "llm_calls": 0, "llm_seconds": 0.0}
        decisions = []
    result = navigator.run(Cf(score), "https://github.com/", "find trending repos", out=str(tmp_path),
                           picker="keyword", log=lambda m: None)
    assert result["verified"] is verified
    last = json.loads((tmp_path / "actions.json").read_text())["actions"][-1]
    assert ("outcome" in last) is (not verified)


def test_an_information_goal_also_needs_the_screen_in_the_state_asked_for(monkeypatch, tmp_path):
    """Trending set to 'Today' showed real repositories for a 'this week' goal: the content passes, the state doesn't."""
    monkeypatch.setattr(navigator, "FINAL_REPLANS", 0)
    monkeypatch.setattr(navigator, "Session", ReadSession)
    monkeypatch.setattr(navigator, "make_plan", lambda cf, goal, page, done=None: {
        "steps": [{"do": "read", "target": "trending repositories"}], "done_text": ""})
    monkeypatch.setattr(navigator, "extract", lambda cf, what, url, text: ["ruvnet / ruflo"])
    scores = [0.94, 0.64]  # content real; final screen in the wrong time range (Clef + screenshot on 'Today')

    class Cf(FakeCf):
        stats = {"jev_calls": 0, "jev_seconds": 0.0, "llm_calls": 0, "llm_seconds": 0.0}
        decisions = []
        def yes(self, instructions, state, true="yes", false="no", model=None, images=None):
            return scores.pop(0)
    result = navigator.run(Cf(0), "https://github.com/", "find trending repos this week", out=str(tmp_path),
                           picker="keyword", log=lambda m: None)
    assert result["verified"] is False and scores == []
