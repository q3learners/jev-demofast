# The hosted service on Cloudflare

`app.onecentdemo.com`: type what the demo should show and the site's URL, and get the founder's script, the
narration, and the video. Only people you allow in Cloudflare Access can use it.

| Path | What |
|---|---|
| `src/worker.js` | The Worker: sign-in, the page, and the API in front of the recorder |
| `src/access.js` | Checks the Cloudflare Access sign-in token on every request. Nobody gets in until Access is configured |
| `public/index.html` | The page |
| `container/` | The recorder: jev-demofast, headless Chromium, ffmpeg, and a small job server (one demo at a time) |
| `wrangler.jsonc` | Worker, container (standard-4: 4 vCPU, 12 GiB), Durable Object, and R2 bucket for finished demos |

Wrangler 4.153 needs Node 22 or newer.

## One-time setup

1. **Sign-in.** In Zero Trust, go to Access → Applications → Add an application → Self-hosted.
   - Domain: `app.onecentdemo.com`.
   - Policy: Allow, with Emails set to yours.
   - Copy the application's **Audience (AUD) tag**, and your team domain (`<team>.cloudflareaccess.com`, under
     Settings → Custom Pages). Put both in `wrangler.jsonc` (`ACCESS_AUD`, `ACCESS_TEAM_DOMAIN`).
2. **Storage.** `npx wrangler r2 bucket create jev-demofast-demos`
3. **Secrets.** Each value is read from your env file and never printed:
   ```bash
   for k in CLOUDFLARE_ACCOUNT_ID CLOUDFLARE_API_TOKEN JEV_TOKEN NEBIUS_API_KEY; do
     grep "^$k=" ../../../mvpjev/.env | cut -d= -f2- | npx wrangler secret put "$k"
   done
   grep "^ELEVENLABS_API_KEY=" ../../../tutorq/.env | cut -d= -f2- | npx wrangler secret put ELEVENLABS_API_KEY
   ```
   With `ELEVENLABS_API_KEY`, demos are narrated in one ElevenLabs take (voices: chris, eric, will, sarah, jessica).

## Deploy, test, run locally

```bash
npm install
npm run deploy     # builds the amd64 recorder image (slow on Apple Silicon: emulated), then deploys
npm test           # the sign-in check
```

`npm run dev` runs the page, the Worker and the container locally. It reads secrets from `.dev.vars` (git-ignored),
which needs the same four keys plus `DEV_NO_AUTH=1` to skip sign-in. On Apple Silicon the container runs under
emulation, so demos are too slow there and time out. Test the recorder natively instead:

```bash
docker build -f deploy/cloudflare/container/Dockerfile -t jdf-recorder:dev .      # from the repository root
docker run --rm -p 8080:8080 --env-file ../mvpjev/.env jdf-recorder:dev
```

## How it behaves

- **One demo at a time.** A second request gets "another demo is still recording" and the page shows that run instead.
- **Waking up.** The recorder sleeps after 20 minutes without requests. The first demo after that waits for it to
  start, and has to explore the site again: the cached map is lost when it sleeps.
- **Results are kept.** Finished demos (video, founder's script, narration, log) are copied to R2 the first time
  they're seen finished, and listed under "Recent demos".
- **Safety.**
  - Only public `http(s)` sites are accepted. Addresses that resolve to private or local networks are refused.
  - Chrome runs as its own user, with no API keys in its environment.
  - Runs stop after 10 minutes.

## Known limits

- **Blocked more often than on your Mac.** The cloud browser identifies itself as headless (`HeadlessChrome`), and
  some sites refuse it. The tool stops with "blocked" and never hides what it is.
- **Private addresses are checked only once.** The check happens when a demo is submitted; a site could still send
  Chrome to a private address later in the run. This is acceptable while only Access-approved users can start demos.
- **Chrome runs without its sandbox.** The container doesn't support it. Running Chrome as a separate user without
  the keys limits what a compromised page could reach.
