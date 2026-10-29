"""A Flutter web app draws on its own surface: until its accessibility layer is on, the page has no text and no
controls to read (k12.tutorq.ai). The session turns that layer on after every load."""
from jev_demofast.drive import session as session_mod
from jev_demofast.drive.session import ENABLE_FLUTTER_JS, FLUTTER_JS, SEMANTICS_READY_JS, Session


class FakeBrowser:
    def __init__(self, flutter=True, appears_after=0, view_after=0):
        self.flutter, self.appears_after, self.view_after = flutter, appears_after, view_after
        self.clicks, self.polls, self.tries, self.calls = 0, 0, 0, []

    def evaluate(self, js, **k):
        self.calls.append(js)
        if js == "document.readyState":
            return "complete"
        if js == FLUTTER_JS:
            return self.flutter
        if js == ENABLE_FLUTTER_JS:
            self.tries += 1
            if self.tries <= self.view_after:  # the loader is there, the view and its placeholder not yet
                return False
            self.clicks += 1
            return True
        if js == SEMANTICS_READY_JS:
            self.polls += 1
            return self.clicks > 0 and self.polls > self.appears_after
        return None

    def call(self, method, **params):
        if method == "Page.navigate":  # a new document: Flutter's layer starts off again
            self.polls, self.tries = 0, 0


def session(browser):
    s = Session.__new__(Session)
    s.browser, s.is_flutter = browser, False
    return s


def test_a_flutter_page_gets_its_layer_turned_on():
    b = FakeBrowser(appears_after=2)
    s = session(b)
    assert s.flutter_ready() is True
    assert b.clicks == 1 and s.is_flutter is True


def test_a_normal_page_is_left_alone():
    b = FakeBrowser(flutter=False)
    s = session(b)
    assert s.flutter_ready() is False
    assert b.clicks == 0 and b.calls == [FLUTTER_JS] and s.is_flutter is False


def test_layer_turned_on_again_after_a_reload():
    b = FakeBrowser()
    s = session(b)
    s.wait_loaded()
    b.call("Page.navigate", url="https://k12.test/setup/who")
    s.wait_loaded()
    assert b.clicks == 2


def test_gives_up_quietly_when_no_semantics_appear(monkeypatch):
    monkeypatch.setattr(session_mod.time, "sleep", lambda s: None)
    b = FakeBrowser(appears_after=10 ** 6)
    s = session(b)
    assert s.flutter_ready(timeout=0.05) is False


def test_a_flutter_view_drawn_after_the_load_still_gets_its_layer(monkeypatch):
    """k12.tutorq.ai: the document was complete at 0.92 s, its flutter-view appeared at 1.35 s; only the loader
    (window._flutter) was there at load."""
    monkeypatch.setattr(session_mod.time, "sleep", lambda s: None)
    b = FakeBrowser(view_after=3)
    s = session(b)
    assert s.flutter_ready() is True and b.clicks == 1


def test_the_loader_alone_marks_a_flutter_page():
    assert "window._flutter" in FLUTTER_JS
