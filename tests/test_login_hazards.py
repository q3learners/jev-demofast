"""In a logged-in run the demo may act like a user (add a student, ask the tutor), but never pays, deletes, logs out,
changes the account's sign-in details or reaches someone outside the account. A brief can't unlock these."""
import pytest

from jev_demofast.drive import guards, jev_drive, tour
from jev_demofast.drive.guards import HazardStop, hazard
from jev_demofast.drive.session import Session

HAZARDS = ["Pay now", "Payment details", "Purchase", "Buy credits", "Checkout", "Subscribe", "Upgrade",
           "Billing", "Add card", "Verify you are the parent", "Delete homework", "Remove student",
           "Cancel subscription", "Close account", "Log out", "Sign out", "Change email", "Change password",
           "Reset password", "Invite a parent", "Share", "Send to a friend"]


@pytest.mark.parametrize("label", HAZARDS)
def test_each_hazard_word_matches(label):
    assert hazard(label)


@pytest.mark.parametrize("label", ["Save", "Add student", "Send", "Continue", "Study plan", "Ask the tutor"])
def test_ordinary_labels_pass(label):
    assert not hazard(label)


def test_report_card_is_refused_by_design():
    """"card" is a whole word: "Report card" costs a shot, which is cheaper than any payment step."""
    assert hazard("Report card")


def test_moving_forward_on_a_money_page_is_refused():
    """K-12's card check is a "Continue" under "Verify you are the parent": the label alone is harmless."""
    assert hazard("Continue", context="Verify you are the parent. Card number CVC")
    assert not hazard("Continue", context="Your kids, next step. Child's first name")
    assert not hazard("Back", context="Verify you are the parent. Card number")


class FakeBrowser:
    def __init__(self, text=""):
        self.text, self.acted = text, []

    def evaluate(self, js, **k):
        return self.text if "innerText" in js else None


def session(hazards=True, own_email=None, text=""):
    s = Session.__new__(Session)
    s.browser, s.hazards, s.own_email, s.page = FakeBrowser(text), hazards, own_email, {"text": text}
    s.refind = lambda e: e
    s.arm = lambda: None
    s.browser.act = lambda action, page, text=None: s.browser.acted.append((action, text))
    return s


DELETE = {"node": 1, "label": "Delete homework", "role": "button", "actions": {"click": {"kind": "click"}}}
SAVE = {"node": 2, "label": "Save", "role": "button", "actions": {"click": {"kind": "click"}}}
EMAIL = {"node": 3, "label": "Parent email", "role": "textbox", "hint": "email", "actions": {"fill": {"kind": "fill"}}}


def test_hazards_are_refused_by_session_act_for_every_caller():
    s = session()
    with pytest.raises(HazardStop):
        s.act(DELETE, "click")
    assert s.browser.acted == []
    s.act(SAVE, "click")
    assert len(s.browser.acted) == 1


def test_hazards_off_changes_nothing():
    s = session(hazards=False)
    s.act(DELETE, "click")
    assert len(s.browser.acted) == 1


def test_an_email_other_than_the_accounts_own_is_refused():
    s = session(own_email="parent@demo.test")
    with pytest.raises(HazardStop):
        s.act(EMAIL, "fill", text="someone@else.test")
    s.act(EMAIL, "fill", text="parent@demo.test")
    assert len(s.browser.acted) == 1


def test_a_refused_click_is_never_filmed():
    s = session()
    snaps = []
    rec = type("R", (), {"dry_run": False, "snap": lambda self, *a, **k: snaps.append(a)})()
    with pytest.raises(HazardStop):
        jev_drive.click_on_camera(s, rec, DELETE, {"do": "click"})
    assert snaps == []


def test_the_tour_stops_and_says_why(monkeypatch):
    said = []

    class S:
        host, start_url = "k12.test", "https://k12.test/"

        def __init__(self, url, fresh=False):
            self.page = {"url": "https://k12.test/", "text": "Home", "actions": []}

        def observe(self): return self.page
        def elements(self): return []
        def close(self): pass

    class R:
        actions, dry_run = [], False
        def __init__(self, out, s): pass
        def tee(self, log): return log
        def snap(self, *a, **k): pass
        def commit(self, *a, **k): self.actions.append({"do": "open"})
        def discard(self): pass
        def save(self, *a, **k): pass

    monkeypatch.setattr(tour, "first_screen", lambda *a: None)
    monkeypatch.setattr(tour, "covered", lambda s: False)
    monkeypatch.setattr(tour, "clear_popups", lambda *a: None)
    monkeypatch.setattr(tour, "_show", lambda *a: (_ for _ in ()).throw(HazardStop("Delete homework")))
    cf = type("Cf", (), {"decisions": [], "stats": {"jev_calls": 0, "jev_seconds": 0.0}})()
    result = tour.run(cf, "https://k12.test/", [{"page": "/", "show": "home"}, {"page": "/x", "show": "x"}], {},
                      log=said.append, session=S, recorder=R)
    assert result["stopped_at"] == "Delete homework" and result["verified"] is False
    assert any("the demo stops here" in line for line in said)
