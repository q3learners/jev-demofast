// Cloudflare Access: the signed sign-in token on every request is verified against the team's keys. Fails closed: with
// Access not configured (ACCESS_TEAM_DOMAIN, ACCESS_AUD), nobody gets in.
const b64url = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
const b64json = (s) => JSON.parse(new TextDecoder().decode(b64url(s)));

export async function signedIn(request, env) {
  if (env.DEV_NO_AUTH === "1") return "dev"; // .dev.vars only, for `wrangler dev`; never set in wrangler.jsonc
  const token = request.headers.get("cf-access-jwt-assertion");
  if (!token || !env.ACCESS_TEAM_DOMAIN || !env.ACCESS_AUD) return null;
  try {
    const [h, p, sig] = token.split(".");
    const header = b64json(h), payload = b64json(p);
    const audience = Array.isArray(payload.aud) ? payload.aud : [payload.aud];
    if (header.alg !== "RS256" || !audience.includes(env.ACCESS_AUD)) return null;
    if (payload.iss !== `https://${env.ACCESS_TEAM_DOMAIN}` || payload.exp * 1000 < Date.now()) return null;
    const certs = await fetch(`https://${env.ACCESS_TEAM_DOMAIN}/cdn-cgi/access/certs`, { cf: { cacheTtl: 3600 } });
    const jwk = (await certs.json()).keys.find((k) => k.kid === header.kid);
    if (!jwk) return null;
    const key = await crypto.subtle.importKey("jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false,
      ["verify"]);
    const ok = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, b64url(sig), new TextEncoder().encode(`${h}.${p}`));
    return ok ? payload.email || "signed in" : null;
  } catch {
    return null;
  }
}
