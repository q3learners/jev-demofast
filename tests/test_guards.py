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
