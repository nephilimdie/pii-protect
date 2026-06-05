import { getKey } from "./auth";

function authHeaders(): Record<string, string> {
  const key = getKey();
  if (!key) return {};
  return { "X-Api-Key": key, "Content-Type": "application/json" };
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json() as Promise<T>;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: authHeaders() });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json() as Promise<T>;
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "PUT",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json() as Promise<T>;
}

async function del(path: string): Promise<void> {
  const res = await fetch(path, { method: "DELETE", headers: authHeaders() });
  if (!res.ok) throw new Error(`${res.status}`);
}

export interface EntityDetail {
  type: string;
  value: string;
  start: number;
  end: number;
  confidence: number;
  replacement: string;
}

export interface AnonymizeResponse {
  anonymized_text: string;
  entity_count: number;
  pii_types_found: string[];
  entities: EntityDetail[];
}

export interface DeanonymizeResponse {
  restored_text: string;
}

export interface StatsResponse {
  total_anonymizations: number;
  total_tokens_created: number;
  pii_types_breakdown: Record<string, number>;
  requests_last_24h: number;
}

export interface AuditLogEntry {
  id: string;
  api_key_id: string | null;
  action: string | null;
  context_id: string | null;
  pii_types_found: string[] | null;
  char_count: number | null;
  created_at: string;
}

export interface AuditLogResponse {
  items: AuditLogEntry[];
  total: number;
  page: number;
}

export interface ApiKeyItem {
  id: string;
  name: string;
  role: string;
  active: boolean;
  created_at: string;
  last_used_at: string | null;
}

export interface CreateApiKeyResponse {
  id: string;
  name: string;
  role: string;
  key: string;
}

export interface ContextWordItem {
  id: number;
  entity_type: string;
  word: string;
  description: string;
  enabled: boolean;
  created_at: string;
}

export interface LanguageInfo {
  code: string;
  name: string;
  model: string;
  size_mb: number;
  installed: boolean;
}

export interface LanguageSettings {
  default_language: string;
}

export interface InstallStatus {
  code: string;
  status: string;
  log: string;
}

export interface DenylistEntryItem {
  id: string;
  pii_type: string;
  value: string;
  match_type: string;
  description: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateDenylistEntryRequest {
  pii_type: string;
  value: string;
  match_type?: string;
  description?: string;
}

export interface UpdateDenylistEntryRequest {
  pii_type?: string;
  value?: string;
  match_type?: string;
  description?: string;
  enabled?: boolean;
}

export interface RegexPatternItem {
  id: string;
  pii_type: string;
  pattern: string;
  flags: string;
  capture_group: number;
  description: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateRegexPatternRequest {
  pii_type: string;
  pattern: string;
  flags: string;
  capture_group: number;
  description: string;
}

export interface UpdateRegexPatternRequest {
  pii_type?: string;
  pattern?: string;
  flags?: string;
  capture_group?: number;
  description?: string;
  enabled?: boolean;
}

export const api = {
  anonymize: (text: string, contextId: string, contextType: string) =>
    post<AnonymizeResponse>("/v1/anonymize", { text, context_id: contextId, context_type: contextType }),

  deanonymize: (text: string, contextId: string, contextType: string) =>
    post<DeanonymizeResponse>("/v1/deanonymize", { text, context_id: contextId, context_type: contextType }),

  getStats: () => get<StatsResponse>("/v1/admin/stats"),

  getAuditLog: (page: number, perPage: number, action?: string) => {
    const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
    if (action) params.set("action", action);
    return get<AuditLogResponse>(`/v1/admin/audit-log?${params}`);
  },

  createApiKey: (name: string, role: string) =>
    post<CreateApiKeyResponse>("/v1/auth/api-keys", { name, role }),

  listApiKeys: () => get<ApiKeyItem[]>("/v1/auth/api-keys"),

  revokeApiKey: (id: string) => del(`/v1/auth/api-keys/${id}`),

  listRegexPatterns: () => get<RegexPatternItem[]>("/v1/admin/regex-patterns"),

  createRegexPattern: (body: CreateRegexPatternRequest) =>
    post<RegexPatternItem>("/v1/admin/regex-patterns", body),

  updateRegexPattern: (id: string, body: UpdateRegexPatternRequest) =>
    put<RegexPatternItem>(`/v1/admin/regex-patterns/${id}`, body),

  deleteRegexPattern: (id: string) => del(`/v1/admin/regex-patterns/${id}`),

  listDenylist: () => get<DenylistEntryItem[]>("/v1/admin/denylist"),

  createDenylistEntry: (body: CreateDenylistEntryRequest) =>
    post<DenylistEntryItem>("/v1/admin/denylist", body),

  updateDenylistEntry: (id: string, body: UpdateDenylistEntryRequest) =>
    put<DenylistEntryItem>(`/v1/admin/denylist/${id}`, body),

  deleteDenylistEntry: (id: string) => del(`/v1/admin/denylist/${id}`),

  listContextWords: () => get<ContextWordItem[]>("/v1/admin/presidio-context"),
  createContextWord: (body: { entity_type: string; word: string; description?: string }) =>
    post<ContextWordItem>("/v1/admin/presidio-context", body),
  updateContextWord: (id: number, body: Partial<{ entity_type: string; word: string; description: string; enabled: boolean }>) =>
    put<ContextWordItem>(`/v1/admin/presidio-context/${id}`, body),
  deleteContextWord: (id: number) => del(`/v1/admin/presidio-context/${id}`),

  listLanguages: () => get<LanguageInfo[]>("/v1/admin/languages"),
  getSettings: () => get<LanguageSettings>("/v1/admin/settings"),
  setSettings: (body: LanguageSettings) => put<LanguageSettings>("/v1/admin/settings", body),
  installLanguage: (code: string) => post<InstallStatus>(`/v1/admin/languages/${code}/install`, {}),
  getLanguageStatus: (code: string) => get<InstallStatus>(`/v1/admin/languages/${code}/status`),
};
