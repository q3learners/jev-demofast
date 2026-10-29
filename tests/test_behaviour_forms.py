"""Forms, dialogs and wizards inside the walk: made-up values (an email only ever the account's own), the dialog
answered the way that carries on ("Add Maya first?" → Add), a wizard walked through, and a one-time account step
walked up to, never through, the click that would finish it."""
from fakeapp import FakeApp

from jev_demofast.behaviour import crawl as crawl_mod
from jev_demofast.behaviour import forms
from jev_demofast.behaviour.crawl import Budget
from jev_demofast.behaviour.model import empty
from jev_demofast.behaviour.screens import read_screen

VALUES = {"First name": "Maya", "Age": "14", "Login ID": "maya-14", "Grade": "9", "Nickname": "Mo",
          "Email": "someone@else.test"}


class Model:
    s = type("S", (), {"read_model": "read", "check_model": "@cf/cloudflare/clef"})()

    def __init__(self, state="set up", finishes=0.01, values_fail=False):
        self.state, self.finishes, self.values_fail = state, finishes, values_fail

    def chat_json(self, model, system, context, extra=None):
        if system == crawl_mod.ACCOUNT:
            return {"setup_unfinished": self.state != "set up", "current_step": "Your kids"}
        if system == forms.MAKE_VALUES:
            if self.values_fail:
                raise RuntimeError("model down")
            return {"values": {f: VALUES[f] for f in context["fields"] if f in VALUES}}
        raise RuntimeError("not scripted")

    def choose(self, instructions, options, state, allow_none=False):
        labels = {v: k for k, v in options.items()}
        for want in ("Add", "Continue", "Next", "Create") if instructions == forms.DIALOG_Q else \
                ("Continue", "Next", "Create", "Add"):
            if want in labels:
                return labels[want], 0.9
        if instructions == forms.DIALOG_Q and options:  # a model may pick anything it's offered
            return next(iter(options)), 0.6
        return None, 0.0

    def yes(self, instructions, state, true="", false="", model=None, images=None):
        assert instructions.startswith("Would pressing") and images
        return self.finishes


def walk(app, cf):
    return crawl_mod.crawl(app.restart, cf, "https://k12.test", log=lambda m: None, now="t1")


def test_adding_a_kid_is_walked_through_the_dialog_and_wizard():
    app = FakeApp()
    m = walk(app, Model())
    assert "Maya" in app.typed and "14" in app.typed and "Maya" in app.kids
    assert app.pressed[app.pressed.index("Continue"):app.pressed.index("Continue") + 4] == \
        ["Continue", "Add", "Next", "Next"]
    did = {(a["screen"], a["control"]): a["outcome"] for a in m["actions"]}
    assert did[("/kids/new · dialog: Add Maya first?", "Skip")] == "not pressed"
    assert any(k.startswith("/kids/setup/done") for k in m["screens"])
    assert m["chains"] and len(m["chains"][0]["steps"]) >= 6 and m["chains"][0]["state"] == "set up"


def test_partway_setup_stops_before_finishing():
    app = FakeApp(state="partway")
    m = walk(app, Model(state="partway", finishes=0.9))
    assert "Continue" not in app.pressed and app.path == "/setup/kids"
    assert {(a["control"], a["outcome"]) for a in m["actions"]} >= {("Continue", "seen, not finished")}
    assert m["account"]["state"] == "partway: Your kids"


def test_no_values_no_submit():
    app = FakeApp()
    walk(app, Model(values_fail=True))
    assert app.typed == [] and "Continue" not in app.pressed and "Add" not in app.pressed


def test_a_dialog_with_only_refused_ways_is_closed():
    app = FakeApp()
    app.dialog = {"title": "Delete Maya?", "buttons": ["Delete", "Remove"]}
    m = empty()
    key, screen = read_screen(app)
    forms.handle(app, Model(), m, key, screen, "set up", Budget(), log=lambda m: None, now="t1", section="Kids")
    assert app.pressed == [] and app.dialog is None
    assert {a["outcome"] for a in m["actions"]} == {"refused: no safe way"}


def test_only_the_accounts_email_is_typed():
    app = FakeApp()
    app.goto("https://k12.test/contacts/new")
    m = empty()
    key, screen = read_screen(app)
    forms.handle(app, Model(), m, key, screen, "set up", Budget(), log=lambda m: None, now="t1", section="Kids")
    assert "parent@demo.test" in app.typed and "someone@else.test" not in app.typed and "Create" in app.pressed


def _on_dialog(app, title, buttons):
    app.dialog = {"title": title, "buttons": buttons}
    return read_screen(app)


def test_a_dialog_click_gets_the_one_time_check_too():
    """Security review: on a partway account, a dialog's button that would finish setup isn't pressed either."""
    app = FakeApp(state="partway")
    key, screen = _on_dialog(app, "Add Maya first?", ["Skip", "Add"])
    m = empty()
    forms.handle(app, Model(state="partway", finishes=0.9), m, key, screen, "partway: Your kids", Budget(),
                 log=lambda m: None, now="t1", section="Setup")
    assert app.pressed == [] and ("Add", "seen, not finished") in {(a["control"], a["outcome"]) for a in m["actions"]}


def test_a_dialog_mapping_didnt_open_from_a_form_allows_no_change():
    """Security review: "Save changes" in a dialog is only pressed for a form mapping itself filled."""
    app = FakeApp()
    key, screen = _on_dialog(app, "Unsaved changes", ["Save changes", "Keep editing"])
    forms.handle(app, Model(), empty(), key, screen, "set up", Budget(), log=lambda m: None, now="t1")
    assert "Save changes" not in app.pressed


def test_an_unknown_account_state_gets_the_one_time_check():
    """Security review: a state the model couldn't read is treated like partway at the finishing click."""
    app = FakeApp(state="partway")
    key, screen = read_screen(app)
    forms.handle(app, Model(state="partway", finishes=0.9), empty(), key, screen, "unknown", Budget(),
                 log=lambda m: None, now="t1")
    assert "Continue" not in app.pressed
