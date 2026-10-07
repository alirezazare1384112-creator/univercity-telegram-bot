import type {
  AdminStats,
  AdminUsers,
  Announcement,
  CalendarEvent,
  CalendarEventInput,
  Course,
  CourseGrades,
  CourseInput,
  Dashboard,
  GradeInput,
  GradeItem,
  GradesSummary,
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

  const response = await fetch(path, { ...init, headers });
  if (!response.ok) throw await toError(response);
  return (await response.json()) as T;
}

function jsonInit(method: string, payload: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  };
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
  courses: () => request<Course[]>("/api/courses"),
  createCourse: (payload: CourseInput) =>
    request<Course>("/api/courses", jsonInit("POST", payload)),
  updateCourse: (id: number, payload: CourseInput) =>
    request<Course>(`/api/courses/${id}`, jsonInit("PUT", payload)),
  deleteCourse: (id: number) =>
    request<{ deleted: boolean }>(`/api/courses/${id}`, { method: "DELETE" }),
  courseGrades: (courseId: number) =>
    request<CourseGrades>(`/api/courses/${courseId}/grades`),
  gradesSummary: () => request<GradesSummary>("/api/grades"),
  createGrade: (courseId: number, payload: GradeInput) =>
    request<GradeItem>(`/api/courses/${courseId}/grades`, jsonInit("POST", payload)),
  updateGrade: (courseId: number, itemId: number, payload: GradeInput) =>
    request<GradeItem>(`/api/courses/${courseId}/grades/${itemId}`, jsonInit("PUT", payload)),
  deleteGrade: (courseId: number, itemId: number) =>
    request<{ deleted: boolean }>(`/api/courses/${courseId}/grades/${itemId}`, {
      method: "DELETE",
    }),
  notes: (courseId?: number) =>
    request<Note[]>(
      courseId === undefined ? "/api/notes" : `/api/notes?course_id=${courseId}`,
    ),
  uploadNote: (file: File, meta: NoteInput) => {
    const form = new FormData();
    form.append("file", file);
    form.append("title", meta.title);
    if (meta.description) form.append("description", meta.description);
    if (meta.course_id != null) form.append("course_id", String(meta.course_id));
    return request<Note>("/api/notes", { method: "POST", body: form });
  },
  updateNote: (id: number, payload: NoteInput) =>
    request<Note>(`/api/notes/${id}`, jsonInit("PUT", payload)),
  deleteNote: (id: number) =>
    request<{ deleted: boolean }>(`/api/notes/${id}`, { method: "DELETE" }),
  noteFile: (id: number) => requestBlob(`/api/notes/${id}/file`),
  calendarEvents: (done = false) =>
    request<CalendarEvent[]>(`/api/calendar?done=${done}`),
  createEvent: (payload: CalendarEventInput) =>
    request<CalendarEvent>("/api/calendar", jsonInit("POST", payload)),
  updateEvent: (id: number, payload: CalendarEventInput) =>
    request<CalendarEvent>(`/api/calendar/${id}`, jsonInit("PUT", payload)),
  deleteEvent: (id: number) =>
    request<{ deleted: boolean }>(`/api/calendar/${id}`, { method: "DELETE" }),
  reminders: (activeOnly = false) =>
    request<Reminder[]>(`/api/reminders?active_only=${activeOnly}`),
  createReminder: (payload: ReminderInput) =>
    request<Reminder>("/api/reminders", jsonInit("POST", payload)),
  updateReminder: (id: number, payload: ReminderInput) =>
    request<Reminder>(`/api/reminders/${id}`, jsonInit("PUT", payload)),
  deleteReminder: (id: number) =>
    request<{ deleted: boolean }>(`/api/reminders/${id}`, { method: "DELETE" }),
  announcements: () => request<Announcement[]>("/api/announcements"),
  announcementFile: (id: number) => requestBlob(`/api/announcements/${id}/file`),
  deleteAnnouncement: (id: number) =>
    request<{ deleted: boolean }>(`/api/announcements/${id}`, { method: "DELETE" }),
  links: () => request<UniversityLink[]>("/api/links"),
  createLink: (payload: LinkInput) =>
    request<UniversityLink>("/api/links", jsonInit("POST", payload)),
  updateLink: (id: number, payload: LinkInput) =>
    request<UniversityLink>(`/api/links/${id}`, jsonInit("PUT", payload)),
  deleteLink: (id: number) =>
    request<{ deleted: boolean }>(`/api/links/${id}`, { method: "DELETE" }),
  updateMe: (payload: ProfileInput) => request<Me>("/api/me", jsonInit("PUT", payload)),
  adminStats: () => request<AdminStats>("/api/admin/stats"),
  adminUsers: (limit = 50) => request<AdminUsers>(`/api/admin/users?limit=${limit}`),
};
