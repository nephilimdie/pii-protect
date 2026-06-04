import { useEffect, useState, FormEvent } from "react";
import { Plus, Trash2, Pencil, Check, X } from "lucide-react";
import { api, RegexPatternItem } from "../lib/api";

interface Props {
  isAdmin: boolean;
}

const FLAG_OPTIONS = ["", "IGNORECASE", "MULTILINE", "DOTALL", "IGNORECASE,MULTILINE"];

export function RegexPatternsPage({ isAdmin }: Props) {
  const [patterns, setPatterns] = useState<RegexPatternItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [editTarget, setEditTarget] = useState<RegexPatternItem | null>(null);

  const [form, setForm] = useState({
    pii_type: "",
    pattern: "",
    flags: "",
    capture_group: 0,
    description: "",
  });

  function resetForm() {
    setForm({ pii_type: "", pattern: "", flags: "", capture_group: 0, description: "" });
    setEditTarget(null);
  }

  function load() {
    setLoading(true);
    api.listRegexPatterns()
      .then(setPatterns)
      .catch(() => setError("Failed to load patterns."))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  function openCreate() {
    resetForm();
    setShowModal(true);
  }

  function openEdit(p: RegexPatternItem) {
    setForm({
      pii_type: p.pii_type,
      pattern: p.pattern,
      flags: p.flags,
      capture_group: p.capture_group,
      description: p.description,
    });
    setEditTarget(p);
    setShowModal(true);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (editTarget) {
        await api.updateRegexPattern(editTarget.id, form);
      } else {
        await api.createRegexPattern(form);
      }
      setShowModal(false);
      resetForm();
      load();
    } catch {
      setError("Invalid pattern or network error.");
    }
  }

  async function handleToggle(p: RegexPatternItem) {
    try {
      await api.updateRegexPattern(p.id, { enabled: !p.enabled });
      load();
    } catch {
      setError("Failed to update pattern.");
    }
  }

  async function handleDelete(p: RegexPatternItem) {
    if (!confirm(`Delete pattern "${p.pii_type}"?`)) return;
    try {
      await api.deleteRegexPattern(p.id);
      load();
    } catch {
      setError("Failed to delete pattern.");
    }
  }

  if (!isAdmin) {
    return <p className="text-slate-400">Admin access required.</p>;
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold">Regex Pattern</h1>
          <p className="text-sm text-slate-400 mt-1">
            Regex patterns used by the deterministic detection layer. Changes take effect immediately.
          </p>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-1 bg-indigo-600 hover:bg-indigo-700 rounded px-3 py-2 text-sm"
        >
          <Plus size={14} />
          New pattern
        </button>
      </div>

      {error && <p className="text-red-400 mb-4 text-sm">{error}</p>}

      {loading ? (
        <p className="text-slate-400">Loading...</p>
      ) : (
        <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-700">
                <th className="px-4 py-3">PII Type</th>
                <th className="px-4 py-3">Pattern</th>
                <th className="px-4 py-3">Flag</th>
                <th className="px-4 py-3">Gruppo</th>
                <th className="px-4 py-3">Description</th>
                <th className="px-4 py-3">Stato</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {patterns.map((p) => (
                <tr key={p.id} className="border-b border-slate-700/50">
                  <td className="px-4 py-3 font-mono font-semibold text-indigo-300">{p.pii_type}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-300 max-w-xs truncate" title={p.pattern}>
                    {p.pattern}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">{p.flags || "—"}</td>
                  <td className="px-4 py-3 text-center text-slate-400">{p.capture_group}</td>
                  <td className="px-4 py-3 text-slate-400 text-xs max-w-xs truncate" title={p.description}>
                    {p.description || "—"}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => handleToggle(p)}
                      className={`flex items-center gap-1 text-xs rounded px-2 py-1 ${
                        p.enabled
                          ? "bg-green-900/40 text-green-400 hover:bg-green-900/60"
                          : "bg-slate-700 text-slate-400 hover:bg-slate-600"
                      }`}
                    >
                      {p.enabled ? <><Check size={10} /> attivo</> : <><X size={10} /> disabilitato</>}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => openEdit(p)}
                        className="text-slate-400 hover:text-white"
                        title="Edit"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        onClick={() => handleDelete(p)}
                        className="text-red-400 hover:text-red-300"
                        title="Delete"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {patterns.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-500">No patterns configured</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 w-full max-w-lg">
            <h2 className="font-semibold mb-4">
              {editTarget ? "Edit pattern" : "New pattern"}
            </h2>
            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">PII Type</span>
                <input
                  type="text"
                  value={form.pii_type}
                  onChange={(e) => setForm({ ...form, pii_type: e.target.value.toUpperCase() })}
                  placeholder="es. FISCAL_CODE"
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm font-mono"
                  required
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Regex pattern</span>
                <input
                  type="text"
                  value={form.pattern}
                  onChange={(e) => setForm({ ...form, pattern: e.target.value })}
                  placeholder="es. \b[A-Z]{6}\d{2}..."
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm font-mono"
                  required
                />
              </label>
              <div className="flex gap-3">
                <label className="flex flex-col gap-1 flex-1">
                  <span className="text-xs text-slate-400">Flag</span>
                  <select
                    value={form.flags}
                    onChange={(e) => setForm({ ...form, flags: e.target.value })}
                    className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm"
                  >
                    {FLAG_OPTIONS.map((f) => (
                      <option key={f} value={f}>{f || "nessuno"}</option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 w-28">
                  <span className="text-xs text-slate-400">Capture group</span>
                  <input
                    type="number"
                    min={0}
                    value={form.capture_group}
                    onChange={(e) => setForm({ ...form, capture_group: parseInt(e.target.value) || 0 })}
                    className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm"
                  />
                </label>
              </div>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Description</span>
                <input
                  type="text"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="Optional description"
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm"
                />
              </label>
              <div className="flex gap-2 mt-2">
                <button
                  type="submit"
                  className="flex-1 bg-indigo-600 hover:bg-indigo-700 rounded px-3 py-2 text-sm"
                >
                  {editTarget ? "Salva" : "Crea"}
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
