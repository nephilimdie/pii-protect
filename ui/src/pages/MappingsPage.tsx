import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { api, MappingItem } from "../lib/api";

interface Props { isAdmin: boolean; }

export function MappingsPage({ isAdmin }: Props) {
  const [items, setItems] = useState<MappingItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const perPage = 50;

  function load() {
    setLoading(true);
    setSelected(new Set());
    api.listMappings(page, perPage)
      .then((res) => { setItems(res.items); setTotal(res.total); })
      .catch(() => setError("Failed to load mappings."))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, [page]);

  const totalPages = Math.ceil(total / perPage);
  const allSelected = items.length > 0 && items.every((i) => selected.has(i.id));

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(items.map((i) => i.id)));
  }

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function handleDeleteSelected() {
    if (selected.size === 0) return;
    if (!confirm(`Eliminare ${selected.size} mapping?`)) return;
    setDeleting(true);
    setError(null);
    try {
      await api.deleteMappingsBulk(Array.from(selected));
      load();
    } catch {
      setError("Delete failed.");
    } finally {
      setDeleting(false);
    }
  }

  if (!isAdmin) return <p className="text-slate-400">Admin access required.</p>;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold">Mappings</h1>
          <p className="text-sm text-slate-400 mt-1">Token ↔ valore originale salvati per la deanonimizzazione.</p>
        </div>
        {selected.size > 0 && (
          <button
            onClick={handleDeleteSelected}
            disabled={deleting}
            className="flex items-center gap-1 bg-red-600 hover:bg-red-700 disabled:opacity-50 rounded px-3 py-2 text-sm"
          >
            <Trash2 size={14} />
            Elimina {selected.size}
          </button>
        )}
      </div>

      {error && <p className="text-red-400 mb-4 text-sm">{error}</p>}

      {loading ? (
        <p className="text-slate-400">Loading...</p>
      ) : (
        <>
          <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-700">
                  <th className="px-4 py-3 w-8">
                    <input type="checkbox" checked={allSelected} onChange={toggleAll} className="accent-indigo-500" />
                  </th>
                  <th className="px-4 py-3">Token</th>
                  <th className="px-4 py-3">Originale</th>
                  <th className="px-4 py-3">Tipo PII</th>
                  <th className="px-4 py-3">Context ID</th>
                  <th className="px-4 py-3">Context Type</th>
                  <th className="px-4 py-3">Data</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr
                    key={item.id}
                    className={`border-b border-slate-700/50 ${selected.has(item.id) ? "bg-slate-700/30" : ""}`}
                  >
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={selected.has(item.id)}
                        onChange={() => toggleOne(item.id)}
                        className="accent-indigo-500"
                      />
                    </td>
                    <td className="px-4 py-3 font-mono text-indigo-300 text-xs">{item.token}</td>
                    <td className="px-4 py-3 font-mono text-xs max-w-xs truncate">{item.original}</td>
                    <td className="px-4 py-3">
                      <span className="text-xs bg-slate-700 px-2 py-0.5 rounded">{item.pii_type}</span>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-400 max-w-xs truncate">{item.context_id}</td>
                    <td className="px-4 py-3 text-xs text-slate-400">{item.context_type}</td>
                    <td className="px-4 py-3 text-slate-400 whitespace-nowrap text-xs">
                      {new Date(item.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
                {items.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-slate-500">Nessun mapping</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between mt-4 text-sm text-slate-400">
            <span>{total} mapping totali</span>
            {totalPages > 1 && (
              <div className="flex items-center gap-2">
                <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} className="px-3 py-1 bg-slate-700 rounded disabled:opacity-40">Previous</button>
                <span>Page {page} of {totalPages}</span>
                <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages} className="px-3 py-1 bg-slate-700 rounded disabled:opacity-40">Next</button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
