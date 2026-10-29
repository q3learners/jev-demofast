"""The tour: the recorder visits every shot of the founder's list, the way a person would (the link on screen,
else straight there), shows each page with a glide down it, and ends with the brief's task when there is one."""
import re

import pytest

from jev_demofast.drive import tour

HOST = "www.tutorq.test"  # where the site lands; the demo is started from the apex, as people type it
LINKS = {"/": ["/k12", "/sat", "/campus", "/pricing"], "/k12": ["/", "/sat"], "/sat": ["/k12"], "/campus": []}
TALL = {"/pricing": 780, "/": 3000, "/k12": 2500, "/sat": 780, "/campus": 2000}  # /sat fits on one screen
REDIRECTS = {"/campus": "https://campus.tutorq.test/", "/pricing": f"https://{HOST}/"}  # /pricing: gone, sent home
TEXT = {"/": "Understand what you're learning.", "/k12": "Your child's personal tutor", "/sat": "Your SAT tutor",
        "/campus": "Every student deserves help"}
MAP = {route: {"kind": "page", "examples": [route], "texts": [text]} for route, text in TEXT.items()}
MAP["/pricing"] = {"kind": "page", "examples": ["/pricing"], "texts": ["Plans for every family"]}
# A Flutter app's page reached only through a button (no href): the map found it by clicking it
BUTTONS = {"/": {"I'm a student\nIt's for my own school work.": "/student"}}
LINKS["/student"], TALL["/student"], TEXT["/student"] = [], 780, "How do you get in?"
MAP["/student"] = {"kind": "page", "examples": ["/student"], "texts": ["How do you get in?"]}


def fake_session(slow=()):
    class FakeSession:
        def __init__(self, url, fresh=False):
            from urllib.parse import urlparse
            self.host = urlparse(url).hostname  # as typed, like Session: "tutorq.test" may land on www.
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
                    if js.startswith("window.scrollBy"):  # one small step of a glide: a fraction of the screen
                        outer.y += round(780 * float(re.search(r"innerHeight \* ([\d.]+)", js).group(1)))
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
            self.page = {"url": self.url, "title": self._path(), "text": TEXT.get(self._path(), ""), "actions": []}
            return self.page

        def elements(self):
            return [{"node": n, "label": f"Go {to}", "actions": ["click"], "role": "link"}
                    for n, to in enumerate(LINKS[self._path()])] + \
                [{"node": 100 + n, "label": label, "actions": ["click"], "role": "button"}
                 for n, label in enumerate(BUTTONS.get(self._path(), {}))]

        def href(self, node):
            return None if node >= 100 else f"https://{HOST}{LINKS[self._path()][node]}"

        def act(self, e, kind, text=None):
            if e["node"] >= 100:
                self.navigated_by_button = True
                return self._go(list(BUTTONS[self._path()].values())[e["node"] - 100])
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
        self.actions, self.dry_run, self.s, self.held = [], False, s, []

    def snap(self, hold, node=None, badge=None): self.held.append((hold, self.s.y))
    def discard(self): pass
    def tee(self, log): return log
    def save(self, goal, decisions=(), skipped=()): self.goal, self.skipped = goal, list(skipped)

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


def play(shots, slow=(), url="https://tutorq.test/"):
    recs = []

    def recorder(out, s, blur_typed=True):
        recs.append(FakeRecorder(out, s))
        return recs[-1]
    result = tour.run(Cf(), url, shots, MAP, log=lambda m: None, session=fake_session(slow), recorder=recorder)
    play.rec = recs[0]
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
    # the result page says which; the voice-over doesn't ("We couldn't reach the contact page, but talk to us...")
    assert not any("outcome" in a for a in actions) and play.rec.skipped == ["/k12"]


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



def test_links_are_matched_on_the_host_the_site_landed_on():
    """Review: --url tutorq.test landing on www.tutorq.test made every shot a cut and any page count as arrived."""
    result, actions = play([HOME, {"page": "/k12", "show": "K-12"}], url="https://tutorq.test/")
    assert [a["do"] for a in actions if a.get("shot") == 1][0] == "click" and result["verified"] is True


def test_a_redirect_to_another_page_is_not_arrived():
    """Review: a shot whose page redirected home counted as shown, and its pitch was spoken over the home page."""
    result, _ = play([HOME, {"page": "/pricing", "show": "plans"}])
    assert result["skipped"] == ["/pricing"] and result["verified"] is False


def test_a_skipped_page_never_disowns_a_verified_task(monkeypatch):
    """Review: "couldn't show /k12" landed on the task's verified results, and the narrator disowned them."""
    def drive_goal(cf, s, rec, goal, index, max_steps, log, ms, steps=None):
        rec.commit({"do": "read", "target": "showcase", "items": ["Dasher NZ $140"]})
        return True, ""
    monkeypatch.setattr(tour, "drive_goal", drive_goal)
    result, actions = play([HOME, {"page": "/k12", "show": "K-12"}, {"task": "find", "show": ""}], slow={"/k12"})
    assert "outcome" not in actions[-1] and result["skipped"] == ["/k12"]
    assert play.rec.skipped == ["/k12"]  # kept with the recording, for the voice-over


def test_a_shot_with_items_ends_on_them_outlined(monkeypatch):
    seen = []

    def showcase(cf, s, rec, goal, log=print, count=3):
        seen.append(goal)
        rec.commit({"do": "read", "target": "showcase", "items": ["Echo Dot $49"]})
        return ["Echo Dot $49"]
    monkeypatch.setattr(tour, "showcase", showcase)
    _, actions = play([HOME, {"page": "/k12", "show": "what's hot today", "items": True}])
    assert actions[-1]["do"] == "read" and actions[-1]["shot"] == 1 and actions[-1]["show"] == "what's hot today"
    assert seen == ["what's hot today"]


def test_a_page_is_shown_with_a_glide_the_viewer_can_follow():
    # each scroll was one jump between two stills: the video cut from the banner to a screen lower, never moving
    play([HOME, {"page": "/k12", "show": "K-12"}])
    looks = [a for a in play.rec.actions if a["do"] == "look" and a["shot"] == 1]
    assert len(looks) == 1  # one moment for the voice-over, however many frames show the motion
    ys = [y for _, y in play.rec.held]
    moving = [y for hold, y in play.rec.held if hold == tour.FRAME_S]
    assert len(moving) == 4 * tour.GLIDE_FRAMES  # home and /k12, two glides each, every step a frame
    assert max(ys) >= 1.5 * 780  # past the first screen, into the page
    assert len(looks[0]["headings"]) == 2  # what the viewer saw at both stops



def test_a_lone_home_page_is_shown_all_the_way_down_one_moment_per_screen():
    # a one-page site's story is down its page: each stop is a moment of its own, so the script has room to be spoken
    play([HOME])
    looks = [a for a in play.rec.actions if a["do"] == "look"]
    assert len(looks) == 4  # 3000 px tall at 624 px per glide, until the page ends
    assert [a["shot"] for a in looks] == [1, 2, 3, 4] and all(len(a["headings"]) == 1 for a in looks)
    assert len(looks) <= tour.LONE_PAGE_GLIDES


def test_back_to_the_top_is_instant_on_a_site_that_scrolls_smoothly():
    """selvage.run sets scroll-behavior: smooth. Asked to scroll to the top, it was still near the bottom two frames
    later, so the tour picked the link it saw there ("Explore all milestones") and clicked as it slid away; nothing
    opened and the shot was skipped. Going back up has to land at once, like each step of a glide."""
    class SmoothPage:
        y = 2400

        class browser:
            @staticmethod
            def evaluate(js, **k):
                if "scrollTo" in js and "'instant'" in js:
                    SmoothPage.y = 0
                # any other scroll starts an animation: two frames later the page has barely moved

        def next_frame(self): pass
        def observe(self): return {}

    page = SmoothPage()
    tour._to_top(page)
    assert SmoothPage.y == 0


def test_every_scroll_the_tool_makes_lands_at_once():
    """A smooth-scrolling site animates any scroll that doesn't say otherwise; what's read or clicked next is then
    wherever the page happened to be. So every scroll in the recorder and the drivers is instant."""
    import pathlib
    src = pathlib.Path(tour.__file__).parents[1]
    calls = [(str(p.relative_to(src)), m.group(0)) for p in src.rglob("*.py") for m in re.finditer(
        r"(scrollTo|scrollBy|scrollIntoView)\(.*", p.read_text())]  # to the line's end: arguments nest parentheses
    assert calls and not [c for c in calls if "instant" not in c[1]], calls


def test_a_page_reached_by_a_button_is_clicked_on_camera():
    """k12.tutorq.ai: its pages are reached with buttons, which have no href. The map knows which button leads where."""
    index = {**MAP, "/": {**MAP["/"], "links": [{"label": "I'm a student", "to": "/student", "via": "button"}]}}
    recs = []
    tour.run(Cf(), "https://tutorq.test/", [HOME, {"page": "/student", "show": "the way in"}], index,
             log=lambda m: None, session=fake_session(), recorder=lambda out, s, blur_typed=True: recs.append(FakeRecorder(out, s)) or recs[-1])
    click = recs[0].actions[-1]
    assert click["do"] == "click" and click["target"].startswith("I'm a student") and click["shot"] == 1


def test_without_a_matching_button_the_tour_still_cuts():
    result, actions = play([HOME, {"page": "/student", "show": "the way in"}])  # MAP has no button links
    assert actions[-1]["do"] == "go" and result["verified"] is True


def test_button_labels_come_from_the_maps_button_links_and_the_page_they_were_found_on():
    index = {"/": {"examples": ["/"], "links": [{"label": "Go", "to": "/a"},
                                                {"label": "I'm a student", "to": "/student", "via": "button"}]},
             "/x": {"examples": ["/x"], "links": [{"label": "Back", "to": "/student", "via": "button"}]}, "_site": {}}
    assert tour.button_labels(index) == {"/student": {"/": ["I'm a student"], "/x": ["Back"]}}


def test_a_button_found_on_another_page_is_never_clicked_here():
    """Review: "Sign in" navigates on K-12's who page but submits on its kid page. A label is only trusted on the page
    the explorer found it on."""
    index = {**MAP, "/x": {"kind": "page", "examples": ["/x"], "texts": ["x"],
                           "links": [{"label": "I'm a student", "to": "/student", "via": "button"}]}}
    recs = []
    tour.run(Cf(), "https://tutorq.test/", [HOME, {"page": "/student", "show": "the way in"}], index,
             log=lambda m: None, session=fake_session(), recorder=lambda out, s, blur_typed=True: recs.append(FakeRecorder(out, s)) or recs[-1])
    assert recs[0].actions[-1]["do"] == "go"  # a cut, not a click on the same-looking button of "/"


def test_pages_that_differ_only_in_query_or_hash_are_different_pages():
    """?mode=signin and ?mode=signup are different K-12 screens; /#/a and /#/b are different hash-routed pages."""
    assert not tour.same_page("https://k12.test/setup/account?mode=signin", "/setup/account?mode=signup")
    assert tour.same_page("https://k12.test/setup/account?mode=signup", "/setup/account?mode=signup")
    assert not tour.same_page("https://k12.test/#/a", "/#/b") and tour.same_page("https://k12.test/#/b", "/#/b")
    assert tour.same_page("https://shop.test/pages/about/?utm=x", "/pages/about")  # a link-found page: path only
