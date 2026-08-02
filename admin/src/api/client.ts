const TOKEN_KEY = "admin_access_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(path, { ...options, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || body.error || detail;
      if (Array.isArray(detail)) {
        detail = detail.map((d) => d.msg || JSON.stringify(d)).join(", ");
      }
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, String(detail));
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface AdminUser {
  id: number;
  username: string;
  email: string;
  is_active: boolean;
  key_count: number;
}

export interface AdminAPIKey {
  id: string;
  user_id: number;
  username: string;
  name: string;
  key_hint: string;
  raw_key: string | null;
  is_active: boolean;
  rate_limit_per_minute: number;
  monthly_token_quota: number;
  created_at: string;
  revoked_at: string | null;
}

export interface AdminAPIKeyCreated extends AdminAPIKey {
  raw_key: string;
}

export interface UsageSummary {
  api_key_id: string;
  user_id: number;
  username: string;
  key_name: string;
  tokens_used: number;
  monthly_token_quota: number;
  percent_used: number;
}

export interface ModelMetricsRow {
  model_id: string;
  requests: number;
  errors: number;
  fallbacks: number;
  error_rate: number;
  avg_latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface ModelMetricsSummary {
  days: number;
  from_date: string;
  to_date: string;
  models: ModelMetricsRow[];
  totals: ModelMetricsRow;
}

export interface AdminConnection {
  id: string;
  name: string;
  provider_type: string;
  base_url: string;
  api_key_hint: string;
  has_api_key: boolean;
  is_active: boolean;
  created_at: string;
}

export interface AdminConnectionTestResult {
  ok: boolean;
  base_url: string;
  status_code?: number | null;
  model_ids: string[];
  error?: string | null;
  connection_id?: string | null;
}

export interface AdminLLMModel {
  id: string;
  model_path: string;
  base_url: string | null;
  effective_base_url: string;
  connection_id: string | null;
  provider: string;
  context_length: number;
  max_output_tokens: number;
  is_active: boolean;
  fallback_model_ids: string[];
  created_at: string;
}

export const api = {
  login(username: string, password: string) {
    return request<TokenResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  },

  listUsers() {
    return request<AdminUser[]>("/api/v1/admin/users");
  },

  createUser(data: {
    username: string;
    password: string;
    email?: string;
    is_active?: boolean;
  }) {
    return request<AdminUser>("/api/v1/admin/users", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  updateUser(
    id: number,
    data: { email?: string; is_active?: boolean },
  ) {
    return request<AdminUser>(`/api/v1/admin/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  listApiKeys(userId?: number) {
    const qs = userId != null ? `?user_id=${userId}` : "";
    return request<AdminAPIKey[]>(`/api/v1/admin/api-keys${qs}`);
  },

  createApiKey(data: {
    user_id: number;
    name?: string;
    rate_limit_per_minute?: number;
    monthly_token_quota?: number;
  }) {
    return request<AdminAPIKeyCreated>("/api/v1/admin/api-keys", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  updateApiKey(
    id: string,
    data: {
      is_active?: boolean;
      rate_limit_per_minute?: number;
      monthly_token_quota?: number;
    },
  ) {
    return request<AdminAPIKey>(`/api/v1/admin/api-keys/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  listUsage() {
    return request<UsageSummary[]>("/api/v1/admin/usage");
  },

  listModelMetrics(days = 7) {
    return request<ModelMetricsSummary>(`/api/v1/admin/metrics/models?days=${days}`);
  },

  listConnections() {
    return request<AdminConnection[]>("/api/v1/admin/connections");
  },

  createConnection(data: {
    id: string;
    name: string;
    base_url: string;
    provider_type?: string;
    api_key?: string;
    is_active?: boolean;
  }) {
    return request<AdminConnection>("/api/v1/admin/connections", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  updateConnection(
    id: string,
    data: {
      name?: string;
      base_url?: string;
      provider_type?: string;
      api_key?: string;
      clear_api_key?: boolean;
      is_active?: boolean;
    },
  ) {
    return request<AdminConnection>(`/api/v1/admin/connections/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  deleteConnection(id: string) {
    return request<void>(`/api/v1/admin/connections/${id}`, { method: "DELETE" });
  },

  testConnectionDraft(data: { base_url: string; api_key?: string; provider_type?: string }) {
    return request<AdminConnectionTestResult>("/api/v1/admin/connections/test", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  testSavedConnection(id: string) {
    return request<AdminConnectionTestResult>(`/api/v1/admin/connections/${id}/test`, {
      method: "POST",
    });
  },

  listAdminModels() {
    return request<AdminLLMModel[]>("/api/v1/admin/models");
  },

  createAdminModel(data: {
    id: string;
    model_path: string;
    connection_id: string;
    base_url?: string;
    provider?: string;
    context_length?: number;
    max_output_tokens?: number;
    is_active?: boolean;
    fallback_model_ids?: string[];
  }) {
    return request<AdminLLMModel>("/api/v1/admin/models", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  updateAdminModel(
    id: string,
    data: {
      model_path?: string;
      connection_id?: string;
      clear_connection?: boolean;
      base_url?: string;
      context_length?: number;
      max_output_tokens?: number;
      is_active?: boolean;
      fallback_model_ids?: string[];
    },
  ) {
    return request<AdminLLMModel>(`/api/v1/admin/models/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  deleteAdminModel(id: string) {
    return request<void>(`/api/v1/admin/models/${id}`, { method: "DELETE" });
  },
};
