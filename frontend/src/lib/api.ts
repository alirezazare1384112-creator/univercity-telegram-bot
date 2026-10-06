import type { Dashboard, Me } from "./types";
import { getWebApp } from "./telegram";

const INIT_DATA_HEADER = "X-Telegram-Init-Data";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const webApp = getWebApp();
  if (webApp?.initData) headers.set(INIT_DATA_HEADER, webApp.initData);

  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    let detail = response.statusText || `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // non JSON body: keep the status text
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  me: () => request<Me>("/api/me"),
  dashboard: () => request<Dashboard>("/api/dashboard"),
};
