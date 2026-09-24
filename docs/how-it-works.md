# How jev-demofast works, and why each rule exists

Every rule below came from a run that went wrong without it. Numbers are from our September 2026 experiments.

## Two drivers

**Navigator (any site, `--url` only).**
1. An LLM (GLM-5.3-flash, reasoning low) writes a rough route once.
2. Each step's element is picked from the live page.
3. Checks decide whether the click counts.

We tried Llama 3.3 as the planner first: it gave three different routes in three runs. GLM-5.3-flash gave the same
sensible route 3 out of 3 times.

**Jev drive (your app, `--index`).** There is no route plan. On each screen Jev answers one question: is the goal
done, is its form on this screen, or is it somewhere else? Every clickable option is annotated with where it leads
(its live link, or the destination the source code navigates to) and what that screen contains, from the index.
Without that context, Jev alone gave up on a marketing home page (blocked, 0.92), even though it ranked the right
link first (0.62). With the index it completed the flow every time.

## Picking elements (`drive/pick.py`)

- **Keyword first, only when every word matches.** A target that shares one word with a nav link ("first trending
  repository" vs "Trending") is not a match. That mistake sent early runs to the wrong page.
- **Otherwise Jev, from the whole page,** with "none of these" allowed and a 0.5 confidence floor. Jev bridged
  "Sign in" → "Log in" at 0.98–0.99 and "Account recovery" → "Forgot password?" at 0.96–0.97.
- **Not sure means not found.** When Jev is below 0.5, the navigator opens a menu (below) or re-plans with the real
  labels now on screen. It never clicks the closest keyword.

## Checks around every click

- **Lookahead.** A click counts only if the next step's target appears. If a *later* step's target is already on
  screen, skip ahead: plans guess hops on pages they haven't seen (GitHub's menu has no "Explore" any more). Exact
  matches are checked before Jev's judgment, and skipping ahead needs every word to match.
- **Reveal.** A target that isn't visible may be inside a menu. Jev picks the menu, dropdown, filter or tab to
  open ("This week" lives in GitHub's "Date range" menu).
- **Settle, then verify.** After a submit, the page counts as settled only after it's been unchanged for ~1.2 s,
  because the first change is often "Sending…". If Jev still isn't sure the goal is done, the tool waits once more
  and asks again.
- **Act on a form only when sure.** Jev's calibrated confidence is used as a rule: at 0.25–0.28 it was about to
  submit a *login* form on the way to "Forgot password?"; requiring ≥ 0.5 sent it on instead.
- **Guards.** Stay on the starting site; never click sign-up, third-party login, log-out or delete (unless the step
  says so); start from a clean session with `--fresh`.

## Secrets and privacy

- `{{PASSWORD}}` (any `{{NAME}}`) stays a placeholder in every prompt and log; the value comes from `DEMO_PASSWORD`
  at typing time.
- The page reader hides password inputs from models by design, so passwords are typed straight into the visible
  password field.
- Every field the tool types into is blurred on screen before any frame is taken.

## Recording and narration

- Frames from undone attempts never reach the video; each accepted step is one segment.
- The script writer only sees what was on screen. It writes plain `id | label | text` lines, because JSON broke on
  quote marks in spoken text, and the line count is enforced by segment id.
- Voice: Deepgram Aura-2 on Cloudflare, generated in parallel.
- Camera follow: embeddings shortlist the 5 on-screen text blocks closest to each line, and Jev picks the one being
  talked about. If it's off-screen, the camera pans to it; a list being read is panned through.

## Where the time goes

A silent GitHub demo measured at 32 s:
- the real browser: ~15 s (page loads, screenshots, fixed waits)
- Jev: 10 decisions in 3.8 s
- reading page text: 3.8 s
- the route plan: 3.3 s
- rendering: 3.8 s

Jev is not the bottleneck. The fixed waits are the next thing to trim.
