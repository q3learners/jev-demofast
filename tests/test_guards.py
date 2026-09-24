import pytest

from jev_demofast.drive.guards import blocked, fill_text, has_secret, on_site


def test_blocked_labels_unless_the_step_asks_for_it():
    assert blocked("Sign up for free")
    assert blocked("Continue with Google")
    assert blocked("Delete account")
    assert not blocked("Log in")
    assert not blocked("Sign up", unless="click Sign up")


def test_on_site_allows_subdomains_only():
    assert on_site("https://staging.example.com/a", "staging.example.com")
    assert on_site("https://app.example.com/", "example.com")
    assert not on_site("https://accounts.google.com/", "example.com")


def test_secrets_are_swapped_only_at_typing_time(monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "s3cret")
    assert has_secret("{{PASSWORD}}")
    assert fill_text("{{PASSWORD}}") == "s3cret"
    assert fill_text("plain") == "plain"
    monkeypatch.delenv("DEMO_PASSWORD")
    with pytest.raises(SystemExit):
        fill_text("{{PASSWORD}}")


def test_task_goal_strips_demo_framing():
    from jev_demofast.drive.guards import task_goal
    assert task_goal("Create a demo of how to invite a teammate") == "invite a teammate"
    assert task_goal("create a demo video showing how to reset my password.") == "reset my password."
    assert task_goal("Show me how to stop GitHub emails") == "stop GitHub emails"
    assert task_goal("Make a demo: turn off watching notifications") == "turn off watching notifications"
    assert task_goal("Invite jane@example.com as a member") == "Invite jane@example.com as a member"
    assert task_goal("Show which signals matter") == "Show which signals matter"  # not a "how to" framing


def test_would_change_data():
    from jev_demofast.drive.guards import would_change
    assert would_change({"role": "button", "label": "Invite Member"})
    assert would_change({"role": "button", "label": "Save changes"})
    assert would_change({"role": "checkbox", "label": "Email"})
    assert would_change({"role": "switch", "label": "Watching"})
    assert not would_change({"role": "link", "label": "Settings"})
    assert not would_change({"role": "button", "label": "Open menu"})
    assert not would_change({"role": "link", "label": "Update notes"})  # links navigate, they don't submit
