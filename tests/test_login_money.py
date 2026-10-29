"""A step that takes money or verifies the parent is judged from the screen, not from one product's wording: before a
forward click in a logged-in run, Clef is asked. Measured 29 October, 3 runs each, the same score every run: K-12's
card check 0.98, its "Verify again" page 0.97, a generic checkout 0.99; K-12's kids page (live) 0.07, a kid's login
0.11, subjects 0.03, a workspace setup 0.01. Unsure, or the model is down: the demo stops there."""
import pytest

from jev_demofast.drive import money
from jev_demofast.drive.guards import HazardStop
from jev_demofast.login import Login
from test_login_flow import Sessions
from test_login_hazards import SAVE, session
from test_login_sign_in import FORM, GOOD, ORIGIN

CONTINUE = {"node": 7, "label": "Continue", "role": "button", "actions": {"click": {"kind": "click"}}}
ADD = {"node": 8, "label": "Add", "role": "button", "actions": {"click": {"kind": "click"}}}
NAME = {"node": 9, "label": "First name", "role": "textbox", "actions": {"fill": {"kind": "fill"}}}


class Clef:
    s = type("S", (), {"check_model": "@cf/cloudflare/clef"})()

    def __init__(self, score):
        self.score, self.asked = score, []

    def yes(self, q, state, true="", false="", model=None, images=None):
        assert q == money.QUESTION and true == money.TRUE and false == money.FALSE and images
        self.asked.append(state)
        if isinstance(self.score, Exception):
            raise self.score
        return self.score


def screen(s, url="https://k12.test/setup/kids", text="Who are we setting up?"):
    s.page = {"url": url, "text": text}
    s.browser.call = lambda method, **p: {"data": ""}
    return s


@pytest.mark.parametrize("score,stops", [(0.98, True), (0.5, True), (0.11, False), (0.01, False)])
def test_a_forward_click_on_a_money_step_is_refused(score, stops):
    s = screen(session())
    s.money_step = money.judge(Clef(score))
    if stops:
        with pytest.raises(HazardStop):
            s.act(CONTINUE, "click")
        assert s.browser.acted == []
    else:
        s.act(CONTINUE, "click")
        assert len(s.browser.acted) == 1


def test_the_model_down_stops_the_demo():
    s = screen(session())
    s.money_step = money.judge(Clef(RuntimeError("model down")))
    with pytest.raises(HazardStop):
        s.act(CONTINUE, "click")


def test_every_click_asks_but_typing_doesnt():
    """Security review: a forward word list missed "Get started", "Proceed" and "OK"."""
    clef = Clef(0.98)
    s = screen(session())
    s.money_step = money.judge(clef)
    s.act(NAME, "fill", text="Maya")
    assert clef.asked == []
    proceed = {"node": 10, "label": "Proceed", "role": "button", "actions": {"click": {"kind": "click"}}}
    with pytest.raises(HazardStop):
        s.act(proceed, "click")


def test_ordinary_clicks_pass():
    clef = Clef(0.07)
    s = screen(session())
    s.money_step = money.judge(clef)
    s.act(ADD, "click")
    s.act(CONTINUE, "click")
    assert len(s.browser.acted) == 2


def test_a_no_is_asked_again_but_a_yes_is_remembered():
    """Security review: a card form in an iframe or a canvas doesn't change the page's text, so a "no" is never reused
    for the same text. A "yes" stays: that screen is never clicked on."""
    clef = Clef(0.01)
    s = screen(session())
    s.money_step = money.judge(clef)
    s.act(CONTINUE, "click")
    s.act(SAVE, "click")
    assert len(clef.asked) == 2
    clef.score = 0.98
    for _ in range(2):
        with pytest.raises(HazardStop):
            s.act(CONTINUE, "click")
    assert len(clef.asked) == 3


def test_hazards_off_never_asks():
    clef = Clef(0.98)
    s = screen(session(hazards=False))
    s.money_step = money.judge(clef)
    s.act(CONTINUE, "click")
    assert clef.asked == []


def test_a_signed_in_session_judges_money_steps():
    login = Login.prepare(cf=Clef(0.01), url=ORIGIN + "/", index={}, log=lambda m: None, session=Sessions(),
                          ask=lambda q: {"id": q["id"], "form": "f1", "values": dict(GOOD)},
                          find_forms=lambda s, origin, index, cf, log: [FORM])
    assert login.session(ORIGIN + "/").money_step is not None
