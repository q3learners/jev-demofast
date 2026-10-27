"""The narration audio. With ElevenLabs: the founder's voice-over in one take, with the time each recorded moment's
marker is spoken (take.mp3 + take.json). Otherwise Deepgram Aura-2 on Cloudflare Workers AI: NN.mp3 per line, in
parallel; a quick step with no words of its own gets a short silence."""
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

from . import voiceover
from .fit import EMPTY
from .script import read_lines


def tempo_filter(speed):
    """ffmpeg filter that speeds speech up or down without changing its pitch; None at normal speed."""
    if not 0.5 <= speed <= 2.0:
        raise SystemExit(f"--voice-speed must be between 0.5 and 2.0, not {speed}")
    return None if speed == 1.0 else f"atempo={speed:.3f}"


def generate(cf, narration_path, out_dir, speaker="apollo", only=None, speed=1.0, log=print):
    lines = read_lines(narration_path)
    os.makedirs(out_dir, exist_ok=True)
    todo = [(n, t) for n, t in enumerate(lines) if not only or n in only]
    tempo = tempo_filter(speed)

    def one(item):
        n, text = item
        path = os.path.join(out_dir, f"{n:02d}.mp3")
        if text == EMPTY:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                            "-t", "0.3", path], check=True)
            return n
        with open(path, "wb") as f:
            f.write(cf.speak(text, speaker))
        if tempo:  # Aura-2 on Workers AI has no speed setting, so the clip is re-timed afterwards
            raw = path + ".raw.mp3"
            os.replace(path, raw)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af", tempo, path], check=True)
            os.remove(raw)
        return n

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(one, todo))
    log(f"voice: {len(todo)} clips, {sum(len(t) for _, t in todo)} characters → {out_dir}")
    return out_dir


def one_take(speaker, run_dir, out_dir, voice_name, log=print):
    """Speak voiceover.txt in one take: take.mp3, and take.json with when each segment's marker is spoken."""
    with open(os.path.join(run_dir, "voiceover.txt")) as f:
        spoken, marks = voiceover.plain(f.read())
    audio, starts, duration = speaker.speak(spoken, voice_name)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "take.mp3")
    with open(path, "wb") as f:
        f.write(audio)
    at = {sid: (starts[k] if k < len(starts) else duration) for sid, k in marks}
    with open(os.path.join(out_dir, "take.json"), "w") as f:
        json.dump({"voice": voice_name, "duration": duration, "starts": at}, f, indent=1)
    log(f"voice: one take, {len(spoken)} characters, {duration:.1f} s → {path}")
    return path
