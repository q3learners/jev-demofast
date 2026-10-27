// Cloudflare Access sign-in check: only a token signed by the team's key, for this application, unexpired, gets in.
// Run: npm test (Node 22+)
import assert from "node:assert/strict";
import { test } from "node:test";
import { signedIn } from "../src/access.js";

const TEAM = "q3.cloudflareaccess.com", AUD = "aud-123";
const env = { ACCESS_TEAM_DOMAIN: TEAM, ACCESS_AUD: AUD };
const { publicKey, privateKey } = await crypto.subtle.generateKey(
  { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
  true, ["sign", "verify"]);
const jwk = { ...(await crypto.subtle.exportKey("jwk", publicKey)), kid: "k1" };
globalThis.fetch = async (url) => {
  assert.equal(url, `https://${TEAM}/cdn-cgi/access/certs`);
  return { json: async () => ({ keys: [jwk] }) };
};
const b64 = (bytes) => Buffer.from(bytes).toString("base64url");

async function token(claims = {}, header = {}, key = privateKey) {
  const h = b64(JSON.stringify({ alg: "RS256", kid: "k1", ...header }));
  const p = b64(JSON.stringify({ aud: [AUD], iss: `https://${TEAM}`, exp: Date.now() / 1000 + 600,
    email: "founder@example.com", ...claims }));
  const sig = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, new TextEncoder().encode(`${h}.${p}`));
  return `${h}.${p}.${b64(new Uint8Array(sig))}`;
}
const request = (t) => new Request("https://app.test/", { headers: t ? { "cf-access-jwt-assertion": t } : {} });

test("a valid Access token signs you in", async () => {
  assert.equal(await signedIn(request(await token()), env), "founder@example.com");
});

test("no token, or Access not configured, keeps everyone out", async () => {
  assert.equal(await signedIn(request(null), env), null);
  assert.equal(await signedIn(request(await token()), { ACCESS_TEAM_DOMAIN: "", ACCESS_AUD: "" }), null);
});

test("a token for another application, another team, or an expired one is refused", async () => {
  assert.equal(await signedIn(request(await token({ aud: ["other"] })), env), null);
  assert.equal(await signedIn(request(await token({ iss: "https://evil.cloudflareaccess.com" })), env), null);
  assert.equal(await signedIn(request(await token({ exp: Date.now() / 1000 - 5 })), env), null);
});

test("a forged signature or an unsigned token is refused", async () => {
  const other = (await crypto.subtle.generateKey({ name: "RSASSA-PKCS1-v1_5", modulusLength: 2048,
    publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" }, true, ["sign", "verify"])).privateKey;
  assert.equal(await signedIn(request(await token({}, {}, other)), env), null);
  const [h, p] = (await token({}, { alg: "none" })).split(".");
  assert.equal(await signedIn(request(`${h}.${p}.`), env), null);
  assert.equal(await signedIn(request("not.a.token"), env), null);
});

test("the local-development bypass works only when set", async () => {
  assert.equal(await signedIn(request(null), { ...env, DEV_NO_AUTH: "1" }), "dev");
  assert.equal(await signedIn(request(null), { ...env, DEV_NO_AUTH: "0" }), null);
});
