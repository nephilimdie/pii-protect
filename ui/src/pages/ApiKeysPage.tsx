import { useEffect, useState, FormEvent } from "react";
import { api, ApiKeyItem } from "../lib/api";
import { Plus, Copy, Trash2 } from "lucide-react";

interface ApiKeysPageProps {
  isAdmin: boolean;
}

export function ApiKeysPage({ isAdmin }: ApiKeysPageProps) {
  const [keys, setKeys] = useState<ApiKeyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [newName, setNewName] = useState("");
  const [newRole, setNewRole] = useState<"service" | "auditor" | "admin">("service");
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { load(); }, []);

  function load() {
    api.listApiKeys()
      .then(setKeys)
      .catch(() => setError("Failed to load API keys."))
      .finally(() => setLoading(false));
  }

  if (!isAdmin) return <p className="text-slate-400">Admin access required.</p>;

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    try {
      const res = await api.createApiKey(newName, newRole);
      setCreatedKey(res.key);
      setNewName("");
      setNewRole("service");
      load();
    } catch {
      setError("Failed to create API key.");
    }
  }

  async function handleRevoke(id: string) {
    try {
      await api.revokeApiKey(id);
      load();
    } catch {
      setError("Failed to revoke API key.");
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold">API Keys</h1>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-1 bg-indigo-600 hover:bg-indigo-700 rounded px-3 py-2 text-sm"
        >
          <Plus size={14} />
          New key
        </button>
      </div>

      {error && <p className="text-red-400 mb-4 text-sm">{error}</p>}

      {loading ? (
        <p className="text-slate-400">Loading...</p>
      ) : (
        <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-700">
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Last used</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.id} className="border-b border-slate-700/50">
                  <td className="px-4 py-3">{k.name}</td>
                  <td className="px-4 py-3 font-mono">{k.role}</td>
                  <td className="px-4 py-3">
                    <span className={k.active ? "text-green-400" : "text-slate-500"}>
                      {k.active ? "active" : "revoked"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-400">
                    {k.last_used_at ? new Date(k.last_used_at).toLocaleString() : "never"}
                  </td>
                  <td className="px-4 py-3">
                    {k.active && (
                      <button onClick={() => handleRevoke(k.id)} className="text-red-400 hover:text-red-300" title="Revoke">
                        <Trash2 size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showModal && !createdKey && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 w-full max-w-sm">
            <h2 className="font-semibold mb-4">Create API Key</h2>
            <form onSubmit={handleCreate} className="flex flex-col gap-3">
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Name"
                className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm"
                autoFocus
              />
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value as typeof newRole)}
                className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm"
              >
                <option value="service">service</option>
                <option value="auditor">auditor</option>
                <option value="admin">admin</option>
              </select>
              <div className="flex gap-2 mt-2">
                <button type="submit" className="flex-1 bg-indigo-600 hover:bg-indigo-700 rounded px-3 py-2 text-sm">Create</button>
                <button type="button" onClick={() => setShowModal(false)} className="flex-1 bg-slate-700 hover:bg-slate-600 rounded px-3 py-2 text-sm">Cancel</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {createdKey && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 w-full max-w-md">
            <h2 className="font-semibold mb-2">Key created</h2>
            <p className="text-slate-400 text-sm mb-4">Copy it now — it won't be shown again.</p>
            <div className="flex items-center gap-2 bg-slate-900 rounded px-3 py-2 font-mono text-sm break-all">
              <span className="flex-1">{createdKey}</span>
              <button onClick={() => navigator.clipboard.writeText(createdKey)} className="text-slate-400 hover:text-white shrink-0">
                <Copy size={14} />
              </button>
            </div>
            <button onClick={() => { setCreatedKey(null); setShowModal(false); }} className="mt-4 w-full bg-indigo-600 hover:bg-indigo-700 rounded px-3 py-2 text-sm">
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
