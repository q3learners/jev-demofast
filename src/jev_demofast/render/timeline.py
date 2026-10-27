"""The video follows the voice: each recorded moment starts on screen when its marker is spoken and lasts until the
next one. Footage shorter than its words holds its last frame (the step's outcome). Footage longer than its words is
shortened, down to half; if it's still longer, the voice pauses there, the way a presenter waits for a page."""
TAIL = 0.8           # the last moment stays on screen this long after the last word
MOST_SHORTENED = 0.5  # footage plays at least this fraction of its recorded length


def plan(visual, starts, duration, tail=TAIL):
    """Per segment: {"video": seconds on screen, "scale": factor for its frames' holds (≤ 1), "pause": seconds of
    silence after its words}. `visual` is each segment's recorded length, `starts` when its marker is spoken."""
    out = []
    for i, length in enumerate(visual):
        words = (starts[i + 1] if i + 1 < len(starts) else duration + tail) - starts[i]
        video = max(words, length * MOST_SHORTENED)
        out.append({"video": round(video, 3), "scale": round(min(1.0, video / length), 3) if length else 1.0,
                    "pause": round(max(0.0, video - words), 3)})
    return out
