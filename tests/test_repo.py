"""A GitHub link gives the founder's script the product's own words: its README, read through GitHub's API. Nothing
is cloned, built or run."""
import pytest

from jev_demofast.narrate import repo


@pytest.mark.parametrize("url,expected", [
    ("https://github.com/q3learners/jev-demofast", ("q3learners", "jev-demofast")),
    ("https://github.com/q3learners/jev-demofast.git", ("q3learners", "jev-demofast")),
    ("https://github.com/q3learners/jev-demofast/tree/main/docs", ("q3learners", "jev-demofast")),
    ("https://www.github.com/a-b/c.d_e/", ("a-b", "c.d_e")),
])
def test_a_repo_link_names_its_owner_and_repo(url, expected):
    assert repo.parse(url) == expected


@pytest.mark.parametrize("url", ["", "https://gitlab.com/a/b", "https://github.com/a", "http://github.com/a/b",
                                 "https://github.com.evil.test/a/b", "https://github.com/../b", "git@github.com:a/b"])
def test_anything_else_is_not_a_repo(url):
    assert repo.parse(url) is None


README = """<p align="center"><img src="logo.png"></p>

# Demo Fast [![CI](https://img.shields.io/badge/ci-passing-green)](https://ci)

One sentence in, a **product demo** video out. See the [docs](https://docs.test) for more.

![screenshot](shot.png)

```bash
uv run jev-demofast demo "..."
```

## Why
Founders re-record demos every release.
"""


def test_the_readme_is_read_as_plain_words(monkeypatch):
    asked = []

    def fetch(api_url):
        asked.append(api_url)
        return README
    text = repo.readme("https://github.com/q3learners/jev-demofast", fetch=fetch, log=lambda m: None)
    assert asked == ["https://api.github.com/repos/q3learners/jev-demofast/readme"]
    assert "One sentence in, a product demo video out. See the docs for more." in text
    assert "Founders re-record demos every release." in text and "Demo Fast" in text
    for gone in ("<img", "shields.io", "shot.png", "uv run", "```", "**", "#"):
        assert gone not in text


def test_a_long_readme_is_cut_to_what_one_prompt_can_carry():
    text = repo.readme("https://github.com/a/b", fetch=lambda u: "word " * 10_000, log=lambda m: None)
    assert len(text) <= repo.README_CHARS


def test_a_readme_that_cant_be_read_gives_nothing_and_says_why():
    said = []

    def fetch(api_url):
        raise OSError("HTTP Error 404: Not Found")
    assert repo.readme("https://github.com/a/private", fetch=fetch, log=said.append) == ""
    assert any("a/private" in line and "404" in line for line in said)
