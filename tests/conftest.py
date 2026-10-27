import pytest


@pytest.fixture(autouse=True)
def no_first_popup_wait(monkeypatch):
    """Demos watch for a first-visit pop-up for up to 5 s before their opening frame; tests have no pop-up timers."""
    from jev_demofast.drive import popups
    monkeypatch.setattr(popups, "FIRST_POPUP_WAIT_S", 0)
