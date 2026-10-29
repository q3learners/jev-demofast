"""Reading the screen the session is on: a dialog is its own screen (Flutter's too, found by its box: its semantics tree
is drawn with opacity 0), and the app's sections are what stays on screen between them."""
from fakeapp import FakeApp

from jev_demofast.behaviour.screens import nav_labels, read_screen, sections


def press(app, label):
    app.act(next(e for e in app.elements() if e["label"] == label), "click")


def type_into(app, label, text):
    app.act(next(e for e in app.elements() if e["label"] == label), "fill", text=text)


def to_add_form_with_a_name(app):
    press(app, "Kids")
    press(app, "Add a kid")
    type_into(app, "First name", "Maya")
    type_into(app, "Age", "14")
    press(app, "Continue")


def test_a_dialog_is_its_own_screen():
    app = FakeApp()
    to_add_form_with_a_name(app)
    key, screen = read_screen(app)
    assert screen["kind"] == "dialog" and key == "/kids/new · dialog: Add Maya first?"
    assert screen["controls"] == ["Skip", "Add"]


def test_a_flutter_dialog_is_found_by_its_box():
    app = FakeApp(flutter=True)
    to_add_form_with_a_name(app)
    assert app.observe()["text"] == "Skip Add"
    key, screen = read_screen(app)
    assert screen["kind"] == "dialog" and key == "/kids/new · dialog: Add Maya first?"


def test_sections_are_what_stays_on_screen():
    app = FakeApp()
    home = nav_labels(app)
    press(app, "Kids")
    assert sections(home, nav_labels(app)) == ["Home", "Kids", "Subjects", "Settings"]


def test_a_wizard_step_is_keyed_by_its_title():
    app = FakeApp()
    press(app, "Kids")
    press(app, "Add a kid")
    type_into(app, "First name", "Maya")
    press(app, "Add")
    key, screen = read_screen(app, wizard=True)
    assert screen["kind"] == "wizard-step" and key == "/kids/setup/login · step: Maya's login"
