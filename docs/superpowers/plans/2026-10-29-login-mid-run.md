# Logging In Mid-Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `jev-demofast demo … --login` asks the founder for a demo account at the login wall, signs in off camera,
maps and records the logged-in app like a user would, and keeps nothing it was given.

**Architecture:**
- A new `login/` package holds four parts:
  - the question channel (`ask.py`: terminal or stdin);
  - choosing the sign-in forms (`forms.py`: Clef tells sign-in from sign-up);
  - signing in (`sign_in.py`);
  - a `Login` object that holds the answer in memory and makes signed-in, isolated sessions (`__init__.py`).
- `Session` gains a hazard mode: when it's on, `Session.act` refuses the logged-in hazards. `click_on_camera` asks
  the session first, so a refused click is never filmed.
- `cmd_demo` wires it together. A logged-in map lives only in the run's work folder.

**Tech Stack:** Python 3.14, CDP via browser-harness, pytest with fakes (no network).

**Spec:** `docs/superpowers/specs/2026-10-29-login-mid-run-design.md`

## Global Constraints

- **No credential is ever written anywhere:** not a log line, the map, `actions.json`, `replay.json`, `cf.decisions`,
  a frame, the cache, or a model prompt. A typed value lives only in the `Login` object.
- **Secret fields:**
  - which fields: an `input[type=password]`, or a label matching `guards.PASSWORD_NAME`;
  - how they're typed: through `Session.type_secret_into_password`, or `Input.insertText` on a focused field;
  - they're never observed, never filled through `Session.act`, and never in a recorded frame.
- `SIGNS_IN_CONFIDENT = 0.8`. The Clef question and true/false strings are verbatim from the spec.
- `ASK_TIMEOUT_S = 300`. No answer, or a garbled answer, counts as a skip.
- **With `--login`, the recording runs in an isolated context.** `--login` with `--use-my-browser` is refused with
  `SystemExit`.
- **The hazards can't be unlocked by a brief.** There's no `unless=` argument.
- **Without `--login`, every behaviour is exactly as today.**

## Review Focus

1. **A credential echoed in an error or traceback** (e.g. an exception message that includes the typed text).
   Covered by Task 5 `test_no_credential_in_any_written_file_or_log`, which raises inside sign-in on purpose.
2. **A hazard reached by the explorer's discovery, not the tour** (a "Delete" button on a logged-in page with no
   fields). Covered by Task 1 `test_hazards_are_refused_by_session_act_for_every_caller`.
3. **The founder answers after the timeout:** a late stdin line must not be read as the answer to a later question.
   Covered by Task 2 `test_an_answer_for_another_question_id_is_ignored`.
4. **The sign-in lands on a card-check page** (K-12's `/setup/verify`) instead of the dashboard: logged in, but every
   path is a hazard. The run must say so, not loop. Covered by Task 4 `test_landing_on_a_hazard_page_is_reported`.
5. **A recording session that fails to sign in** (the session expired between mapping and recording) must not record
   logged-out screens as if logged in. Covered by Task 5 `test_a_failed_sign_in_at_recording_stops_the_run`.

---

### Task 1: Logged-in hazards, enforced in the session

**Files:**
- Modify: `src/jev_demofast/drive/guards.py`, `src/jev_demofast/drive/session.py`,
  `src/jev_demofast/drive/jev_drive.py` (`click_on_camera`, `run`), `src/jev_demofast/drive/tour.py` (`run`)
- Test: `tests/test_login_hazards.py` (new)

**Interfaces:**
- Produces:
  - `guards.LOGGED_IN_HAZARDS`: a compiled regex over "pay, payment, purchase, buy, checkout, subscribe, upgrade,
    billing, card, verify you are the parent, delete, remove, cancel subscription, close account, log out, sign out,
    change email, change password, reset password, invite, share, send to";
  - `guards.HazardStop(Exception)`: its message is the refused label;
  - `guards.hazard(label, context="") -> bool`;
  - `Session.hazards: bool` (default False) and `Session.own_email: str | None`;
  - `Session.check(e, kind, text=None)`, which raises `HazardStop` when `hazards` is on and either the label (or the
    visible text around it, the guard scope `cache.guard` already reads) matches, or `kind == "fill"` into an email
    field (type email, or a label matching `/e-?mail/i`) with text ≠ `own_email`;
  - `Session.act` calls `check` first.
  - `click_on_camera` calls `s.check(e, "click")` before `rec.snap`.
  - `tour.run` and `jev_drive.run` catch `HazardStop`: the log line
    `"the next step is {label!r}; the demo stops here"`, `result["stopped_at"] = label`, and `verified` False.

- [ ] **Step 1: Write the failing tests**

```python
def test_each_hazard_word_matches():           # every word in the list above, and "Verify you are the parent"
def test_ordinary_labels_pass():               # "Save", "Add student", "Send", "Continue", "Study plan", "Ask the tutor"
def test_hazards_are_refused_by_session_act_for_every_caller():   # hazards on: act(click "Delete homework") raises HazardStop
def test_hazards_off_changes_nothing():        # hazards off: the same act() goes through
def test_an_email_other_than_the_accounts_own_is_refused():       # fill "Parent email" with "x@y.z" ≠ own_email → HazardStop
def test_a_refused_click_is_never_filmed():    # click_on_camera with a hazard: no rec.snap call, HazardStop raised
def test_the_tour_stops_and_says_why():        # tour.run with a hazard shot: log has "the demo stops here", result["stopped_at"]
```

  Note: "card" matches as a whole word. "Report card" will be refused, and the spec accepts that false positive (it
  costs a shot, never a payment). Assert `hazard("Report card")` is True and say so in the test's docstring.
- [ ] **Step 2:** `uv run pytest tests/test_login_hazards.py -v`. Expected: FAIL (`LOGGED_IN_HAZARDS` missing).
- [ ] **Step 3: Implement** to the interfaces above.
- [ ] **Step 4:** `uv run pytest -q`. Expected: all pass, the existing tour and drive tests unchanged.
- [ ] **Step 5: Commit** "Logged-in runs refuse payment, deletion, log-out, account and outreach steps, in one place".

### Task 2: The question channel

**Files:**
- Create: `src/jev_demofast/login/__init__.py` (empty for now), `src/jev_demofast/login/ask.py`
- Test: `tests/test_login_ask.py`

**Interfaces:**
- Produces:
  - `secret_field(label: str, input_type: str = "") -> bool`;
  - `question(forms: list[dict], why: str, retry: str | None = None, qid: str = "q1") -> dict` (the spec's JSON shape);
  - `ask_terminal(q, input=input, getpass=getpass.getpass, out=print) -> dict | None`;
  - `ask_stdin(q, stream=sys.stdin, log=print, timeout=ASK_TIMEOUT_S) -> dict | None`, which logs `"ask: " + json.dumps(q)` and reads one line with `select` on the stream;
  - `asker(via: str) -> Callable[[dict], dict | None]`.
- An answer is `{"id", "form", "values"}`, or None for skip, timeout or garbage.

- [ ] **Step 1: Write the failing tests**

```python
def test_secret_fields():                     # "Password", "Passcode", "PIN", type=password → True; "Email", "Your login ID" → False
def test_question_shape():                    # keys id, why, forms[].{id,title,page,fields[].{name,label,secret}}, retry
def test_terminal_reads_secrets_with_getpass():   # getpass called for the secret field only; input for the choice and the rest
def test_terminal_skip():                     # choice "s" → None
def test_stdin_answer():                      # one JSON line → the answer dict; log got one "ask: {...}" line with no values
def test_stdin_timeout_and_garbage_are_skips():
def test_an_answer_for_another_question_id_is_ignored():   # {"id": "q0", ...} → None
def test_the_log_line_never_contains_values(): # the ask: line, and any later log call, contain no answer value
```

- [ ] **Step 2:** `uv run pytest tests/test_login_ask.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement.** A single-form question still names the form. The terminal skips the choice when
  there's one form.
- [ ] **Step 4:** Same command. Expected: PASS.
- [ ] **Step 5: Commit** "The login question: asked in the terminal, or through stdin for a host".

### Task 3: Choosing the sign-in forms

**Files:**
- Create: `src/jev_demofast/login/forms.py`
- Test: `tests/test_login_forms.py`

**Interfaces:**
- Consumes: `Session` (`browser.call("Page.navigate")`, `wait_loaded`, `observe`, `elements`), `cf.yes`, `sees_images`,
  `explore.buttons.SIGN_IN_FORM_JS`, `ask.secret_field`.
- Produces:
  - `SIGNS_IN_CONFIDENT = 0.8`;
  - `QUESTION`, `TRUE` and `FALSE`, verbatim from the spec;
  - `sign_in_forms(s, origin, index, cf, log=print) -> list[dict]`, returning
    `[{"id": "f1", "title", "page", "fields": [{"name", "label", "secret"}]}]`.

  For each entry with `sign_in: true` (its examples, or the route itself) it reopens the page live, asks Clef, keeps
  only scores ≥ 0.8, builds the fields from the page's `fill` elements plus one secret field per visible password
  input (labelled from its `aria-label`, `placeholder`, else "Password"), titles the form, and dedupes by
  (title, field labels). A field's `name` is its label slugified.
- With `cf is None`, or a text-only check model, it returns `[]` and logs
  `login: can't tell sign-in forms apart without the check model`.

- [ ] **Step 1: Write the failing tests**

```python
def test_k12_gives_two_forms():               # fake K-12 (signin, as=student signin, kid, three sign-up pages) with the measured scores → titles ["Welcome back.", "Sign in to your subjects"]
def test_titles_skip_text_shared_by_every_page():   # "TutorQ K-12" is never a title
def test_sign_up_forms_are_dropped():         # scores 0.01 → not offered
def test_duplicates_are_offered_once():       # the parent and student "Welcome back." forms → one entry
def test_no_check_model_offers_nothing():     # cf=None → []
def test_password_fields_are_secret():        # Welcome back.: Email secret False, Password secret True; kid: Your login ID False, Passcode True
```

- [ ] **Step 2:** `uv run pytest tests/test_login_forms.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** Same command. Expected: PASS.
- [ ] **Step 5: Commit** "Sign-in forms are found live and told from sign-up forms by Clef".

### Task 4: Signing in

**Files:**
- Create: `src/jev_demofast/login/sign_in.py`
- Test: `tests/test_login_sign_in.py`

**Interfaces:**
- Consumes: `forms` dicts (Task 3), answers (Task 2), `Session.act(e, "fill", text)` for non-secret fields, and
  `Session.type_secret_into_password` or a focused `Input.insertText` for secret ones.
- Produces: `sign_in(s, origin, form, values, ask=None, log=print) -> str`. It returns one of:
  - `"signed in"`;
  - `"failed: <reason without values>"`;
  - `"stuck: <page>"`, when it lands on a page whose every button is a hazard, e.g. K-12's card check.

  Steps:
  1. Open `form["page"]`.
  2. Fill each field by its label.
  3. Click the submit: the enabled button matching `sign in|log in|continue`, preferring the last such on the page.
  4. Wait.
  5. Success means no visible password field and no visible text matching
     `incorrect|invalid|wrong|doesn't match|try again`.
  6. On an error, `ask` again with `retry` = the visible error line, once.
  7. A code page (one short field and text matching `code|verify`) asks a code question through `ask`.

- [ ] **Step 1: Write the failing tests**

```python
def test_signs_in_and_leaves_the_form():
def test_secret_values_never_go_through_act():   # the fake records act() texts: no password among them
def test_a_wrong_password_asks_once_more_then_fails():
def test_a_code_step_asks_for_the_code():
def test_landing_on_a_hazard_page_is_reported(): # lands on /setup/verify with only "Verify card" → "stuck: /setup/verify"
def test_the_result_never_contains_a_value():
```

- [ ] **Step 2:** `uv run pytest tests/test_login_sign_in.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** Same command. Expected: PASS.
- [ ] **Step 5: Commit** "Signing in: fields by label, secrets never observed, one retry, the code step".

### Task 5: `--login` end to end

**Files:**
- Modify: `src/jev_demofast/login/__init__.py`, `src/jev_demofast/cli.py` (flags, `choose_browser`, `cmd_demo`,
  `cmd_run`, and `site_map`'s stale "a Flutter app can't be mapped" message), `src/jev_demofast/drive/jev_drive.py`
  (`run` gets `session=Session`, as `tour.run` has)
- Test: `tests/test_login_flow.py`

**Interfaces:**
- Produces:
  - `class Login`, holding the form and its values privately;
  - `Login.prepare(cf, url, index, ask, log) -> Login | None`. It opens an isolated explore session, finds the
    forms, asks, signs in, and returns None on skip or failure (logging `login: …`).
  - `Login.session(url, fresh=False, isolated=True) -> Session`, a factory with the signature both `explore()` and
    `tour.run()` call. It makes a new isolated `Session`, signs in, sets `hazards=True` and `own_email`, and raises
    `RuntimeError("login: couldn't sign in for the recording")` if sign-in fails.
  - `Login.forget()`.
- CLI:
  - new flags `--login` and `--login-via {terminal,stdin}` (default `terminal`);
  - `--login` with `--use-my-browser` → `SystemExit`;
  - the logged-in map is written to `<work>/site-map-logged-in.json`, never under `MAPS`;
  - the script and the run use that map; the run passes `session=login.session`;
  - `login.forget()` runs in a `finally`.

- [ ] **Step 1: Write the failing tests**

```python
def test_login_with_use_my_browser_is_refused():
def test_without_login_nothing_changes(monkeypatch):     # cmd_demo never imports or calls login
def test_the_logged_in_map_is_not_cached(tmp_path, monkeypatch):   # MAPS gets no new file; <work>/site-map-logged-in.json exists
def test_recording_uses_a_signed_in_isolated_session(): # the session factory passed to tour.run makes isolated sessions with hazards on
def test_a_failed_sign_in_at_recording_stops_the_run(): # factory raises → run reports it, no frames recorded
def test_no_credential_in_any_written_file_or_log(tmp_path, capsys):   # a fake end-to-end run with password "pw-Zq81-unique"; also a sign-in that raises: grep work dir, MAPS and captured output → absent
def test_a_skip_runs_as_today():
```

- [ ] **Step 2:** `uv run pytest tests/test_login_flow.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** "--login: ask at the login wall, map and record signed in, keep nothing".

### Task 6: Verify live (the founder types the account)

The agent never types the account. The founder runs the command and answers the prompt.

- [ ] **Step 1:** The agent runs `uv run pytest -q` and the regression check from the Flutter plan (onecentdemo.com
  without `--login`, same map as `main`).
- [ ] **Step 2: The founder runs** (with `!` in the session, so the prompt reaches them):
  `uv run jev-demofast demo "Show parents how easy it is to add a student and set up their account" --url https://k12.tutorq.ai/ --login --fresh --voice chris --out /tmp/k12-parent.mp4`.
  The founder picks "Welcome back." and types the parent demo account.
  Expected: `login: signed in`, a logged-in map in the work folder, and `verified: True`, or a clear
  "the demo stops here" at a payment step.
- [ ] **Step 3: The agent checks:**
  - the first frame is signed in;
  - `grep -r` over the work folder and `~/.cache/jev-demofast` for the password the founder names (or the founder runs
    the grep) finds nothing;
  - the Chrome profile has no k12 session.
- [ ] **Step 4:** Open the PR (the founder merges). The hosted app's checkbox and modal follow in the private repo.
