import { useMemo, useState } from "react";
import { createRun, respond } from "./api.js";

// Screens: topic input -> proposal review/edit (or clarification) -> final nested list.
export default function App() {
  const [phase, setPhase] = useState("topic"); // topic | review | clarify | final | loading
  const [error, setError] = useState(null);
  const [runId, setRunId] = useState(null);
  const [review, setReview] = useState(null); // interrupt payload
  const [final, setFinal] = useState(null);

  function routePayload(res) {
    if (res.status === "awaiting_confirmation") {
      setReview(res.review);
      setPhase(res.review.kind === "rescope_clarification" ? "clarify" : "review");
    } else {
      setFinal(res.final_output);
      setPhase("final");
    }
  }

  async function guard(fn, fallback) {
    setError(null);
    setPhase("loading");
    try {
      await fn();
    } catch (e) {
      setError(String(e));
      setPhase(fallback);
    }
  }

  const start = (topic) =>
    guard(async () => {
      const res = await createRun(topic);
      setRunId(res.run_id);
      routePayload(res);
    }, "topic");

  const send = (payload) =>
    guard(async () => routePayload(await respond(runId, payload)), review ? "review" : "topic");

  const startOver = () => {
    setError(null);
    setRunId(null);
    setReview(null);
    setFinal(null);
    setPhase("topic");
  };

  return (
    <main>
      <div className="topbar">
        <h1>Market Map Agent</h1>
        {phase !== "topic" && (
          <button type="button" className="startover" onClick={startOver}>
            Start a new market map
          </button>
        )}
      </div>
      {error && <pre className="error">{error}</pre>}
      {phase === "loading" && <p>Working…</p>}
      {phase === "topic" && <TopicForm onSubmit={start} />}
      {phase === "review" && <ProposalReview review={review} onSend={send} />}
      {phase === "clarify" && <ClarificationForm review={review} onSend={send} />}
      {phase === "final" && <FinalMap final={final} />}
    </main>
  );
}

function TopicForm({ onSubmit }) {
  const [topic, setTopic] = useState("AI observability");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (topic.trim()) onSubmit(topic.trim());
      }}
    >
      <label>
        Topic — broad or narrow
        <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="e.g. neo-cloud, geothermal energy" />
      </label>
      <button type="submit">Research &amp; propose a structure</button>
    </form>
  );
}

const EDIT_KEYWORDS = [
  "scope", "exclude", "includ", "broad", "narrow", "split", "merge", "combine",
  "separate", "layer", "stage", "component", "categor", "granular", "rename",
  "reorder", "sub-cat", "subcateg", "out of scope",
];
const DIRECT_EDIT_VERBS = ["rename", "remove", "drop", "delete", "split", "merge", "reorder", "add"];

function noteIsActionable(notes, layers, minChars) {
  const n = (notes || "").trim();
  if (n.length < minChars) return false;
  const low = n.toLowerCase();
  if (layers.some((l) => low.includes(String(l).toLowerCase()))) return true;
  if (EDIT_KEYWORDS.some((k) => low.includes(k))) return true;
  return n.length >= 40;
}

function looksLikeDirectEdit(notes, layers) {
  const low = (notes || "").toLowerCase();
  const namesLayer = layers.some((l) => low.includes(String(l).toLowerCase()));
  return namesLayer && DIRECT_EDIT_VERBS.some((v) => low.includes(v));
}

function ProposalReview({ review, onSend }) {
  const p = review.proposal;
  const minChars = review.min_note_chars ?? 15;

  const [layers, setLayers] = useState(p.layers);
  const [defs, setDefs] = useState({ ...p.layer_definitions });
  const [zoom, setZoom] = useState(p.zoom_level);
  const [newLayer, setNewLayer] = useState("");
  const [dropped, setDropped] = useState([]); // {name, definition} awaiting a "widen sibling" decision
  const [normalize, setNormalize] = useState(false);

  const [rescopeNotes, setRescopeNotes] = useState("");
  const [differentTopic, setDifferentTopic] = useState(false);
  const [answers, setAnswers] = useState({}); // question index -> chosen option

  const pickAnswer = (i, question, option) => {
    const next = { ...answers, [i]: option };
    setAnswers(next);
    setRescopeNotes(
      Object.entries(next)
        .map(([idx, opt]) => `${p.open_questions[idx].question} -> ${opt}`)
        .join(" ")
    );
  };

  const capText = review.direct_edit_only
    ? review.handoff_message
    : `Rescope requests: ${review.rescopes_remaining} of ${review.rescope_cap} left. ` +
      `A rescope asks the model to try again (costs one attempt). Direct edits below are free and unlimited.`;

  const editLayer = (i, v) => setLayers(layers.map((l, j) => (j === i ? v : l)));
  const editDef = (name, v) => setDefs({ ...defs, [name]: v });

  const dropLayer = (i) => {
    const name = layers[i];
    setLayers(layers.filter((_, j) => j !== i));
    if (defs[name]) setDropped([...dropped, { name, definition: defs[name] }]);
  };

  const addLayer = () => {
    const name = newLayer.trim();
    if (!name || layers.includes(name)) return;
    setLayers([...layers, name]);
    setDefs({ ...defs, [name]: "" });
    setNewLayer("");
  };

  const widenInto = (droppedName, targetLayer) => {
    const d = dropped.find((x) => x.name === droppedName);
    if (d && targetLayer) {
      setDefs({ ...defs, [targetLayer]: `${defs[targetLayer]} Also covers: ${d.definition}` });
    }
    setDropped(dropped.filter((x) => x.name !== droppedName));
  };

  const editedScope = () => ({
    layers,
    layer_definitions: Object.fromEntries(layers.map((l) => [l, defs[l] ?? ""])),
    in_scope: p.in_scope,
    excluded_adjacent: p.excluded_adjacent,
    zoom_level: zoom,
  });

  const submitDirect = () =>
    onSend({ type: "direct_edit", notes: "", different_topic: false, edited_scope: editedScope(), normalize });

  const actionable = noteIsActionable(rescopeNotes, layers, minChars);
  const suggestDirect = looksLikeDirectEdit(rescopeNotes, layers);

  return (
    <section>
      <p className="cap">{capText}</p>
      {p.notes && <p className="notes">Note from the model: {p.notes}</p>}

      <h2>Proposed layers (attempt {review.attempt})</h2>
      <ol>
        {layers.map((l, i) => (
          <li key={i}>
            <input value={l} onChange={(e) => editLayer(i, e.target.value)} />
            <button type="button" onClick={() => dropLayer(i)}>drop</button>
            <textarea
              className="defedit"
              value={defs[l] ?? ""}
              placeholder="One-line definition (used for the category-fit check)"
              onChange={(e) => editDef(l, e.target.value)}
            />
          </li>
        ))}
      </ol>

      <div className="addlayer">
        <input
          value={newLayer}
          onChange={(e) => setNewLayer(e.target.value)}
          placeholder="Add a layer the model missed…"
        />
        <button type="button" onClick={addLayer} disabled={!newLayer.trim()}>add layer</button>
      </div>

      {dropped.map((d) => (
        <div key={d.name} className="widen">
          Dropped <strong>{d.name}</strong>. Fold its definition into another layer so its
          companies still get researched?
          <select
            defaultValue=""
            onChange={(e) => e.target.value && widenInto(d.name, e.target.value)}
          >
            <option value="">— keep dropped —</option>
            {layers.map((l) => (
              <option key={l} value={l}>widen “{l}”</option>
            ))}
          </select>
        </div>
      ))}

      <label>
        Zoom level
        <select value={zoom} onChange={(e) => setZoom(e.target.value)}>
          <option value="component">component</option>
          <option value="company">company</option>
          <option value="category">category</option>
        </select>
      </label>
      <p className="hint">
        How granular the map's entries are: <strong>component</strong> = sub-parts (e.g. "battery
        cells"), <strong>company</strong> = named companies (the usual case), <strong>category</strong> = broader
        groupings instead of naming individual players.
      </p>

      <div className="cols">
        <div>
          <h3>In scope</h3>
          <ul>{p.in_scope.map((x, i) => <li key={i}>{x}</li>)}</ul>
        </div>
        <div>
          <h3>Excluded (adjacent)</h3>
          <ul>{p.excluded_adjacent.map((x, i) => <li key={i}>{x}</li>)}</ul>
        </div>
      </div>

      {p.open_questions?.length > 0 && (
        <>
          <h3>Open questions from the model</h3>
          <p className="hint">
            Pick an answer below to draft a rescope note for it — no need to already know the
            terminology, just choose the option you want.
          </p>
          <ul className="openq">
            {p.open_questions.map((q, i) => (
              <li key={i}>
                {q.affects && <span className="badge">{q.affects}</span>} {q.question}
                {q.options?.length > 0 && (
                  <div className="openq-options">
                    {q.options.map((opt) => (
                      <button
                        key={opt}
                        type="button"
                        className={answers[i] === opt ? "picked" : ""}
                        onClick={() => pickAnswer(i, q, opt)}
                      >
                        {opt}
                      </button>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      <div className="actions">
        <button onClick={() => onSend({ type: "none", notes: "", different_topic: false, edited_scope: null })}>
          Confirm as-is
        </button>
        <button onClick={submitDirect}>Save my direct edits &amp; continue</button>
        <label className="check">
          <input type="checkbox" checked={normalize} onChange={(e) => setNormalize(e.target.checked)} />
          Tidy my layer names &amp; order (one cheap model pass, not a rescope)
        </label>
      </div>

      {!review.direct_edit_only && (
        <div className="rescope">
          <h3>Something fundamentally wrong? Ask the model to rescope</h3>
          <textarea
            value={rescopeNotes}
            onChange={(e) => setRescopeNotes(e.target.value)}
            placeholder="Say what's wrong AND what you'd expect — e.g. 'batteries and charging are lumped together; charging infra should be its own stage'."
          />
          {suggestDirect && (
            <p className="hint">
              That sounds like something you can do yourself above (rename / drop / add a layer) —
              a direct edit is free and doesn't cost a rescope.
            </p>
          )}
          {!actionable && rescopeNotes.trim().length > 0 && (
            <p className="hint">
              Add a bit more — name the layer or boundary that's wrong and what you'd expect. If
              it's still thin, the model will ask you one question before spending an attempt.
            </p>
          )}
          <label className="check">
            <input
              type="checkbox"
              checked={differentTopic}
              onChange={(e) => setDifferentTopic(e.target.checked)}
            />
            This is actually a different topic (re-runs research from scratch)
          </label>
          <button
            disabled={!rescopeNotes.trim()}
            onClick={() =>
              onSend({
                type: "rescope_request",
                notes: rescopeNotes.trim(),
                different_topic: differentTopic,
                edited_scope: null,
              })
            }
          >
            Request rescope
          </button>
        </div>
      )}
    </section>
  );
}

function ClarificationForm({ review, onSend }) {
  const [answer, setAnswer] = useState("");
  return (
    <section>
      <p className="cap">
        This won't spend a rescope attempt — just help the model aim.
      </p>
      <p className="notes">Your note: “{review.original_notes || "(blank)"}”</p>
      <h3>{review.question}</h3>
      <textarea value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Your answer…" />
      <button
        disabled={!answer.trim()}
        onClick={() => onSend({ type: "rescope_clarification", notes: answer.trim() })}
      >
        Send &amp; rescope
      </button>
    </section>
  );
}

function CompanyItem({ c }) {
  const tiers = c.corroboration?.tiers || [];
  return (
    <li>
      <a href={c.url} target="_blank" rel="noreferrer">{c.name}</a> — {c.one_liner}
      <div className="src">
        {tiers.length > 0 && <span className="tiers">[{tiers.join(" · ")}]</span>} sources:{" "}
        {(c.sources || []).join(", ")}
      </div>
    </li>
  );
}

function FinalMap({ final }) {
  const nav = useMemo(() => final.layers.map((l) => l.name), [final]);
  return (
    <section>
      <h2>{final.topic}</h2>
      <p className="cap">zoom level: {final.zoom_level} · layers: {nav.length}</p>

      {final.warnings?.length > 0 && (
        <div className="warnings">
          <h3>Warnings</h3>
          <ul>{final.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
        </div>
      )}

      {final.layers.map((layer, i) => (
        <div key={i} className="layer">
          <h3>
            {layer.name} <span className={`status ${layer.status}`}>{layer.status}</span>
            {layer.reformulated && <span className="badge">broadened query</span>}
            {layer.over_cap && <span className="badge warn">too broad — capped</span>}
          </h3>
          <p>{layer.explanation}</p>
          <ul>{layer.companies.map((c, j) => <CompanyItem key={j} c={c} />)}</ul>
          {layer.under_corroborated_count > 0 && (
            <p className="hint">
              {layer.under_corroborated_count} under-corroborated candidate
              {layer.under_corroborated_count > 1 ? "s" : ""} in the review queue below.
            </p>
          )}
        </div>
      ))}

      {final.needs_review?.length > 0 && (
        <div className="review-queue">
          <h3>Review queue — verified, but under-corroborated</h3>
          <p className="hint">
            These resolve to a real company in the right layer, but fall short of the
            independent-source bar. Promote or drop them by hand.
          </p>
          <ul>
            {final.needs_review.map((c, i) => (
              <li key={i}>
                <strong>{c.name}</strong> ({c.layer}) — {c.one_liner}
                <div className="src">{c.corroboration?.detail}</div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {final.rejected?.length > 0 && (
        <div className="rejected">
          <h3>Rejected — shown, not silently dropped</h3>
          <ul>
            {final.rejected.map((c, i) => (
              <li key={i}>
                <strong>{c.name}</strong> ({c.layer}): {c.rejection_reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
