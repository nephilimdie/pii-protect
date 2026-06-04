import { useEffect, useState } from "react";
import { api, StatsResponse } from "../lib/api";

export function StatsPage() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getStats()
      .then(setStats)
      .catch(() => setError("Impossibile caricare le statistiche."));
  }, []);

  if (error) return <p className="text-red-400">{error}</p>;
  if (!stats) return <p className="text-slate-400">Caricamento...</p>;

  const entries = Object.entries(stats.pii_types_breakdown).sort((a, b) => b[1] - a[1]);
  const maxCount = entries.length > 0 ? entries[0][1] : 1;

  return (
    <div>
      <h1 className="text-lg font-semibold mb-6">Statistiche tipi PII</h1>
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-700">
              <th className="pb-3">Tipo PII</th>
              <th className="pb-3">Distribuzione</th>
              <th className="pb-3 text-right">Conteggio</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([type, count]) => (
              <tr key={type} className="border-b border-slate-700/50">
                <td className="py-3 font-mono">{type}</td>
                <td className="py-3 pr-6">
                  <div className="bg-slate-700 rounded-full h-2 w-full">
                    <div
                      className="bg-indigo-500 h-2 rounded-full"
                      style={{ width: `${(count / maxCount) * 100}%` }}
                    />
                  </div>
                </td>
                <td className="py-3 text-right">{count}</td>
              </tr>
            ))}
            {entries.length === 0 && (
              <tr>
                <td colSpan={3} className="py-8 text-center text-slate-500">Nessun dato disponibile</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
