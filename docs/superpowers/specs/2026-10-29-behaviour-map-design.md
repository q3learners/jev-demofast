# The behaviour map: mapping learns what the product does, not just which pages it has

Status: design, for review · 29 October 2026

## Why

The founder (29 October): "the whole logic or the brain depends on how we build the initial mapping … If you
understand different buttons, different pages, the flow, everything, then only you can build the demo." And: "It is
not that the user has to come and tell, okay, do this, do that step … then it's no different than the regular way."

Today's map records pages and the labels on them. For K-12 signed in, it recorded one page, `/setup/kids`, with the
buttons "Add" and "Continue" and the fields "First name" and "Age". It didn't know what either button does. So the
script step guessed, and the recording ran into a surprise on camera. In the live run of 29 October, "Continue" with a
typed name opened "Add Maya first? Skip / Add", and the demo stopped there. Every new situation (a wizard, a dialog, a
card check) became a special case in the driver.

**The decision:** mapping uses the product the way a person would, off camera and ahead of time. It opens every
section, presses the buttons, follows dialogs and wizards to their end, and writes down what happened. The story and
the recording then choose from paths that mapping has already proven work.

**First target:** TutorQ K-12 (k12.tutorq.ai), signed in as a parent.

## The demo this has to make possible (the founder's, 29 October)

1. The public home page, signed out.
2. Click "Parent login" and sign in.
3. Show the signed-in app's tabs.
4. Come back, add a kid, and set up the kid's account.

The founder: "if we don't explore each tab, how will we know what story to tell? … it's our job to explore the
pages." Exploring everything is mapping's job. The demo shows a selection.

## Decisions made with the founder

- **Mapping may create data in the demo account** ("it's a demo account, it can create data"). It presses Add, saves
  forms with made-up values and walks wizards through, within the safety rules. This replaces the login spec's
  "exploring stays read-only" for logged-in runs.
- **10–20 minutes for a first map is fine, because the map is reused.** Later demos for the same product start from it.
- **The map is persistent and keeps learning** (the founder: "we need a persistent map … so this map gets updated
  with new learnings, so we don't have to redo this every time"). Every run starts from the saved map and adds to it.
  It never starts from nothing unless the founder asks for that.
- **One-time account steps are seen, not finished.** Per-kid steps (a new kid's login and subjects) repeat, because
  mapping adds a new kid each time, so they're walked to the end. A step that happens once per account (K-12's setup
  wizard) is walked up to its last forward click and recorded as "seen, not finished". *(The founder said "yes" to
  this suggestion.)*
- **When the account can't support the demo, the run asks the founder how to proceed** (the founder: "let's ask the
  user how he want to proceed"). It goes through the same question channel as the login question (see "When the
  account can't support the demo").
- **Maps need persistent storage:** locally in the map cache, and per user in the hosted app (its own spec).
- **The founder's input stays what it is today:** a sentence, the URL, `--login`, and the demo account when asked.
  The founder never lists steps. *(My call: the founder didn't ask for a separate input.)*

## Goals

1. **Screens, not just pages.** A dialog, a wizard step and a tab are screens, as well as URLs.
2. **Actions with outcomes.** For each control mapping tries, the map records what happened. It went to a screen,
   opened a dialog, added an item to a list, changed nothing visible, or was refused (a hazard label, a money step,
   off-site).
3. **Jobs.** The product's main tasks as proven paths: named ("Add a kid"), with their steps, their result ("Maya
   appears in the kids list"), whether they can be repeated, and what the account must look like for them to work.
4. **The account's state.** The map says where the account is, for example "partway through setup: Your kids" or
   "set up: Home, Kids, Subjects, Schedule, Settings". A demo the account can't support is caught before
   recording, and the founder is asked how to proceed. It's not discovered on camera.
5. **Persistent and learning.** A later run of the same product and account starts from the saved map. It maps only
   what's new or changed (a new section, a screen that looks different, a job whose result no longer appears) and
   writes what it learned back. `--fresh-map` starts from nothing.

## Non-goals (each is its own spec, after this one)

- **Writing the story from the behaviour map** (choosing tabs and jobs for an audience). This spec delivers the map
  and a readable summary of it. The story step then uses it.
- **Recording from proven paths** (replacing `drive_goal`'s one-task loop).
- **Signing in on camera.** The login spec keeps it off camera on purpose. Showing it, with the password masked, is
  a separate decision.
- **Record first, narrate after.** That would reverse the voice-led approach the founder approved. It needs its own
  conversation.
- Public, logged-out sites. They keep today's map. The behaviour map is for `--login` runs first.

## Anti-goals

- Mapping that pays, deletes, logs out, changes sign-in details or reaches outside the account. Every rule from the
  login branch applies unchanged: hazard labels, the screen-judged money check before every click (`drive/money.py`),
  only the account's own email, never off-site.
- A credential in the map. The map holds what the demo account shows, never what was typed to sign in.
- A map that claims a job works when mapping never saw it finish.
- Endless exploring. Budgets stop it (see "How mapping works").

## What the map holds

One file per product and account (see "Where it lives"). In outline:

```
account: {state: "set up" | "partway: <step name>", sections: ["Home", "Kids", ...]}
screens: {
  "<screen key>": {kind: page | tab | dialog | wizard-step, title, url, texts, fields, controls: [...]}
}
actions: [
  {screen, control, did: "click" | "fill+submit" | "choose", values?: {...},
   outcome: "→ <screen key>" | "dialog <screen key>" | "added '<item>' to <list>" | "no change" |
            "refused: <why>", tried_at}
]
jobs: [
  {name: "Add a kid", steps: [<action refs>], result: "Maya (14) appears in Your kids",
   repeatable: true | false, needs: "account set up" | "partway: Your kids" | ..., proven: true}
]
```

- **The screen key** is stable across visits: the URL path with Flutter's `#/route`, plus a dialog's or wizard step's
  title. ("/setup/kids" and "/setup/kids · dialog: Add Maya first?" are two screens.) Item-specific parts of a URL
  (an id) are grouped the way `templates` groups them today.
- **Values typed by mapping** are made up by the model to fit the field ("Maya", "14"). They're kept in the action,
  so the recording can type the same values or new ones. They're never the founder's own data, and never an email
  other than the account's own.
- **A dialog with two ways forward** ("Skip / Add"): mapping presses the one the model judges moves the task forward,
  and records the other as seen but not pressed.
- **One-shot paths:** a setup wizard runs once per account. Mapping records it as `repeatable: false`, and the
  recording knows it needs a fresh account to show it again.

## How mapping works

1. **Public pages first,** as today (the public map is unchanged and stays cached as today).
2. **Sign in** (the login branch's flow), then read the account's state from the first signed-in screen.
3. **Sections:** find the always-visible navigation (tabs, a sidebar, a bottom bar) and visit each section.
4. **On each screen,** try its controls in order of what a person would try, one at a time. Before each click, the
   safety rules apply. After each, observe what changed and record the outcome. Then go back to the screen the
   action started from: back, the section's tab, or reopening its address. If the way back is lost, start the
   section again.
5. **Forms:** fill with made-up values, submit, and record the outcome. A form whose result is visible (an item in a
   list) becomes a job candidate.
6. **Dialogs and wizards:** followed to their end. A wizard's steps form one job.
7. **Jobs:** the model names the paths that ended in a visible result, in the product's own words where it can
   ("Add a kid", not "Click Add").
8. **Budgets:** a total time (default 20 minutes), a step limit per section, and a limit on how many items in one list
   are opened (one or two subjects, not all forty). When a budget runs out, mapping stops, the map says what was
   left, and the run continues.

## Where it lives (this reverses a login-branch decision, at the founder's request)

The login branch made the logged-in map **never cached** because it holds the account's own data. The founder now
wants it reused.

*My call:* the behaviour map is saved in the local map cache (`~/.cache/jev-demofast/maps/`), keyed by site **and**
account (a hash of the account's email, never the email itself). It holds only what the demo account shows and what
mapping typed. It never holds the password or a code. `--fresh-map` maps again. The hosted app will store it per user;
that's a separate spec.

## How it's used (only enough to prove the map is useful)

- A **readable summary** printed at the end of mapping: the account's state, its sections, and its jobs with steps,
  so the founder can check the map at a glance.
- The existing story step receives the jobs and sections alongside today's pages. Rewriting the story step is the
  next spec.
- **Account-state check:** when the sentence needs something the account can't do, the run asks the founder how to
  proceed before recording (see "When the account can't support the demo").

## Testing

- **A fake multi-screen app** (local HTML, no network) is a plan deliverable. It has tabs, a list with Add, a form, a
  three-step wizard, an "Add X first? Skip / Add" dialog, a gated step (a card form) and a Delete button. Mapping it
  must produce the expected screens, outcomes and jobs, press nothing gated, and stay within budget.
- **Flutter:** the same checks against a Flutter-shaped fixture (semantics nodes), because K-12 is Flutter. How
  Flutter web exposes a `showDialog` in its semantics tree must be verified first (see "For the builder").
- **Live, run by the founder** in their own terminal, because I don't sign in to the live site. The success criteria
  for K-12 with a set-up parent account:
  - the map lists the app's sections;
  - it has an "add a kid" job whose steps include the name, the age, Add and the "Add … first?" dialog when it appears;
  - it marks the card check as refused;
  - it reports the state of an account that is partway through setup.

## Calls made after the builder check (my calls; the founder can overturn any of them)

- **One file, both views.** The behaviour map is the logged-in map: the route entries the current story, shot checks
  and driver read stay as they are, and the new `account`, `screens`, `actions` and `jobs` keys sit beside them. The
  new crawl plugs in where `with_login` calls `explore()` today. It's a new module next to `explore/`, which keeps
  mapping public sites as it does now.
- **Only adding, never changing what's there.** Mapping may press Add or Create, submit new forms, and walk steps for
  things it created itself, such as a new kid's login and subjects. It never flips a switch or a setting, and never
  edits or saves an item it didn't create: it opens Settings and reads it. As today, toggles and change labels on
  existing items (`guards.CHANGES`, `TOGGLES`) are skipped, except on items mapping created in this run.
- **When a job counts as proven.** A job is proven when its visible result appears, for example Maya in the kids list.
  One sighting is enough. A path cut short by a refusal is kept as a partial job that records where it stopped and
  why ("refused: card check").
- **On reuse, the account's state is read again.** Recording signs in anyway, so the first signed-in screen is read and
  compared with the saved state. Where it differs, only the affected sections are mapped again and merged in. Each
  entry keeps when it was last seen, and an entry that mapping looks for and can't find is marked gone, not deleted.
  Each job's `needs` is checked against the state just read.
- **No logged-in cache in the hosted app yet.** Under `--login-via stdin` the behaviour map stays in the run's work
  folder, as the login branch does today, until the hosted storage spec exists. Locally, the cache key is a keyed
  hash of the account's email, using a secret created once in the cache folder, so it can't be recomputed from a
  guessed email.
- **Matching the sentence to jobs** is a model choice over the map's jobs. Below the `CONFIDENT` threshold, the run
  says it found no job for the sentence and carries on as today.

## When the account can't support the demo

After mapping and before recording, if the jobs the sentence needs don't match the account's state (adding a kid
from inside the app while the account is partway through setup), the run asks the founder through the question
channel: what's missing (in the product's words, for example "finish setup and the card check, or add only kids aged
13+"), and the choices:

1. **Record what this account can show.** The story uses only the jobs whose `needs` hold.
2. **Use a different account.** The login question again.
3. **Stop.**

No answer within the question's timeout counts as 3. The hosted app shows the same question as a pop-up (its own
spec).

## For the builder (to verify before planning)

- How Flutter web's semantics tree marks a dialog (`flt-semantics` with `role=dialog`, or a route scope). The live
  run's page text after "Continue" was only "Skip Add", which suggests the dialog scopes what the reader sees.
- Whether the browser's back button returns to the previous screen in K-12 (Flutter's go_router), or the way back has
  to be its tab.

## What comes after

1. The story from the behaviour map: choosing sections and jobs for the audience.
2. Recording proven paths: replaces the one-task driver.
3. Sign-in on camera (password masked): its own decision.
4. The hosted app: the login checkbox, the question pop-up and per-user map storage.
