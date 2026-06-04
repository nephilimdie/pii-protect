import { useEffect, useState } from "react";
import { api, StatsResponse } from "../lib/api";
import { StatCard } from "../components/StatCard";

export function DashboardPage() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getStats()
      .then(setStats)
      .catch(() => setError("Impossibile caricare le statistiche."));
  }, []);

  if (error) {
    return <p className="text-red-400">{error}</p>;
  }

  if (!stats) {
    return <p className="text-slate-400">Caricamento...</p>;
  }

  return (
    <div>
      <h1 className="text-lg font-semibold mb-6">Dashboard</h1>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatCard label="Anonimizzazioni totali" value={stats.total_anonymizations} />
        <StatCard label="Token creati" value={stats.total_tokens_created} />
        <StatCard label="Richieste ultime 24h" value={stats.requests_last_24h} />
        <StatCard label="Tipi PII distinti" value={Object.keys(stats.pii_types_breakdown).length} />
      </div>
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
        <h2 className="text-sm font-medium text-slate-400 mb-4">Breakdown tipi PII</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-700">
              <th className="pb-2">Tipo</th>
              <th className="pb-2 text-right">Occorrenze</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(stats.pii_types_breakdown).map(([type, count]) => (
              <tr key={type} className="border-b border-slate-700/50">
                <td className="py-2 font-mono">{type}</td>
                <td className="py-2 text-right">{count}</td>
              </tr>
            ))}
            {Object.keys(stats.pii_types_breakdown).length === 0 && (
              <tr>
                <td colSpan={2} className="py-4 text-center text-slate-500">Nessun dato</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
