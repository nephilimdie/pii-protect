import { useState, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { saveKey } from "../lib/auth";

export function LoginPage() {
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!apiKey.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/health", { headers: { "X-Api-Key": apiKey } });
      if (!res.ok) {
        setError("Invalid API key or service unreachable.");
        return;
      }
      saveKey(apiKey);
      window.location.href = "/dashboard";
    } catch {
      setError("Could not connect to the service.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-8 w-full max-w-sm">
        <div className="flex items-center gap-2 mb-6">
          <ShieldCheck className="text-indigo-400" size={24} />
          <h1 className="text-xl font-semibold">pii-protect</h1>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-sm text-slate-400">X-Api-Key</span>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-indigo-500"
              placeholder="Enter your API key"
              autoFocus
            />
          </label>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 rounded px-4 py-2 text-sm font-medium transition-colors"
          >
            {loading ? "Verifying..." : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
