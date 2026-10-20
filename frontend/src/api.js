const BASE = import.meta.env.VITE_API_BASE || "/api";

function _ownerHeaders() {
  // Personal rate-limit bypass: set once via
  // localStorage.setItem("mm_owner_token", "<token>") in your own browser's
  // devtools console -- never checked into git or built into the JS bundle,
  // so no public visitor can discover or copy it from the site's code.
  try {
    const token = localStorage.getItem("mm_owner_token");
    return token ? { "X-Owner-Token": token } : {};
  } catch {
    return {};
  }
}

async function req(path, options) {
  const r = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ..._ownerHeaders() },
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

const post = (path, body) =>
  req(path, { method: "POST", body: JSON.stringify(body || {}) });

export const getRun = (runId) => req(`/runs/${runId}`, { method: "GET" });

// Every call starts a background job and returns immediately; the result
// arrives by polling. Railway's edge proxy kills any single HTTP request at
// exactly 300s (measured: a research pass 502'd at 300.3s), and the research
// pass routinely runs longer than that, so the old hold-the-connection
// approach could never have worked for a real map regardless of patience.
async function poll(started, onPhase) {
  let job = started;
  while (job.status === "running") {
    await new Promise((r) => setTimeout(r, 2000));
    job = await getRun(job.run_id);
    if (onPhase) onPhase(job);
  }
  if (job.status === "error") throw new Error(job.error || "the run failed");
  return job;
}

export async function createRun(topic, onPhase) {
  const started = await post("/runs", { topic });
  if (onPhase) onPhase(started);
  return poll(started, onPhase);
}

export async function respond(runId, payload, onPhase) {
  const started = await post(`/runs/${runId}/respond`, payload);
  if (onPhase) onPhase(started);
  return poll(started, onPhase);
}
