"""The walk through the signed-in app: the account's state, every section, every control mapping may press, back
each time, within budget; refusals recorded, never pressed."""
from fakeapp import FakeApp

from jev_demofast.behaviour import crawl as crawl_mod
from jev_demofast.behaviour.crawl import account_state


class Model:
    """A fake Cloudflare: chat_json answers by the system prompt it's asked with."""
    s = type("S", (), {"read_model": "read", "check_model": "@cf/cloudflare/clef"})()

    def __init__(self, answers=None, fail=()):
        self.answers, self.fail, self.asked = answers or {}, set(fail), []

    def chat_json(self, model, system, context, extra=None):
        self.asked.append(system)
        for key, answer in self.answers.items():
            if key == system:
                if key in self.fail:
                    raise RuntimeError("model down")
                return answer(context) if callable(answer) else answer
        raise RuntimeError("not scripted")


def test_partway_names_the_step():
    cf = Model({crawl_mod.ACCOUNT: {"setup_unfinished": True, "current_step": "Your kids"}})
    assert account_state(cf, {"texts": ["Your kids, current step"], "controls": ["Add"]}) == "partway: Your kids"


def test_set_up():
    cf = Model({crawl_mod.ACCOUNT: {"setup_unfinished": False, "current_step": ""}})
    assert account_state(cf, {"texts": ["Welcome back"], "controls": ["Kids"]}) == "set up"


def test_model_down_is_unknown():
    cf = Model({crawl_mod.ACCOUNT: {}}, fail={crawl_mod.ACCOUNT})
    assert account_state(cf, {"texts": [], "controls": []}, log=lambda m: None) == "unknown"


SET_UP = {crawl_mod.ACCOUNT: {"setup_unfinished": False, "current_step": ""}}


def walk(app, budget=None, cf=None):
    return crawl_mod.crawl(app.restart, cf or Model(SET_UP), "https://k12.test", budget=budget, log=lambda m: None,
                           now="t1")


def test_every_section_is_visited():
    app = FakeApp()
    m = walk(app)
    assert m["account"] == {"state": "set up", "sections": ["Home", "Kids", "Subjects", "Settings"]}
    assert {"/home", "/kids", "/subjects", "/settings"} <= set(m["screens"])
    assert m["screens"]["/kids"]["section"] == "Kids"


def test_refused_controls_are_recorded_not_pressed():
    app = FakeApp()
    m = walk(app)
    assert not {"Delete", "Log out", "Upgrade", "Email me weekly", "Verify with a card"} & set(app.pressed)
    assert all(a["outcome"].startswith("refused") for a in m["actions"] if a["control"] in ("Delete", "Log out"))


def test_what_a_press_did_is_recorded():
    m = walk(FakeApp())
    did = {(a["screen"], a["control"]): a["outcome"] for a in m["actions"]}
    assert did[("/kids", "Ava")] == "→ /kids/ava" and did[("/kids", "Add a kid")] == "→ /kids/new"


def test_long_lists_open_two_items():
    app = FakeApp()
    m = walk(app)
    assert sum(label.startswith("Subject ") for label in app.pressed) == 2
    assert "/subjects: 38 more items" in m["left"]


def test_lost_way_back_reopens_the_section():
    app = FakeApp(strand_after="Ava")
    m = walk(app)
    assert ("/kids", "Leo") in {(a["screen"], a["control"]) for a in m["actions"]}
    assert "/settings" in m["screens"]


def test_the_total_budget_stops_the_walk():
    app = FakeApp()
    m = walk(app, budget=crawl_mod.Budget(total_s=0))
    assert m["left"] == [f"{s}: not walked (out of time)" for s in ("Home", "Kids", "Subjects", "Settings")]
