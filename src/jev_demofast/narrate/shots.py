"""The founder's shot list: the pages of the map a demo shows, in the order the script speaks about them.

Given only a goal, the recorder took the shortest path and stopped (tutorq.ai: one click to /sat, a 19 s video for a
script about four products). A founder plans the screens with the story; the shots are those screens.
"""
import re

MAX_SHOTS = 6  # after the home page, which always opens the demo
TEXTS = 3
STATUS_LINE = re.compile(r"\d{3}\b")  # "429 Too Many Requests", "404": the map met an error page there


def offerable(index):
    """The pages a shot can show: each route's example paths with the route's first texts. Error pages and pages
    with no text are left out: there is nothing true to say over them."""
    pages = {}
    for route, entry in index.items():
        texts = entry.get("texts") or []
        if route.startswith("_") or not texts or STATUS_LINE.match(texts[0]):
            continue
        for path in entry.get("examples") or ([] if ":" in route else [route]):
            pages[path] = texts[:TEXTS]
    return pages


def validate(raw, index, log=print):
    """The model's shots, checked against the map: home first, pages from the map only, at most MAX_SHOTS after
    home, a task only as the last shot. [] when no shot beyond the opening is left (no tour)."""
    pages = offerable(index)
    raw = [s for s in raw if isinstance(s, dict)] if isinstance(raw, list) else []
    opening = {"page": "/", "show": ""}
    if raw and raw[0].get("page") == "/":
        opening["show"] = str(raw[0].get("show") or "")
        raw = raw[1:]
    shots = []
    for n, shot in enumerate(raw):
        show = str(shot.get("show") or "")
        if shot.get("task"):
            if n == len(raw) - 1:
                shots.append({"task": str(shot["task"]), "show": show})
            continue
        if shot.get("page") not in pages:
            log(f"  dropped shot {shot.get('page')}: not a page in the map")
            continue
        if shot["page"] == (shots[-1] if shots else opening).get("page"):
            continue  # the same page again is the same screen (Allbirds' list named one listing three times)
        shots.append({"page": shot["page"], "show": show})
    task = shots[-1:] if shots and "task" in shots[-1] else []
    shots = [s for s in shots if "task" not in s][:MAX_SHOTS - len(task)] + task
    return [opening] + shots if shots else []
