"""App index from a Next.js (app router) repository's source, via tree-sitter.

For each route (src/app/**/page.tsx or app/**/page.tsx) it follows local imports and re-exports into components
(depth 3) and records links (label → destination), buttons, form fields, visible text, and whether it submits data.
"""
import json
import re
from pathlib import Path

import tree_sitter_typescript as ts_ts
from tree_sitter import Language, Parser

TSX = Parser(Language(ts_ts.language_tsx()))
TS = Parser(Language(ts_ts.language_typescript()))
LINK_TAGS = {"Link", "a", "NextLink"}
BUTTON_TAGS = {"button", "Button"}
FIELD_TAGS = {"input", "Input", "textarea", "Textarea", "select"}
MAX_DEPTH, MAX_FILES = 3, 40


def route_of(page: Path, app: Path):
    parts = [p for p in page.parent.relative_to(app).parts
             if not (p.startswith("(") and p.endswith(")")) and not p.startswith("_") and not p.startswith("@")]
    if any(p == "api" for p in parts):
        return None
    return "/" + "/".join(re.sub(r"^\[\.{0,3}(.+)\]$", r":\1", p) for p in parts)


def resolve(spec: str, here: Path, src: Path):
    if spec.startswith("@/"):
        base = src / spec[2:]
    elif spec.startswith("."):
        base = (here.parent / spec).resolve()
    else:
        return None
    for cand in (base.with_suffix(".tsx"), base.with_suffix(".ts"), base / "index.tsx", base / "index.ts", base):
        if cand.is_file() and cand.suffix in (".tsx", ".ts"):
            return cand
    return None


def text_of(node, src: bytes):
    return src[node.start_byte:node.end_byte].decode("utf-8", "replace")


def clean(s: str):
    return re.sub(r"\s+", " ", s).strip()


def jsx_label(node, src):
    """Visible text inside a JSX element: jsx_text plus string literals in {...}."""
    out, stack = [], [node]
    while stack:
        n = stack.pop()
        if n.type == "jsx_text":
            out.append(text_of(n, src))
        elif n.type == "string_fragment" and n.parent and n.parent.parent and n.parent.parent.type == "jsx_expression":
            out.append(text_of(n, src))
        elif n.type == "jsx_opening_element":
            continue  # attributes aren't visible text
        stack.extend(reversed(n.children))
    return clean(" ".join(out))


def attr_raw(opening, name, src):
    """The attribute's whole value as written, e.g. "{() => router.push('/x')}"."""
    for a in opening.children:
        if a.type == "jsx_attribute" and a.children and text_of(a.children[0], src) == name:
            return text_of(a, src)[len(name):].lstrip("=").strip()
    return None


def attr_value(opening, name, src):
    for a in opening.children:
        if a.type == "jsx_attribute" and a.children and text_of(a.children[0], src) == name:
            raw = text_of(a, src)[len(name):].lstrip("=").strip()
            m = re.search(r"""["'`]([^"'`]*)["'`]""", raw)
            return m.group(1) if m else raw
    return None


def scan_file(path: Path, src_root: Path):
    code = path.read_bytes()
    tree = (TSX if path.suffix == ".tsx" else TS).parse(code)
    info = {"links": [], "buttons": [], "fields": [], "texts": [], "submits": False, "imports": []}
    text = code.decode("utf-8", "replace")
    if re.search(r"onSubmit|method:\s*['\"](POST|PUT|PATCH|DELETE)|\.(post|put|patch|delete)\(|useMutation", text):
        info["submits"] = True
    stack = [tree.root_node]
    while stack:
        n = stack.pop()
        stack.extend(n.children)
        if n.type in ("import_statement", "export_statement"):  # export { default } from './x' re-exports a page
            m = re.search(r"""from\s+['"]([^'"]+)['"]""", text_of(n, code))
            if m and (t := resolve(m.group(1), path, src_root)):
                info["imports"].append(t)
        elif n.type in ("jsx_element", "jsx_self_closing_element"):
            opening = n.child_by_field_name("open_tag") if n.type == "jsx_element" else n
            if opening is None:
                continue
            name_node = opening.child_by_field_name("name")
            tag = text_of(name_node, code) if name_node else ""
            label = jsx_label(n, code) if n.type == "jsx_element" else ""
            label = label or attr_value(opening, "aria-label", code) or attr_value(opening, "title", code) or ""
            if tag in LINK_TAGS:
                href = attr_value(opening, "href", code)
                if href and label:
                    info["links"].append({"label": label[:80], "to": href})
            elif tag in BUTTON_TAGS:
                onclick = attr_raw(opening, "onClick", code) or ""
                m = re.search(r"""(?:push|replace|navigate)\(\s*['"`]([^'"`]+)""", onclick)
                typ = attr_value(opening, "type", code)
                if label:
                    entry = {"label": label[:80], "submit": typ == "submit"}
                    if m:
                        entry["to"] = m.group(1)
                        info["links"].append({"label": label[:80], "to": m.group(1)})
                    info["buttons"].append(entry)
            elif tag in FIELD_TAGS:
                desc = (attr_value(opening, "aria-label", code) or attr_value(opening, "placeholder", code)
                        or attr_value(opening, "name", code) or attr_value(opening, "type", code) or "")
                if desc and not desc.startswith("{"):
                    info["fields"].append(desc[:60])
            elif tag == "label" and label:
                info["fields"].append(label[:60])
        elif n.type == "jsx_text":
            t = clean(text_of(n, code))
            if len(t.split()) >= 2 and len(t) < 160:
                info["texts"].append(t)
        elif n.type == "object":  # nav config: { label: 'Catalog', href: '/campus/courses' }
            pairs = {}
            for p in n.children:
                if p.type == "pair":
                    k = text_of(p.child_by_field_name("key"), code).strip("'\"")
                    v = p.child_by_field_name("value")
                    if v is not None and v.type == "string":
                        pairs[k] = text_of(v, code).strip("'\"`")
            label = pairs.get("label") or pairs.get("title") or pairs.get("name")
            to = pairs.get("href") or pairs.get("path") or pairs.get("to")
            if label and to and to.startswith("/"):
                info["links"].append({"label": label[:80], "to": to})
    return info


def build(repo: Path):
    """Return {route: {file, links, buttons, fields, texts, submits}} for a Next.js app-router repo."""
    repo = Path(repo)
    src = repo / "src" if (repo / "src" / "app").is_dir() else repo
    app = src / "app"
    if not app.is_dir():
        raise SystemExit(f"no Next.js app router directory at {app}")
    cache, routes = {}, {}
    for page in sorted(app.rglob("page.tsx")):
        route = route_of(page, app)
        if route is None:
            continue
        seen, frontier = set(), [(page, 0)]
        merged = {"links": [], "buttons": [], "fields": [], "texts": [], "submits": False}
        while frontier and len(seen) < MAX_FILES:
            f, depth = frontier.pop(0)
            if f in seen:
                continue
            seen.add(f)
            if f not in cache:
                cache[f] = scan_file(f, src)
            info = cache[f]
            for k in ("links", "buttons", "fields", "texts"):
                merged[k] += info[k]
            merged["submits"] |= info["submits"]
            if depth < MAX_DEPTH:
                frontier += [(t, depth + 1) for t in info["imports"] if "/components/ui/" not in str(t)]
        dedup = lambda xs: list({json.dumps(x, sort_keys=True): x for x in xs}.values())
        routes[route] = {"file": str(page.relative_to(repo)), "links": dedup(merged["links"])[:80],
                         "buttons": dedup(merged["buttons"])[:60],
                         "fields": list(dict.fromkeys(merged["fields"]))[:30],
                         "texts": list(dict.fromkeys(merged["texts"]))[:60], "submits": merged["submits"]}
    return routes
