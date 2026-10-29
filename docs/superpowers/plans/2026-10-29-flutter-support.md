# Flutter Web Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** jev-demofast maps and records Flutter web apps (first target: k12.tutorq.ai, logged out).

**Architecture:** The session turns on Flutter's accessibility layer after every document load, which makes the
existing reader and clicker work unchanged. On Flutter pages, the explorer also finds pages behind buttons. It
clicks the safe ones, gated by Clef on pages with fields, and records them as links with `"via": "button"`. Those
paths keep their query and are never grouped into templates. The tour clicks those buttons on camera.

**Tech Stack:** Python 3.14, Chrome DevTools Protocol via browser-harness, pytest with fake sessions (no network).

**Spec:** `docs/superpowers/specs/2026-10-29-flutter-support-design.md`

## Global Constraints

- A page is Flutter when `document.querySelector('flutter-view, flt-glass-pane')` exists.
- The layer is turned on by clicking `flt-semantics-placeholder` from JavaScript, then waiting for `flt-semantics` nodes.
- No new code may click a Flutter node from JavaScript. Navigation clicks go through `Session.act` (real mouse events).
- Discovery may click a button only if `guards.blocked(label)` is false and `guards.CHANGES` doesn't match. On a page
  with a text or password field, Clef must also score it ≥ `NAVIGATES_CONFIDENT = 0.8`. Any error, timeout, `cf is None`
  or a check model that can't read images means no click.
- Clef's question and its true/false wording are copied verbatim from the spec (Task 3).
- Non-Flutter sites: the explorer's output is unchanged. Flutter work runs only when the page is Flutter.
- The explorer never types and never submits.

## Review Focus

1. A Flutter page reloaded mid-explore (the return-to-page step) must have its layer on again before it's read.
   Covered by Task 1 `test_layer_turned_on_again_after_a_reload`.
2. A button that opens a dialog or toggles, and stays on the same address, adds no link and leaves the next button
   clickable. Covered by Task 3 `test_a_button_that_stays_adds_no_link_and_the_page_is_reloaded`.
3. Two buttons with the same first-line label on one page are clicked once. Covered by Task 3
   `test_same_label_is_tried_once`.
4. A button that leads off the site (another host) records nothing. Covered by Task 3
   `test_a_button_that_leaves_the_site_adds_no_link`.
5. `explore(..., cf=None)`, as the CLI's dry paths call it, never clicks a button on a page with fields. Covered by
   Task 3 `test_no_check_model_means_no_clicks_on_pages_with_fields`.

---

### Task 1: The session turns on Flutter's accessibility layer

**Files:**
- Modify: `src/jev_demofast/drive/session.py` (constants at the top, `Session.__init__`, `wait_loaded`)
- Test: `tests/test_session_flutter.py` (new)

**Interfaces:**
- Produces: `FLUTTER_JS: str` (true when the page is Flutter), `Session.flutter_ready(timeout=3.0) -> bool` (True if
  the page is Flutter and its layer is now on; False for a non-Flutter page, and only one `evaluate` call is made
  for it). `Session.is_flutter` (bool, set by `flutter_ready`). `wait_loaded()` calls `flutter_ready()` once the
  document is complete. `__init__` calls it before its first `observe()`.

- [ ] **Step 1: Write the failing tests** (a fake `Browser` whose `evaluate` answers `FLUTTER_JS`, the placeholder
  click and a `flt-semantics` count)

```python
def test_a_flutter_page_gets_its_layer_turned_on():      # placeholder clicked once, returns True, is_flutter True
def test_a_normal_page_is_left_alone():                  # FLUTTER_JS false: returns False, no placeholder click
def test_layer_turned_on_again_after_a_reload():         # wait_loaded() after Page.navigate clicks the placeholder again
def test_gives_up_quietly_when_no_semantics_appear():    # nodes never appear: returns False after timeout, no raise
```

- [ ] **Step 2:** `uv run pytest tests/test_session_flutter.py -v`. Expected: FAIL (`flutter_ready` not defined).
- [ ] **Step 3: Implement.** Poll every 0.1 s up to `timeout`. Treat `StalePage`/`RuntimeError` during polling as
  "not yet".
- [ ] **Step 4:** `uv run pytest tests/test_session_flutter.py tests/test_session_context_hover.py tests/test_wait_for_page.py -v`.
  Expected: PASS.
- [ ] **Step 5: Commit** "Flutter pages get their accessibility layer turned on after every load".

### Task 2: Button-found paths stay their own routes

**Files:**
- Modify: `src/jev_demofast/explore/templates.py` (`templates`)
- Test: `tests/test_explore_templates.py`

**Interfaces:**
- Produces: `templates(paths, keep=frozenset()) -> dict[str, str]`. Each path in `keep` maps to itself, query
  included, and doesn't count toward other paths' grouping. All other paths behave exactly as today.

- [ ] **Step 1: Write the failing test**

```python
def test_kept_paths_are_their_own_routes_query_included():
    paths = ["/setup/who", "/setup/account?mode=signin", "/setup/account?mode=signup", "/setup/student"]
    r = templates(paths, keep=frozenset(paths))
    assert r == {p: p for p in paths}

def test_other_paths_still_group_beside_kept_ones():
    r = templates(["/collections/mens", "/collections/womens", "/setup/who"], keep=frozenset({"/setup/who"}))
    assert r["/collections/mens"] == "/collections/:handle" and r["/setup/who"] == "/setup/who"
```

- [ ] **Step 2:** `uv run pytest tests/test_explore_templates.py -v`. Expected: FAIL (unexpected keyword `keep`).
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** Same command. Expected: PASS, the existing template tests included.
- [ ] **Step 5: Commit** "Paths found through buttons are their own routes, query included".

### Task 3: Finding pages behind buttons (with the Clef gate)

**Files:**
- Create: `src/jev_demofast/explore/buttons.py`
- Test: `tests/test_explore_buttons.py` (new)

**Interfaces:**
- Consumes: `Session.act`, `Session.wait_for_page`, `Session.observe`, `Session.elements`, `Session.wait_loaded`
  (Task 1 turns the layer back on), `guards.blocked`, `guards.CHANGES`, `guards.on_site`, `cloudflare.sees_images`,
  `cf.yes`.
- Produces:
  - `NAVIGATES_CONFIDENT = 0.8`
  - `QUESTION` and the true/false strings, verbatim from the spec:
    `"A visitor is on this page and has typed nothing into its fields. Does clicking the button named in 'button' only take them to another page or step (navigation such as Back, or a link to a different form), without sending this page's form or signing in?"`,
    `true="yes: it only navigates"`, `false="no: it sends the form, signs in, or changes something"`
  - `only_navigates(cf, label, page, fields, buttons, screenshot) -> bool`. The state is
    `{url, button, fields_on_page, buttons_on_page, visible_text[:1500]}`. Any exception, `cf is None` or
    `not sees_images(cf.s.check_model)` returns False.
  - `discover(s, origin, path, cf, log=print) -> list[dict]`, returning `[{"label", "to", "via": "button"}]`. `label`
    is the button label's first line, stripped. `to` is the landed URL's path plus its `?query` when present. On
    return, the session is back on `origin + path` (via `Page.navigate` + `wait_loaded`).

- [ ] **Step 1: Write the failing tests** (a fake session with pages keyed by path+query, buttons whose click sets
  the next path, a `has_fields` flag, and a fake `cf` whose `yes` returns scores per label)

```python
def test_a_button_that_leads_elsewhere_becomes_a_link():           # [{"label": "I'm a student", "to": "/setup/student", "via": "button"}]
def test_the_query_is_kept_in_the_link():                          # lands on /setup/account?mode=signin → "to" keeps ?mode=signin
def test_blocked_and_changing_buttons_are_never_clicked():         # "Sign up", "Delete", "Save" → zero act() calls
def test_on_a_page_with_fields_clef_decides():                     # 0.93 clicked, 0.03 not clicked
def test_no_check_model_means_no_clicks_on_pages_with_fields():    # cf=None, and a cf whose check model is text-only → zero act() calls
def test_a_clef_error_means_no_click():                            # cf.yes raises → not clicked, discovery continues
def test_a_button_that_stays_adds_no_link_and_the_page_is_reloaded():  # same address → no link; Page.navigate back before the next button
def test_same_label_is_tried_once():                               # two "Sign in" → one act()
def test_a_button_that_leaves_the_site_adds_no_link():             # lands on other.test → no link
def test_ends_on_the_page_it_started_from():                       # last Page.navigate is origin + path
```

- [ ] **Step 2:** `uv run pytest tests/test_explore_buttons.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement.** A page "has fields" when any element has a `"fill"` action or the page has a visible
  password input (`explore.SIGN_IN_FORM_JS`; import it lazily to avoid a cycle, or move the constant to
  `buttons.py`). The screenshot comes from `Page.captureScreenshot` (jpeg, quality 80), taken once per page. Log one
  line per link found: `  button "<label>" → <to>`.
- [ ] **Step 4:** Same command. Expected: PASS.
- [ ] **Step 5: Commit** "On Flutter pages the explorer finds pages behind buttons; Clef decides on pages with fields".

### Task 4: The explorer maps Flutter sites

**Files:**
- Modify: `src/jev_demofast/explore/__init__.py` (`_read_page`, `explore`)
- Test: `tests/test_explore_crawl.py` (a fake Flutter site in the existing `fake_session` style)

**Interfaces:**
- Consumes: `Session.is_flutter` (Task 1), `templates(paths, keep=...)` (Task 2), `buttons.discover` (Task 3).
- Produces: the map. For a Flutter site, entries are keyed by full path+query for button-found pages. Each entry's
  `links` includes the button links (with `"via": "button"`), and its `texts` come from the page text when there are
  no headings.

- [ ] **Step 1: Write the failing tests.** The fake K-12 site has `/setup/who` (no fields; buttons "I'm a parent" →
  `/setup/account?mode=signup`, "I'm a student" → `/setup/student`, "Sign in" ×2 → `/setup/account?mode=signin`),
  `/setup/student` (buttons → `/setup/kid`), the account pages and `/setup/kid` with fields and a password, and
  `HEADINGS_JS` returning `[]` everywhere.

```python
def test_a_flutter_site_is_mapped_through_its_buttons(monkeypatch):
    m = explore("https://k12.test/", session=fake_flutter_session(), cf=FakeClef({"I need an account": .93, "Back": .98, "Sign in": .02}))
    assert {"/setup/who", "/setup/student", "/setup/account?mode=signin", "/setup/kid"} <= set(m)
    assert {"label": "I'm a student", "to": "/setup/student", "via": "button"} in m["/setup/who"]["links"]
    assert m["/setup/account?mode=signin"]["sign_in"] and m["/setup/kid"]["sign_in"] and not m["/setup/who"]["sign_in"]

def test_a_flutter_page_without_headings_gets_texts_from_its_text():
    # m["/setup/who"]["texts"][:2] == ["TutorQ K-12", "Parents and students set up differently, so we ask first."]
    # and no button label appears in texts

def test_button_discovery_respects_the_time_budget(monkeypatch):
    # max_minutes exhausted (monkeypatched clock) after the first page → discover() is not called again, the map is written

def test_a_normal_site_never_runs_button_discovery(monkeypatch):
    # monkeypatch buttons.discover to raise; the existing site_pages() explore still succeeds with the same map as before
```

- [ ] **Step 2:** `uv run pytest tests/test_explore_crawl.py -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.**
  - In `visit()`, when `s.is_flutter`: `page["links"] += discover(s, origin, path, cf, log)`, then queue each
    `to`, and add it to a `button_paths` set.
  - Every `templates(...)` call passes `keep=frozenset(button_paths)`.
  - In `_read_page`, when `s.is_flutter` and the headings are empty: `texts` = the first 10 distinct lines of
    `s.page["text"]`, each 3–119 characters long, excluding any line equal to a button label's first line.
  - Discovery runs only while the explorer is inside `max_minutes`; pages it queues count toward `max_pages` as links do.
  - Non-Flutter code paths stay untouched.
- [ ] **Step 4:** `uv run pytest -q`. Expected: all pass (251 + the new ones).
- [ ] **Step 5: Commit** "The explorer maps Flutter sites: pages behind buttons, texts without headings".

### Task 5: The tour clicks button-found links on camera

**Files:**
- Modify: `src/jev_demofast/drive/tour.py` (`run`, `_reach`)
- Test: `tests/test_tour.py`

**Interfaces:**
- Consumes: map links with `"via": "button"` (Task 4).
- Produces: `button_labels(index) -> dict[str, list[str]]` in `tour.py` (`{to_path: [label, ...]}`, from every entry's
  links with `via == "button"`). `_reach(..., labels=())`: when no href link leads to the page, click the first
  element with a `"click"` action whose label's first line is in `labels`, through `click_on_camera`. Only if there's
  none does it navigate (the cut), as today.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_page_reached_by_a_button_is_clicked_on_camera():   # rec.actions[-1]["do"] == "click", target "I'm a student"; no Page.navigate
def test_without_a_matching_button_the_tour_still_cuts():     # labels don't match → "go" action as today
```

- [ ] **Step 2:** `uv run pytest tests/test_tour.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Match on the shot page's path (`_path`, as `_leads_to` does).
- [ ] **Step 4:** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** "The tour clicks the button that leads to a page, when the map found it through one".

### Task 6: Verify live

**Files:** none (a run log goes into the PR description)

- [ ] **Step 1: Check other sites didn't change.** On `main`, then on this branch, run
  `uv run jev-demofast explore https://onecentdemo.com/ --out /tmp/<branch>-ocd.json` and the same for
  `https://selvage.run/`. Diff the JSON without `explored_at`. Expected: identical, or the differences explained by
  the live site changing between the runs.
- [ ] **Step 2: Map K-12.** `uv run jev-demofast explore https://k12.tutorq.ai/` with the Cloudflare env. Expected:
  the map named in the spec's "How we'll know it works", and log lines `button "I'm a student" → /setup/student`
  etc. Nothing under `/setup/account` or `/setup/kid` is submitted (the log shows no click on "Sign in" there).
- [ ] **Step 3: Record the demo.** `uv run jev-demofast demo "Show students how they get into TutorQ K-12" --url
  https://k12.tutorq.ai/ --fresh --voice chris`. Expected: `verified: True`, and the shots line includes
  `/setup/student (click)`. Watch the MP4 once.
- [ ] **Step 4:** `uv run pytest -q`, and open the PR (the user merges).
