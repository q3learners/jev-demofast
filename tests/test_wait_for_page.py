"""After an action the tool waits for the page, not for a fixed time: quick when nothing happens or the page has
settled, patient while it is still changing, and it follows a navigation to the new document."""
from jev_demofast.drive.session import Session


class FakeBrowser:
    """Answers the watcher's state script from a list: dicts (watching this document) or None (a new document)."""
    def __init__(self, states):
        self.states, self.armed, self.evaluated = list(states), 0, 0

    def evaluate(self, js, await_promise=False):
        if "__jdfWatch=" in js.replace(" ", ""):  # arming the watcher
            self.armed += 1
            return True
        if "readyState" in js:
            return "complete"
        self.evaluated += 1
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]


def session(states):
    s = object.__new__(Session)
    s.browser = FakeBrowser(states)
    return s


def test_nothing_changed_returns_after_the_idle_time():
    s = session([{"since_start": 100, "since_last": None}, {"since_start": 450, "since_last": None}])
    assert s.wait_for_page() == "unchanged"


def test_a_change_counts_once_the_page_has_been_quiet():
    s = session([{"since_start": 60, "since_last": 10}, {"since_start": 120, "since_last": 40},
                 {"since_start": 250, "since_last": 130}])
    assert s.wait_for_page() == "settled"


def test_a_navigation_waits_for_the_new_document_and_watches_it():
    s = session([None, {"since_start": 30, "since_last": None}, {"since_start": 140, "since_last": None}])
    assert s.wait_for_page() == "navigated"
    assert s.browser.armed == 1  # re-armed on the new document


def test_a_page_that_never_stops_changing_is_capped():
    s = session([{"since_start": 10, "since_last": 5}])
    assert s.wait_for_page(max_s=0.15) == "busy"


def test_arming_before_an_action():
    s = session([{"since_start": 0, "since_last": None}])
    s.arm()
    assert s.browser.armed == 1
