import argparse

import pytest

from jev_demofast.cli import choose_browser
from jev_demofast.config import Settings

SETTINGS = Settings(account_id="a", api_token="t", jev_token="t")


def args(**kw):
    base = dict(url="https://app.example.com/", fresh=False, use_my_browser=False, yes=False)
    return argparse.Namespace(**{**base, **kw})


def test_isolated_chrome_is_the_default(monkeypatch):
    for var in ("BU_CDP_URL", "BU_CDP_WS", "BU_NAME"):
        monkeypatch.delenv(var, raising=False)
    choose_browser(args(), SETTINGS)
    import os
    assert os.environ["BU_CDP_URL"] == "http://127.0.0.1:9333"
    assert os.environ["BU_NAME"] == "jdf-isolated"


def test_my_browser_refuses_fresh_so_it_never_logs_you_out():
    with pytest.raises(SystemExit, match="logging you out"):
        choose_browser(args(use_my_browser=True, fresh=True, yes=True), SETTINGS)


def test_my_browser_needs_confirmation_when_not_interactive(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(SystemExit, match="confirmation"):
        choose_browser(args(use_my_browser=True), SETTINGS)


def test_my_browser_discovers_the_running_chrome_on_a_separate_connection(monkeypatch):
    monkeypatch.setenv("BU_CDP_URL", "http://127.0.0.1:9333")
    choose_browser(args(use_my_browser=True, yes=True), SETTINGS)
    import os
    assert "BU_CDP_URL" not in os.environ and os.environ["BU_NAME"] == "jdf-my-browser"
