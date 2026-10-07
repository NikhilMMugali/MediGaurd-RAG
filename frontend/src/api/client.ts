const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler;
}

function getToken(): string | null {
  return sessionStorage.getItem("medigaurd_token");
}

export function setToken(token: string | null) {
  if (token) sessionStorage.setItem("medigaurd_token", token);
  else sessionStorage.removeItem("medigaurd_token");
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  formData?: FormData;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let body: BodyInit | undefined;
  if (options.formData) {
    body = options.formData;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method || "GET",
    headers,
    body,
  });

  if (response.status === 401) {
    setToken(null);
    onUnauthorized?.();
    throw new ApiError(401, "Session expired. Please log in again.");
  }

  if (!response.ok) {
    let message = "Something went wrong while processing your request.";
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
    } catch {
      // keep generic message — never surface raw server/network internals
    }
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
