"""The product's own words, from its GitHub repo: the README, read through GitHub's API, for the founder's script.

A site's map holds its headings, menus and listings; the README says what the product is, who it's for and why, the
way the founder would. Nothing is cloned, built or run: one API request, public repos only (GITHUB_TOKEN, when set,
raises the rate limit). A README that can't be read leaves the script to the map alone.
"""
import os
import re
import urllib.request
from urllib.parse import urlparse

README_CHARS = 6000  # about 1,500 tokens: the gist of a README, not its install steps
API = "https://api.github.com/repos/{owner}/{name}/readme"
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
TIMEOUT_S = 15


def parse(url):
    """(owner, repo) for an https link to a repo on github.com, else None."""
    u = urlparse((url or "").strip())
    if u.scheme != "https" or u.hostname not in ("github.com", "www.github.com"):
        return None
    parts = [p for p in u.path.split("/") if p]
    if len(parts) < 2:
        return None
    owner, name = parts[0], re.sub(r"\.git$", "", parts[1])
    return (owner, name) if NAME.match(owner) and NAME.match(name) else None


def _fetch(api_url):
    headers = {"Accept": "application/vnd.github.raw+json", "User-Agent": "jev-demofast"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    with urllib.request.urlopen(urllib.request.Request(api_url, headers=headers), timeout=TIMEOUT_S) as r:
        return r.read().decode("utf-8", "replace")


def plain(markdown):
    """The README's words: no code, images, badges, HTML or markdown marks."""
    text = re.sub(r"```.*?```", "", markdown, flags=re.S)
    text = re.sub(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)", "", text)  # a badge: an image inside a link
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.M)
    text = re.sub(r"`|\*\*|__|^\s*[-*+]\s+|^\s*>\s?", "", text, flags=re.M)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def readme(url, fetch=_fetch, log=print):
    """The repo's README as plain words, at most README_CHARS; "" when it can't be read (private, missing, offline)."""
    found = parse(url)
    if not found:
        log(f"repo: {url} isn't a GitHub repo link; writing from the site alone")
        return ""
    owner, name = found
    try:
        text = plain(fetch(API.format(owner=owner, name=name)))
    except (OSError, ValueError) as e:
        log(f"repo: couldn't read the README of {owner}/{name} ({e}); writing from the site alone")
        return ""
    log(f"repo: read the README of {owner}/{name}" + (f" (its first {README_CHARS} of {len(text)} characters)"
                                                     if len(text) > README_CHARS else ""))
    return text[:README_CHARS]
