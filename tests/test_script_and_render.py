from jev_demofast.narrate.script import parse_lines
from jev_demofast.render.assemble import segments


def test_plain_line_script_parser_tolerates_markup_and_quotes():
    text = '00 | Landing | So this is it.\n**01** | Log in | "...and sign in."\n- 02 | Catalog | Five courses | here\nnoise'
    lines = parse_lines(text)
    assert lines["00"] == ("Landing", "So this is it.")
    assert lines["01"] == ("Log in", "...and sign in.")
    assert lines["02"][1] == "Five courses | here"
    assert set(lines) == {"00", "01", "02"}


def test_segments_group_and_trim_long_waits():
    frames = [{"path": f"f{i}", "hold": 1, "segment": "00", "pending": i > 0} for i in range(8)]
    frames.append({"path": "g", "hold": 1, "segment": "01", "pending": False})
    segs = segments(frames)
    assert [name for name, _ in segs] == ["00", "01"]
    assert len(segs[0][1]) == 1 + 3 + 1  # the first frame, 3 waiting frames, and the last one


def test_too_long_names_lines_over_the_cap_and_the_budget():
    from jev_demofast.narrate.script import too_long, word_budget
    short = {"00": ("Open", "So here's GitHub, where the trending page shows what's hot."), "01": ("Menu", "...open Trending.")}
    assert too_long(short, ["00", "01"]) == []
    wordy = {"00": ("Open", " ".join(["word"] * 25)), "01": ("Menu", "...open Trending.")}
    assert "00" in too_long(wordy, ["00", "01"])[0]
    assert word_budget(6) < 80  # a six-step demo stays well under a minute of speech
    many = {f"{i:02d}": ("S", " ".join(["w"] * 19)) for i in range(6)}  # every line under the cap, total over budget
    problems = too_long(many, sorted(many))
    assert problems and "total" in problems[-1]
