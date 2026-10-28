# The guide

Everything the [README](../README.md) leaves out: how a demo is made, logins, voices, models, configuration, what we
measured and the limits. How each stage works, and the experiments behind its rules, are in
[how-it-works.md](how-it-works.md).

## Running demos

**You need:**
- Python 3.12+, [uv](https://docs.astral.sh/uv/), ffmpeg and Google Chrome
- a Cloudflare account with Workers AI
- optional: a [Nebius Token Factory](https://tokenfactory.nebius.com) account, to run the language models on NVIDIA
  Nemotron (see [below](#choose-where-the-language-models-run))
- optional: an [ElevenLabs](https://elevenlabs.io) API key, for the narration voice (see **Narrated** below)

Jev runs on Cloudflare as `typesafe/jev` and is paid from **AI Gateway credits**: add a few dollars in the dashboard
(AI → AI Gateway → Credits). A demo costs cents.

```bash
git clone https://github.com/q3learners/jev-demofast && cd jev-demofast
uv sync
export CLOUDFLARE_ACCOUNT_ID=...   CLOUDFLARE_API_TOKEN=...          # a token with Workers AI access

uv run jev-demofast chrome          # an isolated Chrome profile; your own browser and logins are untouched
uv run jev-demofast demo "Show how to find hot trending projects on GitHub this week" \
    --url https://github.com/ --gif --out github.mp4
```

**Your own app, with a map built from source (Next.js app router):**

```bash
uv run jev-demofast index ../my-nextjs-app --out app-index.json      # ~1 s for 190 routes
DEMO_PASSWORD='...' uv run jev-demofast demo "Reset my password for test@example.com" \
    --url https://staging.example.com --index app-index.json --fresh --out reset.mp4
```

**A live site, with a map built by exploring it (no source code needed):**

```bash
uv run jev-demofast demo "Show my investors how easy it is to find men's running shoes under \$150 on our site" \
    --url https://www.allbirds.com/ --fresh --voice chris --out allbirds.mp4
```

With no `--index`, `demo` explores the site first (about 40 s, once) and keeps the map in
`~/.cache/jev-demofast/maps/<host>.json` for later demos; delete that file to explore again. `explore <url> --out map.json`
does the same on its own.

**The founder's script comes first.** Before anything is recorded, the script model (NVIDIA Nemotron on Nebius, or
GLM on Workers AI) reads the prompt (who the demo is for, and why) and what the map knows (pages, headings, menus,
listings, filters and their values) and writes the voice-over a founder would give: the promise, why each moment
matters, the payoff. It's printed and saved as `story.txt` in the run folder.

The script also picks the **shots**: up to six pages of the site to show, in the order the script talks about them,
and the task to finish on, if the prompt asks for one. Each page is reached the way a visitor would (its link on
screen, else straight there) and shown with a smooth scroll down it, recorded frame by frame, so the viewer sees it
move. A site that is one long page is shown the same way, a screen at a time. A page that can't be reached is left out
of the video and listed in the run's result; the narration never mentions it.

After recording, the script is laid over the video in the founder's words, and changed only where the recording
proves it wrong: the value really chosen, a price band the site had greyed out, and the products and prices actually
shown. Setup steps on screen (install commands, tool names) are left out unless the script is about them.

**Give it the product's own words:** `--repo https://github.com/you/your-product` reads the repo's README (its first
6,000 characters, through GitHub's API; nothing is cloned or run) so the script says what the product is and why in
your words, not only what the site's headings say. `--product "one line"` does the same in a sentence.

`explore` browses the site once, the way a visitor would: it closes the newsletter pop-up, opens each menu (by hover
or click), groups pages into templates (`/collections/:handle`), and reads each listing's filters (groups, values, and
how they appear in the URL). It only navigates and reads: it never submits, signs up or types into a pop-up, and on a
site that blocks automated browsers it stops with a message instead of trying to get around it. It waits for pages
that draw their content after loading (React and similar). When the prompt asks for a task, the demo ends on it like a
founder's walkthrough: the menu opens on camera, the filter panel opens, the filters are ticked, and it ends by
highlighting two or three results. A filter the site has disabled ("no results") is reported, and the narration says so.

With an index, **Jev drives on its own**; no LLM plans the route. Without one, an LLM plans the route once and Jev
handles every step that needs judgment.

**Narrated:** add `--voice chris` (or `eric`, `will`, `sarah`, `jessica`) for an ElevenLabs voice; set
`ELEVENLABS_API_KEY` first. The whole voice-over is spoken in **one take**, so it sounds like one person talking, not
sentences stitched together, and the video's timing follows the voice: each moment is held for as long as its words
take. Without an ElevenLabs key, use `--voice apollo` (or a female voice such as `thalia`): Deepgram Aura-2 on
Cloudflare (about $0.03 per 1,000 characters), one clip per line of the script; `--voice-speed 1.2` speaks it faster at
the same pitch. Either works with or without `--index`. With a map, the script is the founder's (above); the Allbirds
demo above runs about a minute.

Add `--music track.mp3` for a background bed: it plays alone for 2 s before the narrator starts and after they finish,
loops to the video's length, and dips gently whenever the narrator speaks (the voice is also softened to sit inside
it). Use a track you have the rights to (Pixabay Music and the YouTube Audio Library allow commercial use).

Use **staging and test accounts**. The tool clicks real buttons and submits real forms. To see the route first,
add `--dry-run`: the run stops before the first action that changes data (a submit, save, invite or toggle) and
the video ends on that element, labelled "would click".

**When a step fails** (for example, a form is refused), the run reports `verified: False`, the video ends on the error,
and the narration says what went wrong, quoting the message on screen. It never presents a failed flow as a success.

"Create a demo of how to X" and "Show me how to X" are treated as X. Every run also writes `replay.json`: each
Jev question with its options, probabilities and timing, plus a timestamped log, so you can see why it clicked what
it clicked.

## Logins

There are three ways to get past a login, safest first:

1. **Log in once in the tool's own Chrome (recommended).**
   ```bash
   uv run jev-demofast chrome --open https://staging.example.com/login
   ```
   You log in by hand, so SSO, "Sign in with Google" and two-factor codes all work. The tool's profile
   (`~/.cache/jev-demofast/chrome-profile`) remembers the session, so later demos start logged in. Don't pass
   `--fresh`: it clears that site's cookies.
2. **Let the tool type the credentials:** put `{{PASSWORD}}` in the prompt and set `DEMO_PASSWORD`. The value is
   typed straight into the password field; no model or log ever sees it. Only a placeholder named like a password or
   other secret (`{{PASSWORD}}`, `{{ADMIN_PIN}}`, `{{API_TOKEN}}`) goes there, and if there's no password field the
   run stops rather than type it anywhere else. Others, such as `{{EMAIL}}`, are typed into the matching field.
3. **Your own everyday Chrome (opt-in):** `--use-my-browser`.
   - You switch on remote debugging in `chrome://inspect/#remote-debugging`, and Chrome asks you to allow the
     connection.
   - The tool asks you to confirm (`--yes` skips this, for scripts). It refuses `--fresh`, so it can never log you
     out, and it works in a new tab without touching your other tabs.
   - It acts **as you**, under your real logins, often on production. The guards still apply, but mistakes are
     real. Use it knowingly.

## How it works

| Stage | What happens | Who decides |
|---|---|---|
| Map (optional) | Routes, links (label → destination), fields, buttons, text and data-changing forms, parsed from source with tree-sitter | code |
| Plan | Without a map: a rough route, written once ("Open Source → Trending → This week → a repo") | LLM |
| Drive | Each step: which element matches, which menu hides a target, whether the form is here, whether it's done | **Jev** |
| Check | Stays on the site; never signs up, logs out or deletes; undoes a click that led nowhere; waits for the page to settle before verifying | code |
| Record | Outlined frames; typed values blurred; secrets typed from `{{NAME}}` placeholders and never shown to a model | code |
| Render | MP4 and GIF, with an optional script, voice and camera that follows the narration | ffmpeg (+ LLM, TTS) |

Details and the experiments behind each rule are in [how-it-works.md](how-it-works.md).

## Measured (September 2026)

- **GitHub, a site it was never tuned for:** 5 of 5 runs verified, **14.4–28.2 s** from sentence to recording; one
  slower run took 44.2 s because a single LLM page read took 30 s. Jev's own decisions take about 0.25 s each.
- **Jev + app index on [nextjs/saas-starter](https://github.com/nextjs/saas-starter):** sign in, then invite a
  teammate as a member, with no LLM route plan. 5 of 5 runs, **8.3–17.1 s** from sentence to video, with the
  invitation confirmed in the database. Reproduce it: `examples/saas-starter-invite.sh`.
- **Jev + app index, a password reset three screens from a marketing home page (a private Next.js app):** 2 of 2 in
  10.8–15.0 s. Without the map, Jev gave up at step 1.
- **Narrated:** script, voice and render add 10–16 s. Sentence to narrated video: **18.3 s** for the saas-starter
  invite (a 27 s video), **30.6 s** for the GitHub demo (35 s).
- **Synonyms:** the plan said "Sign in" where the site said "Log in", and "Account recovery" where it said
  "Forgot password?". Jev matched them at 0.96–0.99; keyword matching alone got stuck.

**Explored maps (26 October 2026), Allbirds, no source code:** `explore` took about 40 s (17 pages: the newsletter
pop-up, the Men and Women menus, the `/collections/:handle` listing with its Size, Color, Price, Product Type and
Material filters). "Show how to find men's running shoes under $150 on Allbirds" then verified **5 of 5** runs in
21–42 s from that map: the Men menu opened on camera, the filter panel opened, Running Shoes and the $126–$150 band
ticked, three shoes highlighted. The same sentence with "under $100" ends honestly unverified: Allbirds has no men's
running shoes under $100, and the narration says so. Everlane mapped in about 60 s, Nike in 2.5 minutes (7 hover
menus); Zara stopped in under a second ("Access Denied").

## Choose where the language models run

Jev makes every click decision, on Cloudflare. The voice is ElevenLabs (`--voice chris` and the others above, with
`ELEVENLABS_API_KEY`) or Deepgram Aura-2 on Cloudflare (`--voice apollo`). The language-model steps (planning the route, reading page text and form values,
writing the founder's script and fitting it to the recording) can run on either provider:

| Provider | Models | Setup |
|---|---|---|
| **Cloudflare Workers AI** (default) | GLM-5.3-flash, Llama 3.3 | nothing extra |
| **Nebius Token Factory** | NVIDIA Nemotron 3 Ultra | three steps below |

**To use Nebius Token Factory:**

1. Create an API key at [tokenfactory.nebius.com](https://tokenfactory.nebius.com) (API keys → Create).
2. Set two variables, next to your Cloudflare ones (Jev and the voice still need those):
   ```bash
   export JDF_LLM_PROVIDER=nebius
   export NEBIUS_API_KEY=...
   ```
3. Run any command as usual, for example:
   ```bash
   uv run jev-demofast demo "Show how to find trending projects on GitHub this week" --url https://github.com/
   ```

To try another Nebius model, set `JDF_NEBIUS_MODEL` (for example `nvidia/nemotron-3-super-120b-a12b`).

**Measured on 24 September 2026** with Nemotron 3 Ultra doing all language-model work:

- **GitHub trending:** 2 of 2 runs verified in **12.2–15.1 s**, including the hidden "This week" menu.
- **saas-starter invite (with the source-code map):** 2 of 2 in **9.4–13.9 s**, invitation confirmed in the database.
- **Narration:** script, voice and render in **6.7 s**; sentence to narrated video about **16 s**.

Of the four Nemotron models on Token Factory, Ultra planned the GitHub route best (Open Source → Trending → This week
→ a repo) in about 1 s. With thinking on, every model took 4–15 s per plan, so the tool turns thinking off.

Any other OpenAI-compatible provider is one entry in `LLM_PROVIDERS` in `src/jev_demofast/config.py`.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` | — | required |
| `JEV_TOKEN` | the API token | a separate token for Jev calls |
| `BU_CDP_URL` | `http://127.0.0.1:9333` | the Chrome to drive (`jev-demofast chrome` starts one) |
| `JDF_PLAN_MODEL` / `JDF_PLAN_EXTRA` | `@cf/zai-org/glm-5.3-flash` / `{"reasoning_effort":"low"}` | route plans |
| `JDF_READ_MODEL` | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | reading page text and form values |
| `JDF_SCRIPT_MODEL` / `JDF_SCRIPT_EXTRA` | GLM-5.3-flash, reasoning low | the narration script |
| `JDF_TTS_MODEL`, `JDF_EMBED_MODEL`, `JDF_JEV_MODEL` | Aura-2 en, bge-base, `typesafe/jev` | voice, camera-follow, decisions |
| `JDF_CHECK_MODEL` | `@cf/cloudflare/clef` (with a screenshot) | confirms a run really got there: the right page, in the state asked for, showing real content; `typesafe/jev` checks from page text only |
| `DEMO_<NAME>` | — | values for `{{NAME}}` placeholders in prompts |
| `JDF_LLM_PROVIDER` | `cloudflare` | where route plans, page reading and scripts run: `cloudflare` or `nebius` |
| `NEBIUS_API_KEY`, `JDF_NEBIUS_MODEL` | — / `nvidia/Nemotron-3-Ultra-550b-a55b` | Nebius Token Factory key and model (thinking off) |
| `ELEVENLABS_API_KEY`, `JDF_ELEVEN_MODEL` | — / `eleven_multilingual_v2` | the ElevenLabs voice (`--voice chris`, `eric`, `will`, `sarah`, `jessica`) |
| `GITHUB_TOKEN` | — | optional, for `--repo`: raises GitHub's rate limit for reading the README |

browser-harness telemetry and update checks are off by default (`BH_TELEMETRY=0`, `BH_UPDATE_CHECK=0`).

## Limits

- The app index reads **Next.js app router** projects today. Other frameworks need an adapter that returns the same
  shape (see `src/jev_demofast/index/__init__.py`). Without an index, any site still works through the LLM plan.
- Jev's "done" judgment is borderline (about 0.5 after the page settles). That's enough to stop a demo, but not to
  pass or fail a test.
- Blind spots inherited from the browser layer: iframes, shadow DOM, file uploads, pop-up windows, and nested scroll
  areas. Sites protected by captchas will block it.
- `explore` (October 2026) maps menus and listing filters; product pages, logins and checkout come next. On Gymshark it
  found no menus, Everlane's menus came out shallow, and Nike's listing filters (links, not checkboxes) aren't read yet.
- Jev is a paid, closed model. The decision layer is small (`cloudflare.py`), so other backends can be added.
