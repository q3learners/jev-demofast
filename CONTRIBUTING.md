# Contributing to jev-demofast

Thanks for helping. This is a young project, so small, focused pull requests are the easiest to review and merge.

## Good places to start

Issues labelled [good first issue](https://github.com/q3learners/jev-demofast/labels/good%20first%20issue) are
scoped and ready. The two areas that matter most right now:

- **Index readers for more frameworks.** The source-code map only reads Next.js (app router) today. React Router
  and Remix are the natural next ones, then Rails and Django.
- **Waiting for pages instead of fixed pauses.** The drivers sleep for fixed times after actions
  (`src/jev_demofast/drive/`). Waiting on real page readiness would make runs faster and steadier.

For anything bigger than a bug fix, open an issue first (or comment on one), so we can agree on the approach before
you write the code.

## Contact

Questions, or want to discuss something before opening an issue? Email Venkat at
[venkat@q3learners.com](mailto:venkat@q3learners.com).

## Set up

You need Python 3.12+, [uv](https://docs.astral.sh/uv/) and ffmpeg.

```bash
git clone https://github.com/q3learners/jev-demofast && cd jev-demofast
uv sync
uv run pytest            # runs offline: no Chrome, no API keys, no network
```

To try real runs you also need Chrome and a Cloudflare account with Workers AI (see the README's Quickstart). Point
it at a staging site and test accounts: it clicks real buttons and submits real forms.

## How the code is laid out

| Path | What it does |
|---|---|
| `src/jev_demofast/index/` | builds the app map from source (`nextjs.py` is the reader to copy) |
| `src/jev_demofast/drive/` | the two drivers (`navigator.py` for any site, `jev_drive.py` with a map), guards, sessions |
| `src/jev_demofast/browser/` | the Chrome connection and page reading |
| `src/jev_demofast/record/`, `render/`, `narrate/` | frames, video, script, voice and music |
| `src/jev_demofast/cloudflare.py` | every model call (Jev, chat, embeddings, voice) |
| `tests/` | offline tests; `tests/fixtures/nextapp/` is a small Next.js app the index tests read |

`docs/how-it-works.md` explains why each rule exists, with the measurements behind it.

## Adding an index reader for a framework

1. Add `src/jev_demofast/index/<framework>.py` with a `build(repo_path)` function. It returns the same shape as the
   Next.js reader:
   `{route: {"file", "links": [{"label", "to"}], "buttons", "fields", "texts", "submits"}}`.
   Dynamic segments use `:name` (for example `/course/:id`).
2. Register it in `build()` in `src/jev_demofast/index/__init__.py`, and add it to the `--framework` help in `cli.py`.
3. Add a small example app under `tests/fixtures/<framework>app/` and tests in the style of `tests/test_index.py`:
   the routes, a link's destination, a form's fields, and a nav link from a shared layout.

## Guidelines

- **Add or update tests** for any behaviour you change, and keep `uv run pytest` green.
- **Keep it general.** No rules written for one particular website: the drivers must work on sites they have never
  seen.
- **Don't weaken the safety guards** (same site only, no sign-up, log-out or delete clicks, secrets typed from
  placeholders and never shown to a model). If a guard gets in your way, open an issue to discuss it.
- **Never commit secrets or run output:** no `.env`, API tokens, recordings, or files under `runs/` and `out/`.
- **Match the surrounding code:** small functions, plain names, and comments only where the reason isn't obvious.
- In the pull request, say what you changed and how you tested it (tests, plus a real run if it touches the drivers).

## License

By contributing, you agree that your contributions are licensed under the project's MIT license.

Be kind in issues and reviews. Everyone here is volunteering their time.
