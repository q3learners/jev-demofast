"""Exploring runs in its own browser context, so the cookies it collects (a closed pop-up) don't change later demos;
and the tool can hover, for menus that open on hover."""
from jev_demofast.browser import cdp as cdpmod
from jev_demofast.drive.session import Session


def fake_cdp(monkeypatch):
    calls = []

    def cdp(method, session_id=None, **params):
        calls.append((method, params))
        if method == "Target.createBrowserContext":
            return {"browserContextId": "ctx-1"}
        if method == "Target.createTarget":
            return {"targetId": "t-1"}
        if method == "Target.attachToTarget":
            return {"sessionId": "s-1"}
        if method == "Runtime.evaluate":
            return {"result": {"value": "complete"}}
        return {}
    monkeypatch.setattr(cdpmod, "cdp", cdp)
    monkeypatch.setattr(cdpmod, "ensure_daemon", lambda: None)
    return calls


def test_an_isolated_browser_opens_its_own_context(monkeypatch):
    calls = fake_cdp(monkeypatch)
    b = cdpmod.Browser("about:blank", isolated=True)
    created = next(p for m, p in calls if m == "Target.createTarget")
    assert ("Target.createBrowserContext", {}) in calls and created["browserContextId"] == "ctx-1"
    b.close()
    assert ("Target.disposeBrowserContext", {"browserContextId": "ctx-1"}) in calls


def test_a_default_browser_uses_the_shared_profile(monkeypatch):
    calls = fake_cdp(monkeypatch)
    cdpmod.Browser("about:blank").close()
    assert not any(m == "Target.createBrowserContext" for m, _ in calls)
    assert "browserContextId" not in next(p for m, p in calls if m == "Target.createTarget")


def test_hover_moves_the_mouse_to_the_element_centre():
    sent = []

    class B:
        evaluate = staticmethod(lambda js, **k: {"x": 100, "y": 50, "w": 40, "h": 20})
        call = staticmethod(lambda method, **params: sent.append((method, params)))
    s = object.__new__(Session)
    s.browser = B()
    s.hover({"node": 7, "label": "Men"})
    assert sent == [("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 120, "y": 60})]
