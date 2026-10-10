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

// For binary responses (the authenticated PDF file endpoint) — same auth
// header and error handling as apiRequest, but returns a Blob instead of
// parsing JSON. The caller turns this into an object URL; the PDF is never
// fetched via a plain <iframe src> or <a href>, which couldn't carry the
// Authorization header at all (section 10B).
export async function apiRequestBlob(path: string): Promise<Blob> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(`${API_BASE_URL}${path}`, { headers });

  if (response.status === 401) {
    setToken(null);
    onUnauthorized?.();
    throw new ApiError(401, "Session expired. Please log in again.");
  }
  if (!response.ok) {
    let message = "Could not load this file.";
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
    } catch {
      // keep generic message
    }
    throw new ApiError(response.status, message);
  }
  return response.blob();
}

// Multipart upload with REAL byte-level progress (fetch cannot report upload
// progress). Same Authorization header and 401/error handling as apiRequest.
export function apiUploadWithProgress<T>(path: string, formData: FormData, onProgress: (fraction: number) => void): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}${path}`);
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onerror = () => reject(new ApiError(0, "Could not reach the server. Check your connection and try again."));
    xhr.onload = () => {
      if (xhr.status === 401) {
        setToken(null);
        onUnauthorized?.();
        reject(new ApiError(401, "Session expired. Please log in again."));
        return;
      }
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        // non-JSON error body — keep the generic message below
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as T);
        return;
      }
      const detail = (body as { detail?: unknown } | null)?.detail;
      reject(new ApiError(xhr.status, typeof detail === "string" ? detail : "Something went wrong while processing your request."));
    };
    xhr.send(formData);
  });
}
