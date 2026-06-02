/// <reference types="@cloudflare/workers-types" />
import { createRemoteJWKSet, jwtVerify } from "jose";

interface Env {
  // R2 bucket binding (see wrangler.toml). Holds the private data files.
  DORA_BUCKET: R2Bucket;
  // Cloudflare Access team domain, e.g. https://focusbear.cloudflareaccess.com
  CF_ACCESS_TEAM_DOMAIN: string;
  // Cloudflare Access Application Audience (AUD) tag for this app.
  CF_ACCESS_AUD: string;
}

// Only these files may be served. Anything else is rejected before touching R2.
const ALLOWED_FILES = new Set([
  "dora.json",
  "repo_summary.csv",
  "repo_summary_7d.csv",
  "repo_summary_30d.csv",
]);

const CONTENT_TYPES: Record<string, string> = {
  json: "application/json",
  csv: "text/csv",
};

// Cache the JWKS resolver across invocations (per isolate).
let jwks: ReturnType<typeof createRemoteJWKSet> | null = null;

function getJwks(teamDomain: string) {
  if (!jwks) {
    jwks = createRemoteJWKSet(
      new URL(`${teamDomain}/cdn-cgi/access/certs`),
    );
  }
  return jwks;
}

export const onRequestGet: PagesFunction<Env> = async (context) => {
  const { request, env, params } = context;

  // Fail closed if the Access config is missing — never serve data unguarded.
  if (!env.CF_ACCESS_TEAM_DOMAIN || !env.CF_ACCESS_AUD) {
    return new Response("Server misconfigured: Access gate not set up", {
      status: 500,
    });
  }
  if (!env.DORA_BUCKET) {
    return new Response("Server misconfigured: storage binding missing", {
      status: 500,
    });
  }

  const file = Array.isArray(params.file) ? params.file[0] : params.file;
  if (!file || !ALLOWED_FILES.has(file)) {
    return new Response("Not found", { status: 404 });
  }

  // Cloudflare Access injects the signed JWT on every request that passed the
  // Access policy. No header => request did not go through Access => reject.
  const token = request.headers.get("Cf-Access-Jwt-Assertion");
  if (!token) {
    return new Response("Unauthorized: missing Access token", { status: 401 });
  }

  try {
    await jwtVerify(token, getJwks(env.CF_ACCESS_TEAM_DOMAIN), {
      issuer: env.CF_ACCESS_TEAM_DOMAIN,
      audience: env.CF_ACCESS_AUD,
    });
  } catch {
    return new Response("Forbidden: invalid Access token", { status: 403 });
  }

  const object = await env.DORA_BUCKET.get(file);
  if (!object) {
    return new Response("Not found", { status: 404 });
  }

  const ext = file.split(".").pop() ?? "";
  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set(
    "Content-Type",
    CONTENT_TYPES[ext] ?? "application/octet-stream",
  );
  headers.set("etag", object.httpEtag);
  // Short cache; data refreshes on each pipeline run. Private = per-user only.
  headers.set("Cache-Control", "private, max-age=60");

  return new Response(object.body, { headers });
};
