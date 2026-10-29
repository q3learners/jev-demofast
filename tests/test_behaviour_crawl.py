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
