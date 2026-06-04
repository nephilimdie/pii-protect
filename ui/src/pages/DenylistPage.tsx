import { useEffect, useState, FormEvent } from "react";
import { Plus, Trash2, Pencil, Check, X } from "lucide-react";
import { api, DenylistEntryItem } from "../lib/api";

interface Props {
  isAdmin: boolean;
}

const PII_TYPES = ["PERSON", "EMAIL", "PHONE", "ADDRESS", "DATE", "SECRET"];

export function DenylistPage({ isAdmin }: Props) {
  const [entries, setEntries] = useState<DenylistEntryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [editTarget, setEditTarget] = useState<DenylistEntryItem | null>(null);
  const [form, setForm] = useState({ pii_type: "PERSON", value: "", match_type: "exact_word", description: "" });

  function resetForm() {
    setForm({ pii_type: "PERSON", value: "", match_type: "exact_word", description: "" });
    setEditTarget(null);
  }

  function load() {
    setLoading(true);
    api.listDenylist()
      .then(setEntries)
      .catch(() => setError("Failed to load denylist."))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  function openCreate() { resetForm(); setShowModal(true); }

  function openEdit(e: DenylistEntryItem) {
    setForm({ pii_type: e.pii_type, value: e.value, match_type: e.match_type, description: e.description });
    setEditTarget(e);
    setShowModal(true);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (editTarget) {
        await api.updateDenylistEntry(editTarget.id, form);
      } else {
        await api.createDenylistEntry(form);
      }
      setShowModal(false);
      resetForm();
      load();
    } catch {
      setError("Save failed.");
    }
  }

  async function handleToggle(entry: DenylistEntryItem) {
    try {
      await api.updateDenylistEntry(entry.id, { enabled: !entry.enabled });
      load();
    } catch {
      setError("Failed to update entry.");
    }
  }

  async function handleDelete(entry: DenylistEntryItem) {
    if (!confirm(`Delete "${entry.value}" from denylist?`)) return;
    try {
      await api.deleteDenylistEntry(entry.id);
      load();
    } catch {
      setError("Failed to delete entry.");
    }
  }

  // Group entries by pii_type for display
  const grouped = entries.reduce<Record<string, DenylistEntryItem[]>>((acc, e) => {
    (acc[e.pii_type] ??= []).push(e);
    return acc;
  }, {});

  if (!isAdmin) {
    return <p className="text-slate-400">Admin access required.</p>;
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold">Entity Denylist</h1>
          <p className="text-sm text-slate-400 mt-1">
            Terms that must never be classified as PII. Changes take effect immediately.
          </p>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-1 bg-indigo-600 hover:bg-indigo-700 rounded px-3 py-2 text-sm"
        >
          <Plus size={14} />
          New term
        </button>
      </div>

      {error && <p className="text-red-400 mb-4 text-sm">{error}</p>}

      {loading ? (
        <p className="text-slate-400">Loading...</p>
      ) : (
        <div className="flex flex-col gap-4">
          {Object.entries(grouped).map(([piiType, items]) => (
            <div key={piiType} className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
              <div className="px-4 py-2 bg-slate-700/50 border-b border-slate-700">
                <span className="text-xs font-semibold text-indigo-400 uppercase tracking-wide">{piiType}</span>
                <span className="text-xs text-slate-500 ml-2">{items.length} terms</span>
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-slate-500 border-b border-slate-700">
                    <th className="px-4 py-2">Value</th>
                    <th className="px-4 py-2">Match</th>
                    <th className="px-4 py-2">Description</th>
                    <th className="px-4 py-2">Status</th>
                    <th className="px-4 py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((entry) => (
                    <tr key={entry.id} className="border-b border-slate-700/50 last:border-0">
                      <td className="px-4 py-2 font-mono text-slate-200">{entry.value}</td>
                      <td className="px-4 py-2">
                        <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${entry.match_type === "contains" ? "bg-amber-900/40 text-amber-400" : "bg-slate-700 text-slate-400"}`}>
                          {entry.match_type === "contains" ? "contains" : "exact"}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-slate-400 text-xs">{entry.description || "—"}</td>
                      <td className="px-4 py-2">
                        <button
                          onClick={() => handleToggle(entry)}
                          className={`flex items-center gap-1 text-xs rounded px-2 py-1 ${
                            entry.enabled
                              ? "bg-green-900/40 text-green-400 hover:bg-green-900/60"
                              : "bg-slate-700 text-slate-400 hover:bg-slate-600"
                          }`}
                        >
                          {entry.enabled ? <><Check size={10} /> active</> : <><X size={10} /> disabled</>}
                        </button>
                      </td>
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-2">
                          <button onClick={() => openEdit(entry)} className="text-slate-400 hover:text-white" title="Edit">
                            <Pencil size={14} />
                          </button>
                          <button onClick={() => handleDelete(entry)} className="text-red-400 hover:text-red-300" title="Delete">
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          {entries.length === 0 && (
            <p className="text-center text-slate-500 py-8">No terms configured</p>
          )}
        </div>
      )}

      {showModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 w-full max-w-md">
            <h2 className="font-semibold mb-4">
              {editTarget ? "Edit term" : "New term denylist"}
            </h2>
            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">PII Type</span>
                <select
                  value={form.pii_type}
                  onChange={(e) => setForm({ ...form, pii_type: e.target.value })}
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm"
                >
                  {PII_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Match type</span>
                <select
                  value={form.match_type}
                  onChange={(e) => setForm({ ...form, match_type: e.target.value })}
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm"
                >
                  <option value="exact_word">exact word — single word, stripped of honorifics</option>
                  <option value="contains">contains — entity text contains this phrase</option>
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Value (case-insensitive)</span>
                <input
                  type="text"
                  value={form.value}
                  onChange={(e) => setForm({ ...form, value: e.target.value })}
                  placeholder="es. coniuge"
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm font-mono"
                  required
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Descrizione</span>
                <input
                  type="text"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="Optional reason"
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm"
                />
              </label>
              <div className="flex gap-2 mt-2">
                <button type="submit" className="flex-1 bg-indigo-600 hover:bg-indigo-700 rounded px-3 py-2 text-sm">
                  {editTarget ? "Salva" : "Add"}
                </button>
                <button
                  type="button"
                  onClick={() => { setShowModal(false); resetForm(); }}
                  className="flex-1 bg-slate-700 hover:bg-slate-600 rounded px-3 py-2 text-sm"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
