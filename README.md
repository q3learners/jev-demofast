# jev-demofast

[![onecentdemo: one sentence in, a narrated demo out](docs/banner.jpg)](https://onecentdemo.com)

**One sentence in, a narrated product demo out.** Tell it what to show and to whom. It explores your site, writes the
voice-over a founder would give, drives a real browser through it, and hands you an MP4.

![GitHub trending demo, generated from one sentence](docs/github-trending.gif)

```bash
jev-demofast demo "Show how to find hot trending projects on GitHub this week" --url https://github.com/ --gif
```

That GIF is the unedited output, about 20 seconds from sentence to video.

**Two ways to try it:**
- **In your browser, nothing to install:** [app.onecentdemo.com](https://app.onecentdemo.com). Sign in and get $1 of
  free credit, four demos.
- **On your own machine:** this repository. It's free and MIT-licensed; you bring your own keys and a demo costs cents.

## Quickstart

You need Python 3.12+, [uv](https://docs.astral.sh/uv/), ffmpeg, Google Chrome and a Cloudflare account with Workers
AI. Jev, the model that makes each click decision, is paid from AI Gateway credits: add a few dollars under AI → AI
Gateway → Credits.

```bash
git clone https://github.com/q3learners/jev-demofast && cd jev-demofast
uv sync
export CLOUDFLARE_ACCOUNT_ID=...  CLOUDFLARE_API_TOKEN=...    # a token with Workers AI access

uv run jev-demofast chrome      # starts its own Chrome; your browser and logins are untouched
uv run jev-demofast demo "Show how to find hot trending projects on GitHub this week" \
    --url https://github.com/ --out github.mp4
```

The video, the founder's script (`story.txt`) and a log of every decision land next to `github.mp4`.

## More to try

**Add a voice.** Set `ELEVENLABS_API_KEY` and add `--voice chris` (or `eric`, `will`, `sarah`, `jessica`). The
voice-over is spoken in one take and the video follows it.

```bash
uv run jev-demofast demo "Show my investors how easy it is to find men's running shoes under \$150 on our site" \
    --url https://www.allbirds.com/ --voice chris --out allbirds.mp4
```

**Use your product's own words.** `--repo` reads your public README so the script says what the product is, in your
words. Nothing is cloned or run.

```bash
uv run jev-demofast demo "Show founders how this turns one sentence into a narrated demo" \
    --url https://onecentdemo.com/ --repo https://github.com/q3learners/jev-demofast --voice eric --out ours.mp4
```

**Demo your own app.** For a Next.js app, build a map from the source first; Jev then drives without an LLM plan. Log
in once with `jev-demofast chrome --open <your login page>` and later demos start logged in.

```bash
uv run jev-demofast index ../my-nextjs-app --out app-index.json
uv run jev-demofast demo "Invite a teammate as a member" --url https://staging.example.com --index app-index.json
```

**Run the language models on NVIDIA Nemotron.** Set `JDF_LLM_PROVIDER=nebius` and `NEBIUS_API_KEY` from
[Nebius Token Factory](https://tokenfactory.nebius.com).

## What you get

- **A founder's script, written first.** Who the demo is for and why, then a page-by-page tour of your site, then the
  payoff.
- **A real browser on camera.** Pages scroll smoothly, menus open, filters get ticked, and each element used is
  outlined.
- **Honest results.** If a step fails, the video ends on the error and the narration says so. It never fakes a success.
- **Safe by default.** It stays on your site, never signs up or deletes anything, and blurs what it types. Use
  `--dry-run` to stop before anything that changes data, and point it at staging.
- **Every decision on record.** `replay.json` shows each choice Jev made, with its options and timing.

## Learn more

- [The guide](docs/guide.md): every option, logins, voices, models, configuration, measurements and limits.
- [How it works](docs/how-it-works.md): each stage and the experiments behind it.
- [The story](https://www.linkedin.com/pulse/jev-couldnt-find-password-reset-form-we-gave-map-venkat-podugu-p23fe/):
  Jev couldn't find the password reset form. Then we gave it a map.

## Contributing

Contributions are welcome, especially map readers for more frameworks (React Router, Remix, Rails, Django). Start with
the [good first issues](https://github.com/q3learners/jev-demofast/labels/good%20first%20issue) and
[CONTRIBUTING.md](CONTRIBUTING.md); the tests run offline.

## Credits

Built on [browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast) and
[laya-ultrafast](https://github.com/ipenywis/laya-ultrafast) (MIT, Browser Use; see `NOTICE`),
[browser-harness](https://pypi.org/project/browser-harness/) (MIT), and Jev by [TypeSafe](https://typesafe.ai),
used through Cloudflare Workers AI. Not affiliated with TypeSafe or Browser Use. MIT License.
