# Behaviour Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In a `--login` run, mapping uses the signed-in app like a person (sections, buttons, forms, dialogs, wizards)
and writes a persistent, learning map of screens, actions with outcomes, jobs and the account's state.

**Architecture:** A new package `src/jev_demofast/behaviour/` crawls with the signed-in sessions from `login/flow.py`.
Every click and fill goes through `Session.act`, so the login branch's safety rules apply unchanged. Its result is
stored under one `_behaviour` key in the same file as today's route entries. Every reader already skips keys that
start with `_`, so the current story and recording keep working. `with_login` calls the crawl where it calls
`explore()` today. A keyed local store makes the map persistent, and later runs merge into it.

**Tech Stack:** Python 3.14, pytest, the existing `Session` / `Cloudflare` (`cf.yes`, `cf.choose`, `cf.chat_json`).

**Spec:** `docs/superpowers/specs/2026-10-29-behaviour-map-design.md`

## Global Constraints

- Every click and fill goes through `Session.act`. Never use `browser.call("Input...")` or JS `.click()` to press a
  control. That's how hazard labels, the screen-judged money check (`drive/money.py`) and the own-email rule apply.
- Mapping never flips a toggle (`guards.TOGGLES`) and never presses a `guards.CHANGES` label, except: an add or create
  label (`ADDS`, Task 4); and a submit or forward button on a screen where mapping itself filled fields during this
  visit.
- No credential in the map, the store, a log line or a model prompt. The map holds what the account shows and what
  mapping typed (made-up values only). An email typed is only ever the account's own.
- Budgets (defaults): total 20 minutes (`TOTAL_S = 1200`), `STEPS_PER_SECTION = 40`, `ITEMS_PER_LIST = 2`.
- One-time account steps are walked up to, but not through, the forward click that would finish them. They're
  recorded as `"seen, not finished"`.
- Under `--login-via stdin`, nothing is stored outside the run's work folder. Locally, the store key is an HMAC of the
  account email with a secret created once at `~/.cache/jev-demofast/maps/.key` (mode 0600).
- Outcome strings, exactly: `"→ <screen key>"`, `"dialog <screen key>"`, `"added '<item>'"`, `"no change"`,
  `"refused: <why>"`.
- Code style: match the surrounding code (short docstrings that give the reason, measured numbers in comments, no
  type annotations except where the module already uses them). Files under 300 lines.

## Review Focus

1. **The way back is lost after a click** (a dialog that won't close, a page that moved). The crawl must recover by
   reopening the section and keep going, not end the whole map. Test: `test_lost_way_back_reopens_the_section` (Task 6).
2. **A dialog whose buttons are all hazards or refused** (a "Delete Maya?" confirm). Record it as refused and close it
   with Escape. Never press anything in it. Test: `test_a_dialog_with_only_refused_ways_is_closed` (Task 7).
3. **A saved map from an older run with screens that no longer exist.** They're marked `gone`, kept, and not offered
   as a job's steps. Test: `test_a_job_through_a_gone_screen_is_not_proven` (Task 8).
4. **The model is down partway through.** Value-making and job-naming failures must not crash the crawl. A form with
   no values isn't submitted, and an unnamed job is named from its last control. Tests:
   `test_no_values_no_submit` (Task 7), `test_unnamed_job_falls_back` (Task 8).
5. **A list with forty items.** Only `ITEMS_PER_LIST` are opened, and the rest are counted in `left`. Test:
   `test_long_lists_open_two_items` (Task 6).

---

## File Structure

- `src/jev_demofast/behaviour/__init__.py`: exports `crawl`, `load_map`, `save_map`.
- `behaviour/model.py`: the map's shape. Screen keys, adding screens and actions, merging a new crawl into a saved
  map (last seen, gone), and the legacy route view. Pure, with no browser.
- `behaviour/store.py`: where maps live (keyed path, secret, load, save).
- `behaviour/screens.py`: reading the screen the session is on: its kind, title, key, controls, the open dialog, and
  the app's navigation.
- `behaviour/rules.py`: which controls mapping may press, and the outcome of a press.
- `behaviour/crawl.py`: the walk: account state, sections, controls, going back, budgets.
- `behaviour/forms.py`: forms, dialogs and wizards inside the walk: made-up values, the forward choice, the one-time
  stop.
- `behaviour/jobs.py`: jobs from actions (proven, partial, repeatable, needs) and naming them.
- `behaviour/fit.py`: does the account support the sentence, the summary printout, and asking the founder.
- Modify `login/ask.py`: a choice question (in a terminal and on stdin).
- Modify `login/flow.py`: `with_login` crawls and stores. Modify `cli.py`: `--fresh-map` and the fit check before
  recording. Modify `narrate/story.py`: `context()` adds sections and jobs.
- Tests: `tests/fakeapp.py` (a K-12-shaped fake app behind the session interface, as every test here fakes the
  browser), `tests/fixtures/fakeapp.html` (the same app as one HTML page, for the live check in Task 11), and
  `tests/test_behaviour_*.py`.

---

### Task 1: The map's shape and how a new crawl merges in

**Files:**
- Create: `src/jev_demofast/behaviour/__init__.py`, `src/jev_demofast/behaviour/model.py`
- Test: `tests/test_behaviour_model.py`

**Interfaces:**
- Produces:
  - `empty() -> dict`, which returns
    `{"account": {"state": None, "sections": []}, "screens": {}, "actions": [], "jobs": [], "left": []}`.
  - `screen_key(url, title=None, kind="page") -> str`: the path, plus the query and `#/route` exactly as
    `session.address` keeps them, followed by `" · dialog: <title>"` or `" · step: <title>"` for those kinds.
  - `add_screen(m, key, screen, now)`, where `screen` is
    `{kind, title, url, texts, fields, controls}`. It sets `last_seen=now` and clears `gone`.
  - `add_action(m, screen_key, control, did, outcome, now, values=None) -> int`: the action's index. The same
    `(screen, control, did)` updates the existing entry in place.
  - `merge(saved, fresh, seen_sections, now) -> dict`. `fresh` wins for anything it saw. A saved screen in one of
    `seen_sections` that `fresh` didn't see gets `gone=True`. Screens in other sections are kept as they were. Each
    screen carries its `section`.
  - `legacy_routes(m, origin) -> {route: entry}`: entries in today's route format
    (`file, submits, examples, links, buttons, fields, texts, kind, filters, sort, sign_in`), one per non-dialog
    screen URL path.

- [ ] **Step 1: Write the failing tests**

```python
def test_dialog_and_step_keys_are_distinct_from_their_page():
    assert screen_key("https://k12.test/setup/kids") == "/setup/kids"
    assert screen_key("https://k12.test/setup/kids", "Add Maya first?", "dialog") == "/setup/kids · dialog: Add Maya first?"
    assert screen_key("https://k12.test/#/kids/new", "Maya's login", "wizard-step") == "/#/kids/new · step: Maya's login"

def test_the_same_action_is_updated_not_repeated():
    m = empty()
    i = add_action(m, "/kids", "Add", "click", "no change", "t1")
    assert add_action(m, "/kids", "Add", "click", "added 'Maya'", "t2") == i
    assert m["actions"][i]["outcome"] == "added 'Maya'" and len(m["actions"]) == 1

def test_merge_marks_unseen_screens_of_a_remapped_section_gone_and_keeps_others():
    saved = empty(); add_screen(saved, "/kids", {"kind": "tab", "section": "Kids", **BLANK}, "t1")
    add_screen(saved, "/kids/old", {"kind": "page", "section": "Kids", **BLANK}, "t1")
    add_screen(saved, "/settings", {"kind": "tab", "section": "Settings", **BLANK}, "t1")
    fresh = empty(); add_screen(fresh, "/kids", {"kind": "tab", "section": "Kids", **BLANK}, "t2")
    m = merge(saved, fresh, seen_sections={"Kids"}, now="t2")
    assert m["screens"]["/kids/old"]["gone"] and not m["screens"]["/kids"].get("gone")
    assert m["screens"]["/settings"]["last_seen"] == "t1" and not m["screens"]["/settings"].get("gone")

def test_legacy_routes_feed_todays_readers():
    m = empty(); add_screen(m, "/kids", {"kind": "tab", "title": "Kids", "url": "https://k12.test/kids",
                                         "texts": ["Your kids"], "fields": [], "controls": ["Add a kid"]}, "t1")
    add_screen(m, "/kids · dialog: Add?", {"kind": "dialog", **BLANK}, "t1")
    r = legacy_routes(m, "https://k12.test")
    assert list(r) == ["/kids"] and r["/kids"]["buttons"] == [{"label": "Add a kid", "submit": False}]
    assert r["/kids"]["texts"] == ["Your kids"] and r["/kids"]["kind"] == "page"
```

(`BLANK = {"title": "", "url": "", "texts": [], "fields": [], "controls": []}`, defined in the test module.)

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_behaviour_model.py -q`. Expected: fails with ModuleNotFoundError `jev_demofast.behaviour`.

- [ ] **Step 3: Implement `model.py` and `__init__.py`.** `screen_key` uses `drive.session.address`.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_behaviour_model.py -q`. Expected: 4 passed.

- [ ] **Step 5: Commit.** Message: "Behaviour map: screens, actions, merge and the legacy route view".

---

### Task 2: Where maps live

**Files:**
- Create: `src/jev_demofast/behaviour/store.py`
- Test: `tests/test_behaviour_store.py`

**Interfaces:**
- Consumes: `model.empty()`.
- Produces:
  - `MAPS = Path("~/.cache/jev-demofast/maps").expanduser()`. Tests monkeypatch `store.MAPS`.
  - `map_path(host, email, maps=None) -> Path` gives `<maps>/<host>.<hmac16>.behaviour.json`. `hmac16` is the first 16
    hex characters of `hmac.new(secret, email.lower().encode(), sha256)`. The secret comes from `<maps>/.key`: 32
    random bytes, created with mode 0600 if missing.
  - `load_map(host, email) -> dict | None`.
  - `save_map(m, host, email) -> Path`.

- [ ] **Step 1: Write the failing tests:**
  - `test_the_path_never_holds_the_email`: `"parent@demo.test"` and `"parent"` are not in `str(map_path(...))`.
  - `test_the_key_needs_the_secret`: deleting `.key` and recomputing gives a different path.
  - `test_the_secret_is_private`: `.key` has mode `0o600`.
  - `test_save_then_load_round_trips`.
  - `test_unknown_account_loads_none`.
- [ ] **Step 2: Run them.** Expected: fails with ImportError.
- [ ] **Step 3: Implement `store.py`.** Use `secrets.token_bytes(32)` and `os.open(..., 0o600)`.
- [ ] **Step 4: Run them.** Expected: 5 passed.
- [ ] **Step 5: Commit.** Message: "Behaviour map store: keyed by site and a secret-keyed hash of the account".

---

### Task 3: Reading the screen

**Files:**
- Create: `src/jev_demofast/behaviour/screens.py`
- Test: `tests/test_behaviour_screens.py`
- Create: `tests/fakeapp.py`. It's used from here on, so build it whole now (Interfaces below).

**Interfaces:**
- Consumes: `Session` (`page`, `observe()`, `elements()`, `browser.evaluate`), `model.screen_key`.
- Produces:
  - `DIALOG_JS`: the title of an open `[role=dialog],[role=alertdialog],dialog[open],[aria-modal=true]` whose box has
    a non-zero size, else `null`. The title is its `aria-label`, else its first line of text. Size is judged by
    `getBoundingClientRect`, **not** `checkVisibility`: Flutter's semantics tree has `filter: opacity(0)`.
  - `read_screen(s, wizard=False) -> (key, screen)`. `kind` is `"dialog"` when `DIALOG_JS` gives a title, else
    `"wizard-step"` when `wizard`, else `"page"`. `controls` are the first lines of the labels of clickable
    elements, in screen order. `fields` are the labels of fillable elements.
  - `nav_labels(s) -> list[str]`: the clickable labels whose elements have role `tab`, `link` or `button`, are not
    fields, and are not `guards.blocked`.
  - `sections(first, second) -> list[str]`: labels in both `nav_labels` lists, in `first`'s order. The app's
    navigation is what stays on screen when you move between sections.
- `tests/fakeapp.py` is a `FakeApp(state="set up" | "partway", flutter=False)` session with the session interface
  (`page`, `observe`, `elements`, `act`, `refind`, `check`, `wait_for_page`, `wait_loaded`, `browser.call`,
  `browser.evaluate`, `close`, `hazards=True`, `money_step`). Its screens:
  - Home, Kids, Subjects and Settings as tabs, always visible.
  - Kids: a list with "Maya" and "Leo", "Add a kid" (opens the add form), "Delete".
  - The add form: "First name" and "Age" with "Add" and "Continue". Continue with a name typed but not added opens
    the dialog "Add <name> first?" with "Skip" and "Add".
  - Adding a kid opens the wizard "<name>'s login" → "Subjects" → "All set" (the steps' forward button is "Next").
  - Subjects: 40 subject items.
  - Settings: an "Email me weekly" switch and "Log out".
  - "Upgrade": a card form ("Card number", "Continue").
  - With `state="partway"`, the first screen is the setup step "Your kids, current step / Verify you are the parent,
    next" with First name, Age, Add and Continue, and Continue after an add goes to "Verify you are the parent".
  - With `flutter=True`, a dialog is exposed only as `role=dialog` on a node whose page text is just the dialog's
    controls (the "Skip Add" seen live on 29 October).
  - It records every press in `app.pressed` and every typed value in `app.typed`.

- [ ] **Step 1: Write the failing tests:**
  - `test_a_dialog_is_its_own_screen`: on the fake app's add form, press Continue with a name typed (call `act`
    directly). `read_screen` then gives kind `"dialog"` and the key `"/kids/new · dialog: Add Maya first?"`.
  - `test_a_flutter_dialog_is_found_by_its_box`: the same with `flutter=True`.
  - `test_sections_are_what_stays_on_screen`: `sections(nav_labels(home), nav_labels(kids)) == ["Home", "Kids",
    "Subjects", "Settings"]`. The list doesn't hold "Add a kid", "Delete" or "Log out".
- [ ] **Step 2: Run them.** Expected: fails with ImportError.
- [ ] **Step 3: Implement `screens.py` and `tests/fakeapp.py`.**
- [ ] **Step 4: Run them.** Expected: 3 passed.
- [ ] **Step 5: Commit.** Message: "Behaviour map: read the screen (dialogs incl. Flutter's), the app's sections; fake app".

---

### Task 4: What mapping may press, and what a press did

**Files:**
- Create: `src/jev_demofast/behaviour/rules.py`
- Test: `tests/test_behaviour_rules.py`

**Interfaces:**
- Consumes: `guards.blocked`, `guards.CHANGES`, `guards.TOGGLES`, `guards.hazard`.
- Produces:
  - `ADDS = re.compile(r"\b(add|create|new)\b", re.I)`.
  - `may_press(e, filled_here) -> bool`. It's False when any of these holds:
    - the label is `blocked` or a `hazard`;
    - the element's role is in `TOGGLES`;
    - the label matches `CHANGES` but not `ADDS`, and `filled_here` is false.
  - `outcome(before_key, before_text, after_key, after_kind, after_text, typed) -> str`, one of the Global Constraints
    strings:
    - a dialog → `"dialog <after_key>"`;
    - a different key → `"→ <after_key>"`;
    - the same key with a typed value newly in the text → `"added '<value>'"`;
    - otherwise `"no change"`.

- [ ] **Step 1: Write the failing tests:**
  - `test_may_press` checks these labels and roles:
    - "Add a kid" → True;
    - "Next" → True;
    - "Delete" → False;
    - "Log out" → False;
    - "Save" with `filled_here=False` → False, and with `filled_here=True` → True;
    - a "switch" role "Email me weekly" → False;
    - "Verify with a card" → False.
  - `test_outcomes` checks four cases: a move, a dialog, an add (`typed=["Maya", "14"]` where "Maya" is new in the
    after text) and no change.
- [ ] **Step 2: Run them.** Expected: fails with ImportError.
- [ ] **Step 3: Implement `rules.py`.**
- [ ] **Step 4: Run them.** Expected: all passed.
- [ ] **Step 5: Commit.** Message: "Behaviour map: press rules (add, never change what's there) and outcomes".

---

### Task 5: The account's state

**Files:**
- Create: `src/jev_demofast/behaviour/crawl.py` (this task adds `account_state` only)
- Test: `tests/test_behaviour_crawl.py`

**Interfaces:**
- Consumes: `cf.chat_json(cf.s.read_model, ACCOUNT, context)`.
- Produces:
  - `ACCOUNT`: the system prompt, which asks for JSON
    `{"setup_unfinished": bool, "current_step": "<the step's name as shown, or empty>"}` from the first signed-in
    screen's text and controls.
  - `account_state(cf, screen) -> str`, either `"set up"` or `"partway: <current_step>"`. When the model fails it
    returns `"unknown"` (logged, never guessed).

- [ ] **Step 1: Write the failing tests:**
  - `test_partway_names_the_step`: the fake model answers
    `{"setup_unfinished": true, "current_step": "Your kids"}`, which gives `"partway: Your kids"`.
  - `test_set_up`.
  - `test_model_down_is_unknown`.
- [ ] **Step 2: Run them.** Expected: fails with ImportError.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run them.** Expected: 3 passed.
- [ ] **Step 5: Commit.** Message: "Behaviour map: read the account's state from the first signed-in screen".

---

### Task 6: The walk: sections, controls, going back, budgets

**Files:**
- Modify: `src/jev_demofast/behaviour/crawl.py`
- Test: `tests/test_behaviour_crawl.py`

**Interfaces:**
- Consumes: Tasks 1, 3, 4 and 5. `forms.handle` comes from Task 7. Until then, a screen with fields is recorded and
  not pressed.
- Produces:
  - `Budget(total_s=1200, steps_per_section=40, items_per_list=2)`, a dataclass.
  - `crawl(new_session, cf, origin, saved=None, budget=None, log=print, now=None) -> dict`. `new_session(url)` is
    `Login.session`. It returns the merged map. Each section is walked like this:
    1. Open it by pressing its nav label from the section's start screen.
    2. Read the screen.
    3. For each control `may_press` allows, in screen order: press it with `Session.act`, then `s.wait_for_page()`,
       then read the screen again, record the screen and the action with its `outcome`, then go back.
  - Going back: reopen the section's start URL with `Page.navigate` and press its nav label again. If the expected
    screen doesn't come back, use `new_session` once. If that fails, add `"<section>: way back lost"` to `left` and go
    on to the next section.
  - Repeated items: of controls whose labels sit in a list (the same screen holds 3+ sibling controls that each
    lead to a screen with the same key template, using `explore.templates`), only `items_per_list` are pressed. The
    rest are counted in `left` as `"<screen>: <n> more items"`.
  - A `HazardStop` from `act` is recorded as `"refused: <label>"`.

- [ ] **Step 1: Write the failing tests** against `FakeApp()`:
  - `test_every_section_is_visited`: `m["account"]["sections"] == ["Home", "Kids", "Subjects", "Settings"]`, and each
    has a tab screen.
  - `test_refused_controls_are_recorded_not_pressed`:
    - "Delete", "Log out" and "Upgrade → Continue" are never in `app.pressed`;
    - the switch is never pressed;
    - "Delete" has an action with an outcome starting `"refused"` or is absent.

    (Absent is allowed: `may_press` skips it before `act`.)
  - `test_long_lists_open_two_items`: two of the 40 subjects are opened, and `left` holds `"38 more items"`.
  - `test_lost_way_back_reopens_the_section`: the fake app is set to strand the session after "Maya". The crawl still
    records the Settings section.
  - `test_the_total_budget_stops_the_walk`: with `Budget(total_s=0)` it returns at once, and `left` names every
    section.
- [ ] **Step 2: Run them.** Expected: fails with AttributeError `crawl`.
- [ ] **Step 3: Implement `Budget` and `crawl`.** Keep `crawl.py` under 300 lines. The per-screen loop is a helper,
  `_try_controls(s, m, section, budget, log)`.
- [ ] **Step 4: Run them.** Expected: all passed.
- [ ] **Step 5: Commit.** Message: "Behaviour map: walk the sections and their controls, back each time, within budget".

---

### Task 7: Forms, dialogs and wizards

**Files:**
- Create: `src/jev_demofast/behaviour/forms.py`
- Modify: `src/jev_demofast/behaviour/crawl.py` (call `forms.handle` on screens with fields, and on dialogs)
- Test: `tests/test_behaviour_forms.py`

**Interfaces:**
- Consumes: `cf.chat_json(cf.s.read_model, MAKE_VALUES, ctx)`, `cf.choose`, `cf.yes`, `rules`, `screens`, `model`.
- Produces:
  - `MAKE_VALUES`: asks for `{"values": {"<field label>": "<value>"}}`. The values are believable and made up, and
    an email is only `own_email`. It's given the labels, the screen's text and the names already used in this map,
    so they aren't reused ("Maya" → "Leo").
  - `FINISHES`, `FINISH_TRUE`, `FINISH_FALSE`: a `cf.yes` question with a screenshot: "Would pressing '<label>' finish
    a setup the account goes through only once, leaving it for good?"
  - `ONE_TIME = 0.5`: at or above, the button isn't pressed. A model error counts as finishing.
  - `handle(s, cf, m, key, screen, account, budget, log) -> list[int]` returns the action indexes it recorded,
    and appends them as one list to `m["chains"]` (a list of lists, which Task 8 reads). The account's email is
    `s.own_email`. It works like
    this:
    1. Fill the fields with made-up values through `Session.act(e, "fill", text=v)`.
    2. Choose the forward button with `cf.choose("Which button moves this form forward?", ...)` among those
       `may_press(e, filled_here=True)` allows.
    3. If `account` starts with `"partway"`, ask `FINISHES` first. If the button would finish the setup, record
       `"seen, not finished"` and stop.
    4. Press, read the screen and record the outcome.
    5. If the outcome is a dialog, choose its forward button with `cf.choose("Which button in this dialog carries on
       with what was being done?", ...)`. Press that one, and record each other button as seen but not pressed
       (outcome `"not pressed"`).
    6. If the outcome is a screen with fields, continue on it as the next wizard step (`read_screen(s, wizard=True)`),
       up to `budget.steps_per_section`.

- [ ] **Step 1: Write the failing tests** against `FakeApp()` with a scripted fake model:
  - `test_adding_a_kid_is_walked_through_the_dialog_and_wizard`: `app.typed` holds the made-up name and age, then the
    dialog's "Add" is pressed, then the wizard reaches "All set". The dialog's "Skip" has outcome `"not pressed"`.
  - `test_partway_setup_stops_before_finishing`: on `FakeApp(state="partway")` with `FINISHES` scored 0.9 on the
    Continue that leads to "Verify you are the parent", the Continue isn't pressed and its action's outcome is
    `"seen, not finished"`.
  - `test_no_values_no_submit`: the values model raises. Nothing is filled and nothing is pressed.
  - `test_a_dialog_with_only_refused_ways_is_closed`: "Delete Maya?" with "Delete" and "Cancel" (Cancel is
    `blocked`). Nothing is pressed, the dialog is closed with Escape, and its outcome is `"refused: no safe way"`.
  - `test_only_the_accounts_email_is_typed`: an "Email" field gets `own_email`, never a made-up address.
- [ ] **Step 2: Run them.** Expected: fails with ImportError.
- [ ] **Step 3: Implement `forms.py` and call it from `crawl`.**
- [ ] **Step 4: Run them, then the whole suite.** Run `uv run pytest -q`. Expected: all passed.
- [ ] **Step 5: Commit.** Message: "Behaviour map: fill forms with made-up values, carry on through dialogs and
  wizards, stop before one-time finishes".

---

### Task 8: Jobs

**Files:**
- Create: `src/jev_demofast/behaviour/jobs.py`
- Modify: `src/jev_demofast/behaviour/crawl.py` (set `m["jobs"] = jobs.find(cf, m)` at the end)
- Test: `tests/test_behaviour_jobs.py`

**Interfaces:**
- Produces: `find(cf, m) -> list[dict]`. Each job is
  `{name, steps: [action indexes], result, repeatable, needs, proven, stopped?}`. A job is a chain of actions that a
  form or wizard visit recorded (Task 7 `handle`'s indexes, kept as `m["chains"]`), starting from the section control
  that opened it.
  - `proven`: the chain holds an `"added '<x>'"` outcome, or ends on a screen whose text shows a typed value.
  - `stopped`: the chain ends `"refused: …"` or `"seen, not finished"`. It's then partial: `proven` is False and
    `stopped` holds the outcome.
  - `repeatable`: False when the chain ran while the account was `"partway"`.
  - `needs`: the account state the chain ran under.
  - `name`: from `cf.chat_json` with `NAME_JOBS`, in the product's words. On a model error it falls back to the first
    control's label.
  - A job with a step on a `gone` screen is not proven.

- [ ] **Step 1: Write the failing tests:**
  - `test_add_a_kid_is_a_proven_repeatable_job`: on the set-up fake app, after a crawl, one job has the steps "Add a
    kid", "First name", "Age", "Continue", dialog "Add", "Next", "Next", with `proven=True`, `repeatable=True` and
    `needs="set up"`.
  - `test_partway_setup_is_a_partial_one_time_job`.
  - `test_unnamed_job_falls_back`.
  - `test_a_job_through_a_gone_screen_is_not_proven`.
- [ ] **Step 2: Run them.** Expected: fails with ImportError.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run them.** Expected: all passed.
- [ ] **Step 5: Commit.** Message: "Behaviour map: jobs, proven or partial, repeatable or one-time, named by the model".

---

### Task 9: Learning on reuse

**Files:**
- Modify: `src/jev_demofast/behaviour/crawl.py`
- Test: `tests/test_behaviour_crawl.py`

**Interfaces:**
- `crawl(..., saved=<map>)` reads the account state and the sections first:
  - A section whose tab screen has the same key and the same `controls` as in `saved` isn't walked again. Its screens
    get `last_seen=now`.
  - A new or changed section is walked.
  - If the account state differs from `saved`, every section is walked.
  - The result is `model.merge(saved, fresh, seen_sections, now)`.

- [ ] **Step 1: Write the failing tests:**
  - `test_an_unchanged_map_is_not_walked_again`: the second crawl presses nothing past the tabs.
  - `test_a_new_section_is_walked`: the fake app gains "Schedule".
  - `test_a_changed_account_state_walks_everything`.
- [ ] **Step 2: Run them.** Expected: fails (everything is walked again).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run them.** Expected: all passed.
- [ ] **Step 5: Commit.** Message: "Behaviour map: a saved map is reused and only what changed is walked again".

---

### Task 10: The summary, the fit check, and asking the founder

**Files:**
- Create: `src/jev_demofast/behaviour/fit.py`
- Modify: `src/jev_demofast/login/ask.py`
- Test: `tests/test_behaviour_fit.py`, `tests/test_login_ask.py`

**Interfaces:**
- `login/ask.py`:
  - `choice_question(why, choices, qid) -> {"id", "why", "choices": [{"id", "label"}]}`.
  - `ask_terminal` and `ask_stdin` accept it. The terminal prints numbered labels and reads a number. Stdin
    validates `{"id", "choice"}`. The answer is `{"id", "choice"}`, or None for no answer, a timeout or garbage.
- `fit.py`:
  - `summary(m) -> str`: the lines printed after mapping. They give the account's state, the sections, each job as
    `name: step → step (proven | stopped: …)` and `left`.
  - `fits(cf, sentence, m) -> (bool, needed)`. `cf.choose` picks the job the sentence needs (with `allow_none`). It
    returns True when there's no job at `CONFIDENT` (`drive.check.CONFIDENT`) or the job's `needs` matches the
    account's state. Otherwise it returns False and the job's `needs`.
  - `CHOICES = [("record", "Record what this account can show"), ("account", "Use a different account"),
    ("stop", "Stop")]`.
  - `ask_how(ask, needed, state) -> "record" | "account" | "stop"`. No answer counts as `"stop"`.

- [ ] **Step 1: Write the failing tests:**
  - `test_summary_lists_state_sections_jobs_and_what_was_left`.
  - `test_a_partway_account_does_not_fit_an_in_app_add`.
  - `test_no_matching_job_fits`.
  - `test_no_answer_is_stop`.
  - In `test_login_ask.py`: `test_terminal_choice` and `test_stdin_choice_and_garbage`.
- [ ] **Step 2: Run them.** Expected: fails with ImportError.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run them.** Expected: all passed.
- [ ] **Step 5: Commit.** Message: "Behaviour map: summary, does the account fit the demo, ask the founder how to proceed".

---

### Task 11: Wire it in, and check it live

**Files:**
- Modify: `src/jev_demofast/login/flow.py`, `src/jev_demofast/cli.py`, `src/jev_demofast/narrate/story.py`
- Create: `tests/fixtures/fakeapp.html` (the fake app's screens as one HTML page with `role=dialog`, for the live
  check)
- Test: `tests/test_login_flow.py`, `tests/test_founder_script.py`

**Interfaces:**
- `flow.with_login(a, cf)` works like this:
  1. Prepare as today.
  2. Load the saved map with `store.load_map(host, login.own_email)`, unless `a.fresh_map` or `a.login_via ==
     "stdin"`.
  3. `m = crawl(login.session, cf, origin, saved=...)`.
  4. Store it with `save_map` under the same conditions.
  5. Write `{**legacy_routes(m, origin), "_site": <as today>, "_behaviour": m}` to
     `<work>/site-map-logged-in.json`.
  6. Print `fit.summary(m)`.
  7. Run `fit.fits` on `a.prompt`. If it doesn't fit, `ask_how(asker(a.login_via), ...)`:
     - `"record"` carries on;
     - `"account"` runs `prepare` again and maps that account;
     - `"stop"` raises `RuntimeError("login: the demo account can't show this; stopped as asked")`.
- `cli.py`: `--fresh-map`, under `demo`.
- `story.context(index)` adds `"sections"` and `"jobs"` (name, result, proven) when `index` has `_behaviour`.
- In `tests/test_login_flow.py`, `test_the_logged_in_map_is_not_cached` becomes
  `test_the_logged_in_map_is_stored_keyed_and_never_under_stdin`, because the spec reverses the login branch's
  "never cached".

- [ ] **Step 1: Write the failing tests:**
  - The renamed flow test.
  - `test_a_partway_account_asks_and_stop_stops`.
  - `test_story_context_has_sections_and_jobs`.
  - `test_without_login_nothing_changes` stays as it is.
- [ ] **Step 2: Run them.** Expected: fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the whole suite.** Run `uv run pytest -q`. Expected: all passed.
- [ ] **Step 5: Live check on the HTML fixture (no login, run by the implementer).**
  1. Serve `tests/fixtures/fakeapp.html` on `127.0.0.1`.
  2. Run `crawl` with `Session(url, isolated=True)` and `hazards=True`, using `BU_NAME=jdf-isolated` exported
     *before* Python starts.
  3. Expected:
     - the four sections;
     - the add-a-kid job proven through the dialog;
     - Delete, the switch and the card form never pressed;
     - a summary printed.

  Record the output in the ledger.
- [ ] **Step 6: Commit.** Message: "--login maps the app's behaviour, stores it keyed, and asks when the account
  can't show the demo".
- [ ] **Step 7: Live check on K-12 (run by the founder in their own Terminal; I never sign in to the live site).**
  Write the command and the success criteria into the final message:
  - the map lists the app's sections;
  - an "add a kid" job whose steps include the name, the age, Add and the "Add … first?" dialog;
  - the card check refused or `"seen, not finished"`;
  - for `+k1201`, the state `"partway: Your kids"` and the question about how to proceed.
