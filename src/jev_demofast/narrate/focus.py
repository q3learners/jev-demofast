"""Point the camera at what each narration line talks about.

Per segment: embeddings shortlist the 5 on-screen text blocks most similar to the line; Jev picks one (or none).
If it isn't already in view, frames pan the full-page screenshot to it while the line plays. A line that lists
items (a read step) drifts down through all of them. Needs a run recorded with page maps.
"""
import json
import os
import re

from PIL import Image

from ..cloudflare import cosine
from ..render.assemble import LEAD, TAIL, clip_files, media_length
from .script import read_lines

FPS = 15


def _pick_block(cf, line, blocks):
    texts = [b["text"] for b in blocks]
    vecs = cf.embed([line] + texts)
    ranked = sorted(range(len(texts)), key=lambda i: -cosine(vecs[0], vecs[i + 1]))[:5]
    key, conf = cf.choose("A presenter says this line while showing a web page. Which on-screen text is the line about?",
                          {str(i): blocks[i]["text"][:160] for i in ranked}, {"narration": line}, allow_none=True)
    return (blocks[int(key)] if key is not None and conf >= 0.5 else None), key, conf


def _item_span(items, blocks):
    ys = [(b["y"], b["y"] + b["h"]) for it in items for b in blocks if it[:30].lower() in b["text"].lower()]
    return (min(y for y, _ in ys), max(y for _, y in ys)) if ys else None


def _ease(t):
    return t * t * (3 - 2 * t)


def follow(cf, run_dir, narration_path, clips_dir, out_dir, log=print):
    run_dir, out_dir = os.path.abspath(run_dir), os.path.abspath(out_dir)
    os.makedirs(os.path.join(out_dir, "frames"), exist_ok=True)
    frames = json.load(open(os.path.join(run_dir, "frames.json")))
    actions = json.load(open(os.path.join(run_dir, "actions.json")))["actions"]
    lines, clips = read_lines(narration_path), clip_files(clips_dir)
    if not (len(lines) == len(actions) == len(clips)):
        raise SystemExit(f"{len(lines)} lines, {len(actions)} segments, {len(clips)} clips: they must match")
    out = []
    for n, act in enumerate(actions):
        seg = [dict(f) for f in frames if f["segment"] == act["segment"]]
        need = LEAD + media_length(clips[n]) + TAIL
        if not act.get("page_shot") or not act.get("blocks"):
            out += seg
            continue
        vw, vh, sy = act["vw"], act["vh"], act["scroll_y"]
        if act.get("do") == "read" and act.get("items"):
            span = _item_span(act["items"], act["blocks"])
        else:
            b, _, _ = _pick_block(cf, lines[n], act["blocks"])
            span = (b["y"], b["y"] + b["h"]) if b else None
        if not span or (span[0] >= sy + 40 and span[1] <= sy + vh - 40):
            out += seg  # already in view, or nothing specific to point at
            continue
        page = Image.open(act["page_shot"]).convert("RGB")
        long_list = span[1] - span[0] > vh - 200
        target = span[0] - 120 if long_list else (span[0] + span[1]) / 2 - vh / 2
        end = max(0, min(target, page.height - vh))
        rest = max(need - sum(f["hold"] for f in seg) - 1.0, 1.0)
        steps = [(sy + (end - sy) * _ease(k / FPS), 1 / FPS) for k in range(1, FPS + 1)]  # 1 s glide
        if long_list:
            last = max(0, min(span[1] - vh + 80, page.height - vh))
            k_n = max(1, int(rest * FPS))
            steps += [(end + (last - end) * _ease(k / k_n), 1 / FPS) for k in range(1, k_n + 1)]
        else:
            steps.append((end, rest))
        pan = []
        for y, hold in steps:
            y = max(0, min(int(y), page.height - vh))
            path = os.path.join(out_dir, "frames", f"{act['segment']}-{len(out) + len(seg) + len(pan):05d}.png")
            page.crop((0, y, vw, y + vh)).save(path)
            pan.append({"path": path, "hold": hold, "segment": act["segment"], "pending": False})
        out += seg + pan
        log(f"  focus {act['segment']}: pan {int(sy)}→{int(end)}{' through the list' if long_list else ''}")
    with open(os.path.join(out_dir, "frames.json"), "w") as f:
        json.dump(out, f, indent=1)
    return out_dir
