import { useEffect, useState } from "react";
import { Download, CheckCircle, Loader, AlertCircle, Globe } from "lucide-react";
import { api, LanguageInfo } from "../lib/api";

interface Props {
  isAdmin: boolean;
}

export function LanguagesPage({ isAdmin }: Props) {
  const [languages, setLanguages] = useState<LanguageInfo[]>([]);
  const [defaultLang, setDefaultLang] = useState<string>("it");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [installing, setInstalling] = useState<Record<string, string>>({});
  const [savingDefault, setSavingDefault] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [langs, settings] = await Promise.all([
        api.listLanguages(),
        api.getSettings(),
      ]);
      setLanguages(langs);
      setDefaultLang(settings.default_language);
    } catch {
      setError("Impossibile caricare i dati.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  // Poll status for languages being installed
  useEffect(() => {
    const codes = Object.keys(installing).filter(c => installing[c] === "downloading");
    if (codes.length === 0) return;
    const timer = setInterval(async () => {
      for (const code of codes) {
        try {
          const st = await api.getLanguageStatus(code);
          if (st.status !== "downloading") {
            setInstalling(prev => ({ ...prev, [code]: st.status }));
            if (st.status === "installed") {
              setLanguages(prev => prev.map(l => l.code === code ? { ...l, installed: true } : l));
            }
          }
        } catch { /* ignore */ }
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [installing]);

  async function handleInstall(code: string) {
    setInstalling(prev => ({ ...prev, [code]: "downloading" }));
    try {
      await api.installLanguage(code);
    } catch {
      setInstalling(prev => ({ ...prev, [code]: "error" }));
    }
  }

  async function handleSetDefault(code: string) {
    setSavingDefault(true);
    try {
      const result = await api.setSettings({ default_language: code });
      setDefaultLang(result.default_language);
    } catch (e: any) {
      setError(e?.message || "Impossibile impostare la lingua predefinita.");
    } finally {
      setSavingDefault(false);
    }
  }

  function statusIcon(lang: LanguageInfo) {
    const st = installing[lang.code];
    if (st === "downloading") return <Loader size={16} className="animate-spin text-indigo-400" />;
    if (st === "error") return <AlertCircle size={16} className="text-red-400" />;
    if (lang.installed) return <CheckCircle size={16} className="text-green-400" />;
    return null;
  }

  if (!isAdmin) return <p className="text-slate-400">Accesso riservato agli amministratori.</p>;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold flex items-center gap-2">
            <Globe size={20} className="text-indigo-400" />
            Lingue
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Installa modelli spaCy per abilitare il rilevamento NER in più lingue.
            Dopo l'installazione Presidio viene ricaricato automaticamente.
          </p>
        </div>
      </div>

      {error && <p className="text-red-400 mb-4 text-sm">{error}</p>}

      {loading ? (
        <p className="text-slate-400">Caricamento...</p>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
            {languages.map(lang => {
              const st = installing[lang.code];
              const isDownloading = st === "downloading";
              const isDefault = defaultLang === lang.code;

              return (
                <div
                  key={lang.code}
                  className={`bg-slate-800 border rounded-xl p-4 flex flex-col gap-3 ${
                    isDefault ? "border-indigo-500" : "border-slate-700"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-medium text-white">{lang.name}</span>
                      <span className="text-xs text-slate-500 ml-2 font-mono">{lang.code}</span>
                    </div>
                    {statusIcon(lang)}
                  </div>

                  <div className="text-xs text-slate-500 font-mono">{lang.model}</div>
                  <div className="text-xs text-slate-500">{lang.size_mb} MB</div>

                  <div className="flex gap-2 mt-auto">
                    {!lang.installed && !isDownloading && (
                      <button
                        onClick={() => handleInstall(lang.code)}
                        className="flex items-center gap-1 text-xs bg-slate-700 hover:bg-slate-600 rounded px-3 py-1.5"
                      >
                        <Download size={12} />
                        Installa
                      </button>
                    )}
                    {isDownloading && (
                      <span className="text-xs text-indigo-400 flex items-center gap-1">
                        <Loader size={12} className="animate-spin" />
                        Download in corso…
                      </span>
                    )}
                    {lang.installed && (
                      <button
                        onClick={() => handleSetDefault(lang.code)}
                        disabled={isDefault || savingDefault}
                        className={`flex-1 text-xs rounded px-3 py-1.5 transition-colors ${
                          isDefault
                            ? "bg-indigo-600/30 text-indigo-300 cursor-default"
                            : "bg-slate-700 hover:bg-indigo-600 text-slate-300 hover:text-white"
                        }`}
                      >
                        {isDefault ? "✓ Lingua predefinita" : "Imposta come predefinita"}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 text-sm text-slate-400">
            <p className="font-medium text-slate-300 mb-1">Come funziona</p>
            <ul className="list-disc list-inside space-y-1 text-xs">
              <li>La <strong>lingua predefinita</strong> viene usata quando la request non specifica <code>language</code></li>
              <li>Puoi forzare una lingua per singola request passando <code>"language": "en"</code> nel JSON</li>
              <li>I layer <em>ai4privacy</em> e <em>openai/privacy-filter</em> sono già multilingua — non richiedono installazione</li>
              <li>I pattern Regex si applicano indipendentemente dalla lingua</li>
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
