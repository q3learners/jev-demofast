"""What mapping may press (add and create, carry a form it filled forward; never change what's there, never a
toggle, never a hazard), and what a press did."""
import pytest

from jev_demofast.behaviour.rules import may_press, outcome


def el(label, role="button"):
    return {"node": 1, "role": role, "label": label, "actions": {"click": {}}}


@pytest.mark.parametrize("label,role,filled,ok", [
    ("Add a kid", "button", False, True), ("Next", "button", False, True), ("Kids", "tab", False, True),
    ("Delete", "button", False, False), ("Log out", "button", False, False),
    ("Save", "button", False, False), ("Save", "button", True, True),
    ("Email me weekly", "switch", False, False), ("Email me weekly", "switch", True, False),
    ("Verify with a card", "button", True, False), ("Upgrade", "button", False, False)])
def test_may_press(label, role, filled, ok):
    assert may_press(el(label, role), filled_here=filled) is ok


def test_outcomes():
    assert outcome("/kids", "Your kids", "/kids/new", "page", "Who are we setting up?", []) == "→ /kids/new"
    assert outcome("/kids/new", "", "/kids/new · dialog: Add Maya first?", "dialog", "Skip Add", ["Maya"]) == \
        "dialog /kids/new · dialog: Add Maya first?"
    assert outcome("/setup/kids", "Your kids", "/setup/kids", "page", "Your kids\nMaya", ["Maya", "14"]) == \
        "added 'Maya'"
    assert outcome("/kids", "Your kids", "/kids", "page", "Your kids", ["Maya"]) == "no change"
