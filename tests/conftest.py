import pytest


@pytest.fixture(autouse=True)
def no_opening_wait(monkeypatch):
    """Demos wait 3 s for a first-visit pop-up before their opening frame; tests have no pop-up timers."""
    from jev_demofast.drive import jev_drive
    monkeypatch.setattr(jev_drive, "OPENING_SETTLE_S", 0)
