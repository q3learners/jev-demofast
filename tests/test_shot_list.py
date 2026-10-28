"""The founder's shot list: which pages of the map can be shown, and the list the model gives, checked against it."""
from jev_demofast.narrate.shots import MAX_SHOTS, offerable, validate

MAP = {"_site": {"start": "https://tutorq.ai", "menus": []},
       "/": {"kind": "page", "examples": ["/"], "texts": ["Understand what you're learning."]},
       "/k12": {"kind": "page", "examples": ["/k12"], "texts": ["Your child's personal tutor"]},
       "/sat": {"kind": "page", "examples": ["/sat"], "texts": ["Your personal SAT tutor"]},
       "/:handle/login": {"kind": "page", "examples": ["/grader/login"], "texts": ["429 Too Many Requests"]},
       "/downloads/:handle": {"kind": "page", "examples": ["/downloads/x.dmg"], "texts": ["404", "not found"]},
       "/empty": {"kind": "page", "examples": ["/empty"], "texts": []}}


def test_error_and_empty_pages_are_never_offered():
    assert set(offerable(MAP)) == {"/", "/k12", "/sat"}


def test_the_opening_is_home_and_unknown_pages_are_dropped():
    said = []
    shots = validate([{"page": "/k12", "show": "a"}, {"page": "/pricing", "show": "b"}], MAP, log=said.append)
    assert shots == [{"page": "/", "show": ""}, {"page": "/k12", "show": "a"}]
    assert any("/pricing" in line for line in said)


def test_a_task_is_kept_only_as_the_last_shot():
    shots = validate([{"task": "t1", "show": ""}, {"page": "/sat", "show": ""}, {"task": "t2", "show": ""}], MAP,
                     log=lambda m: None)
    assert [s.get("task") for s in shots] == [None, None, "t2"]


def test_shots_are_capped():
    many = {**MAP, **{f"/p{n}": {"kind": "page", "examples": [f"/p{n}"], "texts": [f"Page {n}"]} for n in range(9)}}
    shots = validate([{"page": f"/p{n}", "show": str(n)} for n in range(9)], many, log=lambda m: None)
    assert len(shots) == 1 + MAX_SHOTS


def test_a_reply_that_isnt_a_shot_list_means_no_tour():
    assert validate("junk", MAP, log=lambda m: None) == []
    assert validate(None, MAP, log=lambda m: None) == []


def test_a_page_is_shown_once():
    # Allbirds: "/ → mens-new-arrivals → mens-new-arrivals → mens-new-arrivals → task"; q3learners.ai: "/ → /about → /",
    # the home page played twice
    shots = validate([{"page": "/k12", "show": "a"}, {"page": "/k12", "show": "b"}, {"page": "/sat", "show": "c"},
                      {"page": "/k12", "show": "d"}, {"page": "/", "show": "e"}], MAP, log=lambda m: None)
    assert [s["page"] for s in shots] == ["/", "/k12", "/sat"]


def test_a_shot_can_ask_for_its_items_to_be_shown():
    # Amazon: "look at hot items sold today" ended on the new-releases list without naming one item
    shots = validate([{"page": "/k12", "show": "a", "items": True}, {"page": "/sat", "show": "b", "items": "yes"}],
                     MAP, log=lambda m: None)
    assert shots[1] == {"page": "/k12", "show": "a", "items": True} and "items" not in shots[2]


def test_a_one_page_site_is_toured_down_its_home_page():
    # onecentdemo.com: one page; with no shot beyond home the demo hunted for a goal, got stuck, and lasted 6 s
    one_page = {"_site": MAP["_site"], "/": MAP["/"]}
    assert validate([{"page": "/", "show": "the promise"}], one_page, log=lambda m: None) == [
        {"page": "/", "show": "the promise"}]
    assert validate([], one_page, log=lambda m: None) == [{"page": "/", "show": ""}]


def test_a_site_with_pages_but_no_page_to_show_is_toured_down_its_home_page():
    # reafi.ai: 6 pages mapped, a script about the home page alone, no shot beyond it. The demo hunted for a goal and
    # went home → /register → home six times
    assert validate([{"page": "/", "show": "the promise"}], MAP, log=lambda m: None) == [
        {"page": "/", "show": "the promise"}]
    assert validate([{"page": "/nope"}], MAP, log=lambda m: None) == [{"page": "/", "show": ""}]
    assert validate([], MAP, log=lambda m: None) == [{"page": "/", "show": ""}]


def test_a_sign_in_page_is_never_a_shot():
    """reafi.ai: /login and /register were the only pages besides home, and the tour went to them."""
    from jev_demofast.narrate.shots import offerable
    m = {"/login": {"texts": ["Welcome back"], "sign_in": True}, "/about": {"texts": ["Our story"], "sign_in": False}}
    assert list(offerable(m)) == ["/about"]
