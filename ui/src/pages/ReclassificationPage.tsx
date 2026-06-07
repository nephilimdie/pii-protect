import { useEffect, useState, FormEvent } from "react";
import { Plus, Trash2, Pencil, Check, X } from "lucide-react";
import { api, ReclassificationRule } from "../lib/api";

interface Props { isAdmin: boolean; }

const TYPE_COLORS: Record<string, string> = {
  PERSON: "#6366f1", ACCOUNT: "#8b5cf6", ORGANIZATION: "#a78bfa",
  EMAIL: "#0ea5e9", PHONE: "#06b6d4", ADDRESS: "#14b8a6",
  DATE: "#f59e0b", FISCAL_CODE: "#f97316", IBAN: "#ef4444",
  CREDIT_CARD: "#ec4899", SECRET: "#e11d48", API_KEY: "#be123c",
  URL: "#84cc16", IP_ADDRESS: "#22c55e", MAC_ADDRESS: "#10b981",
  GPS_COORDINATE: "#3b82f6", PASSPORT: "#64748b", IDENTITY_CARD: "#475569",
  DRIVER_LICENSE: "#6b7280", HEALTH_CARD: "#f43f5e", TARGA: "#d97706",
};
const typeColor = (t: string) => TYPE_COLORS[t] ?? "#94a3b8";

function trunc(s: string | null | undefined, n: number) {
  if (!s) return "";
  return s.length > n ? s.slice(0, n) + "…" : s;
}

// ── SVG graph ─────────────────────────────────────────────────────────────────
const SVG_W      = 740;
const ROW_H      = 90;   // height per rule row
const PAD_TOP    = 20;
const PAD_BOT    = 20;
const NODE_W     = 130;
const NODE_H     = 42;
const FROM_X     = 20;
const TO_X       = SVG_W - NODE_W - 20;
const ARROW_X1   = FROM_X + NODE_W + 6;
const ARROW_X2   = TO_X - 6;
const MID_X      = (ARROW_X1 + ARROW_X2) / 2;

function RuleGraph({ rules, hoveredRule, onHover }: {
  rules: ReclassificationRule[];
  hoveredRule: string | null;
  onHover: (id: string | null) => void;
}) {
  const visible = rules; // all rules, one row each
  const svgH = PAD_TOP + visible.length * ROW_H + PAD_BOT;

  return (
    <svg width="100%" viewBox={`0 0 ${SVG_W} ${svgH}`} className="block">
      <defs>
        <marker id="arr-default" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
          <path d="M0,0 L7,3.5 L0,7 Z" fill="#64748b" />
        </marker>
        {Object.entries(TYPE_COLORS).map(([t, c]) => (
          <marker key={t} id={`arr-${t}`} markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
            <path d="M0,0 L7,3.5 L0,7 Z" fill={c} />
          </marker>
        ))}
        <marker id="arr-discard" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
          <path d="M0,0 L7,3.5 L0,7 Z" fill="#ef4444" />
        </marker>
      </defs>

      {visible.map((rule, i) => {
        const cy     = PAD_TOP + i * ROW_H + ROW_H / 2;
        const boxY   = cy - NODE_H / 2;
        const hov    = hoveredRule === rule.id;
        const fColor = typeColor(rule.from_type);
        const tColor = rule.to_type ? typeColor(rule.to_type) : "#ef4444";
        const dis    = !rule.enabled;
        const alpha  = dis ? "55" : "ff";
        const arrowId = rule.to_type ? (`arr-${rule.to_type}` in {} ? `arr-${rule.to_type}` : "arr-default") : "arr-discard";

        // pattern lines
        const ctxLine = rule.context_pattern ? `ctx: ${trunc(rule.context_pattern, 36)}` : null;
        const entLine = rule.entity_pattern  ? `ent: ${trunc(rule.entity_pattern, 36)}`  : null;
        const descLine = trunc(rule.description, 52);

        return (
          <g key={rule.id}
            onMouseEnter={() => onHover(rule.id)}
            onMouseLeave={() => onHover(null)}
            style={{ opacity: dis ? 0.45 : 1, cursor: "default" }}>

            {/* FROM box */}
            <rect x={FROM_X} y={boxY} width={NODE_W} height={NODE_H} rx={6}
              fill={fColor + "22"} stroke={fColor + alpha} strokeWidth={hov ? 2 : 1.5} />
            <text x={FROM_X + NODE_W / 2} y={cy + 5} textAnchor="middle"
              fontSize={11} fontWeight={700} fill={fColor} className="select-none">
              {rule.from_type}
            </text>

            {/* Arrow */}
            <line x1={ARROW_X1} y1={cy} x2={ARROW_X2} y2={cy}
              stroke={tColor} strokeWidth={hov ? 2 : 1.5}
              strokeDasharray={dis ? "5 3" : undefined}
              markerEnd={`url(#${arrowId})`} />

            {/* Rule labels on the arrow */}
            {ctxLine && (
              <text x={MID_X} y={cy - (entLine ? 9 : 5)} textAnchor="middle"
                fontSize={9} fill="#94a3b8" fontFamily="monospace" className="select-none">
                {ctxLine}
              </text>
            )}
            {entLine && (
              <text x={MID_X} y={cy + (ctxLine ? 0 : -5)} textAnchor="middle"
                fontSize={9} fill="#c4b5fd" fontFamily="monospace" className="select-none">
                {entLine}
              </text>
            )}
            {descLine && (
              <text x={MID_X} y={cy + (ctxLine || entLine ? 11 : 5)} textAnchor="middle"
                fontSize={8.5} fill="#64748b" className="select-none">
                {descLine}
              </text>
            )}

            {/* TO box */}
            {rule.to_type ? (
              <>
                <rect x={TO_X} y={boxY} width={NODE_W} height={NODE_H} rx={6}
                  fill={tColor + "22"} stroke={tColor + alpha} strokeWidth={hov ? 2 : 1.5} />
                <text x={TO_X + NODE_W / 2} y={cy + 5} textAnchor="middle"
                  fontSize={11} fontWeight={700} fill={tColor} className="select-none">
                  {rule.to_type}
                </text>
              </>
            ) : (
              <>
                <rect x={TO_X} y={boxY} width={NODE_W} height={NODE_H} rx={6}
                  fill="#ef444422" stroke={"#ef4444" + alpha} strokeWidth={hov ? 2 : 1.5}
                  strokeDasharray="4 2" />
                <text x={TO_X + NODE_W / 2} y={cy + 5} textAnchor="middle"
                  fontSize={11} fontWeight={700} fill="#ef4444" className="select-none">
                  discard
                </text>
              </>
            )}

            {/* Divider between rows */}
            {i < visible.length - 1 && (
              <line x1={0} y1={PAD_TOP + (i + 1) * ROW_H} x2={SVG_W} y2={PAD_TOP + (i + 1) * ROW_H}
                stroke="#1e293b" strokeWidth={1} />
            )}
          </g>
        );
      })}

      {visible.length === 0 && (
        <text x={SVG_W / 2} y={60} textAnchor="middle" fill="#475569" fontSize={13}>
          Nessuna regola — aggiungine una
        </text>
      )}
    </svg>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
const EMPTY_FORM = {
  from_type: "PERSON", to_type: "",
  context_pattern: "", entity_pattern: "",
  context_window: 60, description: "",
};

export function ReclassificationPage({ isAdmin }: Props) {
  const [rules, setRules]           = useState<ReclassificationRule[]>([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState<string | null>(null);
  const [showModal, setShowModal]   = useState(false);
  const [editTarget, setEditTarget] = useState<ReclassificationRule | null>(null);
  const [form, setForm]             = useState(EMPTY_FORM);
  const [hoveredRule, setHoveredRule] = useState<string | null>(null);

  function load() {
    setLoading(true);
    api.listReclassificationRules()
      .then(setRules)
      .catch(() => setError("Failed to load rules."))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  function openAdd() {
    setForm(EMPTY_FORM);
    setEditTarget(null);
    setShowModal(true);
  }

  function openEdit(r: ReclassificationRule) {
    setForm({
      from_type: r.from_type, to_type: r.to_type ?? "",
      context_pattern: r.context_pattern ?? "", entity_pattern: r.entity_pattern ?? "",
      context_window: r.context_window, description: r.description,
    });
    setEditTarget(r);
    setShowModal(true);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const body = {
      ...form,
      to_type: form.to_type.trim() || null,
      context_pattern: form.context_pattern.trim() || null,
      entity_pattern: form.entity_pattern.trim() || null,
    };
    if (!body.context_pattern && !body.entity_pattern) {
      setError("Almeno un pattern (contestuale o entità) è richiesto.");
      return;
    }
    try {
      if (editTarget) { await api.updateReclassificationRule(editTarget.id, body); }
      else             { await api.createReclassificationRule(body); }
      setShowModal(false);
      load();
    } catch { setError("Save failed."); }
  }

  async function handleToggle(r: ReclassificationRule) {
    try { await api.updateReclassificationRule(r.id, { enabled: !r.enabled }); load(); }
    catch { setError("Failed to update."); }
  }

  async function handleDelete(r: ReclassificationRule) {
    if (!confirm(`Eliminare la regola "${r.description || r.from_type + " → " + (r.to_type ?? "discard")}"?`)) return;
    try { await api.deleteReclassificationRule(r.id); load(); }
    catch { setError("Failed to delete."); }
  }

  if (!isAdmin) return <p className="text-slate-400">Admin access required.</p>;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-lg font-semibold">Reclassification Rules</h1>
          <p className="text-sm text-slate-400 mt-1">
            Post-detection rules: cambiano il tipo di un'entità in base al contesto o al suo testo.
          </p>
        </div>
        <button onClick={openAdd}
          className="flex items-center gap-1 bg-indigo-600 hover:bg-indigo-700 rounded px-3 py-2 text-sm">
          <Plus size={14} /> New rule
        </button>
      </div>

      {error && <p className="text-red-400 mb-4 text-sm">{error}</p>}

      {/* ── Graph ── */}
      {!loading && (
        <div className="bg-slate-900 border border-slate-700 rounded-xl mb-4 overflow-hidden">
          <RuleGraph rules={rules} hoveredRule={hoveredRule} onHover={setHoveredRule} />
        </div>
      )}

      {/* ── Action strip per ogni regola ── */}
      {!loading && (
        <div className="flex flex-col gap-1">
          {rules.map((r, i) => (
            <div key={r.id}
              className={`flex items-center justify-between px-4 py-2 rounded text-xs transition-colors
                ${hoveredRule === r.id ? "bg-slate-700/60" : "bg-slate-800/40"}
                ${!r.enabled ? "opacity-50" : ""}`}
              onMouseEnter={() => setHoveredRule(r.id)}
              onMouseLeave={() => setHoveredRule(null)}>
              <span className="text-slate-500 w-4 shrink-0">{i + 1}</span>
              <span className="font-semibold shrink-0"
                style={{ color: typeColor(r.from_type) }}>{r.from_type}</span>
              <span className="text-slate-600 mx-1">→</span>
              <span className="font-semibold shrink-0"
                style={{ color: r.to_type ? typeColor(r.to_type) : "#ef4444" }}>
                {r.to_type ?? "discard"}
              </span>
              <span className="text-slate-500 mx-3 truncate max-w-xs">
                {r.description || "—"}
              </span>
              <div className="flex gap-2 ml-auto shrink-0">
                <button onClick={() => handleToggle(r)} className="hover:text-white text-slate-400" title="Toggle">
                  {r.enabled ? <Check size={13} /> : <X size={13} />}
                </button>
                <button onClick={() => openEdit(r)} className="hover:text-white text-slate-400" title="Edit">
                  <Pencil size={13} />
                </button>
                <button onClick={() => handleDelete(r)} className="hover:text-red-400 text-slate-400" title="Delete">
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {loading && <p className="text-slate-400 text-sm">Loading...</p>}

      {/* ── Modal ── */}
      {showModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 w-full max-w-lg">
            <h2 className="font-semibold mb-4">{editTarget ? "Modifica regola" : "Nuova regola"}</h2>
            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              <div className="grid grid-cols-2 gap-3">
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">FROM</span>
                  <input type="text" value={form.from_type}
                    onChange={e => setForm({ ...form, from_type: e.target.value.toUpperCase() })}
                    placeholder="es. PERSON" required
                    className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm font-mono" />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">TO — vuoto = scarta</span>
                  <input type="text" value={form.to_type}
                    onChange={e => setForm({ ...form, to_type: e.target.value.toUpperCase() })}
                    placeholder="es. ACCOUNT"
                    className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm font-mono" />
                </label>
              </div>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Context pattern — regex nel testo prima dell'entità</span>
                <input type="text" value={form.context_pattern}
                  onChange={e => setForm({ ...form, context_pattern: e.target.value })}
                  placeholder='es. (?i)username\s*:\s*$'
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm font-mono" />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-violet-300">Entity pattern — regex nel testo dell'entità stessa</span>
                <input type="text" value={form.entity_pattern}
                  onChange={e => setForm({ ...form, entity_pattern: e.target.value })}
                  placeholder='es. @'
                  className="bg-slate-900 border border-violet-800 rounded px-3 py-2 text-sm font-mono" />
              </label>
              <p className="text-xs text-slate-500">
                Se entrambi sono impostati devono corrispondere entrambi (AND). Almeno uno è obbligatorio.
              </p>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Finestra di contesto (chars)</span>
                <input type="number" value={form.context_window}
                  onChange={e => setForm({ ...form, context_window: parseInt(e.target.value) || 60 })}
                  min={10} max={500}
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm w-28" />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Descrizione</span>
                <input type="text" value={form.description}
                  onChange={e => setForm({ ...form, description: e.target.value })}
                  placeholder="Spiegazione della regola"
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm" />
              </label>
              <div className="flex gap-2 mt-2">
                <button type="submit"
                  className="flex-1 bg-indigo-600 hover:bg-indigo-700 rounded px-3 py-2 text-sm">
                  {editTarget ? "Salva" : "Aggiungi"}
                </button>
                <button type="button" onClick={() => setShowModal(false)}
                  className="flex-1 bg-slate-700 hover:bg-slate-600 rounded px-3 py-2 text-sm">
                  Annulla
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
