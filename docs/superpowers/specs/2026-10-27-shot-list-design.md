# The founder's shot list: the recording shows what the script says

## Why

A founder plans a demo as a story *and* the screens that go with it, then records every one of them. Today only the
story is planned. The recorder gets a single goal, takes the shortest path to it, and stops the moment the screen
matches.

That worked for Allbirds ("men's running shoes under $150"), where the shortest path *is* the demo. It failed for
tutorq.ai on 2026-10-27:
- The script promised four products (K-12, SAT, Campus, Grader).
- The goal became "use tutorq platform". The recorder clicked "Start SAT Prep", judged the goal reached (0.96), and
  stopped after 14 s.
- The voice-over budget follows the number of recorded moments (13 words each), so most of the script was cut.
  The video was 19 s.

## What changes

**1. The founder's script comes with a shot list.** `story.write` makes one Nemotron call (thinking on, as now) and
gets back JSON:
```json
{"script": "<the spoken script, as today>",
 "shots": [{"page": "/k12", "show": "what this moment shows, in the founder's words"}, ...]}
```
- Each shot's `page` must be a page in the map: a concrete example path of a route (e.g. `/k12`, `/download/sat`).
  The founder picks the pages that tell the brief's story, in the order the script speaks about them.
- The opening shot is always the home page. It is added if missing, and is never counted against the cap.
- When the brief is a task the map can do (a listing with filters, a form), the last shot is
  `{"task": "<the goal>"}`. That shot is driven by today's goal loop: filters, forms, the results showcase.
- **Validation, with no invented fallbacks:**
  - Shots whose page isn't in the map are dropped, and the drop is logged.
  - At most `MAX_SHOTS = 6`, not counting the opening.
  - If no valid shot is left, there is no tour: the demo runs as today (the goal loop) and the log says so.
- Written to `story.txt` (the script, as now) and `shots.json` (the list).
- The prompt loses its shop shape ("menu; listing; each filter"). It describes moments from the map: pages with what
  they say, plus menus, listings and filters where they exist. Script length is about 20 words per shot.
- Pages the map recorded as errors are never offered, e.g. the map's `/:handle/login` read "429 Too Many Requests"
  and `/downloads/...` read "404". The test is the page's own text: an HTTP status line, or no text at all. No list
  of route words: which pages tell the story is the founder's call (the model's), from what each page says.

**2. The recorder visits every shot.** This is a new `jev_drive.tour(cf, url, shots, index, out, ...)`. It uses the
same Session and Recorder, so the opening (first-screen pop-up handling) is unchanged. For each shot, in order:
- **Get there the way a person would.**
  - If a link to the shot's page is visible on the current screen (its href's path equals the page), click it. That
    is one recorded "click" moment.
  - Otherwise, use the map's menus: if a menu item leads there, open the menu and click the item.
  - Otherwise, go there directly (`Page.navigate`). That's a cut, which is fine for a demo.
  - No LLM call is needed to choose. The shot already names the page.
- **Confirm the page.** The URL's path must match the shot's page; a redirect within the site counts (`/campus` →
  `campus.tutorq.ai`).
  - A shot that leaves the site, or whose page doesn't load, is skipped and logged. Its words go with it.
  - The tour continues with the next shot.
- **Show the page.** Scroll down in steps of about one screen, at most `SCROLL_STEPS = 2`, so the viewer sees what
  the founder talks about rather than only the top banner. Each scroll is a recorded "look" moment, with the visible
  headings as its facts.
- **Task shot:** run today's goal loop from where the tour is (`run`'s body, refactored to start from an open
  Session). Its verdict is the demo's verdict.
- **Verdict:**
  - A tour with no task shot is verified when every shot was shown.
  - It is "not confirmed" when any shot was skipped, and the page says which ones.

Each recorded moment carries its shot's `show` text. The voice-over writer then knows why each screen is there.

**3. The voice-over fits the shots.**
- `fit.write` gets each segment's `show`.
- The budget becomes per shot, not per click: about 20 words per shot, plus 8 per further moment in that shot (so a task shot, with its menu, filters and results, keeps about today's length).
- Truth rules are unchanged:
  - A skipped shot isn't spoken about.
  - Names and prices come from what was recorded.

## What doesn't change

- The map: explore, its 40-page and 5-minute caps, public pages only, and the empty-map stop.
- One ElevenLabs take, with the voice-led timeline.
- `jev-demofast run` with a single goal, and every existing test.
- The Allbirds demo: home → task shot. Expected about the same length and verdict as now.

## Expected results

- **tutorq.ai**, prompt "Show users how to use the TutorQ platform for their kids' education":
  - Shots like home → /k12 → /sat (or /about), with a short scroll on each.
  - About 45–60 s, verified.
- **Allbirds**, the same prompt as before: home → task (menu, listing, filters, results). About 30–35 s, verified.

## Out of scope

- Signing in to show the apps themselves (k12, campus, grader).
- Flutter or canvas sites.
- Choosing the video length from the prompt.
- Background music.

## Left to the builder

- How a scroll step is recorded (frames during the scroll versus one held frame after it).
- The exact test for "an error page", as long as it comes from the page's own text in the map.
- Whether the shot list is checked against the script's wording. It is not required.
