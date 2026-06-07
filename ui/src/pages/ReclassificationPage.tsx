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
const tc = (t: string) => TYPE_COLORS[t] ?? "#94a3b8";

function trunc(s: string | null | undefined, n: number) {
  if (!s) return null;
  return s.length > n ? s.slice(0, n) + "…" : s;
}

// ── Bipartite graph ───────────────────────────────────────────────────────────
const W       = 560;
const NODE_W  = 100;
const NODE_H  = 30;
const FROM_X  = 14;
const TO_X    = W - NODE_W - 14;
const V_PAD   = 28;
const V_STEP  = 52;

function BiGraph({ rules, hovered, onHover }: {
  rules: ReclassificationRule[];
  hovered: string | null;
  onHover: (id: string | null) => void;
}) {
  // Unique types in stable order
  const fromTypes = Array.from(new Set(rules.map(r => r.from_type)));
  const toTypes   = Array.from(new Set(rules.map(r => r.to_type ?? "__discard__")));

  const nLeft  = fromTypes.length;
  const nRight = toTypes.length;
  const H = V_PAD * 2 + Math.max(nLeft, nRight) * V_STEP;

  const fromY = (t: string) => {
    const i = fromTypes.indexOf(t);
    return V_PAD + i * (H - 2 * V_PAD) / Math.max(nLeft - 1, 1);
  };
  const toY = (t: string) => {
    const i = toTypes.indexOf(t);
    return V_PAD + i * (H - 2 * V_PAD) / Math.max(nRight - 1, 1);
  };

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="block">
      <defs>
        {[...fromTypes, ...toTypes.filter(t => t !== "__discard__")].map(t => (
          <marker key={t} id={`g-arr-${t}`} markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill={tc(t)} />
          </marker>
        ))}
        <marker id="g-arr-discard" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#ef4444" />
        </marker>
      </defs>

      {/* Arrows */}
      {rules.map(rule => {
        const x1 = FROM_X + NODE_W;
        const y1 = fromY(rule.from_type);
        const x2 = TO_X;
        const y2 = toY(rule.to_type ?? "__discard__");
        const mx = (x1 + x2) / 2;
        const my = (y1 + y2) / 2;
        const isH = hovered === rule.id;
        const dis = !rule.enabled;
        const arrowColor = rule.to_type ? tc(rule.from_type) : "#ef4444";
        const markerId = rule.to_type ? `g-arr-${rule.from_type}` : "g-arr-discard";

        const label1 = trunc(rule.context_pattern, 30) ?? trunc(rule.entity_pattern, 30);
        const label2 = rule.context_pattern && rule.entity_pattern ? trunc(rule.entity_pattern, 22) : null;

        return (
          <g key={rule.id}
            onMouseEnter={() => onHover(rule.id)}
            onMouseLeave={() => onHover(null)}
            style={{ opacity: dis ? 0.35 : 1 }}>

            <line x1={x1} y1={y1} x2={x2 - 4} y2={y2}
              stroke={arrowColor} strokeWidth={isH ? 2 : 1}
              strokeDasharray={dis ? "4 3" : undefined}
              markerEnd={`url(#${markerId})`} />

            {/* label on arrow — small, midpoint */}
            {label1 && (
              <text x={mx} y={my - (label2 ? 6 : 3)} textAnchor="middle"
                fontSize={8} fill={isH ? "#e2e8f0" : "#64748b"}
                fontFamily="monospace" className="pointer-events-none select-none">
                {label1}
              </text>
            )}
            {label2 && (
              <text x={mx} y={my + 5} textAnchor="middle"
                fontSize={8} fill={isH ? "#c4b5fd" : "#4c3d7a"}
                fontFamily="monospace" className="pointer-events-none select-none">
                {label2}
              </text>
            )}
            {isH && rule.description && (
              <text x={mx} y={my + (label1 ? 16 : 6)} textAnchor="middle"
                fontSize={7.5} fill="#94a3b8"
                className="pointer-events-none select-none">
                {trunc(rule.description, 48)}
              </text>
            )}
          </g>
        );
      })}

      {/* FROM nodes */}
      {fromTypes.map(t => {
        const cy = fromY(t);
        const color = tc(t);
        return (
          <g key={`from-${t}`}>
            <rect x={FROM_X} y={cy - NODE_H / 2} width={NODE_W} height={NODE_H} rx={5}
              fill={color + "22"} stroke={color} strokeWidth={1.5} />
            <text x={FROM_X + NODE_W / 2} y={cy + 4} textAnchor="middle"
              fontSize={10} fontWeight={700} fill={color} className="select-none">
              {t}
            </text>
          </g>
        );
      })}

      {/* TO nodes */}
      {toTypes.map(t => {
        const cy = toY(t);
        const isDiscard = t === "__discard__";
        const color = isDiscard ? "#ef4444" : tc(t);
        return (
          <g key={`to-${t}`}>
            <rect x={TO_X} y={cy - NODE_H / 2} width={NODE_W} height={NODE_H} rx={5}
              fill={color + "22"} stroke={color} strokeWidth={1.5}
              strokeDasharray={isDiscard ? "4 2" : undefined} />
            <text x={TO_X + NODE_W / 2} y={cy + 4} textAnchor="middle"
              fontSize={10} fontWeight={700} fill={color} className="select-none">
              {isDiscard ? "discard" : t}
            </text>
          </g>
        );
      })}

      {rules.length === 0 && (
        <text x={W / 2} y={50} textAnchor="middle" fill="#475569" fontSize={12}>
          Nessuna regola
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
  const [rules, setRules]             = useState<ReclassificationRule[]>([]);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState<string | null>(null);
  const [showModal, setShowModal]     = useState(false);
  const [editTarget, setEditTarget]   = useState<ReclassificationRule | null>(null);
  const [form, setForm]               = useState(EMPTY_FORM);
  const [hovered, setHovered]         = useState<string | null>(null);

  function load() {
    setLoading(true);
    api.listReclassificationRules()
      .then(setRules)
      .catch(() => setError("Failed to load rules."))
      .finally(() => setLoading(false));
  }
  useEffect(() => { load(); }, []);

  function openAdd() { setForm(EMPTY_FORM); setEditTarget(null); setShowModal(true); }
  function openEdit(r: ReclassificationRule) {
    setForm({
      from_type: r.from_type, to_type: r.to_type ?? "",
      context_pattern: r.context_pattern ?? "", entity_pattern: r.entity_pattern ?? "",
      context_window: r.context_window, description: r.description,
    });
    setEditTarget(r); setShowModal(true);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault(); setError(null);
    const body = {
      ...form,
      to_type: form.to_type.trim() || null,
      context_pattern: form.context_pattern.trim() || null,
      entity_pattern: form.entity_pattern.trim() || null,
    };
    if (!body.context_pattern && !body.entity_pattern) {
      setError("Almeno un pattern è richiesto."); return;
    }
    try {
      if (editTarget) await api.updateReclassificationRule(editTarget.id, body);
      else             await api.createReclassificationRule(body);
      setShowModal(false); load();
    } catch { setError("Save failed."); }
  }

  async function handleToggle(r: ReclassificationRule) {
    try { await api.updateReclassificationRule(r.id, { enabled: !r.enabled }); load(); }
    catch { setError("Failed to update."); }
  }
  async function handleDelete(r: ReclassificationRule) {
    if (!confirm(`Eliminare "${r.description || r.from_type + " → " + (r.to_type ?? "discard")}"?`)) return;
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
            Post-detection: reclassifica un'entità in base al contesto o al suo testo.
          </p>
        </div>
        <button onClick={openAdd}
          className="flex items-center gap-1 bg-indigo-600 hover:bg-indigo-700 rounded px-3 py-2 text-sm">
          <Plus size={14} /> New rule
        </button>
      </div>

      {error && <p className="text-red-400 mb-3 text-sm">{error}</p>}

      <div className="flex gap-4 items-start">
        {/* Graph */}
        {!loading && (
          <div className="bg-slate-900 border border-slate-700 rounded-xl shrink-0" style={{ width: 560 }}>
            <BiGraph rules={rules} hovered={hovered} onHover={setHovered} />
          </div>
        )}

        {/* Rule list */}
        <div className="flex-1 min-w-0">
          {loading ? (
            <p className="text-slate-400 text-sm">Loading...</p>
          ) : (
            <div className="flex flex-col gap-1">
              {rules.map((r, i) => (
                <div key={r.id}
                  className={`flex items-center gap-2 px-3 py-2 rounded text-xs cursor-default transition-colors
                    ${hovered === r.id ? "bg-slate-700/70" : "bg-slate-800/50"}
                    ${!r.enabled ? "opacity-45" : ""}`}
                  onMouseEnter={() => setHovered(r.id)}
                  onMouseLeave={() => setHovered(null)}>
                  <span className="text-slate-600 w-4 shrink-0 text-right">{i + 1}</span>
                  <span className="font-bold shrink-0" style={{ color: tc(r.from_type) }}>{r.from_type}</span>
                  <span className="text-slate-600">→</span>
                  <span className="font-bold shrink-0" style={{ color: r.to_type ? tc(r.to_type) : "#ef4444" }}>
                    {r.to_type ?? "discard"}
                  </span>
                  <span className="text-slate-500 truncate flex-1">{r.description || "—"}</span>
                  <div className="flex gap-1.5 shrink-0">
                    <button onClick={() => handleToggle(r)} className="hover:text-white text-slate-500">
                      {r.enabled ? <Check size={12} /> : <X size={12} />}
                    </button>
                    <button onClick={() => openEdit(r)} className="hover:text-white text-slate-500">
                      <Pencil size={12} />
                    </button>
                    <button onClick={() => handleDelete(r)} className="hover:text-red-400 text-slate-500">
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              ))}
              {rules.length === 0 && (
                <p className="text-slate-500 text-xs">Nessuna regola.</p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Modal */}
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
                <span className="text-xs text-slate-400">Context pattern</span>
                <input type="text" value={form.context_pattern}
                  onChange={e => setForm({ ...form, context_pattern: e.target.value })}
                  placeholder='es. (?i)username\s*:\s*$'
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm font-mono" />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-violet-300">Entity pattern</span>
                <input type="text" value={form.entity_pattern}
                  onChange={e => setForm({ ...form, entity_pattern: e.target.value })}
                  placeholder='es. @'
                  className="bg-slate-900 border border-violet-800 rounded px-3 py-2 text-sm font-mono" />
              </label>
              <p className="text-xs text-slate-500">Almeno uno dei due pattern è obbligatorio. Se entrambi: AND.</p>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Finestra contesto (chars)</span>
                <input type="number" value={form.context_window}
                  onChange={e => setForm({ ...form, context_window: parseInt(e.target.value) || 60 })}
                  min={10} max={500}
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm w-24" />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Descrizione</span>
                <input type="text" value={form.description}
                  onChange={e => setForm({ ...form, description: e.target.value })}
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm" />
              </label>
              <div className="flex gap-2 mt-1">
                <button type="submit" className="flex-1 bg-indigo-600 hover:bg-indigo-700 rounded px-3 py-2 text-sm">
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
