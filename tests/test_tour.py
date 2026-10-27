"""The tour: the recorder visits every shot of the founder's list, the way a person would (the link on screen,
else straight there), shows each page with a scroll or two, and ends with the brief's task when there is one."""
import pytest

from jev_demofast.drive import tour

HOST = "tutorq.test"
LINKS = {"/": ["/k12", "/sat", "/campus"], "/k12": ["/", "/sat"], "/sat": ["/k12"], "/campus": []}
TALL = {"/": 3000, "/k12": 2500, "/sat": 780, "/campus": 2000}  # /sat fits on one screen
REDIRECTS = {"/campus": f"https://campus.{HOST}/"}


def fake_session(slow=()):
    class FakeSession:
        host = HOST

        def __init__(self, url, fresh=False):
            self.start_url, self.url, self.y = url, f"https://{HOST}/", 0
            self.observe()

        def _path(self):
            from urllib.parse import urlparse
            return urlparse(self.url).path if urlparse(self.url).hostname == HOST else "/campus"

        @property
        def browser(self):
            outer = self

            class B:
                def evaluate(self, js, **k):
                    if js == tour.CAN_SCROLL:
                        return outer.y + 780 < TALL[outer._path()] - 40
                    if js == tour.SCROLL:
                        outer.y += 624
                    if js == tour.TO_TOP:
                        outer.y = 0
                    if js == tour.HEADINGS:
                        return [f"{outer._path()} at {outer.y}"]
                    return None

                def call(self, method, **params):
                    if method == "Page.navigate":
                        path = "/" + params["url"].split("/", 3)[3]
                        if path in slow:
                            raise TimeoutError("Page.navigate timed out after 30s")
                        outer._go(path)
                    return {}
            return B()

        def _go(self, path):
            self.url, self.y = REDIRECTS.get(path, f"https://{HOST}{path}"), 0

        def observe(self):
            self.page = {"url": self.url, "title": self._path(), "text": "", "actions": []}
            return self.page

        def elements(self):
            return [{"node": n, "label": f"Go {to}", "actions": ["click"], "role": "link"}
                    for n, to in enumerate(LINKS[self._path()])]

        def href(self, node):
            return f"https://{HOST}{LINKS[self._path()][node]}"

        def act(self, e, kind, text=None):
            path = LINKS[self._path()][e["node"]]
            if path in slow:
                raise TimeoutError("timed out")
            self._go(path)

        def wait_loaded(self, timeout=10): pass
        def wait_for_page(self): return "settled"
        def next_frame(self): pass
        def close(self): pass
    return FakeSession


class FakeRecorder:
    def __init__(self, out, s, blur_typed=True):
        self.actions, self.dry_run = [], False

    def snap(self, hold, node=None, badge=None): pass
    def discard(self): pass
    def tee(self, log): return log
    def save(self, goal, decisions=()): self.goal = goal

    def commit(self, action, page=None):
        self.actions.append({"segment": f"{len(self.actions):02d}", **action})

    def unconfirmed(self, why):
        self.actions[-1].setdefault("outcome", f"not confirmed: {why}")


class Cf:
    decisions, stats = [], {"jev_calls": 0, "jev_seconds": 0.0}


@pytest.fixture(autouse=True)
def no_popups(monkeypatch):
    monkeypatch.setattr(tour, "first_screen", lambda cf, s, log: None)
    monkeypatch.setattr(tour, "covered", lambda s: False)
    monkeypatch.setattr(tour, "clear_popups", lambda cf, s, log: None)


def play(shots, slow=()):
    recs = []

    def recorder(out, s, blur_typed=True):
        recs.append(FakeRecorder(out, s))
        return recs[-1]
    result = tour.run(Cf(), f"https://{HOST}/", shots, {}, log=lambda m: None, session=fake_session(slow),
                      recorder=recorder)
    return result, recs[0].actions


HOME = {"page": "/", "show": "the promise"}


def test_each_shot_is_reached_by_its_link_and_shown():
    result, actions = play([HOME, {"page": "/k12", "show": "K-12"}, {"page": "/sat", "show": "SAT"}])
    assert [a["do"] for a in actions] == ["open", "look", "click", "look", "click"]
    assert [a["shot"] for a in actions if a["do"] == "click"] == [1, 2] and actions[2]["show"] == "K-12"
    assert result["verified"] is True and result["skipped"] == []


def test_a_shot_without_a_visible_link_is_a_cut():
    _, actions = play([HOME, {"page": "/sat", "show": "SAT"}, {"page": "/campus", "show": "Campus"}])
    assert [a["do"] for a in actions if a.get("shot") == 2][0] == "go"  # /sat doesn't link to /campus


def test_a_redirect_to_a_subdomain_counts_as_arrived():
    result, _ = play([HOME, {"page": "/campus", "show": "Campus"}])
    assert result["skipped"] == [] and result["verified"] is True


def test_a_shot_that_wont_load_is_skipped_and_the_tour_goes_on():
    result, actions = play([HOME, {"page": "/k12", "show": "K-12"}, {"page": "/sat", "show": "SAT"}], slow={"/k12"})
    assert result["skipped"] == ["/k12"] and result["verified"] is False
    assert any(a.get("shot") == 2 for a in actions)
    assert actions[-1]["outcome"].startswith("not confirmed") and "/k12" in actions[-1]["outcome"]


def test_a_short_page_gets_no_look():
    _, actions = play([HOME, {"page": "/sat", "show": "SAT"}])
    assert [a["do"] for a in actions if a.get("shot") == 1] == ["click"]


def test_the_task_shot_runs_the_goal_loop(monkeypatch):
    def drive_goal(cf, s, rec, goal, index, max_steps, log, ms, steps=None):
        rec.commit({"do": "filter", "target": "Price: $126 - $150"})
        return True, ""
    monkeypatch.setattr(tour, "drive_goal", drive_goal)
    result, actions = play([HOME, {"task": "find shoes under $150", "show": "the payoff"}])
    assert actions[-1] == {**actions[-1], "do": "filter", "shot": 1, "show": "the payoff"}
    assert result["verified"] is True and result["goal"] == "find shoes under $150"


def test_the_task_starts_from_the_top_of_the_page(monkeypatch):
    # Allbirds: after the listing's scroll, every filter "isn't on screen"
    seen = {}

    def drive_goal(cf, s, rec, goal, index, max_steps, log, ms, steps=None):
        seen["y"] = s.y
        return True, ""
    monkeypatch.setattr(tour, "drive_goal", drive_goal)
    play([HOME, {"page": "/k12", "show": "K-12"}, {"task": "find a tutor", "show": ""}])
    assert seen["y"] == 0
