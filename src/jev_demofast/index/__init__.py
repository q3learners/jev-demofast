"""App index: a map of every screen, what it shows, and where its links go, built from source.

An index is {route: {"file", "links": [{"label", "to"}], "buttons", "fields", "texts", "submits"}}.
Adapters build it per framework; today: Next.js app router (`nextjs.build`). Add an adapter by returning the
same shape.
"""
import json
import re
from pathlib import Path


def build(repo, framework="nextjs"):
    if framework == "nextjs":
        from .nextjs import build as nextjs_build
        return nextjs_build(Path(repo))
    raise SystemExit(f"no index adapter for {framework!r} yet (available: nextjs)")


def save(index, path):
    Path(path).write_text(json.dumps(index, indent=1))


def load(path):
    return json.loads(Path(path).read_text())


def route_for(path, index):
    """The index route for a URL path, matching dynamic segments (/course/:id)."""
    path = (path or "/").rstrip("/") or "/"
    if path in index:
        return path
    for r in index:
        if re.match("^" + re.sub(r":[^/]+", "[^/]+", r.rstrip("/") or "/") + "$", path):
            return r
    return None


def summary(route, index, limit=6):
    """What a screen shows, compactly, for a decision model: texts, fields, link labels."""
    e = index.get(route or "", {})
    if not e:
        return "unknown screen"
    parts = []
    if e["texts"]:
        parts.append("shows: " + "; ".join(t[:60] for t in e["texts"][:limit]))
    if e["fields"]:
        parts.append("fields: " + ", ".join(e["fields"][:limit]))
    links = [l["label"][:28] for l in e["links"] if not l["to"].startswith(("{", "#"))][:limit + 2]
    if links:
        parts.append("links: " + ", ".join(links))
    return " | ".join(parts)[:420]
