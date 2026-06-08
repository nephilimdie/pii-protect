import { useEffect, useState, FormEvent } from "react";
import { Plus, Trash2, Pencil, Shield, Eye, Wand2 } from "lucide-react";
import { api, DomainPolicy, PiiTypeItem } from "../lib/api";

interface Props { isAdmin: boolean; }

const ACTION_COLOR: Record<string, string> = {
  protect: "#6366f1",
  keep:    "#10b981",
};

export function DomainPoliciesPage({ isAdmin }: Props) {
  const [policies, setPolicies] = useState<DomainPolicy[]>([]);
  const [allTypes, setAllTypes] = useState<PiiTypeItem[]>([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [editDomain, setEditDomain] = useState<string | null>(null);
  type PiiState = "protect" | "keep" | "surrogate" | null;

  const [form, setForm] = useState({
    domain: "", description: "",
    protect: [] as string[], keep: [] as string[], surrogate: [] as string[],
  });

  function load() {
    setLoading(true);
    Promise.all([api.listDomainPolicies(), api.listPiiTypes()])
      .then(([p, t]) => { setPolicies(p); setAllTypes(t); })
      .catch(() => setError("Failed to load."))
      .finally(() => setLoading(false));
  }
  useEffect(() => { load(); }, []);

  function openAdd() {
    setForm({ domain: "", description: "", protect: [], keep: [], surrogate: [] });
    setEditDomain(null); setShowModal(true);
  }
  function openEdit(p: DomainPolicy) {
    setForm({ domain: p.domain, description: p.description ?? "", protect: [...p.protect_types], keep: [...p.keep_types], surrogate: [...(p.surrogate_types ?? [])] });
    setEditDomain(p.domain); setShowModal(true);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault(); setError(null);
    const target = editDomain ?? form.domain;
    try {
      await api.upsertDomainPolicy(target, {
        protect_types: form.protect, keep_types: form.keep, surrogate_types: form.surrogate, description: form.description || undefined,
      });
      setShowModal(false); load();
    } catch { setError("Save failed."); }
  }

  async function handleDelete(domain: string) {
    if (!confirm(`Eliminare la policy "${domain}"?`)) return;
    try { await api.deleteDomainPolicy(domain); load(); }
    catch { setError("Delete failed."); }
  }

  function toggleType(list: "protect" | "keep" | "surrogate", code: string) {
    setForm(f => {
      const others = (["protect", "keep", "surrogate"] as const).filter(l => l !== list);
      const isActive = f[list].includes(code);
      return {
        ...f,
        [list]: isActive ? f[list].filter(c => c !== code) : [...f[list], code],
        ...Object.fromEntries(others.map(o => [o, f[o].filter(c => c !== code)])),
      };
    });
  }

  const categories = Array.from(new Set(allTypes.map(t => t.category))).sort();

  if (!isAdmin) return <p className="text-slate-400">Admin access required.</p>;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-lg font-semibold">Domain Policies</h1>
          <p className="text-sm text-slate-400 mt-1">
            Per ogni dominio definisce quali tipi PII proteggere e quali mantenere nel testo.
          </p>
        </div>
        <button onClick={openAdd} className="flex items-center gap-1 bg-indigo-600 hover:bg-indigo-700 rounded px-3 py-2 text-sm">
          <Plus size={14} /> New policy
        </button>
      </div>

      {error && <p className="text-red-400 mb-3 text-sm">{error}</p>}

      {loading ? <p className="text-slate-400 text-sm">Loading...</p> : (
        <div className="flex flex-col gap-3">
          {policies.map(p => (
            <div key={p.domain} className={`bg-slate-800 border border-slate-700 rounded-lg p-4 ${!p.enabled ? "opacity-50" : ""}`}>
              <div className="flex items-center justify-between mb-3">
                <div>
                  <span className="font-semibold font-mono text-sm">{p.domain}</span>
                  {p.description && <span className="text-slate-400 text-xs ml-3">{p.description}</span>}
                </div>
                <div className="flex gap-2">
                  <button onClick={() => openEdit(p)} className="hover:text-white text-slate-400"><Pencil size={13} /></button>
                  <button onClick={() => handleDelete(p.domain)} className="hover:text-red-400 text-slate-400"><Trash2 size={13} /></button>
                </div>
              </div>
              <div className="flex flex-wrap gap-1">
                {p.protect_types.map(t => (
                  <span key={t} className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300">
                    <Shield size={10} /> {t}
                  </span>
                ))}
                {p.keep_types.map(t => (
                  <span key={t} className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300">
                    <Eye size={10} /> {t}
                  </span>
                ))}
                {(p.surrogate_types ?? []).map(t => (
                  <span key={t} className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300">
                    <Wand2 size={10} /> {t}
                  </span>
                ))}
              </div>
            </div>
          ))}
          {policies.length === 0 && <p className="text-slate-500 text-sm">Nessuna policy.</p>}
        </div>
      )}

      {showModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <h2 className="font-semibold mb-4">{editDomain ? `Modifica policy: ${editDomain}` : "Nuova domain policy"}</h2>
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              {!editDomain && (
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Domain (identificatore)</span>
                  <input type="text" value={form.domain}
                    onChange={e => setForm({ ...form, domain: e.target.value.toLowerCase().replace(/\s+/g, "_") })}
                    placeholder="es. fine_appeal" required
                    className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm font-mono" />
                </label>
              )}
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Descrizione</span>
                <input type="text" value={form.description}
                  onChange={e => setForm({ ...form, description: e.target.value })}
                  className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm" />
              </label>

              <div>
                <div className="flex gap-4 text-xs text-slate-500 mb-3">
                  <span className="flex items-center gap-1"><Shield size={10} className="text-indigo-400" /> Nascondi</span>
                  <span className="flex items-center gap-1"><Eye size={10} className="text-emerald-400" /> Vedi</span>
                  <span className="flex items-center gap-1"><Wand2 size={10} className="text-amber-400" /> Faker</span>
                  <span className="text-slate-600">· nessuno = default del tipo</span>
                </div>
                {categories.map(cat => (
                  <div key={cat} className="mb-3">
                    <p className="text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wide">{cat}</p>
                    <div className="flex flex-wrap gap-1.5">
                      {allTypes.filter(t => t.category === cat).map(t => {
                        const cur = form.protect.includes(t.code) ? "protect"
                                  : form.keep.includes(t.code)    ? "keep"
                                  : form.surrogate.includes(t.code)? "surrogate"
                                  : null;
                        return (
                          <div key={t.code} className="flex items-stretch rounded-lg overflow-hidden border border-slate-700 text-xs">
                            <span className={`px-2.5 py-1.5 font-mono font-semibold flex items-center select-none transition-colors ${
                              cur === "protect"  ? "bg-indigo-600/30 text-indigo-300" :
                              cur === "keep"     ? "bg-emerald-600/30 text-emerald-300" :
                              cur === "surrogate"? "bg-amber-600/30 text-amber-300" :
                              "bg-slate-900 text-slate-400"
                            }`}>{t.code}</span>
                            <button type="button" onClick={() => toggleType("protect", t.code)} title="Nascondi"
                              className={`px-2 py-1.5 border-l border-slate-700 transition-colors ${cur === "protect" ? "bg-indigo-600 text-white" : "bg-slate-900 text-slate-500 hover:text-indigo-400 hover:bg-slate-800"}`}>
                              <Shield size={10} />
                            </button>
                            <button type="button" onClick={() => toggleType("keep", t.code)} title="Vedi"
                              className={`px-2 py-1.5 border-l border-slate-700 transition-colors ${cur === "keep" ? "bg-emerald-600 text-white" : "bg-slate-900 text-slate-500 hover:text-emerald-400 hover:bg-slate-800"}`}>
                              <Eye size={10} />
                            </button>
                            <button type="button" onClick={() => toggleType("surrogate", t.code)} title="Faker"
                              className={`px-2 py-1.5 border-l border-slate-700 transition-colors ${cur === "surrogate" ? "bg-amber-600 text-white" : "bg-slate-900 text-slate-500 hover:text-amber-400 hover:bg-slate-800"}`}>
                              <Wand2 size={10} />
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex gap-2 mt-1">
                <button type="submit" className="flex-1 bg-indigo-600 hover:bg-indigo-700 rounded px-3 py-2 text-sm">
                  {editDomain ? "Salva" : "Crea"}
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
