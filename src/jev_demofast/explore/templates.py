"""Group explored URLs into route templates: /collections/mens and /collections/womens are one screen type,
/collections/:handle, as the source-code map writes dynamic routes. Exploring visits a couple of examples per template
instead of a whole catalogue."""
from collections import defaultdict
from urllib.parse import urlparse


def _segments(path):
    return [p for p in urlparse(path).path.split("/") if p]


def templates(paths, keep=frozenset()):
    """{path: route}. Paths with the same number of segments that differ in one position, with at least two values
    there, share a route with that segment as :handle. Query strings and trailing slashes are ignored. A path in `keep`
    (found through a button) is its own route, query included, and doesn't count toward others' grouping."""
    routes = {p: p for p in paths if p in keep}
    segs = {p: _segments(p) for p in paths if p not in keep}
    for p, parts in segs.items():
        best, best_count = None, 1
        for k in range(len(parts) if len(parts) >= 2 else 0):  # /men and /about aren't one template
            key = tuple(parts[:k] + ["*"] + parts[k + 1:])
            values = {q[k] for q in segs.values() if len(q) == len(parts)
                      and tuple(q[:k] + ["*"] + q[k + 1:]) == key}
            if len(values) > best_count:
                best, best_count = k, len(values)
        if best is None:
            routes[p] = "/" + "/".join(parts)
        else:
            routes[p] = "/" + "/".join(parts[:best] + [":handle"] + parts[best + 1:])
    return routes


def pick_examples(paths, routes, per_route=2):
    """The first per_route paths of each route, in discovery order (menu destinations come first)."""
    seen, picked = defaultdict(int), []
    for p in paths:
        if seen[routes[p]] < per_route:
            seen[routes[p]] += 1
            picked.append(p)
    return picked
