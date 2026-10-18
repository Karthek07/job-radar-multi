// Picks where Job Radar keeps your data: the hosted server (Azure) when the page is served from it,
// otherwise your own private GitHub repo.
//
// Profiles: every profile keeps the same folders (profile/, data/, user/, requests/, uploads/). The first profile
// ("main") keeps them at the repo root; the others under profiles/<id>/. Pages keep asking for "data/jobs.json";
// this layer adds the folder of the profile you're looking at. Files shared by all profiles (profiles.json,
// applications.json, shared/...) are reached through backend.shared.
import * as github from "./gh.js";
import * as azure from "./az.js";

const hosted = await azure.detect();
const base = hosted ? azure : { mode: "github", ...github };

const SCOPED = /^(profile|data|user|requests|uploads)\//;
let root = "";
const at = (path) => (root && SCOPED.test(path) ? `${root}/${path}` : path);

const overrides = {
  /** Multiple profiles need your own GitHub repo (not the hosted site). */
  profilesSupported: !hosted,
  setRoot(r) { root = hosted ? "" : (r || "").replace(/\/+$/, ""); },
  text: (p) => base.text(at(p)),
  json: (p) => base.json(at(p)),
  blob: (p) => base.blob(at(p)),
  putText: (p, s, m) => base.putText(at(p), s, m),
  putBase64: (p, b, m) => base.putBase64(at(p), b, m),
  request: (type, fields) => (hosted ? base.request(type, fields)
    : base.putText(at(`requests/${Date.now()}-${type}.json`), JSON.stringify({ type, ...fields }), `app: ${type}`)),
  /** Unprefixed access for the files every profile shares. */
  shared: { text: base.text, json: base.json, putText: base.putText },
};
// a Proxy keeps live module bindings (the hosted backend's `me` changes after sign-in)
const backend = new Proxy(base, { get: (t, k) => (k === "root" ? root : k in overrides ? overrides[k] : t[k]) });
export default backend;
