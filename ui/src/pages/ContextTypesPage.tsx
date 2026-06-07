import { useEffect, useState, FormEvent } from "react";
import { Plus, Trash2, Pencil, Check, X } from "lucide-react";
import { api, ContextTypeItem, DomainPolicy } from "../lib/api";

interface Props { isAdmin: boolean; }

const MODE_COLORS: Record<string, string> = {
  tag: "#6366f1",
  surrogate: "#10b981",
};

const EMPTY: Partial<ContextTypeItem> & { code: string } = {
  code: "", display_name: "", domain: "", default_mode: "tag", description: "",
};

export function ContextTypesPage({ isAdmin }: Props) {
  const [items, setItems]       = useState<ContextTypeItem[]>([]);
  const [policies, setPolicies] = useState<DomainPolicy[]>([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [editTarget, setEditTarget] = useState<ContextTypeItem | null>(null);
  const [form, setForm]         = useState(EMPTY);

  function load() {
    setLoading(true);
    Promise.all([api.listContextTypes(), api.listDomainPolicies()])
      .then(([ct, dp]) => { setItems(ct); setPolicies(dp); })
      .catch(() => setError("Failed to load."))
      .finally(() => setLoading(false));
  }
  useEffect(() => { load(); }, []);

  function openAdd() { setForm({ ...EMPTY }); setEditTarget(null); setShowModal(true); }
  function openEdit(r: ContextTypeItem) {
    setForm({ code: r.code, display_name: r.display_name, domain: r.domain ?? "", default_mode: r.default_mode, description: r.description ?? "" });
    setEditTarget(r); setShowModal(true);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault(); setError(null);
    const body = { ...form, domain: form.domain || undefined };
    try {
      if (editTarget) await api.updateContextType(editTarget.code, body);
      else             await api.createContextType(body as any);
      setShowModal(false); load();
    } catch { setError("Save failed."); }
  }

  async function handleToggle(r: ContextTypeItem) {
    try { await api.updateContextType(r.code, { enabled: !r.enabled }); load(); }
    catch { setError("Update failed."); }
  }

  async function handleDelete(r: ContextTypeItem) {
    if (!confirm(`Eliminare il context type "${r.code}"?`)) return;
    try { await api.deleteContextType(r.code); load(); }
    catch { setError("Delete failed."); }
  }

  if (!isAdmin) return <p className="text-slate-400">Admin access required.</p>;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-lg font-semibold">Context Types</h1>
          <p className="text-sm text-slate-400 mt-1">
            Definisce i contesti d'uso — ognuno ha una policy e un mode di default.
          </p>
        </div>
        <button onClick={openAdd} className="flex items-center gap-1 bg-indigo-600 hover:bg-indigo-700 rounded px-3 py-2 text-sm">
          <Plus size={14} /> New context
        </button>
      </div>

      {error && <p className="text-red-400 mb-3 text-sm">{error}</p>}

      {loading ? <p className="text-slate-400 text-sm">Loading...</p> : (
        <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-700 text-xs">
                <th className="px-4 py-3">Codice</th>
                <th className="px-4 py-3">Nome</th>
                <th className="px-4 py-3">Policy (domain)</th>
                <th className="px-4 py-3">Mode</th>
                <th className="px-4 py-3">Descrizione</th>
                <th className="px-4 py-3 text-right">Azioni</th>
              </tr>
            </thead>
            <tbody>
              {items.map(r => (
                <tr key={r.code} className={`border-b border-slate-700/50 ${!r.enabled ? "opacity-50" : ""}`}>
                  <td className="px-4 py-3 font-mono text-xs text-slate-300">{r.code}</td>
                  <td className="px-4 py-3 font-medium text-sm">{r.display_name}</td>
                  <td className="px-4 py-3 text-xs text-slate-400">{r.domain ?? <span className="text-slate-600">—</span>}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs font-semibold px-2 py-0.5 rounded-full"
                      style={{ background: (MODE_COLORS[r.default_mode] ?? "#64748b") + "33", color: MODE_COLORS[r.default_mode] ?? "#94a3b8" }}>
                      {r.default_mode}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">{r.description || "—"}</td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2 justify-end">
                      <button onClick={() => handleToggle(r)} className="hover:text-white text-slate-400">
                        {r.enabled ? <Check size={13} /> : <X size={13} />}
                      </button>
                      <button onClick={() => openEdit(r)} className="hover:text-white text-slate-400"><Pencil size={13} /></button>
                      <button onClick={() => handleDelete(r)} className="hover:text-red-400 text-slate-400"><Trash2 size={13} /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500">Nessun context type</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 w-full max-w-lg">
            <h2 className="font-semibold mb-4">{editTarget ? "Modifica context type" : "Nuovo context type"}</h2>
            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              {!editTarget && (
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Codice (immutabile)</span>
                  <input type="text" value={form.code}
                    onChange={e => setForm({ ...form, code: e.target.value.toLowerCase().replace(/\s+/g, "_") })}
                    placeholder="es. fine_appeal" required
                    className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm font-mono" />
                </label>
              )}
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Nome visualizzato</span>
                <input type="text" value={form.display_name}
                  onChange={e => setForm({ ...form, display_name: e.target.value })}
                  required className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm" />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Policy (domain)</span>
                <select value={form.domain ?? ""}
                  onChange={e => setForm({ ...form, domain: e.target.value })}
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm">
                  <option value="">— nessuna (usa default) —</option>
                  {policies.map(p => (
                    <option key={p.domain} value={p.domain}>{p.domain}</option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Mode di default</span>
                <select value={form.default_mode}
                  onChange={e => setForm({ ...form, default_mode: e.target.value })}
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm">
                  <option value="tag">tag — token opaco [TIPO_1]</option>
                  <option value="surrogate">surrogate — valore finto realistico</option>
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Descrizione</span>
                <input type="text" value={form.description ?? ""}
                  onChange={e => setForm({ ...form, description: e.target.value })}
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm" />
              </label>
              <div className="flex gap-2 mt-1">
                <button type="submit" className="flex-1 bg-indigo-600 hover:bg-indigo-700 rounded px-3 py-2 text-sm">
                  {editTarget ? "Salva" : "Crea"}
                </button>
                <button type="button" onClick={() => setShowModal(false)}
                  className="flex-1 bg-slate-700 hover:bg-slate-600 rounded px-3 py-2 text-sm">Annulla</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
