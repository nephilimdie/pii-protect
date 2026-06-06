import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { api, AuditLogEntry } from "../lib/api";

interface Props { isAdmin?: boolean; }

const ACTION_OPTIONS = ["", "anonymize", "deanonymize", "admin_cleanup"];

export function AuditLogPage({ isAdmin }: Props) {
  const [items, setItems] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const perPage = 50;

  function load() {
    setLoading(true);
    setSelected(new Set());
    api.getAuditLog(page, perPage, action || undefined)
      .then((res) => { setItems(res.items); setTotal(res.total); })
      .catch(() => setError("Failed to load audit log."))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, [page, action]);

  const totalPages = Math.ceil(total / perPage);
  const allSelected = items.length > 0 && items.every((i) => selected.has(i.id));

  function toggleAll() {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(items.map((i) => i.id)));
    }
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
    if (!confirm(`Eliminare ${selected.size} voci dal log?`)) return;
    setDeleting(true);
    setError(null);
    try {
      await api.deleteAuditLogBulk(Array.from(selected));
      load();
    } catch {
      setError("Delete failed.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold">Audit Log</h1>
        <div className="flex items-center gap-2">
          {isAdmin && selected.size > 0 && (
            <button
              onClick={handleDeleteSelected}
              disabled={deleting}
              className="flex items-center gap-1 bg-red-600 hover:bg-red-700 disabled:opacity-50 rounded px-3 py-2 text-sm"
            >
              <Trash2 size={14} />
              Elimina {selected.size}
            </button>
          )}
          <select
            value={action}
            onChange={(e) => { setAction(e.target.value); setPage(1); }}
            className="bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm"
          >
            {ACTION_OPTIONS.map((a) => (
              <option key={a} value={a}>{a || "All actions"}</option>
            ))}
          </select>
        </div>
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
                  {isAdmin && (
                    <th className="px-4 py-3 w-8">
                      <input type="checkbox" checked={allSelected} onChange={toggleAll} className="accent-indigo-500" />
                    </th>
                  )}
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3">Action</th>
                  <th className="px-4 py-3">Context ID</th>
                  <th className="px-4 py-3">PII Types</th>
                  <th className="px-4 py-3 text-right">Chars</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr
                    key={item.id}
                    className={`border-b border-slate-700/50 ${selected.has(item.id) ? "bg-slate-700/30" : ""}`}
                  >
                    {isAdmin && (
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          checked={selected.has(item.id)}
                          onChange={() => toggleOne(item.id)}
                          className="accent-indigo-500"
                        />
                      </td>
                    )}
                    <td className="px-4 py-3 text-slate-400 whitespace-nowrap">
                      {new Date(item.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 font-mono">{item.action ?? "-"}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-400 max-w-xs truncate">{item.context_id ?? "-"}</td>
                    <td className="px-4 py-3 text-xs text-slate-300">{item.pii_types_found?.join(", ") ?? "-"}</td>
                    <td className="px-4 py-3 text-right">{item.char_count ?? "-"}</td>
                  </tr>
                ))}
                {items.length === 0 && (
                  <tr>
                    <td colSpan={isAdmin ? 6 : 5} className="px-4 py-8 text-center text-slate-500">No results</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {totalPages > 1 && (
            <div className="flex items-center gap-2 mt-4 justify-end text-sm">
              <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} className="px-3 py-1 bg-slate-700 rounded disabled:opacity-40">Previous</button>
              <span className="text-slate-400">Page {page} of {totalPages}</span>
              <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages} className="px-3 py-1 bg-slate-700 rounded disabled:opacity-40">Next</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
