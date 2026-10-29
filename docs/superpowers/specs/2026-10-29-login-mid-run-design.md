# Logging in mid-run: the founder gives a demo account when the run asks

Status: design, for review · 29 October 2026

## Why

A product's best screens are usually behind its login. Today the tool tours what a visitor can see and ends the
script on "what signing up opens". The founder wants the demo to go inside: when the product has a login, the run
asks for a demo account, signs in off camera, and records the logged-in app.

**Who it's for:** a founder recording their own product with a demo account they control.

**First target:** TutorQ K-12 (k12.tutorq.ai), signed in as a **parent**. Flutter support (merged 29 October, PR #28)
already maps its public pages and marks its sign-in forms.

## Decisions made with the founder

- **The founder says up front whether the product has a login** (a flag on the CLI, a checkbox in the hosted app).
  No guessing: without it, runs behave exactly as today.
- **The run asks mid-run, not up front,** once it has mapped the public pages and knows the sign-in forms and their
  fields.
- **When there is more than one sign-in form, the founder chooses.** K-12 has a parent/student form ("Welcome back.":
  Email, Password) and a child form ("Sign in to your subjects": Your login ID, Passcode).
- **First test: a K-12 parent account.**
- **A logged-in demo does what a real user does** (the founder, 29 October): a parent adds a student and sets up
  their account; a child browses subjects, has a conversation with the tutor about a concept, and checks their
  schedule. So the logged-in run may type, save and send in the demo account. Only the hazards below stay blocked.

## Goals

1. `--login` (CLI) asks for a demo account when the run has mapped the public site and found at least one sign-in
   form, then signs in and maps the logged-in pages too, and records the demo signed in.
2. **One question, any host.** The tool asks through a small channel that works in a terminal (prompts, password
   hidden) and for a host process (the hosted app answers through stdin). See "The question channel".
3. **The answer is never kept.** It's held in memory for the run, used to sign in, and never written to a log, the
   map, `actions.json`, `replay.json`, the decisions log, a frame or any file.
4. **The demo opens already signed in.** Signing in is off camera. The script can say "once you sign in…".
5. **The logged-in demo acts like a user, within hard limits.** Exploring stays read-only (it only maps). The
   recorded demo may type, save, add and send to show a workflow. It never pays, deletes, logs out, changes the
   account's sign-in details, or sends anything to someone outside the account (see "Safety once signed in").

## Non-goals

- Guessing whether a login is needed (the founder says so).
- "Sign in with Google/Apple/Microsoft" and other third-party sign-in. If the only way in is one of those, the
  question says so and the run continues logged out.
- CAPTCHAs: never worked around. A sign-in that shows one fails, and the run continues logged out.
- Creating accounts. Sign-up forms are never offered and never submitted.
- Showing the sign-in step on camera.
- Reusing a logged-in map across runs (see "Caching").

## Anti-goals

- A credential in any file, log line, frame, cache or model prompt.
- A logged-in run that pays, deletes, or reaches outside the demo account: no payment, card or billing step, no
  delete or remove, no log out, no change to the account's email or password, and no invite or share sent to an
  address.
- A demo that claims to be logged in when sign-in failed. A failed sign-in says so in the log and the run carries on
  logged out, as today.

## Design

### Flow (with `--login`)

1. **Map the public site** as today. The map marks sign-in forms (`sign_in: true`).
2. **Pick the forms to offer.** The cached public map is reused, but its sign-in pages are reopened live: the map
   doesn't hold password fields (the snapshot skips them) or a submit button that's disabled while the form is
   empty. Then:
   - **Sign-in, not sign-up, is Clef's call** from the screenshot, `cf.yes` as in `explore/buttons.py`, kept only at
     ≥ `SIGNS_IN_CONFIDENT = 0.8`. The question:
     > Is this a form for signing in to an account that already exists (not for creating a new account, and not a
     > later step of making one)?

     with `true` = "yes: it signs in to an existing account", `false` = "no: it creates an account or is a step of
     making one", and the state `{url, fields, buttons, visible_text}`. **Measured on K-12 (29 October, 3 runs each,
     the same score every run):**

     | Page | Truth | Score |
     |---|---|---|
     | `/setup/account?mode=signin` | sign-in | 0.95 |
     | `/setup/account?as=student&mode=signin` | sign-in | 0.97 |
     | `/setup/kid` | sign-in | 0.90 |
     | `/setup/account` | sign-up | 0.01 |
     | `/setup/account?mode=new` | sign-up | 0.01 |
     | `/setup/account?as=student` | sign-up | 0.01 |

     No check model that reads images means no form is offered (`login: can't tell sign-in forms apart without the
     check model`), and the run continues logged out.
   - **One entry per distinct form,** keyed by its title and its field labels. The title is the form page's first
     text line that isn't on every sign-in page: "TutorQ K-12" heads every K-12 page, so the title is "Welcome
     back.". K-12's parent and student "Welcome back." forms have the same title and fields, so they're offered once.
   - If no form is left, log `login: no sign-in form found` and continue logged out.
3. **Ask** (the question channel), with the forms. The founder picks one and fills its fields, or skips.
4. **Sign in** in the explore session:
   - type into the chosen form's fields;
   - a field whose label or type says password goes through `Session.type_secret_into_password`, never through
     observation or the recorder;
   - submit with the form's submit button (the one Clef scored as *not* navigating, or the only enabled button
     matching "sign in" / "log in" / "continue").
5. **Check it worked:** the page left the sign-in form (no visible password field) and isn't showing an error. If
   it's still on the form, or text such as "incorrect" / "invalid" appears, ask again once ("That didn't work: …"),
   then give up and continue logged out.
   - **If a code is asked for next** (a page with one short field and words such as "code" / "verify"), ask a
     second question for the code. The code expires on the site's own timer.
6. **Map again, logged in,** from where sign-in landed. This uses the same explorer, which stays read-only (it only
   maps), with the hazards below.
7. **Script and record from the logged-in map only.** The video opens signed in, so public pages aren't shots. The
   founder's script and the shot list get the logged-in map. The recording runs in a **new isolated browser
   context**, not the persistent profile, so the session cookie is thrown away with it. It signs in there, off
   camera, before the recorder takes its first frame. `--login` can't be combined with `--use-my-browser`.
8. **End of run:** the answer is dropped (the variable is cleared and nothing else holds it).

### The question channel

The tool asks with `ask(question) -> answer | None`. Two implementations, chosen by `--login-via`:

- `terminal` (default): prints the form choices, reads the choice and non-secret fields with `input()`, and reads
  secret fields with `getpass`.
- `stdin`, for a host process:
  - the tool writes one log line `ask: {json}` (the question, no secrets) and reads one JSON line from stdin, with a
    timeout (`ASK_TIMEOUT_S = 300`); no answer means skip;
  - the host shows the question and writes the answer line into the process's stdin;
  - the answer is never echoed.

The question:

```json
{"id": "q1", "why": "Part of this site is behind a login. Which sign-in should the demo use?",
 "forms": [{"id": "f1", "title": "Welcome back.", "page": "/setup/account?mode=signin",
            "fields": [{"name": "email", "label": "Email", "secret": false},
                       {"name": "password", "label": "Password", "secret": true}]},
           {"id": "f2", "title": "Sign in to your subjects", "page": "/setup/kid",
            "fields": [{"name": "login", "label": "Your login ID", "secret": false},
                       {"name": "passcode", "label": "Passcode", "secret": true}]}],
 "retry": null}
```

The answer: `{"id": "q1", "form": "f1", "values": {"email": "…", "password": "…"}}` or `{"id": "q1", "skip": true}`.

A code question has one form with one field (`{"label": "Code", "secret": false}`).

**Which fields are secret:** `type=password` inputs, and labels matching `guards.PASSWORD_NAME` (pass, pin, code,
passcode, …).

### Safety once signed in

- **Exploring (mapping) stays read-only,** logged in or not: discovery never clicks `guards.blocked` or
  `guards.CHANGES` labels, never types, and asks Clef on pages with fields, as today.
- **The recorded demo may act like a user:** type into fields, choose options, and click save, add, create, send,
  submit, continue and next, as the brief's task needs ("add a student and set up their account", "ask the tutor
  about fractions").
- **Never clicked by anything, in a `--login` run** (a new `guards.LOGGED_IN_HAZARDS`, checked with the label and
  the page's visible text around it):
  - money: pay, payment, purchase, buy, checkout, subscribe, upgrade, billing, card, "verify you are the parent";
  - loss: delete, remove, cancel subscription, close account;
  - leaving: log out, sign out;
  - the account itself: change email, change password, reset password;
  - reaching outside: invite, share, "send to", and any field asking for an email address other than the demo
    account's own.

  The same "unless the brief names it" rule as `guards.blocked` does **not** apply here: a brief can't unlock these.
- **Off-site:** a click that leads to another host (K-12's Stripe) ends that step, as discovery already does.
- **If a workflow needs a blocked step,** the demo stops there and says so ("the next step is a payment; the demo
  stops here"). For example, if adding a K-12 student needs a card or a price confirmation, the video shows
  everything up to that step.

### What the founder should know

- **Each logged-in run adds data to the demo account** (another student, another conversation). Cleaning it up is
  the founder's job. Use an account made for demos.
- **The video shows what the account shows:** names, the email on the dashboard. Text read from logged-in pages also
  goes to the script model, as page text always does. What's never kept is what the founder *typed* to sign in.

## Caching

The explorer caches maps per site (`~/.cache/jev-demofast/maps/<host>.json`), and the hosted container shares that
cache across users. **A logged-in map is never written to the shared cache:** it holds the founder's own data (their
children's names on K-12). It lives in the run's work folder, and the run's public map is cached as today.

### What the hosted app needs (private repo; its own short spec)

A "This product has a login" checkbox that adds `--login --login-via stdin`; the run's status exposing the latest
`ask:` question; a modal; `POST /runs/<id>/answer` through the Worker to the container, which writes the line into the
process's stdin. This design only fixes the protocol the app must speak.

## How we'll know it works

- **K-12 parent, CLI:**
  `jev-demofast demo "Show parents how TutorQ K-12 shows them their child's progress" --url https://k12.tutorq.ai/ --login --fresh --voice chris`.
  - The terminal offers "Welcome back." and "Sign in to your subjects". The founder picks the first and types a
    parent demo account.
  - The run maps logged-in pages and records the demo signed in, `verified: True`.
  - The video's first frame is already signed in.
- **Nothing kept:** after the run, `grep -r` for the demo password, and for the email as typed into the form, over
  the work folder, the map cache and the log finds the password nowhere. The email appears only where the
  dashboard itself shows it. A test does the same with a fake run. The persistent Chrome profile has no K-12
  session afterwards.
- **Wrong password:** one retry prompt, then "login: couldn't sign in; continuing logged out", and the demo is made
  as today.
- **Skip:** the same as running without `--login`.
- **Tests (no network):**
  - picking forms: K-12's map gives two forms, and the sign-up pages and duplicates are dropped;
  - the question JSON's shape;
  - the stdin channel: answer, skip, timeout and garbage, where garbage counts as skip;
  - sign-in success, wrong password then retry, and the code step;
  - the logged-in hazards are never clicked, even when the brief names them;
  - a demo step that needs a blocked step stops there and says so;
  - the recording uses an isolated context with `--login`, and `--login --use-my-browser` is refused;
  - a logged-in map isn't cached;
  - no credential in any written file.

## Left to the builder

- Where `ask` and the sign-in step live (a `login/` package is expected).
- How the submit button is found when Clef isn't available (the "sign in"/"log in"/"continue" label rule above).
- Polling and timeouts beyond `ASK_TIMEOUT_S`.
- The exact wording of log lines, as long as no secret appears.

## Prerequisite (the founder's)

A K-12 **parent demo account** that is fully set up (card check done, at least one child), so signing in lands on the
family dashboard and not on the card-check step. The tool never does the card check.
