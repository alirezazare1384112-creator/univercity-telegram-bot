import type { Dashboard, Me, ScheduleInfo } from "./types";
import { getWebApp } from "./telegram";

const INIT_DATA_HEADER = "X-Telegram-Init-Data";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function authHeaders(): Headers {
  const headers = new Headers();
  const webApp = getWebApp();
  if (webApp?.initData) headers.set(INIT_DATA_HEADER, webApp.initData);
  return headers;
}

async function toError(response: Response): Promise<ApiError> {
  let detail = response.statusText || `HTTP ${response.status}`;
  try {
    const body = (await response.json()) as { detail?: string };
    if (body.detail) detail = body.detail;
  } catch {
    // non JSON body: keep the status text
  }
  return new ApiError(response.status, detail);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = authHeaders();
  new Headers(init.headers).forEach((value, key) => headers.set(key, value));

  const response = await fetch(path, { ...init, headers });
  if (!response.ok) throw await toError(response);
  return (await response.json()) as T;
}

async function requestBlob(path: string): Promise<Blob> {
  const response = await fetch(path, { headers: authHeaders() });
  if (!response.ok) throw await toError(response);
  return response.blob();
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  me: () => request<Me>("/api/me"),
  dashboard: () => request<Dashboard>("/api/dashboard"),
  schedule: () => request<ScheduleInfo>("/api/schedule"),
  scheduleFile: () => requestBlob("/api/schedule/file"),
  uploadSchedule: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ScheduleInfo>("/api/schedule", { method: "POST", body: form });
  },
  deleteSchedule: () => request<{ deleted: boolean }>("/api/schedule", { method: "DELETE" }),
};
