import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { getKey } from "./lib/auth";
import { Layout } from "./components/Layout";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { ApiKeysPage } from "./pages/ApiKeysPage";
import { AuditLogPage } from "./pages/AuditLogPage";
import { StatsPage } from "./pages/StatsPage";
import { RegexPatternsPage } from "./pages/RegexPatternsPage";
import { DenylistPage } from "./pages/DenylistPage";
import { LanguagesPage } from "./pages/LanguagesPage";
import { ContextWordsPage } from "./pages/ContextWordsPage";
import { MappingsPage } from "./pages/MappingsPage";
import { ReclassificationPage } from "./pages/ReclassificationPage";
import { PiiTypesPage } from "./pages/PiiTypesPage";
import { DomainPoliciesPage } from "./pages/DomainPoliciesPage";
import { ContextTypesPage } from "./pages/ContextTypesPage";

function useRole(): { ready: boolean; isAdmin: boolean; isAuthenticated: boolean } {
  const [ready, setReady] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    const key = getKey();
    if (!key) {
      setReady(true);
      return;
    }
    fetch("/v1/auth/api-keys", { headers: { "X-Api-Key": key } })
      .then((res) => {
        setIsAuthenticated(res.ok);
        // If listing api-keys succeeds, the user has admin role
        setIsAdmin(res.ok);
      })
      .catch(() => {
        setIsAuthenticated(false);
        // Try stats to see if at least auditor
        return fetch("/v1/admin/stats", { headers: { "X-Api-Key": key } }).then((r) => {
          setIsAuthenticated(r.ok);
        });
      })
      .finally(() => setReady(true));
  }, []);

  return { ready, isAdmin, isAuthenticated };
}

export default function App() {
  const { ready, isAdmin, isAuthenticated } = useRole();

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <span className="text-slate-400">Caricamento...</span>
      </div>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            isAuthenticated ? <Layout isAdmin={isAdmin} /> : <Navigate to="/login" replace />
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="api-keys" element={<ApiKeysPage isAdmin={isAdmin} />} />
          <Route path="audit-log" element={<AuditLogPage isAdmin={isAdmin} />} />
          <Route path="mappings" element={<MappingsPage isAdmin={isAdmin} />} />
          <Route path="stats" element={<StatsPage />} />
          <Route path="regex-patterns" element={<RegexPatternsPage isAdmin={isAdmin} />} />
          <Route path="denylist" element={<DenylistPage isAdmin={isAdmin} />} />
          <Route path="languages" element={<LanguagesPage isAdmin={isAdmin} />} />
          <Route path="context-words" element={<ContextWordsPage isAdmin={isAdmin} />} />
          <Route path="reclassification" element={<ReclassificationPage isAdmin={isAdmin} />} />
          <Route path="pii-types" element={<PiiTypesPage isAdmin={isAdmin} />} />
          <Route path="domain-policies" element={<DomainPoliciesPage isAdmin={isAdmin} />} />
          <Route path="context-types" element={<ContextTypesPage isAdmin={isAdmin} />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
