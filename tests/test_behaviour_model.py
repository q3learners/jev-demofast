"""The behaviour map's shape: screens (pages, tabs, dialogs, wizard steps), actions with what they did, and how a new
crawl merges into a saved map. Today's readers get the same route entries they always had."""
from jev_demofast.behaviour.model import add_action, add_screen, empty, legacy_routes, merge, screen_key

BLANK = {"title": "", "url": "", "texts": [], "fields": [], "controls": []}


def test_dialog_and_step_keys_are_distinct_from_their_page():
    assert screen_key("https://k12.test/setup/kids") == "/setup/kids"
    assert screen_key("https://k12.test/setup/kids", "Add Maya first?", "dialog") == \
        "/setup/kids · dialog: Add Maya first?"
    assert screen_key("https://k12.test/#/kids/new", "Maya's login", "wizard-step") == \
        "/#/kids/new · step: Maya's login"


def test_the_same_action_is_updated_not_repeated():
    m = empty()
    i = add_action(m, "/kids", "Add", "click", "no change", "t1")
    assert add_action(m, "/kids", "Add", "click", "added 'Maya'", "t2") == i
    assert m["actions"][i]["outcome"] == "added 'Maya'" and len(m["actions"]) == 1


def test_merge_marks_unseen_screens_of_a_remapped_section_gone_and_keeps_others():
    saved = empty()
    add_screen(saved, "/kids", {**BLANK, "kind": "tab", "section": "Kids"}, "t1")
    add_screen(saved, "/kids/old", {**BLANK, "kind": "page", "section": "Kids"}, "t1")
    add_screen(saved, "/settings", {**BLANK, "kind": "tab", "section": "Settings"}, "t1")
    fresh = empty()
    add_screen(fresh, "/kids", {**BLANK, "kind": "tab", "section": "Kids"}, "t2")
    m = merge(saved, fresh, seen_sections={"Kids"}, now="t2")
    assert m["screens"]["/kids/old"]["gone"] and not m["screens"]["/kids"].get("gone")
    assert m["screens"]["/settings"]["last_seen"] == "t1" and not m["screens"]["/settings"].get("gone")


def test_legacy_routes_feed_todays_readers():
    m = empty()
    add_screen(m, "/kids", {"kind": "tab", "title": "Kids", "url": "https://k12.test/kids", "texts": ["Your kids"],
                            "fields": [], "controls": ["Add a kid"]}, "t1")
    add_screen(m, "/kids · dialog: Add?", {**BLANK, "kind": "dialog"}, "t1")
    r = legacy_routes(m, "https://k12.test")
    assert list(r) == ["/kids"] and r["/kids"]["buttons"] == [{"label": "Add a kid", "submit": False}]
    assert r["/kids"]["texts"] == ["Your kids"] and r["/kids"]["kind"] == "page"
