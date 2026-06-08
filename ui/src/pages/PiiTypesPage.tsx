import { useEffect, useState } from "react";
import { Pencil, Check, X } from "lucide-react";
import { api, PiiTypeItem } from "../lib/api";

interface Props { isAdmin: boolean; }

const CATEGORY_COLORS: Record<string, string> = {
  IDENTITY:   "#6366f1",
  CONTACT:    "#0ea5e9",
  FINANCIAL:  "#f59e0b",
  LEGAL:      "#64748b",
  VEHICLE:    "#d97706",
  NETWORK:    "#22c55e",
  CREDENTIAL: "#ef4444",
};
const cc = (c: string) => CATEGORY_COLORS[c] ?? "#94a3b8";

const ACTION_BADGE: Record<string, string> = {
  protect: "bg-indigo-500/20 text-indigo-300",
  keep:    "bg-emerald-500/20 text-emerald-300",
  redact:  "bg-red-500/20 text-red-300",
};

export function PiiTypesPage({ isAdmin }: Props) {
  const [types, setTypes]   = useState<PiiTypeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<Partial<PiiTypeItem>>({});

  function load() {
    setLoading(true);
    api.listPiiTypes()
      .then(setTypes)
      .catch(() => setError("Failed to load."))
      .finally(() => setLoading(false));
  }
  useEffect(() => { load(); }, []);

  function startEdit(t: PiiTypeItem) {
    setEditing(t.code);
    setEditForm({ default_action: t.default_action, faker_strategy: t.faker_strategy ?? "", description: t.description ?? "" });
  }

  async function saveEdit(code: string) {
    setError(null);
    try {
      await api.updatePiiType(code, {
        default_action: editForm.default_action,
        faker_strategy: editForm.faker_strategy || undefined,
        description: editForm.description || undefined,
      });
      setEditing(null);
      load();
    } catch { setError("Save failed."); }
  }

  async function toggleEnabled(t: PiiTypeItem) {
    try { await api.updatePiiType(t.code, { enabled: !t.enabled }); load(); }
    catch { setError("Update failed."); }
  }

  const categories = Array.from(new Set(types.map(t => t.category))).sort();

  if (!isAdmin) return <p className="text-slate-400">Admin access required.</p>;

  return (
    <div>
      <div className="mb-4">
        <h1 className="text-lg font-semibold">PII Type Registry</h1>
        <p className="text-sm text-slate-400 mt-1">
          Registro di tutti i tipi PII — category, azione di default, strategia Faker.
        </p>
      </div>

      {error && <p className="text-red-400 mb-3 text-sm">{error}</p>}

      {loading ? <p className="text-slate-400 text-sm">Loading...</p> : (
        <div className="flex flex-col gap-4">
          {categories.map(cat => (
            <div key={cat}>
              <div className="flex items-center gap-2 mb-2">
                <div className="w-2 h-2 rounded-full" style={{ background: cc(cat) }} />
                <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">{cat}</span>
              </div>
              <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-slate-600 border-b border-slate-700 text-xs">
                      <th className="px-4 py-2">Codice</th>
                      <th className="px-4 py-2">Nome</th>
                      <th className="px-4 py-2">Default action</th>
                      <th className="px-4 py-2">Faker strategy</th>
                      <th className="px-4 py-2">Rev.</th>
                      <th className="px-4 py-2 text-right">Azioni</th>
                    </tr>
                  </thead>
                  <tbody>
                    {types.filter(t => t.category === cat).map(t => (
                      <tr key={t.code} className={`border-b border-slate-700/40 ${!t.enabled ? "opacity-40" : ""}`}>
                        <td className="px-4 py-2">
                          <span className="font-mono text-xs font-semibold" style={{ color: cc(t.category) }}>{t.code}</span>
                        </td>
                        <td className="px-4 py-2 text-xs text-slate-300">{t.display_name}</td>
                        <td className="px-4 py-2">
                          {editing === t.code ? (
                            <select value={editForm.default_action} onChange={e => setEditForm({ ...editForm, default_action: e.target.value })}
                              className="bg-slate-900 border border-slate-600 rounded px-2 py-1 text-xs">
                              <option value="protect">protect</option>
                              <option value="keep">keep</option>
                              <option value="redact">redact</option>
                            </select>
                          ) : (
                            <span className={`text-xs px-2 py-0.5 rounded-full ${ACTION_BADGE[t.default_action] ?? "bg-slate-700 text-slate-300"}`}>
                              {t.default_action}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-2">
                          {editing === t.code ? (
                            <input type="text" value={editForm.faker_strategy ?? ""}
                              onChange={e => setEditForm({ ...editForm, faker_strategy: e.target.value })}
                              className="bg-slate-900 border border-slate-600 rounded px-2 py-1 text-xs font-mono w-28" />
                          ) : (
                            <span className="text-xs font-mono text-slate-400">{t.faker_strategy ?? "—"}</span>
                          )}
                        </td>
                        <td className="px-4 py-2 text-xs text-slate-500">{t.reversible ? "✓" : "—"}</td>
                        <td className="px-4 py-2">
                          <div className="flex gap-1.5 justify-end">
                            {editing === t.code ? (
                              <>
                                <button onClick={() => saveEdit(t.code)} className="hover:text-emerald-400 text-slate-400"><Check size={13} /></button>
                                <button onClick={() => setEditing(null)} className="hover:text-red-400 text-slate-400"><X size={13} /></button>
                              </>
                            ) : (
                              <>
                                <button onClick={() => startEdit(t)} className="hover:text-white text-slate-400"><Pencil size={13} /></button>
                                <button onClick={() => toggleEnabled(t)} className="hover:text-white text-slate-400">
                                  {t.enabled ? <Check size={13} /> : <X size={13} />}
                                </button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
