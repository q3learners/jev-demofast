"""The founder's script is written before recording, from the prompt and the map; after recording it is fitted over
the segments in the founder's own words, corrected only where the recording differs. Every demo has a map."""
import json

import pytest

from jev_demofast import cli
from jev_demofast import explore as explore_mod
from jev_demofast.drive import jev_drive
from jev_demofast.narrate import fit, script, story

from test_drive_filters_showcase import MAP, UNDER_100, Cf, Listing

PROMPT = "Show my investors how easy it is to find men's running shoes under $150 on our site"
SITE = {"_site": {"start": "https://shop.test/", "menus": [
            {"opener": "Men", "opens_on": "hover", "items": [{"label": "Active", "to": "/collections/mens-active"},
                                                             {"label": "Socks", "to": "/collections/socks"}]}]},
        "/": {"links": [{"label": f"link {n}", "to": f"/x/{n}"} for n in range(80)], "fields": [], "texts": [
            "Wildly Comfortable. Super Natural."], "kind": "page"},
        "/collections/:handle": {"links": [], "fields": [], "texts": ["Men's Active Shoes"], "kind": "listing",
                                 "filters": [{"group": "Price", "kind": "checkbox", "param": None,
                                              "values": ["Under $75", "$126 - $150"]},
                                             {"group": "Product Type", "kind": "checkbox", "param": None,
                                              "values": ["Running Shoes", "Golf"]}]}}


class Writer:
    """A model that answers every chat with `reply`, keeping what it was asked."""
    s = type("S", (), {"script_model": "nemotron", "script_extra": {}})

    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def chat(self, model, system, user, extra=None, max_tokens=4000):
        self.calls.append({"model": model, "system": system, "user": json.loads(user)})
        return self.reply


def test_the_founders_script_is_written_from_the_prompt_and_the_map(tmp_path):
    cf = Writer("Finding the right running shoe should take seconds. Watch.")
    text = story.write(cf, PROMPT, SITE, str(tmp_path), log=lambda m: None)
    assert text == "Finding the right running shoe should take seconds. Watch."
    assert (tmp_path / "story.txt").read_text().strip() == text
    (call,) = cf.calls
    assert call["model"] == "nemotron" and "founder" in call["system"]
    sent = json.dumps(call["user"])
    assert PROMPT.replace("$", "") in sent.replace("$", "")  # the audience and purpose, as typed
    for known in ("Men", "Active", "Product Type", "Running Shoes", "$126 - $150", "Wildly Comfortable"):
        assert known in sent
    assert "link 79" not in sent and len(sent) < 4000  # what the map knows, not the whole map


def test_the_brief_never_carries_a_secret_and_includes_the_product_line(tmp_path):
    cf = Writer("Script.")
    story.write(cf, "Sign in as {{EMAIL}} and show my team the reports", SITE, str(tmp_path), product="Acme Reports",
                log=lambda m: None)
    sent = cf.calls[0]["user"]
    assert "{{EMAIL}}" not in sent["brief"] and "(secret)" in sent["brief"] and sent["product"] == "Acme Reports"


def test_the_story_prompt_has_no_example_lines_about_shoes():
    """Nemotron copied example lines word for word ("ten tabs", "heavy lifting"): nothing it could copy into a shop."""
    for word in ("shoe", "filter", "price", "menu"):
        assert word not in story.SAMPLE.lower()


def actions(tmp_path, segs):
    (tmp_path / "actions.json").write_text(json.dumps({"goal": "find running shoes", "actions": segs}))


def test_narration_fits_the_founders_script_over_the_segments(tmp_path):
    actions(tmp_path, [{"segment": "00", "do": "open", "screen_text": "Free shipping over $100 Skip to content"},
                       {"segment": "01", "do": "filter", "target": "Price: $126 - $150",
                        "unavailable": ["Price: Under $75"]},
                       {"segment": "02", "do": "read", "target": "showcase", "items": ["Dasher NZ $140"]}])
    (tmp_path / "story.txt").write_text("Finding a running shoe should take seconds. Our filters get you there.")
    cf = Writer("[00] Finding a running shoe should take seconds. [01] Nothing under $75 today, so we go up to $150. "
                "[02] And there's the Dasher NZ at $140.")
    lines = script.read_lines(script.write(cf, str(tmp_path), log=lambda m: None))
    assert lines[0] == "Finding a running shoe should take seconds." and len(lines) == 3
    call = cf.calls[0]
    assert call["system"] == fit.SYSTEM.format(budget=fit.budget([{}] * 3))
    assert call["user"]["founder_script"].startswith("Finding a running shoe")
    assert call["user"]["segments"][1]["unavailable"] == ["Price: Under $75"]  # the truth pass sees what was greyed out
    assert "screen_text" not in call["user"]["segments"][0]  # given page text, it described the screen again


def test_without_a_founders_script_the_narration_is_written_as_before(tmp_path):
    actions(tmp_path, [{"segment": "00", "do": "open"}])
    cf = Writer("00 | Open | So here's the site.")
    script.write(cf, str(tmp_path), log=lambda m: None)
    assert cf.calls[0]["system"] == script.SYSTEM.format(cap=script.LINE_CAP, budget=script.word_budget(1))


def test_a_founders_sentence_fits_the_word_budget():
    """At 11 words a segment the model wrote captions; a spoken founder sentence needs more room."""
    assert script.WORDS_PER_SEGMENT >= 16 and script.LINE_CAP >= 24
    assert "2-6 words" not in script.SYSTEM and "2-6 words" not in fit.SYSTEM


def test_filter_values_the_site_disabled_reach_the_narrator_on_their_own_filter(monkeypatch, tmp_path):
    def apply(cf, s, rec, goal, entry, log, unavailable=None):
        rec.commit({"do": "filter", "target": "Price: $126 - $150"}, s.page)
        unavailable.append("Price: Under $75")
        rec.commit({"do": "filter", "target": "Product Type: Running Shoes"}, s.page)
        return []
    monkeypatch.setattr(jev_drive, "apply_filters", apply)
    monkeypatch.setattr(jev_drive, "Session", lambda url, fresh=False: Listing())
    jev_drive.run(Cf(UNDER_100), "https://shop.test/collections/mens", "goal", MAP, out=str(tmp_path),
                  log=lambda m: None)
    segs = json.loads((tmp_path / "actions.json").read_text())["actions"]
    price, kind = [a for a in segs if a["do"] == "filter"]
    assert price["unavailable"] == ["Price: Under $75"] and "unavailable" not in kind


@pytest.fixture
def demo(monkeypatch, tmp_path):
    """The demo command with explore, the script writer, the run and the render faked; returns what happened."""
    seen = {"order": [], "explored": 0}
    monkeypatch.setattr(cli, "MAPS", tmp_path / "maps")
    monkeypatch.setattr(cli, "_cf", lambda a=None, require=True: "cf")

    def explore(url, out=None, **k):
        seen["explored"] += 1
        seen["order"].append("explore")
        home = {"kind": "page", "texts": [] if seen.get("empty") else ["Wildly Comfortable. Super Natural."]}
        found = {"_site": {"menus": [], "blocked": seen.get("blocked")}, "/": home}
        with open(out, "w") as f:
            json.dump(found, f)
        return found
    monkeypatch.setattr(explore_mod, "explore", explore)
    monkeypatch.setattr(story, "write", lambda cf, prompt, index, work, product="", readme="", log=print: seen["order"].append(
        ("story", prompt, sorted(index))) or "script")

    def run(a, cf=None):
        seen["order"].append(("run", a.index))
        return {"verified": True}
    monkeypatch.setattr(cli, "cmd_run", run)
    monkeypatch.setattr(cli, "cmd_narrate", lambda a, cf=None: seen["order"].append("narrate"))
    monkeypatch.setattr(cli, "cmd_render", lambda a: seen["order"].append("render"))
    monkeypatch.chdir(tmp_path)
    return seen


def test_a_demo_without_a_map_explores_first_then_writes_the_script_then_records(demo, tmp_path):
    cli.main(["demo", PROMPT, "--url", "https://www.shop.test/", "--voice", "apollo", "--out", "d.mp4"])
    cached = str(tmp_path / "maps" / "shop.test.json")
    assert demo["order"] == ["explore", ("story", PROMPT, ["/", "_site"]), ("run", cached), "narrate"]


def test_a_cached_map_is_reused(demo):
    cli.main(["demo", PROMPT, "--url", "https://shop.test/", "--voice", "apollo", "--out", "d.mp4"])
    cli.main(["demo", PROMPT, "--url", "https://shop.test/", "--voice", "apollo", "--out", "d.mp4"])
    assert demo["explored"] == 1


def test_a_given_map_is_used_as_is(demo, tmp_path):
    (tmp_path / "mine.json").write_text(json.dumps({"/": {"kind": "page"}}))
    cli.main(["demo", PROMPT, "--url", "https://shop.test/", "--index", "mine.json", "--out", "d.mp4"])
    assert demo["explored"] == 0 and demo["order"] == [("run", "mine.json"), "render"]  # no voice: no script


def test_a_demo_on_a_site_that_blocks_the_tool_stops_before_recording(demo):
    demo["blocked"] = "Access Denied"
    with pytest.raises(SystemExit) as stop:
        cli.main(["demo", PROMPT, "--url", "https://shop.test/", "--out", "d.mp4"])
    assert "blocked: Access Denied" in str(stop.value) and demo["order"] == ["explore"]


def test_a_site_with_nothing_readable_stops_before_a_script_is_written(demo, tmp_path):
    # k12.tutorq.ai draws on a canvas (Flutter): the map had one page and no text, and the script invented a menu,
    # a listing and filters. No map, no product: stop instead, and keep no cache of the empty map.
    demo["empty"] = True
    with pytest.raises(SystemExit) as stop:
        cli.main(["demo", PROMPT, "--url", "https://k12.shop.test/", "--voice", "apollo", "--out", "d.mp4"])
    assert str(stop.value).startswith("stopped: nothing readable on k12.shop.test") and demo["order"] == ["explore"]
    assert not (tmp_path / "maps" / "k12.shop.test.json").exists()


def test_an_empty_map_knows_nothing_and_a_page_with_text_knows_something():
    assert story.knows_nothing({"_site": {"menus": []}, "/": {"kind": "page", "texts": []}})
    assert not story.knows_nothing({"_site": {"menus": []}, "/": {"kind": "page", "texts": ["A tutor for every subject"]}})
    assert not story.knows_nothing(SITE)


# --- the shot list comes with the script ------------------------------------------------------------------------

def test_the_script_comes_with_shots_from_the_map(tmp_path):
    from test_shot_list import MAP as TUTORQ
    cf = Writer(json.dumps({"script": "Every learner hits a wall.",
                            "shots": [{"page": "/k12", "show": "K-12"}, {"page": "/pricing", "show": "x"}]}))
    story.write(cf, "Show parents how TutorQ works", TUTORQ, str(tmp_path), log=lambda m: None)
    assert (tmp_path / "story.txt").read_text() == "Every learner hits a wall.\n"
    assert story.shots(str(tmp_path)) == [{"page": "/", "show": ""}, {"page": "/k12", "show": "K-12"}]
    pages = cf.calls[0]["user"]["what_we_know"]["pages"]
    assert "/k12" in pages and "/grader/login" not in pages


def test_a_reply_that_is_not_json_is_the_script_with_no_shots(tmp_path):
    story.write(Writer("Just a spoken script."), PROMPT, SITE, str(tmp_path), log=lambda m: None)
    assert (tmp_path / "story.txt").read_text() == "Just a spoken script.\n" and story.shots(str(tmp_path)) == []
    fenced = "```json\n" + json.dumps({"script": "Fenced.", "shots": [{"page": "/", "show": "home"}]}) + "\n```"
    story.write(Writer(fenced), PROMPT, SITE, str(tmp_path), log=lambda m: None)
    assert (tmp_path / "story.txt").read_text() == "Fenced.\n"


def test_the_prompt_has_no_shop_shape():
    from jev_demofast.narrate.shots import MAX_SHOTS
    assert "the menu; the listing" not in story.SYSTEM and '"shots"' in story.SYSTEM
    assert str(MAX_SHOTS) in story.SYSTEM.format(sample="", max_shots=MAX_SHOTS)


def test_pattern_routes_without_examples_are_not_offered():
    from jev_demofast.narrate.shots import offerable
    assert "/collections/:handle" not in offerable(SITE)


def _run_args(tmp_path):
    import argparse
    (tmp_path / "map.json").write_text(json.dumps(SITE))
    return argparse.Namespace(index=str(tmp_path / "map.json"), url="https://shop.test/", goal="find shoes",
                              work=str(tmp_path), fresh=False, no_blur=False, dry_run=False, voice="sarah")


def test_a_demo_with_shots_records_the_tour(monkeypatch, tmp_path):
    from jev_demofast.drive import tour
    shots = [{"page": "/", "show": ""}, {"task": "find shoes", "show": "payoff"}]
    called = []
    monkeypatch.setattr(tour, "run", lambda cf, url, s, index, **k: called.append(("tour", s)) or {})
    monkeypatch.setattr(jev_drive, "run", lambda *a, **k: called.append("goal") or {})
    a = _run_args(tmp_path)
    a.shots = shots
    cli.cmd_run(a, cf="cf")
    assert called == [("tour", shots)]


def test_a_demo_without_shots_records_the_goal(monkeypatch, tmp_path):
    from jev_demofast.drive import tour
    called = []
    monkeypatch.setattr(tour, "run", lambda *a, **k: called.append("tour") or {})
    monkeypatch.setattr(jev_drive, "run", lambda *a, **k: called.append("goal") or {})
    cli.cmd_run(_run_args(tmp_path), cf="cf")
    assert called == ["goal"]


def test_the_task_shot_is_the_briefs_goal_in_its_own_words(tmp_path):
    """Allbirds: the model's task "Apply filters ... Under $75, $76 - $100, $101 - $125, $126 - $150" failed the
    check on a screen that showed men's running shoes under $150 (the lower ranges were greyed out)."""
    cf = Writer(json.dumps({"script": "Watch.", "shots": [
        {"page": "/", "show": ""}, {"task": "Apply filters Under $75, $76 - $100", "show": "payoff"}]}))
    story.write(cf, PROMPT, SITE, str(tmp_path), log=lambda m: None)
    assert story.shots(str(tmp_path))[-1] == {"task": cli.task_goal(PROMPT), "show": "payoff"}


def test_a_leftover_shot_list_is_never_replayed(monkeypatch, tmp_path):
    """Review: every demo shares demo.run by default; a later run without --voice toured the old list on a new site."""
    from jev_demofast.drive import tour
    (tmp_path / "shots.json").write_text(json.dumps({"shots": [{"page": "/", "show": ""}, {"task": "old", "show": ""}]}))
    called = []
    monkeypatch.setattr(tour, "run", lambda *a, **k: called.append("tour") or {})
    monkeypatch.setattr(jev_drive, "run", lambda *a, **k: called.append("goal") or {})
    cli.cmd_run(_run_args(tmp_path), cf="cf")
    assert called == ["goal"]


def test_the_demo_passes_the_shot_list_it_just_wrote(demo, tmp_path, monkeypatch):
    shots = [{"page": "/", "show": ""}, {"task": "x", "show": ""}]

    def write(cf, prompt, index, work, product="", readme="", log=print):
        import os
        os.makedirs(work, exist_ok=True)
        with open(os.path.join(work, "shots.json"), "w") as f:
            json.dump({"shots": shots}, f)
    monkeypatch.setattr(story, "write", write)
    seen = {}
    monkeypatch.setattr(cli, "cmd_run", lambda a, cf=None: seen.update(shots=getattr(a, "shots", None)) or {})
    cli.main(["demo", PROMPT, "--url", "https://shop.test/", "--voice", "apollo", "--out", "d.mp4"])
    assert seen["shots"] == shots


def test_the_task_keeps_the_briefs_secret_placeholders(tmp_path):
    """Review: the task was "Sign in as (secret) ...": the value step had nothing real to type."""
    cf = Writer(json.dumps({"script": "Watch.", "shots": [{"page": "/", "show": ""}, {"task": "sign in", "show": ""}]}))
    story.write(cf, "Sign in as {{EMAIL}} and show my team the reports", SITE, str(tmp_path), log=lambda m: None)
    assert "{{EMAIL}}" in story.shots(str(tmp_path))[-1]["task"] and "{{EMAIL}}" not in json.dumps(cf.calls[0]["user"])


def test_a_reply_with_thinking_and_prose_still_gives_the_script_and_shots(tmp_path):
    body = json.dumps({"script": "Watch this.", "shots": [{"page": "/", "show": "home"}]})
    cf = Writer("<think>plan the demo {first}</think>\nHere's the plan:\n```json\n" + body + "\n```\nHope it helps.")
    story.write(cf, PROMPT, SITE, str(tmp_path), log=lambda m: None)
    assert (tmp_path / "story.txt").read_text() == "Watch this.\n"


def test_the_founder_never_narrates_the_route_or_invents_how_the_site_behaves():
    """Amazon: "We open on Amazon's home page... From there we go straight to..." and "the page refreshes constantly"."""
    assert "we open on" in story.SYSTEM.lower() and "refreshes" in story.SYSTEM.lower()
    assert '"items": true' in story.SYSTEM


def test_browsing_is_an_items_shot_not_a_task():
    """Amazon: "look at hot items sold today" became a task; the goal loop had nothing to aim at and ran out of steps."""
    assert "is not a task" in story.SYSTEM and "specific" in story.SYSTEM


def test_the_readme_reaches_the_founder_as_the_products_own_words(tmp_path):
    cf = Writer("Script.")
    story.write(cf, PROMPT, SITE, str(tmp_path), readme="Demo Fast: one sentence in, a product demo out.",
                log=lambda m: None)
    assert cf.calls[0]["user"]["readme"] == "Demo Fast: one sentence in, a product demo out."
    assert "readme" in cf.calls[0]["system"].lower()


def test_without_a_repo_nothing_about_a_readme_is_sent(tmp_path):
    cf = Writer("Script.")
    story.write(cf, PROMPT, SITE, str(tmp_path), log=lambda m: None)
    assert "readme" not in cf.calls[0]["user"]


def test_the_demo_reads_the_repos_readme_for_the_script(demo, tmp_path, monkeypatch):
    from jev_demofast.narrate import repo
    monkeypatch.setattr(repo, "readme", lambda url, log=print: f"README of {url}")
    seen = {}
    monkeypatch.setattr(story, "write", lambda cf, prompt, index, work, product="", readme="", log=print:
                        seen.update(readme=readme))
    monkeypatch.setattr(cli, "cmd_run", lambda a, cf=None: {})
    cli.main(["demo", PROMPT, "--url", "https://shop.test/", "--repo", "https://github.com/a/b", "--voice", "apollo",
              "--out", "d.mp4"])
    assert seen["readme"] == "README of https://github.com/a/b"


def test_the_voice_over_keeps_the_script_over_setup_headings():
    """onecentdemo.com: gliding down its page, the voice-over read the install section ("FFmpeg recording the result",
    "here's what you need to install", "Start the browser, describe the demo") instead of the founder's script."""
    rules = fit.SYSTEM.lower()
    assert "install" in rules and "tool names" in rules and "carry on with your script" in rules


def test_pages_behind_a_login_reach_the_founder_as_what_comes_after_signing_up(tmp_path):
    """The tour shows only what a visitor can see; the script closes on what an account opens, said, never shown."""
    walled = {**SITE, "_site": {**SITE["_site"], "behind_login": ["/dashboard", "/portfolio"]}}
    cf = Writer("Script.")
    story.write(cf, PROMPT, walled, str(tmp_path), log=lambda m: None)
    (call,) = cf.calls
    assert call["user"]["what_we_know"]["behind_login"] == ["/dashboard", "/portfolio"]
    rule = " ".join(call["system"].split())
    assert "When what the brief cares about is behind_login" in rule and "what signing up opens" in rule
    assert "never describe those screens as if they were on screen" in rule
    assert "/dashboard" not in call["user"]["what_we_know"]["pages"]


def test_a_map_from_before_logins_were_noticed_has_nothing_behind_login(tmp_path):
    cf = Writer("Script.")
    story.write(cf, PROMPT, SITE, str(tmp_path), log=lambda m: None)
    assert cf.calls[0]["user"]["what_we_know"]["behind_login"] == []
