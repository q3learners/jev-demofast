from jev_demofast.browser.elements import observed, relevance, shortlist, words
from jev_demofast.drive.pick import Picker

PAGE = {"url": "https://x.test/", "title": "Home", "actions": [
    {"kind": "click", "node": 1, "id": "c1", "label": "Acme Campus", "role": "link"},
    {"kind": "click", "node": 2, "id": "c2", "label": "Explore Acme Campus", "role": "link"},
    {"kind": "click", "node": 3, "id": "c3", "label": "Log in", "role": "link"},
    {"kind": "fill", "node": 4, "id": "f4", "label": "Email address", "role": "textbox", "current_value": ""},
]}


class FakeJev:
    """Stands in for Cloudflare: picks the option whose description contains `answer`."""
    def __init__(self, answer):
        self.answer, self.calls = answer, 0

    def choose(self, instructions, options, state, allow_none=False):
        self.calls += 1
        key = next((k for k, v in options.items() if self.answer in v), "none" if allow_none else next(iter(options)))
        return (None if key == "none" else key), 0.9


def test_words_and_relevance():
    els = observed(PAGE)
    assert words("the Forgot password?") == {"forgo", "passw"}
    assert relevance(els[2], "Log in") == 1
    assert [e["label"] for e in shortlist(els, "Acme Campus", 2)] == ["Acme Campus", "Explore Acme Campus"]


def test_keyword_mode_never_calls_a_model():
    els = [e for e in observed(PAGE) if "click" in e["actions"]]
    fake = FakeJev("Log in")
    chosen, conf, how = Picker(fake, "keyword").pick("Log in", "click", els, PAGE, "goal")
    assert chosen["label"] == "Log in" and how == "keyword" and fake.calls == 0
    assert Picker(fake, "keyword").pick("Sign in", "click", els, PAGE, "goal")[0] is None


def test_hybrid_asks_jev_only_when_words_dont_line_up():
    els = [e for e in observed(PAGE) if "click" in e["actions"]]
    fake = FakeJev("Log in")
    chosen, _, how = Picker(fake, "hybrid").pick("Sign in", "click", els, PAGE, "goal")   # synonym: no shared words
    assert chosen["label"] == "Log in" and how == "jev" and fake.calls == 1
    chosen, _, how = Picker(fake, "hybrid").pick("Log in", "click", els, PAGE, "goal")    # full keyword match
    assert how == "keyword" and fake.calls == 1
