"""Narration clips with Deepgram Aura-2 on Cloudflare Workers AI: NN.mp3 per line, generated in parallel."""
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

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
