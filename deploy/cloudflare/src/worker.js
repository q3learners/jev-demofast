// The hosted jev-demofast service: sign-in (Cloudflare Access), the page, and the API in front of the recorder.
//   POST /api/runs            {url, prompt, voice} → start a demo (one at a time)
//   GET  /api/runs            recent demos
//   GET  /api/runs/:id        status, log, the founder's script, the narration
//   GET  /api/runs/:id/video  the MP4
// The container's disk goes when it sleeps, so a finished demo is copied to R2 the first time it's seen finished,
// and R2 answers for it from then on.
import { Container, getContainer } from "@cloudflare/containers";
import { signedIn } from "./access.js";

const SECRETS = ["CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "JEV_TOKEN", "NEBIUS_API_KEY", "ELEVENLABS_API_KEY",
  "JDF_LLM_PROVIDER"];
const RUN_ID = /^[0-9a-f]{12}$/;

export class Recorder extends Container {
  defaultPort = 8080;
  sleepAfter = "20m"; // a demo takes 1-4 minutes; the page polls while one runs

  constructor(ctx, env) {
    super(ctx, env);
    this.envVars = Object.fromEntries(SECRETS.filter((k) => env[k]).map((k) => [k, env[k]]));
  }
}

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

function recorder(env) {
  return getContainer(env.RECORDER, "main"); // one recorder: one demo at a time
}

async function toRecorder(env, path, init) {
  try {
    return await recorder(env).fetch(new Request(`http://recorder${path}`, init));
  } catch (error) {
    console.log(`recorder unavailable: ${error}`);
    return json({ error: "The recorder is starting up. Try again in a moment.", starting: true }, 503);
  }
}

// --- Runs ---

async function saved(env, id) {
  const object = await env.DEMOS.get(`runs/${id}.json`);
  return object ? await object.json() : null;
}

async function status(env, id) {
  const kept = await saved(env, id);
  if (kept) return json(kept);
  const response = await toRecorder(env, `/runs/${id}`);
  if (!response.ok) return response;
  const run = await response.json();
  if (run.status !== "running") {
    if (run.video) {
      const video = await toRecorder(env, `/runs/${id}/video`);
      if (video.ok) {
        await env.DEMOS.put(`runs/${id}.mp4`, await video.arrayBuffer(), { httpMetadata: { contentType: "video/mp4" } });
      } else {
        run.video = false;
      }
    }
    await env.DEMOS.put(`runs/${id}.json`, JSON.stringify({ ...run, saved: new Date().toISOString() }),
      { httpMetadata: { contentType: "application/json" } });
  }
  return json(run);
}

async function video(request, env, id) {
  const range = request.headers.get("range");
  const object = await env.DEMOS.get(`runs/${id}.mp4`, range ? { range: request.headers } : {});
  if (!object) return json({ error: "no video for this demo" }, 404);
  const headers = new Headers({ "content-type": "video/mp4", "accept-ranges": "bytes", etag: object.httpEtag });
  if (range && object.range) {
    const { offset = 0, length = object.size - offset } = object.range;
    headers.set("content-range", `bytes ${offset}-${offset + length - 1}/${object.size}`);
    headers.set("content-length", String(length));
    return new Response(object.body, { status: 206, headers });
  }
  headers.set("content-length", String(object.size));
  return new Response(object.body, { headers });
}

async function recent(env) {
  const listed = await env.DEMOS.list({ prefix: "runs/", limit: 200 });
  const keys = listed.objects.filter((o) => o.key.endsWith(".json"))
    .sort((a, b) => b.uploaded - a.uploaded).slice(0, 20);
  const runs = await Promise.all(keys.map(async (o) => (await env.DEMOS.get(o.key))?.json()));
  return json(runs.filter(Boolean).map(({ id, url, prompt, status, verified, video, started }) =>
    ({ id, url, prompt, status, verified, video, started })));
}

export default {
  async fetch(request, env) {
    if (!(await signedIn(request, env))) return new Response("Sign in required.", { status: 403 });
    const url = new URL(request.url);
    const parts = url.pathname.split("/").filter(Boolean);
    if (parts[0] !== "api") return env.ASSETS.fetch(request);

    if (parts[1] === "runs" && parts.length === 2) {
      if (request.method === "POST") {
        const body = await request.text();
        if (body.length > 10000) return json({ error: "too long" }, 413);
        return toRecorder(env, "/runs", { method: "POST", body, headers: { "content-type": "application/json" } });
      }
      return recent(env);
    }
    if (parts[1] === "runs" && RUN_ID.test(parts[2] || "")) {
      if (parts.length === 3) return status(env, parts[2]);
      if (parts[3] === "video" && parts.length === 4) return video(request, env, parts[2]);
    }
    return json({ error: "not found" }, 404);
  },
};
