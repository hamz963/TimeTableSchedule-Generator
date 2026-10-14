export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TIMEOUT_MS = 30000;

const TOKEN_KEY = "tte_token";
const USER_KEY = "tte_user";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getUser(): { username: string; role: string } | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function saveSession(token: string, username: string, role: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(USER_KEY, JSON.stringify({ username, role }));
}

export function clearSession() {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
}

export function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export class ApiError extends Error {
  status: number;
  fields?: Record<string, string>;
  constructor(status: number, message: string, fields?: Record<string, string>) {
    super(message);
    this.status = status;
    this.fields = fields;
  }
}

function parseErrorBody(text: string): { message: string; fields?: Record<string, string> } {
  try {
    const data = JSON.parse(text);
    if (typeof data?.detail === "string") return { message: data.detail };
    if (Array.isArray(data?.detail)) {
      // FastAPI validation errors -> field map + summary
      const fields: Record<string, string> = {};
      for (const err of data.detail) {
        const loc = Array.isArray(err.loc) ? err.loc.filter((l: any) => l !== "body") : [];
        if (loc.length) fields[String(loc[loc.length - 1])] = err.msg;
      }
      const first = data.detail[0];
      return { message: first?.msg ?? "Invalid request", fields };
    }
    return { message: text.slice(0, 300) || "Request failed" };
  } catch {
    return { message: text.slice(0, 300) || "Request failed" };
  }
}

export async function api(path: string, init?: RequestInit) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${API_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...authHeaders(), ...(init?.headers ?? {}) },
    });
    if (res.status === 401 && typeof window !== "undefined") {
      clearSession();
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
    }
    if (!res.ok) {
      const { message, fields } = parseErrorBody(await res.text());
      throw new ApiError(res.status, message, fields);
    }
    if (res.status === 204) return null;
    return res.json();
  } catch (e: any) {
    if (e?.name === "AbortError") {
      throw new ApiError(408, `Request timed out after ${TIMEOUT_MS / 1000}s`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}
