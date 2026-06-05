import { useEffect, useState, FormEvent } from "react";
import { Plus, Trash2, Pencil, Check, X } from "lucide-react";
import { api, ContextWordItem } from "../lib/api";

interface Props { isAdmin: boolean; }

const PII_TYPES = ["PERSON", "EMAIL", "PHONE", "ADDRESS", "DATE", "IBAN", "FISCAL_CODE"];

export function ContextWordsPage({ isAdmin }: Props) {
  const [entries, setEntries] = useState<ContextWordItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [editTarget, setEditTarget] = useState<ContextWordItem | null>(null);
  const [form, setForm] = useState({ entity_type: "PERSON", word: "", description: "" });

  function resetForm() {
    setForm({ entity_type: "PERSON", word: "", description: "" });
    setEditTarget(null);
  }

  function load() {
    setLoading(true);
    api.listContextWords()
      .then(setEntries)
      .catch(() => setError("Failed to load context words."))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  function openEdit(e: ContextWordItem) {
    setForm({ entity_type: e.entity_type, word: e.word, description: e.description });
    setEditTarget(e);
    setShowModal(true);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (editTarget) {
        await api.updateContextWord(editTarget.id, form);
      } else {
        await api.createContextWord(form);
      }
      setShowModal(false);
      resetForm();
      load();
    } catch {
      setError("Save failed.");
    }
  }

  async function handleToggle(entry: ContextWordItem) {
    try {
      await api.updateContextWord(entry.id, { enabled: !entry.enabled });
      load();
    } catch {
      setError("Failed to update.");
    }
  }

  async function handleDelete(entry: ContextWordItem) {
    if (!confirm(`Delete context word "${entry.word}"?`)) return;
    try {
      await api.deleteContextWord(entry.id);
      load();
    } catch {
      setError("Failed to delete.");
    }
  }

  const grouped = entries.reduce<Record<string, ContextWordItem[]>>((acc, e) => {
    (acc[e.entity_type] ??= []).push(e);
    return acc;
  }, {});

  if (!isAdmin) return <p className="text-slate-400">Admin access required.</p>;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold">Presidio Context Words</h1>
          <p className="text-sm text-slate-400 mt-1">
            Words that boost Presidio's confidence when found near an entity.
            E.g. "coniuge" before a name → PERSON score raised to 0.90.
          </p>
        </div>
        <button onClick={() => { resetForm(); setShowModal(true); }}
          className="flex items-center gap-1 bg-indigo-600 hover:bg-indigo-700 rounded px-3 py-2 text-sm">
          <Plus size={14} /> New word
        </button>
      </div>

      {error && <p className="text-red-400 mb-4 text-sm">{error}</p>}

      {loading ? <p className="text-slate-400">Loading...</p> : (
        <div className="flex flex-col gap-4">
          {Object.entries(grouped).map(([type, items]) => (
            <div key={type} className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
              <div className="px-4 py-2 bg-slate-700/50 border-b border-slate-700 flex items-center gap-2">
                <span className="text-xs font-semibold text-indigo-400 uppercase tracking-wide">{type}</span>
                <span className="text-xs text-slate-500">{items.filter(i => i.enabled).length} active</span>
              </div>
              <div className="flex flex-wrap gap-2 p-3">
                {items.map(entry => (
                  <div key={entry.id}
                    className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs border ${
                      entry.enabled
                        ? "bg-indigo-900/30 border-indigo-700 text-indigo-300"
                        : "bg-slate-700/40 border-slate-600 text-slate-500"
                    }`}>
                    <span className="font-mono">{entry.word}</span>
                    <button onClick={() => handleToggle(entry)} className="hover:text-white ml-1" title="Toggle">
                      {entry.enabled ? <Check size={10} /> : <X size={10} />}
                    </button>
                    <button onClick={() => openEdit(entry)} className="hover:text-white" title="Edit">
                      <Pencil size={10} />
                    </button>
                    <button onClick={() => handleDelete(entry)} className="hover:text-red-400" title="Delete">
                      <Trash2 size={10} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ))}
          {entries.length === 0 && <p className="text-center text-slate-500 py-8">No context words configured</p>}
        </div>
      )}

      {showModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 w-full max-w-sm">
            <h2 className="font-semibold mb-4">{editTarget ? "Edit context word" : "New context word"}</h2>
            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Entity type</span>
                <select value={form.entity_type} onChange={e => setForm({ ...form, entity_type: e.target.value })}
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm">
                  {PII_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Word (case-insensitive, matched in surrounding text)</span>
                <input type="text" value={form.word} onChange={e => setForm({ ...form, word: e.target.value })}
                  placeholder="e.g. coniuge" required
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm font-mono" />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Description</span>
                <input type="text" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
                  placeholder="Optional reason"
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm" />
              </label>
              <div className="flex gap-2 mt-2">
                <button type="submit" className="flex-1 bg-indigo-600 hover:bg-indigo-700 rounded px-3 py-2 text-sm">
                  {editTarget ? "Save" : "Add"}
                </button>
                <button type="button" onClick={() => { setShowModal(false); resetForm(); }}
                  className="flex-1 bg-slate-700 hover:bg-slate-600 rounded px-3 py-2 text-sm">Cancel</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
