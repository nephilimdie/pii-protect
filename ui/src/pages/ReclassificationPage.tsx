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

const NODE_R = 28;
const SVG_W = 900;
const SVG_H = 460;

function layoutNodes(types: string[]): Record<string, { x: number; y: number }> {
  const positions: Record<string, { x: number; y: number }> = {};
  const n = types.length;
  if (n === 0) return positions;
  types.forEach((t, i) => {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2;
    positions[t] = {
      x: SVG_W / 2 + (SVG_W / 2 - NODE_R - 30) * Math.cos(angle),
      y: SVG_H / 2 + (SVG_H / 2 - NODE_R - 20) * Math.sin(angle),
    };
  });
  return positions;
}

function edgePath(x1: number, y1: number, x2: number, y2: number, curvature = 0.25): string {
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
  const dx = x2 - x1, dy = y2 - y1;
  return `M ${x1} ${y1} Q ${mx - dy * curvature} ${my + dx * curvature} ${x2} ${y2}`;
}

function bezierMid(x1: number, y1: number, x2: number, y2: number, curvature = 0.25) {
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
  const dx = x2 - x1, dy = y2 - y1;
  const cx = mx - dy * curvature, cy = my + dx * curvature;
  return { x: 0.25 * x1 + 0.5 * cx + 0.25 * x2, y: 0.25 * y1 + 0.5 * cy + 0.25 * y2 };
}

function truncate(s: string | null, n = 28) {
  if (!s) return "";
  return s.length > n ? s.slice(0, n) + "…" : s;
}

const EMPTY_FORM = {
  from_type: "PERSON",
  to_type: "",
  context_pattern: "",
  entity_pattern: "",
  context_window: 60,
  description: "",
};

export function ReclassificationPage({ isAdmin }: Props) {
  const [rules, setRules] = useState<ReclassificationRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [editTarget, setEditTarget] = useState<ReclassificationRule | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [hoveredRule, setHoveredRule] = useState<string | null>(null);

  function load() {
    setLoading(true);
    api.listReclassificationRules()
      .then(setRules)
      .catch(() => setError("Failed to load rules."))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  const types = Array.from(new Set(
    rules.flatMap(r => [r.from_type, ...(r.to_type ? [r.to_type] : [])])
  )).sort();
  const positions = layoutNodes(types);

  function openAdd() {
    setForm(EMPTY_FORM);
    setEditTarget(null);
    setShowModal(true);
  }

  function openEdit(r: ReclassificationRule) {
    setForm({
      from_type: r.from_type,
      to_type: r.to_type ?? "",
      context_pattern: r.context_pattern ?? "",
      entity_pattern: r.entity_pattern ?? "",
      context_window: r.context_window,
      description: r.description,
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
      if (editTarget) {
        await api.updateReclassificationRule(editTarget.id, body);
      } else {
        await api.createReclassificationRule(body);
      }
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
        <button onClick={openAdd} className="flex items-center gap-1 bg-indigo-600 hover:bg-indigo-700 rounded px-3 py-2 text-sm">
          <Plus size={14} /> New rule
        </button>
      </div>

      {error && <p className="text-red-400 mb-4 text-sm">{error}</p>}

      {/* SVG Graph */}
      {!loading && types.length > 0 && (
        <div className="bg-slate-800 border border-slate-700 rounded-xl mb-6 overflow-hidden">
          <svg width="100%" viewBox={`0 0 ${SVG_W} ${SVG_H}`} className="block">
            <defs>
              {types.map(t => (
                <marker key={t} id={`arrow-${t}`} markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
                  <path d="M0,0 L0,6 L8,3 z" fill={typeColor(t)} />
                </marker>
              ))}
              <marker id="arrow-discard" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
                <path d="M0,0 L0,6 L8,3 z" fill="#ef4444" />
              </marker>
            </defs>

            {rules.map(rule => {
              const from = positions[rule.from_type];
              const to = rule.to_type ? positions[rule.to_type] : null;
              if (!from) return null;

              const isHovered = hoveredRule === rule.id;
              const strokeColor = rule.to_type ? typeColor(rule.from_type) : "#ef4444";
              const opacity = !rule.enabled ? 0.3 : isHovered ? 1 : 0.7;
              const label = rule.entity_pattern
                ? (rule.context_pattern ? `ctx+ent` : `ent: ${truncate(rule.entity_pattern, 22)}`)
                : truncate(rule.context_pattern, 28);

              if (!to || rule.from_type === rule.to_type) {
                const tx = from.x, ty = from.y - NODE_R - 18;
                return (
                  <g key={rule.id} onMouseEnter={() => setHoveredRule(rule.id)} onMouseLeave={() => setHoveredRule(null)}>
                    <ellipse cx={tx} cy={ty} rx={18} ry={12} fill="none" stroke={strokeColor}
                      strokeWidth={isHovered ? 2.5 : 1.5} strokeDasharray={!rule.enabled ? "4 3" : undefined} opacity={opacity} />
                    {isHovered && (
                      <text x={tx} y={ty - 18} textAnchor="middle" fontSize={10} fill="#e2e8f0">{rule.to_type ?? "discard"}</text>
                    )}
                  </g>
                );
              }

              const angle = Math.atan2(to.y - from.y, to.x - from.x);
              const x1 = from.x + NODE_R * Math.cos(angle);
              const y1 = from.y + NODE_R * Math.sin(angle);
              const x2 = to.x - (NODE_R + 6) * Math.cos(angle);
              const y2 = to.y - (NODE_R + 6) * Math.sin(angle);
              const mid = bezierMid(x1, y1, x2, y2);
              const markerId = rule.to_type ? `arrow-${rule.from_type}` : "arrow-discard";

              return (
                <g key={rule.id} onMouseEnter={() => setHoveredRule(rule.id)} onMouseLeave={() => setHoveredRule(null)}>
                  <path d={edgePath(x1, y1, x2, y2)} fill="none" stroke={strokeColor}
                    strokeWidth={isHovered ? 2.5 : 1.5} strokeDasharray={!rule.enabled ? "5 4" : undefined}
                    markerEnd={`url(#${markerId})`} opacity={opacity} />
                  {isHovered && (
                    <text x={mid.x} y={mid.y - 8} textAnchor="middle" fontSize={10} fill="#e2e8f0" className="pointer-events-none">
                      {label}
                    </text>
                  )}
                </g>
              );
            })}

            {types.map(t => {
              const pos = positions[t];
              if (!pos) return null;
              return (
                <g key={t}>
                  <circle cx={pos.x} cy={pos.y} r={NODE_R} fill={typeColor(t)} opacity={0.15} />
                  <circle cx={pos.x} cy={pos.y} r={NODE_R} fill="none" stroke={typeColor(t)} strokeWidth={2} />
                  <text x={pos.x} y={pos.y + 4} textAnchor="middle" fontSize={9} fontWeight={600}
                    fill={typeColor(t)} className="pointer-events-none select-none">
                    {t.length > 10 ? t.slice(0, 9) + "…" : t}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      )}

      {/* Rules list */}
      {loading ? (
        <p className="text-slate-400">Loading...</p>
      ) : (
        <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-700">
                <th className="px-4 py-3">Da</th>
                <th className="px-4 py-3">A</th>
                <th className="px-4 py-3">Context pattern</th>
                <th className="px-4 py-3">Entity pattern</th>
                <th className="px-4 py-3">Win</th>
                <th className="px-4 py-3">Descrizione</th>
                <th className="px-4 py-3 text-right">Azioni</th>
              </tr>
            </thead>
            <tbody>
              {rules.map(r => (
                <tr key={r.id}
                  className={`border-b border-slate-700/50 transition-colors ${hoveredRule === r.id ? "bg-slate-700/40" : ""} ${!r.enabled ? "opacity-50" : ""}`}
                  onMouseEnter={() => setHoveredRule(r.id)}
                  onMouseLeave={() => setHoveredRule(null)}>
                  <td className="px-4 py-3">
                    <span className="text-xs font-semibold px-2 py-0.5 rounded-full"
                      style={{ background: typeColor(r.from_type) + "33", color: typeColor(r.from_type) }}>
                      {r.from_type}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {r.to_type ? (
                      <span className="text-xs font-semibold px-2 py-0.5 rounded-full"
                        style={{ background: typeColor(r.to_type) + "33", color: typeColor(r.to_type) }}>
                        {r.to_type}
                      </span>
                    ) : (
                      <span className="text-xs text-red-400 font-mono">discard</span>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-300 max-w-[180px] truncate">
                    {r.context_pattern ?? <span className="text-slate-600">—</span>}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-violet-300 max-w-[120px] truncate">
                    {r.entity_pattern ?? <span className="text-slate-600">—</span>}
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs">{r.context_window}</td>
                  <td className="px-4 py-3 text-slate-400 text-xs">{r.description || "—"}</td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2 justify-end">
                      <button onClick={() => handleToggle(r)} className="hover:text-white text-slate-400" title="Toggle">
                        {r.enabled ? <Check size={14} /> : <X size={14} />}
                      </button>
                      <button onClick={() => openEdit(r)} className="hover:text-white text-slate-400" title="Edit">
                        <Pencil size={14} />
                      </button>
                      <button onClick={() => handleDelete(r)} className="hover:text-red-400 text-slate-400" title="Delete">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {rules.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-500">Nessuna regola</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

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
                <span className="text-xs text-slate-400">
                  Context pattern — regex nel testo prima dell'entità (opzionale)
                </span>
                <input type="text" value={form.context_pattern}
                  onChange={e => setForm({ ...form, context_pattern: e.target.value })}
                  placeholder='es. (?i)username\s*:\s*$'
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm font-mono" />
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-xs text-violet-300">
                  Entity pattern — regex nel testo dell'entità stessa (opzionale)
                </span>
                <input type="text" value={form.entity_pattern}
                  onChange={e => setForm({ ...form, entity_pattern: e.target.value })}
                  placeholder='es. @ — contiene una chiocciola'
                  className="bg-slate-900 border border-violet-800 rounded px-3 py-2 text-sm font-mono" />
              </label>

              <p className="text-xs text-slate-500">
                Se entrambi i pattern sono impostati, devono corrispondere entrambi (AND).
                Almeno uno è obbligatorio.
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
