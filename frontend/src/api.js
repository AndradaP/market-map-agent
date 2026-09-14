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

async function post(path, body) {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ..._ownerHeaders() },
    body: JSON.stringify(body || {}),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export const createRun = (topic) => post("/runs", { topic });
export const respond = (runId, payload) => post(`/runs/${runId}/respond`, payload);
