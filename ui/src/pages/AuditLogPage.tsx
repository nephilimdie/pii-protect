import { useEffect, useState } from "react";
import { api, AuditLogEntry } from "../lib/api";

const ACTION_OPTIONS = ["", "anonymize", "deanonymize", "admin_cleanup"];

export function AuditLogPage() {
  const [items, setItems] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const perPage = 50;

  useEffect(() => {
    setLoading(true);
    api.getAuditLog(page, perPage, action || undefined)
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .catch(() => setError("Impossibile caricare il log."))
      .finally(() => setLoading(false));
  }, [page, action]);

  const totalPages = Math.ceil(total / perPage);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold">Audit Log</h1>
        <select
          value={action}
          onChange={(e) => { setAction(e.target.value); setPage(1); }}
          className="bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm"
        >
          {ACTION_OPTIONS.map((a) => (
            <option key={a} value={a}>{a || "Tutte le azioni"}</option>
          ))}
        </select>
      </div>

      {error && <p className="text-red-400 mb-4 text-sm">{error}</p>}

      {loading ? (
        <p className="text-slate-400">Caricamento...</p>
      ) : (
        <>
          <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-700">
                  <th className="px-4 py-3">Data</th>
                  <th className="px-4 py-3">Azione</th>
                  <th className="px-4 py-3">Context ID</th>
                  <th className="px-4 py-3">Tipi PII</th>
                  <th className="px-4 py-3 text-right">Caratteri</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className="border-b border-slate-700/50">
                    <td className="px-4 py-3 text-slate-400 whitespace-nowrap">
                      {new Date(item.created_at).toLocaleString("it-IT")}
                    </td>
                    <td className="px-4 py-3 font-mono">{item.action ?? "-"}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-400 max-w-xs truncate">
                      {item.context_id ?? "-"}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-300">
                      {item.pii_types_found?.join(", ") ?? "-"}
                    </td>
                    <td className="px-4 py-3 text-right">{item.char_count ?? "-"}</td>
                  </tr>
                ))}
                {items.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-slate-500">Nessun risultato</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {totalPages > 1 && (
            <div className="flex items-center gap-2 mt-4 justify-end text-sm">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1 bg-slate-700 rounded disabled:opacity-40"
              >
                Precedente
              </button>
              <span className="text-slate-400">Pagina {page} di {totalPages}</span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-3 py-1 bg-slate-700 rounded disabled:opacity-40"
              >
                Successiva
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
