import { useEffect, useMemo, useState } from "react";
import { createRun, respond } from "./api.js";

// A real propose takes ~70s and a full execute pass considerably longer. A
// bare "Working…" for that long reads as a hang -- which it did, to the
// first person who tried the deployed demo. These are elapsed-time cues,
// deliberately not a fake progress bar: the backend doesn't stream phase
// updates, so claiming to know the current step would be made up.
const STAGES = [
  [0, "Searching the web for how this space is structured…"],
  [15, "Reading what came back…"],
  [35, "Drafting a structure…"],
  [70, "Still working. A first draft usually lands around now…"],
  [110, "Taking longer than usual, but the run is still going."],
];

const RESEARCH_STAGES = [
  [0, "Researching companies for each layer…"],
  [30, "Corroborating each company against independent sources…"],
  [90, "Verifying the companies that made the cut…"],
  [180, "Assembling the map…"],
  [300, "Still going. Bigger maps take a few minutes."],
];

const BREADTH_OPTIONS = [10, 25, 50];
const DEFAULT_BREADTH = 25;

// Screens: topic input -> review (one screen) -> final nested list.
export default function App() {
  const [phase, setPhase] = useState("topic"); // topic | review | clarify | final | loading
  const [error, setError] = useState(null);
  const [runId, setRunId] = useState(null);
  const [review, setReview] = useState(null); // interrupt payload
  const [final, setFinal] = useState(null);
  const [maps, setMaps] = useState(null); // {used, limit, owner}
  const [topic, setTopic] = useState("");
  const [dirty, setDirty] = useState(false); // has the user touched anything?
  const [stage, setStage] = useState("propose"); // which wait the user is in

  function routePayload(res) {
    if (res.maps) setMaps(res.maps);
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

  const start = (t) =>
    guard(async () => {
      setStage("propose");
      setTopic(t);
      const res = await createRun(t);
      setRunId(res.run_id);
      setDirty(false);
      routePayload(res);
    }, "topic");

  const send = (payload) =>
    guard(async () => {
      // Continuing runs the whole research pass; a redraft just re-proposes.
      setStage(payload.type === "direct_edit" || payload.type === "none" ? "research" : "propose");
      const res = await respond(runId, payload);
      setDirty(false);
      routePayload(res);
    }, review ? "review" : "topic");

  const startOver = () => {
    // Always confirms: a misclick here loses every edit on the screen and
    // the next topic you submit spends one of the day's maps.
    if (!window.confirm("Start a new map? Anything you've changed here is lost.")) return;
    setError(null);
    setRunId(null);
    setReview(null);
    setFinal(null);
    setTopic("");
    setDirty(false);
    setPhase("topic");
  };

  return (
    <main>
      {phase !== "topic" && (
        <Header
          topic={topic}
          maps={maps}
          review={phase === "review" ? review : null}
          onNewMap={startOver}
          onRedraft={(notes) => send({ type: "rescope_request", notes, edited_scope: null })}
          dirty={dirty}
        />
      )}
      {phase === "topic" && <h1>Market Map Agent</h1>}
      {error && <div className="error">{friendlyError(error)}</div>}
      {phase === "loading" && <Working stages={stage === "research" ? RESEARCH_STAGES : STAGES} />}
      {phase === "topic" && <TopicForm onSubmit={start} />}
      {phase === "review" && (
        <ProposalReview review={review} onSend={send} onDirty={() => setDirty(true)} />
      )}
      {phase === "clarify" && <ClarificationForm review={review} onSend={send} />}
      {phase === "final" && <FinalMap final={final} />}
    </main>
  );
}

function Working({ stages }) {
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);
  const [, label] = [...stages].reverse().find(([at]) => secs >= at) || stages[0];
  return (
    <div className="working">
      <p>{label}</p>
      <p className="meta">{secs}s elapsed · leaving this page loses the run</p>
    </div>
  );
}

// A thrown fetch error arrives as "429 {"detail":"..."}". Showing that raw
// reads as a crash to anyone who isn't the person who wrote it.
function friendlyError(raw) {
  const s = String(raw);
  const match = s.match(/\{.*\}/);
  let detail = "";
  if (match) {
    try {
      detail = JSON.parse(match[0]).detail || "";
    } catch {
      detail = "";
    }
  }
  if (s.includes("429")) return detail || "You've hit today's limit. Try again tomorrow.";
  if (s.includes("404")) {
    return "That run is no longer available — the server restarted. Start a new map.";
  }
  if (s.includes("Load failed") || s.includes("NetworkError") || s.includes("Failed to fetch")) {
    return "Couldn't reach the server. It may still be starting up — try again in a moment.";
  }
  return detail || "Something went wrong on the server. Try again.";
}

function mapsLabel(maps) {
  if (!maps) return null;
  if (maps.owner || maps.limit == null) return "unlimited";
  return `map ${Math.min(maps.used, maps.limit)} of ${maps.limit} today`;
}

// Everything in the header spends something. Everything in the body is free.
// That's the whole rule, so neither needs explaining on screen.
function Header({ topic, maps, review, onNewMap, onRedraft, dirty }) {
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState("");
  const left = review ? review.rescopes_remaining : null;
  const capped = review ? review.direct_edit_only : false;

  return (
    <>
      <div className="topbar">
        <div>
          <div className="topic">{topic || "Market Map Agent"}</div>
          {maps && <div className="meta">{mapsLabel(maps)}</div>}
        </div>
        <div className="topactions">
          {review && !capped && (
            <span className="meta">{left} redraft{left === 1 ? "" : "s"} left</span>
          )}
          {review && (
            <button type="button" onClick={() => setOpen(!open)} disabled={capped || left === 0}>
              Redraft
            </button>
          )}
          <button type="button" onClick={onNewMap}>New map</button>
        </div>
      </div>

      {open && (
        <div className="redraft">
          <p className="meta">
            Asks the model for a different structure. Spends one redraft
            {dirty ? ", and replaces your edits on this screen." : "."}
          </p>
          <textarea
            value={notes}
            autoFocus
            onChange={(e) => setNotes(e.target.value)}
            placeholder="What's wrong with the structure, and what would you expect instead?"
          />
          <div className="topactions">
            <button type="button" onClick={() => setOpen(false)}>Cancel</button>
            <button
              type="button"
              disabled={!notes.trim()}
              onClick={() => onRedraft(notes.trim())}
            >
              Send redraft
            </button>
          </div>
        </div>
      )}
      {capped && review?.handoff_message && <p className="notes">{review.handoff_message}</p>}
    </>
  );
}

function TopicForm({ onSubmit }) {
  const [topic, setTopic] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (topic.trim()) onSubmit(topic.trim());
      }}
    >
      <label>
        Topic
        <input
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="e.g. neo-cloud, geothermal energy"
        />
      </label>
      <button type="submit">Research &amp; propose a structure</button>
    </form>
  );
}

function SegRow({ label, options, value, onPick }) {
  return (
    <div className="prow">
      <span className="plabel">{label}</span>
      <span className="seg">
        {options.map((o, i) => (
          <button
            key={i}
            type="button"
            className={value === i ? "on" : ""}
            onClick={() => onPick(i)}
          >
            {o}
          </button>
        ))}
      </span>
    </div>
  );
}

function Chips({ items, onRemove, onAdd }) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const v = draft.trim();
    if (!v || items.includes(v)) return;
    onAdd(v);
    setDraft("");
  };
  return (
    <div className="chips">
      {items.map((x) => (
        <span className="chip" key={x}>
          <span title={x}>{x}</span>
          <i onClick={() => onRemove(x)} title="remove">×</i>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), add())}
        placeholder="add…"
      />
    </div>
  );
}

function ProposalReview({ review, onSend, onDirty }) {
  const p = review.proposal;
  const questions = p.open_questions || [];

  const [layers, setLayers] = useState(p.layers);
  const [defs, setDefs] = useState({ ...p.layer_definitions });
  const [zoom, setZoom] = useState(p.zoom_level);
  const [breadth, setBreadth] = useState(DEFAULT_BREADTH);
  const [inScope, setInScope] = useState(p.in_scope || []);
  const [excluded, setExcluded] = useState(p.excluded_adjacent || []);
  const [newLayer, setNewLayer] = useState("");
  const [dropped, setDropped] = useState([]);
  const [guidance, setGuidance] = useState("");
  // Each pick-list question opens on the option the model already took, so
  // there's no empty state to interpret and no "unanswered" to explain.
  const [answers, setAnswers] = useState(() =>
    Object.fromEntries(questions.map((q, i) => [i, q.default])),
  );
  const [freeAnswers, setFreeAnswers] = useState({});

  const touch = (fn) => (...args) => {
    onDirty();
    fn(...args);
  };

  const swap = (list, remove, add) => {
    const kept = list.filter((x) => !remove.includes(x));
    return [...kept, ...add.filter((x) => !kept.includes(x))];
  };

  // Each question owns its chips: switching options swaps the old option's
  // entries out and the new option's in, so the answer is visible in the
  // lists instead of recorded somewhere the user can't see.
  const pick = touch((qi, oi) => {
    const q = questions[qi];
    const prev = q.options[answers[qi]] || { in_scope: [], excluded: [] };
    const next = q.options[oi] || { in_scope: [], excluded: [] };
    setAnswers({ ...answers, [qi]: oi });
    setInScope((s) => swap(s, prev.in_scope || [], next.in_scope || []));
    setExcluded((s) => swap(s, prev.excluded || [], next.excluded || []));
  });

  const editLayer = touch((i, v) => setLayers(layers.map((l, j) => (j === i ? v : l))));
  const editDef = touch((name, v) => setDefs({ ...defs, [name]: v }));

  const dropLayer = touch((i) => {
    const name = layers[i];
    setLayers(layers.filter((_, j) => j !== i));
    if (defs[name]) setDropped([...dropped, { name, definition: defs[name] }]);
  });

  const addLayer = touch(() => {
    const name = newLayer.trim();
    if (!name || layers.includes(name)) return;
    setLayers([...layers, name]);
    setDefs({ ...defs, [name]: "" });
    setNewLayer("");
  });

  const widenInto = touch((droppedName, targetLayer) => {
    const d = dropped.find((x) => x.name === droppedName);
    if (d && targetLayer) {
      setDefs({ ...defs, [targetLayer]: `${defs[targetLayer]} Also covers: ${d.definition}` });
    }
    setDropped(dropped.filter((x) => x.name !== droppedName));
  });

  // Free-text answers and the catch-all steer both land in one guidance
  // string, which reaches the search query and the category-fit check.
  const fullGuidance = () =>
    [
      ...questions
        .map((q, i) => (!q.options.length && freeAnswers[i]?.trim() ? `${q.question}: ${freeAnswers[i].trim()}` : ""))
        .filter(Boolean),
      guidance.trim(),
    ]
      .filter(Boolean)
      .join(". ");

  const submit = () =>
    onSend({
      type: "direct_edit",
      notes: "",
      different_topic: false,
      edited_scope: {
        layers,
        layer_definitions: Object.fromEntries(layers.map((l) => [l, defs[l] ?? ""])),
        in_scope: inScope,
        excluded_adjacent: excluded,
        zoom_level: zoom,
        companies_per_layer: breadth,
        guidance: fullGuidance(),
      },
    });

  const pickQuestions = questions.filter((q) => q.options.length);
  const freeQuestions = questions.map((q, i) => ({ q, i })).filter((x) => !x.q.options.length);

  return (
    <section>
      <div className="card">
        <h2>Parameters</h2>
        <SegRow
          label="Zoom level"
          options={["component", "company", "category"]}
          value={["component", "company", "category"].indexOf(zoom)}
          onPick={touch((i) => setZoom(["component", "company", "category"][i]))}
        />
        <p className="hint">
          component = sub-parts, company = named companies, category = broader groupings.
        </p>
        <SegRow
          label="Companies per layer"
          options={BREADTH_OPTIONS.map((n) => `~${n}`)}
          value={BREADTH_OPTIONS.indexOf(breadth)}
          onPick={touch((i) => setBreadth(BREADTH_OPTIONS[i]))}
        />

        {pickQuestions.map((q) => {
          const qi = questions.indexOf(q);
          return (
            <SegRow
              key={qi}
              label={q.question}
              options={q.options.map((o) => o.label)}
              value={answers[qi]}
              onPick={(oi) => pick(qi, oi)}
            />
          );
        })}

        <div className="divider">
          <div className="plabel small">In scope</div>
          <Chips
            items={inScope}
            onAdd={touch((v) => setInScope([...inScope, v]))}
            onRemove={touch((v) => setInScope(inScope.filter((x) => x !== v)))}
          />
          <div className="plabel small">Excluded</div>
          <Chips
            items={excluded}
            onAdd={touch((v) => setExcluded([...excluded, v]))}
            onRemove={touch((v) => setExcluded(excluded.filter((x) => x !== v)))}
          />
        </div>

        {freeQuestions.map(({ q, i }) => (
          <div className="prow divider" key={i}>
            <span className="plabel">{q.question}</span>
            <input
              className={freeAnswers[i]?.trim() ? "answered" : ""}
              value={freeAnswers[i] || ""}
              onChange={touch((e) => setFreeAnswers({ ...freeAnswers, [i]: e.target.value }))}
            />
          </div>
        ))}

        <div className="divider">
          <div className="plabel">Anything else to steer this</div>
          <input
            className={guidance.trim() ? "answered" : ""}
            value={guidance}
            onChange={touch((e) => setGuidance(e.target.value))}
            placeholder="Series A and later only"
          />
          <p className="hint">Shapes the search and what counts as a fit. Free.</p>
        </div>
      </div>

      <div className="card">
        <h2>Layers</h2>
        {layers.map((l, i) => (
          <div className="layerblock" key={i}>
            <div className="layerrow">
              <input value={l} onChange={(e) => editLayer(i, e.target.value)} />
              <button type="button" onClick={() => dropLayer(i)}>drop</button>
            </div>
            <input
              className="defedit"
              value={defs[l] ?? ""}
              placeholder="One-line definition (used for the category-fit check)"
              onChange={(e) => editDef(l, e.target.value)}
            />
          </div>
        ))}

        {dropped.map((d) => (
          <div key={d.name} className="widen">
            Dropped <strong>{d.name}</strong>. Fold its definition into another layer so its
            companies still get researched?
            <select defaultValue="" onChange={(e) => e.target.value && widenInto(d.name, e.target.value)}>
              <option value="">keep dropped</option>
              {layers.map((l) => (
                <option key={l} value={l}>widen “{l}”</option>
              ))}
            </select>
          </div>
        ))}

        <div className="addlayer divider">
          <input
            value={newLayer}
            onChange={(e) => setNewLayer(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addLayer())}
            placeholder="Add a layer the model missed"
          />
          <button type="button" onClick={addLayer} disabled={!newLayer.trim()}>add</button>
        </div>
      </div>

      <button className="primary" onClick={submit}>Continue</button>
    </section>
  );
}

function ClarificationForm({ review, onSend }) {
  const [answer, setAnswer] = useState("");
  return (
    <section>
      <div className="card">
        <p className="meta">This won't spend a redraft. It just helps the model aim.</p>
        <p className="notes">Your note: “{review.original_notes || "(blank)"}”</p>
        <h2>{review.question}</h2>
        <textarea value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Your answer…" />
        <button
          className="primary"
          disabled={!answer.trim()}
          onClick={() => onSend({ type: "rescope_clarification", notes: answer.trim() })}
        >
          Send
        </button>
      </div>
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
      {/* The topic already sits in the sticky header, so it isn't repeated here. */}
      <p className="meta">zoom level: {final.zoom_level} · layers: {nav.length}</p>

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
