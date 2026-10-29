# Flutter web support: map and record sites drawn by Flutter

Status: design, for review · 29 October 2026

## Why

The next feature is logging in mid-run: when a demo reaches a login wall, the founder is asked for a demo account
and the recorder signs in and carries on (a separate design, after this one). Its first target is TutorQ K-12,
k12.tutorq.ai, which is a **Flutter web app**. Today jev-demofast can't see a Flutter app at all, so Flutter support
comes first.

**Who it's for:** a founder whose product is a Flutter web app, recording a demo of it the same way as any other site.

## What is there today (recon, 29 October, k12.tutorq.ai)

Measured with the tool's own `Session`, page reader and click, in its isolated Chrome:

| | Before Flutter's accessibility layer is on | After |
|---|---|---|
| Page text (`HAS_CONTENT_JS`, snapshot text) | empty, 0 characters | 232 characters |
| Observed actions | none | 4 buttons: "Sign in", "I'm a parent…", "I'm a student…", "Sign in" |
| Links (`VISIBLE_LINKS_JS`) | 0 | **0** |
| Headings (`HEADINGS_JS`) | none | **none** |
| `document.documentElement.scrollHeight` | 780 (= the window) | 780 |

- Flutter draws the page on its own surface. The DOM has a `flt-semantics-placeholder` element; clicking it
  (`element.click()` from JavaScript works) turns on Flutter's accessibility layer, a tree of `flt-semantics` nodes
  with `role="button"`, `role="group"`, text and real `<input>` elements for text fields.
- With that layer on, the tool's existing reader (`browser/snapshot.js`) and click (`Session.act`, which sends real
  mouse events through CDP) work unchanged: clicking "Sign in" went to `/setup/account?mode=signin`,
  `wait_for_page()` returned "settled", and the page then had an `Email` textbox and a `type=password` input, so
  `SIGN_IN_FORM_JS` was true.
- A JavaScript `.click()` on a `flt-semantics` button does **not** navigate. Only real mouse events do. (The tool
  already clicks that way; nothing new is needed, but no new code may click Flutter nodes from JavaScript.)
- Flutter navigates with buttons, not `<a href>` links, so the explorer, which discovers pages by following links,
  would map one page and stop.
- **Opening a page by its address shows the same screen as clicking to it** (checked for `/setup/account?mode=signin`,
  `/setup/account?mode=signup`, `/setup/account`, `/setup/student`, `/setup/kid`). So the explorer can visit and
  return to button-found pages with `Page.navigate`. A logged-out `/today` is moved to `/setup/who`.
- **The query string matters:** `?mode=signin` ("Welcome back.") and `?mode=signup` (the new-account steps) are
  different screens.
- `/setup/kid` (a child's login ID and passcode) has an **enabled** "Sign in" button that submits the form.
- The K-12 web app's addresses are listed in its source, `tutorq_campus/lib/k12/web/router.dart` (`/setup/who`,
  `/setup/account`, `/setup/student`, `/setup/kid`, `/today`, `/tutor`, …). The explorer must not depend on source
  code; it's mentioned here only as a way to check what the explorer found.

## Goals

1. **See a Flutter page.** On any page that uses Flutter, turn on its accessibility layer before reading it, and
   again after every new document load (a reload or a full navigation resets it). In-app navigation keeps it on.
2. **Find pages reached by buttons.** On a Flutter page, the explorer discovers where each safe button leads (see
   "Safety") and records it in the map as a link (`{"label": <button label>, "to": <path>}`), so the rest of the
   pipeline (shot list, tour, founder's script) treats it like any other link.
3. **Give the founder's script something true to say.** When a page has no `h1`–`h3`, the map's `texts` come from
   the accessibility layer's visible text, with the same visibility rules and caps as headings.
4. **Record it.** A demo of k12.tutorq.ai (logged out) maps, writes a script and records with real clicks, ending
   `verified: True`, e.g. "Show students how they get into TutorQ K-12" going `/setup/who` → "I'm a student" →
   `/setup/student` ("How do you get in?"). It ends on a page that isn't a sign-in form, because
   `shots.offerable` leaves sign-in pages out on purpose, and this design doesn't change that.

## Non-goals (this design)

- **Logging in.** The next design. This one only has to get the explorer and recorder to the login wall and
  recognise it, which today's check already does once the page is readable.
- **Scrolling inside Flutter.** Flutter pages scroll inside their own surface, not the document, so
  `window.scrollBy` does nothing. The K-12 setup pages fit the window (scrollHeight 780 at a 780 px window), so v1
  doesn't need it. A long Flutter page shows its top only. Recorded as a known gap.
- Flutter apps that turn their accessibility layer off, or native (non-web) Flutter apps.
- Typing into Flutter fields during exploring (the explorer never types, as today).

## Anti-goals

- **Never click anything that changes data while discovering.** Exploring "only navigates, opens menus and reads; it
  never submits, signs up or types". Discovering by clicking buttons must keep that promise.
- Never fake a page: a button whose destination couldn't be confirmed is left out of the map, not guessed.
- No slowdown for ordinary sites: Flutter handling runs only when the page is a Flutter page.

## Design

### Detecting Flutter and turning on its accessibility layer

- A page is a Flutter page when it has a `flutter-view` or `flt-glass-pane` element (both seen on k12.tutorq.ai).
- Turning it on: click `flt-semantics-placeholder` from JavaScript, then wait for `flt-semantics` nodes to appear
  (poll, capped; about 1.5 s was enough on k12.tutorq.ai).
- Where it runs: wherever the tool waits for a page before reading it, so the explorer, the tour, the shot list's
  page reads and the recorder all see the same page. `_wait_for_content` already waits up to 10 s for text that a
  Flutter page never shows on its own. The builder decides the exact place (`Session.wait_loaded`, `observe`, or
  both), as long as goal 1 holds after reloads and full navigations.

### Discovering pages behind buttons (Flutter pages only)

For each page the explorer visits, after reading it:

1. Take its buttons that pass the safety filter.
2. For each, click it (`Session.act`), wait (`wait_for_page`), and read where it landed.
   - Landed on another on-site address: record `{"label", "to"}` and queue that path for a visit, as a followed
     link would be.
   - Same address (a toggle, a dialog, "Show password"): no link. Close anything it opened by going back to the
     page (next step).
3. Return to the page before the next button: navigate to its address and turn the accessibility layer on again.
   Don't rely on the browser's Back: Flutter's history may not match.

**Button-found pages are their own routes, query included.** `explore/templates.py` groups link-found paths that
differ in one segment (`/setup/who`, `/setup/account`, `/setup/student` would become `/setup/:handle`), and the
link reader keeps only the path. Grouped, the account step's password field would mark the whole route `sign_in`,
and `shots.offerable` would drop every K-12 page. So a path found through a button keeps its query string and is
never grouped. Link-found paths are grouped as today, so other sites' maps don't change. (Decision made while
writing the spec. If wrong, the cost is K-12 pages that could have been grouped.)

Discovery counts against the explorer's existing limits (`max_pages`, `max_minutes`). Buttons with the same label on
the same page are tried once (K-12's "Who is this?" page has two "Sign in" buttons, both going to the same place).

### Safety: which buttons discovery may click

A button is clicked during discovery only if **all** of these hold:

- `guards.blocked(label)` is false (sign up, register, create account, delete, log out, Google/Apple sign-in…).
- `guards.CHANGES` doesn't match the label (save, submit, send, pay, confirm, verify…).
- **On a page with a text or password field, Clef must say it only navigates.** Flutter's accessibility layer has
  no `<form>`, so the code can't tell a form's submit button from a navigation button. The check model (Clef,
  `cf.yes` with the screenshot, as `drive/check.py` uses it) is asked per button, and the button is clicked only if
  the score is at least **0.8** (`NAVIGATES_CONFIDENT`). A lower score, an error, a timeout, or a check model that
  can't read images means no click. Pages without fields don't need the check.

  The question, as measured:
  > A visitor is on this page and has typed nothing into its fields. Does clicking the button named in 'button' only
  > take them to another page or step (navigation such as Back, or a link to a different form), without sending this
  > page's form or signing in?

  with `true` = "yes: it only navigates", `false` = "no: it sends the form, signs in, or changes something", and the
  state `{url, button, fields_on_page, buttons_on_page, visible_text}`.

  **Measured on k12.tutorq.ai (29 October, 3 runs each, the same score every run, 0.4–0.9 s per call):**

  | Page | Button | Score | Truth |
  |---|---|---|---|
  | `/setup/account?mode=signin` | I need an account | 0.93 | navigates |
  | `/setup/account?mode=signin` | Back | 0.98 | navigates |
  | `/setup/account?mode=signup` | I already have one | 0.95 | navigates |
  | `/setup/account?mode=signup` | Back | 0.98 | navigates |
  | `/setup/kid` | Back | 0.98 | navigates |
  | `/setup/account?mode=signin` | Show password | 0.09 | stays (a toggle) |
  | `/setup/account?mode=signin` | Sign in | 0.03 | submits |
  | `/setup/kid` | Sign in | 0.02 | submits |

  0.8 sits in the gap (0.09 to 0.93). It's one site and eight buttons, so the floor is set on the safe side: a miss
  costs a link, a wrong pass an empty form sent (the explorer never types, so a submit carries no data, but it must
  still not happen).

Expected on K-12: on `/setup/who`, "I'm a parent", "I'm a student" and both "Sign in" buttons are clicked (no fields,
no check). On `/setup/student`, "Back", "My parent gave me a login" and "I'm setting it up myself". On the account
pages, "Back", "I need an account" and "I already have one", after Clef. On `/setup/kid`, "Back" only. Its "Sign in"
scores 0.02 and is never clicked.

### The login wall on a Flutter app

A logged-out visitor to a K-12 app page (`/today`) is moved to `/setup/who` ("Who is this?"), which has no password
field, so `_sent_to_sign_in` won't call it a wall. This design doesn't change that. The explorer only reaches app
pages through buttons, and logged out it can't. Recognising the wall is part of the login design.

## How we'll know it works

- **k12.tutorq.ai, logged out:** the map has `/setup/who` with links found by buttons to
  `/setup/account?mode=signin`, `/setup/account?mode=signup` (or `/setup/account`) and `/setup/student`; and
  `/setup/student` with a link to `/setup/kid`. Each is its own entry, and the account pages and `/setup/kid` are
  marked `sign_in`. A demo
  with the brief in goal 4 records and verifies, with real clicks on camera.
- **No change elsewhere:** a non-Flutter site's map is identical before and after (the tests' fake sites, and one
  real run each on onecentdemo.com and selvage.run).
- **Tests** (no network), in the style of `tests/test_explore_crawl.py`'s fake pages:
  - a fake Flutter page with no text until the placeholder is clicked is read after turning on accessibility;
  - discovery records a button's destination as a link and queues it;
  - a blocked or data-changing button is never clicked;
  - on a page with a text or password field, a button is clicked only when the (faked) check scores ≥ 0.8, and never
    when the check errors, times out or can't read images;
  - a button-found path keeps its query and isn't grouped with its neighbours, while link-found paths group as before;
  - a button that stays on the same address adds no link;
  - the layer is turned on again after a reload.

## Left to the builder

- Where exactly the "turn on accessibility" step lives (session, explorer or both), its polling interval and cap.
- How the fake Flutter pages are built in tests.
- Whether discovered links carry a marker that they came from a button (only if the tour needs it to click them).
- Whether `texts` for Flutter pages come from `flt-semantics` nodes or from the snapshot's text.
