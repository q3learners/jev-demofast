"""The final review's findings, each pinned: the forms path never leaves the app; a refused fill or a failed
re-sign-in costs a section, not the map; a dialog from a plain click is handled; the list cap never swallows an add;
a tab with a search box keeps its other controls; a job keeps the account state it ran under; the account's email
never reaches the map or a prompt."""
import json

from fakeapp import FakeApp
from test_behaviour_forms import VALUES, Model

from jev_demofast.behaviour import crawl as crawl_mod
from jev_demofast.behaviour import forms, jobs
from jev_demofast.behaviour.crawl import Budget
from jev_demofast.behaviour.model import empty
from jev_demofast.behaviour.screens import read_screen


def walk(app, cf=None, new_session=None):
    return crawl_mod.crawl(new_session or app.restart, cf or Model(), "https://k12.test", log=lambda m: None,
                           now="t1")


def on(app, path):
    app.goto("https://k12.test" + path)
    return read_screen(app)


def test_c1_a_form_that_hands_off_to_another_site_is_left():
    app = FakeApp(create_leaves=True)
    key, screen = on(app, "/contacts/new")
    m = empty()
    forms.handle(app, Model(), m, key, screen, "set up", Budget(), log=lambda m: None, now="t1")
    assert app.pressed == ["Create"] and app.typed.count("Mo") == 1  # ours only, never the partner's form
    assert ("Create", "refused: leaves the app → help.other.test") in {(a["control"], a["outcome"])
                                                                       for a in m["actions"]}
    assert not any("help.other.test" in (s.get("url") or "") for s in m["screens"].values())


def test_c2_a_refused_fill_costs_the_form_not_the_map(monkeypatch):
    monkeypatch.setitem(VALUES, "Age", "maya@school.test")  # an address that isn't the account's: refused
    app = FakeApp()
    m = walk(app)
    assert "Continue" not in app.pressed and "/settings" in m["screens"]
    assert ("Age", "refused: Age") in {(a["control"], a["outcome"]) for a in m["actions"]}


def test_c2_a_failed_sign_in_on_the_way_back_costs_the_section():
    app = FakeApp(strand_after="Ava")
    calls = []

    def new_session(url):
        calls.append(url)
        if len(calls) > 1:
            raise RuntimeError("login: couldn't sign in for the recording")
        return app.restart(url)
    m = walk(app, new_session=new_session)
    assert "Kids: way back lost" in m["left"] and m["account"]["sections"]


def test_c2_malformed_model_output_costs_the_section(monkeypatch):
    class Odd(Model):
        def chat_json(self, model, system, context, extra=None):
            if system == forms.MAKE_VALUES:
                return {"values": ["Maya", "14"]}
            return super().chat_json(model, system, context, extra)
    m = walk(FakeApp(), Odd())
    assert "/settings" in m["screens"]


def test_i1_a_dialog_from_a_plain_click_is_handled_and_the_section_goes_on():
    app = FakeApp(tips=True)
    m = walk(app)
    assert "Got it" in app.pressed and "Kids: way back lost" not in m["left"]
    assert any(j["name"] == "Add a kid" for j in m["jobs"])


def test_i2_the_list_cap_never_swallows_an_add():
    app = FakeApp(kid_buttons=True)
    walk(app)
    assert "Add a kid" in app.pressed


def test_i3_a_tab_with_a_search_box_keeps_its_other_controls():
    app = FakeApp(search=True)
    walk(app)
    assert sum(label.startswith("Subject ") for label in app.pressed) == 2


def test_i4_a_job_keeps_the_account_state_it_ran_under():
    m = walk(FakeApp(state="partway"), Model(state="partway", finishes=0.9))
    m["account"]["state"] = "set up"  # the founder finished setup since
    job = jobs.find(Model(), m)[0]
    assert job["needs"] == "partway: Your kids" and not job["repeatable"]


def test_i5_the_accounts_email_never_reaches_the_map_or_a_prompt():
    app = FakeApp()
    key, screen = on(app, "/contacts/new")
    m = empty()
    prompts = []

    class Watch(Model):
        def chat_json(self, model, system, context, extra=None):
            prompts.append(json.dumps(context))
            return super().chat_json(model, system, context, extra)
    forms.handle(app, Watch(), m, key, screen, "set up", Budget(), log=lambda m: None, now="t1")
    key, screen = on(app, "/contacts/new")
    forms.handle(app, Watch(), m, key, screen, "set up", Budget(), log=lambda m: None, now="t2")
    assert "parent@demo.test" in app.typed
    assert "parent@demo.test" not in json.dumps(m) and not any("parent@demo.test" in p for p in prompts)


def test_a_dialog_from_a_plain_click_is_only_ever_dismissed():
    """Security review: "Archive" opens "Archive Ava? Yes / Cancel"; confirming would change an existing kid."""
    from test_behaviour_forms import Model as FormModel

    class SaysYes(FormModel):
        def choose(self, instructions, options, state, allow_none=False):
            labels = {v: k for k, v in options.items()}
            if instructions == forms.DIALOG_Q and "Yes" in labels:
                return labels["Yes"], 0.9
            return super().choose(instructions, options, state, allow_none)
    app = FakeApp(archive=True, tips=True)
    walk(app, SaysYes())
    assert "Yes" not in app.pressed and "Ava" in app.kids and "Got it" in app.pressed
