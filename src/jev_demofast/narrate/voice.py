"""Narration clips with Deepgram Aura-2 on Cloudflare Workers AI: NN.mp3 per line, generated in parallel."""
import os
from concurrent.futures import ThreadPoolExecutor

from .script import read_lines


def generate(cf, narration_path, out_dir, speaker="apollo", only=None, log=print):
    lines = read_lines(narration_path)
    os.makedirs(out_dir, exist_ok=True)
    todo = [(n, t) for n, t in enumerate(lines) if not only or n in only]

    def one(item):
        n, text = item
        with open(os.path.join(out_dir, f"{n:02d}.mp3"), "wb") as f:
            f.write(cf.speak(text, speaker))
        return n

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(one, todo))
    log(f"voice: {len(todo)} clips, {sum(len(t) for _, t in todo)} characters → {out_dir}")
    return out_dir
