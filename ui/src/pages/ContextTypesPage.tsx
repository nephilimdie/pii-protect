import { useEffect, useState, FormEvent } from "react";
import { Plus, Trash2, Pencil, Check, X, ChevronDown, Shield, Eye, AlertCircle } from "lucide-react";
import { api, ContextTypeItem, DomainPolicy, PiiTypeItem } from "../lib/api";

interface Props { isAdmin: boolean; }

const MODE_COLORS: Record<string, string> = {
  tag:       "#6366f1",
  surrogate: "#10b981",
};

const CATEGORY_ORDER = ["IDENTITY", "CONTACT", "FINANCIAL", "LEGAL", "VEHICLE", "NETWORK", "CREDENTIAL"];

const EMPTY: Partial<ContextTypeItem> & { code: string } = {
  code: "", display_name: "", domain: "", default_mode: "tag", description: "",
};

// ── inline policy editor ────────────────────────────────────────────────────

interface PolicyEditorProps {
  contextCode: string;
  domain: string | null;
  policies: DomainPolicy[];
  allTypes: PiiTypeItem[];
  onSaved: () => void;
  onError: (msg: string) => void;
}

function PolicyEditor({ contextCode, domain, policies, allTypes, onSaved, onError }: PolicyEditorProps) {
  const linked = policies.find(p => p.domain === domain) ?? null;

  const [protect, setProtect] = useState<string[]>(linked?.protect_types ?? []);
  const [keep,    setKeep]    = useState<string[]>(linked?.keep_types    ?? []);
  const [saving,  setSaving]  = useState(false);

  useEffect(() => {
    setProtect(linked?.protect_types ?? []);
    setKeep(linked?.keep_types    ?? []);
  }, [domain]);

  function toggle(list: "protect" | "keep", code: string) {
    const other = list === "protect" ? "keep" : "protect";
    const setList  = list  === "protect" ? setProtect : setKeep;
    const setOther = other === "protect" ? setProtect : setKeep;
    setList(prev  => prev.includes(code) ? prev.filter(c => c !== code) : [...prev, code]);
    setOther(prev => prev.filter(c => c !== code));
  }

  async function save() {
    if (!domain) return;
    setSaving(true);
    try {
      await api.upsertDomainPolicy(domain, {
        protect_types: protect,
        keep_types: keep,
        description: linked?.description ?? undefined,
        enabled: linked?.enabled ?? true,
      });
      onSaved();
    } catch {
      onError("Salvataggio policy fallito.");
    } finally {
      setSaving(false);
    }
  }

  if (!domain) {
    return (
      <div className="flex items-center gap-2 text-slate-500 text-xs py-2">
        <AlertCircle size={13} />
        Nessuna domain policy collegata. Assegna una policy a questo context type per configurare i tipi PII.
      </div>
    );
  }

  const categories = CATEGORY_ORDER.filter(c => allTypes.some(t => t.category === c));

  return (
    <div>
      <div className="flex items-center gap-3 mb-3 text-xs text-slate-500">
        <span className="font-semibold text-slate-400">Policy: <span className="font-mono text-indigo-400">{domain}</span></span>
        <span className="flex items-center gap-1"><Shield size={10} className="text-indigo-400" /> Protect — anonimizzato</span>
        <span className="flex items-center gap-1"><Eye size={10} className="text-emerald-400" /> Keep — lasciato nel testo</span>
        <span className="text-slate-600">· non assegnato = default del tipo</span>
      </div>

      <div className="flex flex-col gap-3 mb-4">
        {categories.map(cat => (
          <div key={cat}>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">{cat}</p>
            <div className="flex flex-wrap gap-1">
              {allTypes.filter(t => t.category === cat).map(t => {
                const isProtect = protect.includes(t.code);
                const isKeep    = keep.includes(t.code);
                return (
                  <div key={t.code} className="flex rounded overflow-hidden border border-slate-700 text-xs">
                    <button
                      type="button"
                      onClick={() => toggle("protect", t.code)}
                      title="Protect (anonimizza)"
                      className={`px-2 py-1 transition-colors ${isProtect ? "bg-indigo-600 text-white" : "bg-slate-900 text-slate-400 hover:bg-slate-700"}`}>
                      <Shield size={9} className="inline mr-0.5" />{t.code}
                    </button>
                    <button
                      type="button"
                      onClick={() => toggle("keep", t.code)}
                      title="Keep (lascia nel testo)"
                      className={`px-2 py-1 border-l border-slate-700 transition-colors ${isKeep ? "bg-emerald-700 text-white" : "bg-slate-900 text-slate-400 hover:bg-slate-700"}`}>
                      <Eye size={9} />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <button
        onClick={save}
        disabled={saving}
        className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 rounded px-4 py-1.5 text-xs font-medium">
        {saving ? "Salvo…" : "Salva policy"}
      </button>
    </div>
  );
}

// ── main page ───────────────────────────────────────────────────────────────

export function ContextTypesPage({ isAdmin }: Props) {
  const [items,    setItems]    = useState<ContextTypeItem[]>([]);
  const [policies, setPolicies] = useState<DomainPolicy[]>([]);
  const [allTypes, setAllTypes] = useState<PiiTypeItem[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const [showModal,   setShowModal]   = useState(false);
  const [editTarget,  setEditTarget]  = useState<ContextTypeItem | null>(null);
  const [form,        setForm]        = useState(EMPTY);

  function load() {
    setLoading(true);
    Promise.all([api.listContextTypes(), api.listDomainPolicies(), api.listPiiTypes()])
      .then(([ct, dp, pt]) => { setItems(ct); setPolicies(dp); setAllTypes(pt); })
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
      else            await api.createContextType(body as any);
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
            Ogni context type definisce una policy e un mode. Clicca una riga per configurare i tipi PII visibili.
          </p>
        </div>
        <button onClick={openAdd} className="flex items-center gap-1 bg-indigo-600 hover:bg-indigo-700 rounded px-3 py-2 text-sm">
          <Plus size={14} /> New context
        </button>
      </div>

      {error && <p className="text-red-400 mb-3 text-sm">{error}</p>}

      {loading ? <p className="text-slate-400 text-sm">Loading...</p> : (
        <div className="flex flex-col gap-2">
          {items.map(r => {
            const isOpen = expanded === r.code;
            return (
              <div key={r.code} className={`bg-slate-800 border rounded-lg overflow-hidden transition-all ${!r.enabled ? "opacity-50" : ""} ${isOpen ? "border-indigo-500/50" : "border-slate-700"}`}>
                {/* row header */}
                <div
                  className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-slate-700/30 transition-colors"
                  onClick={() => setExpanded(isOpen ? null : r.code)}
                >
                  <ChevronDown
                    size={14}
                    className={`text-slate-500 transition-transform shrink-0 ${isOpen ? "rotate-180" : ""}`}
                  />
                  <span className="font-mono text-xs text-slate-300 w-36 shrink-0">{r.code}</span>
                  <span className="text-sm font-medium flex-1">{r.display_name}</span>

                  {/* domain badge */}
                  {r.domain ? (
                    <span className="text-xs text-slate-400 font-mono bg-slate-700 px-2 py-0.5 rounded">
                      {r.domain}
                    </span>
                  ) : (
                    <span className="text-xs text-slate-600">no policy</span>
                  )}

                  {/* mode badge */}
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full shrink-0"
                    style={{ background: (MODE_COLORS[r.default_mode] ?? "#64748b") + "33", color: MODE_COLORS[r.default_mode] ?? "#94a3b8" }}>
                    {r.default_mode}
                  </span>

                  {/* actions — stop propagation to avoid toggling expand */}
                  <div className="flex gap-2 shrink-0" onClick={e => e.stopPropagation()}>
                    <button onClick={() => handleToggle(r)} className="hover:text-white text-slate-400">
                      {r.enabled ? <Check size={13} /> : <X size={13} />}
                    </button>
                    <button onClick={() => openEdit(r)} className="hover:text-white text-slate-400"><Pencil size={13} /></button>
                    <button onClick={() => handleDelete(r)} className="hover:text-red-400 text-slate-400"><Trash2 size={13} /></button>
                  </div>
                </div>

                {/* expandable policy editor */}
                {isOpen && (
                  <div className="px-4 pb-4 pt-2 border-t border-slate-700/50">
                    <PolicyEditor
                      contextCode={r.code}
                      domain={r.domain ?? null}
                      policies={policies}
                      allTypes={allTypes}
                      onSaved={() => { load(); }}
                      onError={setError}
                    />
                  </div>
                )}
              </div>
            );
          })}
          {items.length === 0 && (
            <p className="text-slate-500 text-sm text-center py-8">Nessun context type</p>
          )}
        </div>
      )}

      {/* modal add/edit */}
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
