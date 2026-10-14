import type {
  AdminStats,
  AdminUsers,
  Announcement,
  AnnouncementChannel,
  CalendarEvent,
  CalendarEventInput,
  Course,
  CourseGrades,
  CourseInput,
  Dashboard,
  GradeInput,
  GradeItem,
  GradesSummary,
  LinkBookmarklet,
  LinkCredentials,
  LinkInput,
  Me,
  Note,
  NoteInput,
  ProfileInput,
  Reminder,
  ReminderInput,
  ScheduleInfo,
  UniversityLink,
} from "./types";
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

  // 30s timeout: serverless cold starts can be slow, but anything longer
  // than 30s is almost certainly a hung connection. The AbortController
  // lets us reject cleanly instead of leaving the user on a spinner.
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 30_000);
  try {
    const response = await fetch(path, { ...init, headers, signal: controller.signal });
    if (!response.ok) throw await toError(response);
    return (await response.json()) as T;
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(0, "زمان درخواست به پایان رسید. دوباره تلاش کنید.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function jsonInit(method: string, payload: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  };
}

// --- In-memory GET cache (stale-while-revalidate) ---
// Cheap read-only endpoints (dashboard, courses list, notes list) are
// cached for 30s. Navigating between pages no longer triggers a full
// reload — the cached data shows instantly, then a background refresh
// updates if needed.
const CACHE_TTL_MS = 30_000;
const _cache = new Map<string, { data: unknown; expires: number }>();

function _cacheGet<T>(key: string): T | null {
  const entry = _cache.get(key);
  if (!entry) return null;
  if (Date.now() > entry.expires) {
    _cache.delete(key);
    return null;
  }
  return entry.data as T;
}

function _cachePut(key: string, data: unknown): void {
  _cache.set(key, { data, expires: Date.now() + CACHE_TTL_MS });
  // Cap the cache at 20 entries so memory doesn't grow unbounded.
  if (_cache.size > 20) {
    const oldest = _cache.keys().next().value;
    if (oldest) _cache.delete(oldest);
  }
}

/** Invalidate one cache entry (call after a mutation that changes the
 *  data, e.g. after creating a note → invalidate "/api/notes"). */
export function invalidateCache(path: string): void {
  _cache.delete(path);
}

/** Clear every cached entry (used after logout / auth change). */
export function clearApiCache(): void {
  _cache.clear();
}

async function requestCached<T>(path: string): Promise<T> {
  const cached = _cacheGet<T>(path);
  if (cached !== null) return cached;
  const data = await request<T>(path);
  _cachePut(path, data);
  return data;
}

async function requestBlob(path: string): Promise<Blob> {
  const response = await fetch(path, { headers: authHeaders() });
  if (!response.ok) throw await toError(response);
  return response.blob();
}

// File tokens are valid for one hour server-side; reusing one per note keeps
// the file URL stable so the browser can serve <img>/<iframe> from its own
// cache instead of refetching on every preview tap.
const NOTE_TOKEN_REUSE_MS = 55 * 60 * 1000;
const noteTokens = new Map<number, { token: string; media_type: string; expires: number }>();

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  me: () => request<Me>("/api/me"),
  dashboard: () => requestCached<Dashboard>("/api/dashboard"),
  schedule: () => requestCached<ScheduleInfo>("/api/schedule"),
  scheduleFile: () => requestBlob("/api/schedule/file"),
  uploadSchedule: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ScheduleInfo>("/api/schedule", { method: "POST", body: form }).then(
      (r) => {
        invalidateCache("/api/schedule");
        return r;
      },
    );
  },
  deleteSchedule: () =>
    request<{ deleted: boolean }>("/api/schedule", { method: "DELETE" }).then((r) => {
      invalidateCache("/api/schedule");
      return r;
    }),
  courses: () => requestCached<Course[]>("/api/courses"),
  createCourse: (payload: CourseInput) =>
    request<Course>("/api/courses", jsonInit("POST", payload)).then((r) => {
      invalidateCache("/api/courses");
      return r;
    }),
  updateCourse: (id: number, payload: CourseInput) =>
    request<Course>(`/api/courses/${id}`, jsonInit("PUT", payload)).then((r) => {
      invalidateCache("/api/courses");
      return r;
    }),
  deleteCourse: (id: number) =>
    request<{ deleted: boolean }>(`/api/courses/${id}`, { method: "DELETE" }).then(
      (r) => {
        invalidateCache("/api/courses");
        return r;
      },
    ),
  courseGrades: (courseId: number) =>
    requestCached<CourseGrades>(`/api/courses/${courseId}/grades`),
  gradesSummary: () => requestCached<GradesSummary>("/api/grades"),
  createGrade: (courseId: number, payload: GradeInput) =>
    request<GradeItem>(`/api/courses/${courseId}/grades`, jsonInit("POST", payload)).then(
      (r) => {
        invalidateCache(`/api/courses/${courseId}/grades`);
        invalidateCache("/api/grades");
        return r;
      },
    ),
  updateGrade: (courseId: number, itemId: number, payload: GradeInput) =>
    request<GradeItem>(
      `/api/courses/${courseId}/grades/${itemId}`,
      jsonInit("PUT", payload),
    ).then((r) => {
      invalidateCache(`/api/courses/${courseId}/grades`);
      invalidateCache("/api/grades");
      return r;
    }),
  deleteGrade: (courseId: number, itemId: number) =>
    request<{ deleted: boolean }>(
      `/api/courses/${courseId}/grades/${itemId}`,
      { method: "DELETE" },
    ).then((r) => {
      invalidateCache(`/api/courses/${courseId}/grades`);
      invalidateCache("/api/grades");
      return r;
    }),
  notes: (courseId?: number) =>
    requestCached<Note[]>(
      courseId === undefined ? "/api/notes" : `/api/notes?course_id=${courseId}`,
    ),
  uploadNote: (file: File, meta: NoteInput) => {
    const form = new FormData();
    form.append("file", file);
    form.append("title", meta.title);
    if (meta.description) form.append("description", meta.description);
    if (meta.course_id != null) form.append("course_id", String(meta.course_id));
    return request<Note>("/api/notes", { method: "POST", body: form }).then((r) => {
      invalidateCache("/api/notes");
      invalidateCache("/api/dashboard");
      return r;
    });
  },
  updateNote: (id: number, payload: NoteInput) =>
    request<Note>(`/api/notes/${id}`, jsonInit("PUT", payload)).then((r) => {
      invalidateCache("/api/notes");
      return r;
    }),
  deleteNote: (id: number) =>
    request<{ deleted: boolean }>(`/api/notes/${id}`, { method: "DELETE" }).then(
      (r) => {
        invalidateCache("/api/notes");
        invalidateCache("/api/dashboard");
        return r;
      },
    ),
  sendNoteToTelegram: (id: number) =>
    request<{ sent: boolean }>(`/api/notes/${id}/send`, { method: "POST" }),
  shareNote: (id: number, recipient: string) => {
    const form = new FormData();
    form.append("recipient", recipient);
    return request<{ sent: boolean; recipient: string }>(
      `/api/notes/${id}/share`,
      { method: "POST", body: form },
    ).then((r) => {
      invalidateCache("/api/notes");
      invalidateCache("/api/dashboard");
      return r;
    });
  },
  noteFileToken: (id: number) => {
    const hit = noteTokens.get(id);
    if (hit && hit.expires > Date.now()) {
      return Promise.resolve({ token: hit.token, media_type: hit.media_type });
    }
    return request<{ token: string; media_type: string }>(`/api/notes/${id}/file-token`, {
      method: "POST",
    }).then((fresh) => {
      noteTokens.set(id, { ...fresh, expires: Date.now() + NOTE_TOKEN_REUSE_MS });
      return fresh;
    });
  },
  calendarEvents: (done = false) =>
    requestCached<CalendarEvent[]>(`/api/calendar?done=${done}`),
  createEvent: (payload: CalendarEventInput) =>
    request<CalendarEvent>("/api/calendar", jsonInit("POST", payload)).then((r) => {
      invalidateCache("/api/calendar?done=false");
      invalidateCache("/api/calendar?done=true");
      return r;
    }),
  updateEvent: (id: number, payload: CalendarEventInput) =>
    request<CalendarEvent>(`/api/calendar/${id}`, jsonInit("PUT", payload)).then((r) => {
      invalidateCache("/api/calendar?done=false");
      invalidateCache("/api/calendar?done=true");
      return r;
    }),
  deleteEvent: (id: number) =>
    request<{ deleted: boolean }>(`/api/calendar/${id}`, { method: "DELETE" }).then(
      (r) => {
        invalidateCache("/api/calendar?done=false");
        invalidateCache("/api/calendar?done=true");
        return r;
      },
    ),
  reminders: (activeOnly = false) =>
    requestCached<Reminder[]>(`/api/reminders?active_only=${activeOnly}`),
  createReminder: (payload: ReminderInput) =>
    request<Reminder>("/api/reminders", jsonInit("POST", payload)).then((r) => {
      invalidateCache("/api/reminders?active_only=false");
      invalidateCache("/api/reminders?active_only=true");
      return r;
    }),
  updateReminder: (id: number, payload: ReminderInput) =>
    request<Reminder>(`/api/reminders/${id}`, jsonInit("PUT", payload)).then((r) => {
      invalidateCache("/api/reminders?active_only=false");
      invalidateCache("/api/reminders?active_only=true");
      return r;
    }),
  deleteReminder: (id: number) =>
    request<{ deleted: boolean }>(`/api/reminders/${id}`, { method: "DELETE" }).then(
      (r) => {
        invalidateCache("/api/reminders?active_only=false");
        invalidateCache("/api/reminders?active_only=true");
        return r;
      },
    ),
  announcements: () => requestCached<Announcement[]>("/api/announcements"),
  announcementFile: (id: number) => requestBlob(`/api/announcements/${id}/file`),
  deleteAnnouncement: (id: number) =>
    request<{ deleted: boolean }>(`/api/announcements/${id}`, { method: "DELETE" }).then(
      (r) => {
        invalidateCache("/api/announcements");
        return r;
      },
    ),
  channels: () => requestCached<AnnouncementChannel[]>("/api/announcements/channels"),
  addChannel: (url: string) =>
    request<AnnouncementChannel>(
      "/api/announcements/channels",
      jsonInit("POST", { url }),
    ).then((r) => {
      invalidateCache("/api/announcements/channels");
      return r;
    }),
  deleteChannel: (id: number) =>
    request<{ deleted: boolean }>(`/api/announcements/channels/${id}`, {
      method: "DELETE",
    }).then((r) => {
      invalidateCache("/api/announcements/channels");
      return r;
    }),
  links: () => requestCached<UniversityLink[]>("/api/links"),
  createLink: (payload: LinkInput) =>
    request<UniversityLink>("/api/links", jsonInit("POST", payload)).then((r) => {
      invalidateCache("/api/links");
      return r;
    }),
  updateLink: (id: number, payload: LinkInput) =>
    request<UniversityLink>(`/api/links/${id}`, jsonInit("PUT", payload)).then((r) => {
      invalidateCache("/api/links");
      return r;
    }),
  deleteLink: (id: number) =>
    request<{ deleted: boolean }>(`/api/links/${id}`, { method: "DELETE" }).then((r) => {
      invalidateCache("/api/links");
      return r;
    }),
  linkCredentials: (id: number) =>
    request<LinkCredentials>(`/api/links/${id}/credentials`),
  linkBookmarklet: (id: number) =>
    request<LinkBookmarklet>(`/api/links/${id}/bookmarklet`),
  updateMe: (payload: ProfileInput) => request<Me>("/api/me", jsonInit("PUT", payload)),
  adminStats: () => requestCached<AdminStats>("/api/admin/stats"),
  adminUsers: (limit = 50) =>
    requestCached<AdminUsers>(`/api/admin/users?limit=${limit}`),
};
