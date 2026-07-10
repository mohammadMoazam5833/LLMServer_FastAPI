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
};
