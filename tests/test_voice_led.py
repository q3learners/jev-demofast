"""The voice sets the timeline: one continuous founder voice-over with [NN] screen markers, spoken in one take by
ElevenLabs, and each recorded moment starts on screen when its marker is spoken."""
import base64
import json

import httpx
import pytest

from jev_demofast.config import load
from jev_demofast.narrate import eleven, script, voice, voiceover
from jev_demofast.render import timeline

IDS = ["00", "01", "02"]


# --- the marked voice-over -------------------------------------------------------------------------------------

def test_a_marked_voiceover_splits_into_segments_and_allows_quick_steps():
    text = "[00] Finding a shoe should take seconds. So watch this. [01] [02] Running shoes, and nothing over $150."
    assert voiceover.split(text, IDS) == {"00": "Finding a shoe should take seconds. So watch this.", "01": "",
                                          "02": "Running shoes, and nothing over $150."}


@pytest.mark.parametrize("bad", ["[00] a [02] b", "[01] a [00] b [02] c", "[00] a [01] b [01] c [02] d",
                                 "no markers at all", "[00] a [01] b [02] c [03] d"])
def test_markers_must_cover_every_segment_once_in_order(bad):
    assert voiceover.split(bad, IDS) is None


def test_the_spoken_text_has_no_markers_and_each_marker_knows_where_its_words_start():
    plain, marks = voiceover.plain("[00] Hello there. [01] [02] Menu talk.")
    assert plain == "Hello there. Menu talk."
    assert marks == [("00", 0), ("01", 13), ("02", 13)]


def test_words_before_the_first_marker_belong_to_the_opening():
    plain, marks = voiceover.plain("So, watch this. [00] Hello. [01] Menu. [02] End.")
    assert voiceover.split("So, watch this. [00] Hello. [01] Menu. [02] End.", IDS)["00"] == "So, watch this. Hello."
    assert marks[0] == ("00", 0)


# --- the script step writes the marked voice-over --------------------------------------------------------------

class Writer:
    s = type("S", (), {"script_model": "nemotron", "script_extra": {}})

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def chat(self, model, system, user, extra=None, max_tokens=4000):
        self.calls.append({"system": system, "user": json.loads(user)})
        return self.replies.pop(0)


def recorded(tmp_path):
    (tmp_path / "actions.json").write_text(json.dumps({"goal": "find shoes", "actions": [
        {"segment": "00", "do": "open"}, {"segment": "01", "do": "hover", "target": "open the Men menu"},
        {"segment": "02", "do": "read", "target": "showcase", "items": ["Dasher NZ $140"]}]}))
    (tmp_path / "story.txt").write_text("Finding a shoe should take seconds. Our menu puts it right there.\n")


def test_the_founders_voiceover_is_written_with_markers_and_retried_when_they_are_wrong(tmp_path):
    recorded(tmp_path)
    cf = Writer("[00] Finding a shoe should take seconds. [02] There it is.",  # a marker missing: retried
                "[00] Finding a shoe should take seconds, so watch this. [01] Our menu puts it right there... "
                "[02] and there it is: the Dasher NZ at $140.")
    path = script.write(cf, str(tmp_path), log=lambda m: None)
    assert len(cf.calls) == 2 and "[NN]" in cf.calls[0]["system"]
    assert (tmp_path / "voiceover.txt").read_text().startswith("[00] Finding a shoe")
    assert script.read_lines(path) == ["Finding a shoe should take seconds, so watch this.",
                                       "Our menu puts it right there...", "and there it is: the Dasher NZ at $140."]


def test_a_quick_step_without_words_still_gets_a_narration_entry(tmp_path):
    recorded(tmp_path)
    cf = Writer("[00] Finding a shoe should take seconds... [01] [02] and there's the Dasher NZ at $140.")
    lines = script.read_lines(script.write(cf, str(tmp_path), log=lambda m: None))
    assert len(lines) == 3 and lines[1] == "…"


# --- ElevenLabs: one take, with the time each character is spoken ----------------------------------------------

def test_elevenlabs_speaks_in_one_take_and_returns_character_timings():
    seen = {}

    def handler(request):
        seen["url"], seen["key"], seen["body"] = str(request.url), request.headers["xi-api-key"], json.loads(request.content)
        return httpx.Response(200, json={"audio_base64": base64.b64encode(b"mp3").decode(),
                                         "alignment": {"characters": list("Hi you"),
                                                       "character_start_times_seconds": [0, .1, .2, .3, .4, .5],
                                                       "character_end_times_seconds": [.1, .2, .3, .4, .5, .6]}})
    client = eleven.ElevenLabs("k-1", "eleven_multilingual_v2", http=httpx.Client(transport=httpx.MockTransport(handler)))
    audio, starts, duration = client.speak("Hi you", "chris")
    assert audio == b"mp3" and starts == [0, .1, .2, .3, .4, .5] and duration == .6
    assert seen["key"] == "k-1" and seen["body"] == {"text": "Hi you", "model_id": "eleven_multilingual_v2"}
    assert f"/text-to-speech/{eleven.VOICES['chris']}/with-timestamps" in seen["url"]


def test_elevenlabs_is_used_only_with_its_key_and_a_voice_it_has(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "a")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "t")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert not eleven.speaks(load(), "chris")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    s = load()
    assert eleven.speaks(s, "chris") and eleven.speaks(s, "Sarah") and not eleven.speaks(s, "apollo")
    assert s.eleven_model == "eleven_multilingual_v2"


def test_one_take_gives_each_marker_the_time_its_words_start(tmp_path):
    (tmp_path / "voiceover.txt").write_text("[00] Hi. [01] [02] You there.")

    class Speaker:
        def speak(self, text, voice_name):
            assert text == "Hi. You there."
            return b"mp3", [i * 0.1 for i in range(len(text))], 2.0
    out = voice.one_take(Speaker(), str(tmp_path), str(tmp_path / "voice"), "chris", log=lambda m: None)
    take = json.loads((tmp_path / "voice" / "take.json").read_text())
    assert out.endswith("take.mp3") and take["duration"] == 2.0
    assert take["starts"] == {"00": 0.0, "01": 0.4, "02": 0.4}  # "You" starts at character 4


# --- the video follows the voice --------------------------------------------------------------------------------

def test_footage_shorter_than_its_words_holds_its_outcome():
    plan = timeline.plan(visual=[1.0, 1.0], starts=[0.0, 3.0], duration=5.0)
    assert plan[0] == {"video": 3.0, "scale": 1.0, "pause": 0.0}  # holds the last frame for the words
    assert plan[1]["video"] == pytest.approx(2.0 + timeline.TAIL)


def test_footage_longer_than_its_words_is_shortened_then_the_voice_pauses():
    plan = timeline.plan(visual=[4.0, 6.0, 1.0], starts=[0.0, 3.0, 4.0], duration=6.0)
    assert plan[0] == {"video": 3.0, "scale": 0.75, "pause": 0.0}  # 4 s of footage shortened to the 3 s of words
    assert plan[1] == {"video": 3.0, "scale": 0.5, "pause": 2.0}  # shortened by half at most; the voice waits 2 s


def test_a_marker_with_no_words_still_shows_its_footage():
    plan = timeline.plan(visual=[1.0, 2.0, 1.0], starts=[0.0, 2.0, 2.0], duration=4.0)
    assert plan[1]["video"] == pytest.approx(1.0) and plan[1]["pause"] == pytest.approx(1.0)


@pytest.mark.skipif(not __import__("shutil").which("ffmpeg"), reason="needs ffmpeg")
def test_the_video_is_assembled_on_the_voices_timeline(tmp_path):
    import subprocess
    from PIL import Image
    from jev_demofast.render.assemble import LEAD, assemble, media_length
    frames = []
    for n, (seg, hold) in enumerate([("00", 1.0), ("01", 4.0), ("02", 1.0)]):
        path = tmp_path / f"f{n}.jpg"
        Image.new("RGB", (64, 48), (n * 80, 0, 0)).save(path)
        frames.append({"path": str(path), "hold": hold, "segment": seg, "pending": False})
    (tmp_path / "frames.json").write_text(json.dumps(frames))
    take = tmp_path / "voice"
    take.mkdir()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                    str(take / "take.mp3")], check=True)
    # "01" and "02" share a start: a quick step with no words of its own (ffmpeg refuses an empty cut)
    (take / "take.json").write_text(json.dumps({"duration": 6.0, "starts": {"00": 0.0, "01": 3.0, "02": 3.0}}))
    out = assemble(str(tmp_path), str(tmp_path / "demo.mp4"), take_dir=str(take), log=lambda m: None)
    plan = timeline.plan([1.0, 4.0, 1.0], [0.0, 3.0, 3.0], 6.0)
    assert media_length(out) == pytest.approx(LEAD + sum(p["video"] for p in plan), abs=0.15)


def test_narrate_uses_one_take_with_an_elevenlabs_voice_and_clips_otherwise(monkeypatch, tmp_path):
    import argparse
    from jev_demofast import cli
    from jev_demofast.render import assemble as assemble_mod
    calls = []
    (tmp_path / "voiceover.txt").write_text("[00] Hi.")
    monkeypatch.setattr(script, "write", lambda cf, work, product="", log=print: str(tmp_path / "narration.txt"))
    monkeypatch.setattr(voice, "one_take", lambda speaker, work, out, name, log=print: calls.append(("take", name)))
    monkeypatch.setattr(voice, "generate", lambda cf, path, out, speaker="", speed=1.0, log=print:
                        calls.append(("clips", speaker)) or out)
    from jev_demofast.narrate import focus
    monkeypatch.setattr(focus, "follow", lambda cf, work, path, clips, out: work)
    monkeypatch.setattr(assemble_mod, "assemble", lambda work, out, **k: calls.append(("assemble", k.get("take_dir"))))

    class Cf:
        s = type("S", (), {"eleven_key": "k", "eleven_model": "eleven_multilingual_v2"})
    a = argparse.Namespace(work=str(tmp_path), product="", voice="chris", voice_speed=1.0, out="d.mp4", gif=False)
    cli.cmd_narrate(a, Cf())
    assert calls[0] == ("take", "chris") and calls[1] == ("assemble", str(tmp_path / "voice"))
    calls.clear()
    cli.cmd_narrate(argparse.Namespace(**{**vars(a), "voice": "apollo"}), Cf())
    assert calls[0] == ("clips", "apollo") and calls[1] == ("assemble", None)


# --- the shot list sets the voice-over's length ----------------------------------------------------------------

def test_the_budget_is_per_shot():
    from jev_demofast.narrate import fit
    assert fit.budget([{"shot": 0}, {"shot": 1}, {"shot": 1}, {"shot": 2}]) == 20 + 20 + 8 + 20
    assert fit.budget([{}, {}]) == 26


def test_the_voiceover_writer_sees_why_each_moment_is_there(tmp_path):
    (tmp_path / "actions.json").write_text(json.dumps({"goal": "tour", "actions": [
        {"segment": "00", "do": "open", "shot": 0, "show": "the promise"},
        {"segment": "01", "do": "click", "target": "K-12", "shot": 1, "show": "help for every subject",
         "headings": ["Your child's personal tutor"]}]}))
    (tmp_path / "story.txt").write_text("Every learner hits a wall.\n")
    cf = Writer("[00] Every learner hits a wall. [01] K-12 covers every subject.")
    script.write(cf, str(tmp_path), log=lambda m: None)
    segs = cf.calls[0]["user"]["segments"]
    assert segs[1]["show"] == "help for every subject" and segs[1]["headings"] == ["Your child's personal tutor"]
    assert "show" in cf.calls[0]["system"]
