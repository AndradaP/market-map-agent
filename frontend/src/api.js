const BASE = import.meta.env.VITE_API_BASE || "/api";

async function post(path, body) {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export const createRun = (topic) => post("/runs", { topic });
export const respond = (runId, payload) => post(`/runs/${runId}/respond`, payload);
