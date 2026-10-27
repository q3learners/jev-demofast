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
    assert len(validate([{"page": ("/k12", "/sat")[n % 2], "show": str(n)} for n in range(9)], MAP, log=lambda m: None)) == 1 + MAX_SHOTS


def test_nothing_valid_means_no_tour():
    assert validate([{"page": "/nope"}], MAP, log=lambda m: None) == []
    assert validate("junk", MAP, log=lambda m: None) == []


def test_the_same_page_twice_in_a_row_is_one_shot():
    # Allbirds: "/ → mens-new-arrivals → mens-new-arrivals → mens-new-arrivals → task"
    shots = validate([{"page": "/k12", "show": "a"}, {"page": "/k12", "show": "b"}, {"page": "/sat", "show": "c"},
                      {"page": "/k12", "show": "d"}], MAP, log=lambda m: None)
    assert [s["page"] for s in shots] == ["/", "/k12", "/sat", "/k12"]
