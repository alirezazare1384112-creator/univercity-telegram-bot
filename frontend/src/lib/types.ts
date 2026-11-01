export interface Me {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  photo_url: string | null;
  photo_token: string | null;
  student_number: string | null;
  field_of_study: string | null;
  university: string | null;
  semester: string | null;
  bio: string | null;
  is_admin: boolean;
  credentials_enabled: boolean;
}

export interface ProfileInput {
  student_number: string | null;
  field_of_study: string | null;
  university: string | null;
  semester: string | null;
  bio: string | null;
}

export interface AdminStats {
  users: number;
  active_users: number;
  admins: number;
  courses: number;
  grades: number;
  reminders: number;
  announcements: number;
  notes: number;
  links: number;
  events: number;
  schedules: number;
}

export interface AdminUser {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  is_active: boolean;
}

export interface AdminUsers {
  total: number;
  active: number;
  users: AdminUser[];
}

export interface DashboardCounts {
  courses: number;
  notes: number;
  announcements: number;
  reminders: number;
  events_today: number;
  links: number;
  grade_items: number;
}

export interface NextReminder {
  id: number;
  title: string;
  when: string;
}

export interface Dashboard {
  user: Me;
  today: string;
  counts: DashboardCounts;
  schedule: boolean;
  next_reminder: NextReminder | null;
}

export interface ScheduleInfo {
  exists: boolean;
  file_type: string | null;
  caption: string | null;
}

export interface Course {
  id: number;
  name: string;
  units: number;
  teacher_name: string | null;
  semester: string | null;
  academic_year: string | null;
}

export interface CourseInput {
  name: string;
  units: number;
  teacher_name?: string | null;
  semester?: string | null;
  academic_year?: string | null;
}

export type GradeKind = "HOMEWORK" | "QUIZ" | "MIDTERM" | "FINAL" | "PROJECT" | "OTHER";

export const GRADE_KIND_LABELS: Record<GradeKind, string> = {
  HOMEWORK: "تکلیف",
  QUIZ: "کوییز",
  MIDTERM: "میان‌ترم",
  FINAL: "پایان‌ترم",
  PROJECT: "پروژه",
  OTHER: "سایر",
};

export const GRADE_KINDS = Object.keys(GRADE_KIND_LABELS) as GradeKind[];

export interface GradeItem {
  id: number;
  title: string;
  score: number;
  max_score: number;
  kind: GradeKind;
  description: string | null;
  percent: number;
}

export interface GradeTotals {
  total: number;
  maximum: number;
  percent: number;
}

export interface CourseGrades {
  course: Course;
  items: GradeItem[];
  totals: GradeTotals;
}

export interface CourseGradeSummary {
  course_id: number;
  name: string;
  item_count: number;
  totals: GradeTotals;
}

export interface GradesSummary {
  courses: CourseGradeSummary[];
  totals: GradeTotals;
  item_count: number;
}

export interface GradeInput {
  title: string;
  score: number;
  max_score: number;
  kind: GradeKind;
  description?: string | null;
}

export interface Note {
  id: number;
  title: string;
  description: string | null;
  course_id: number | null;
  course_name: string | null;
  file_type: "photo" | "document";
  file_name: string | null;
}

export interface NoteInput {
  title: string;
  description?: string | null;
  course_id?: number | null;
}

export type EventType =
  | "EXAM"
  | "QUIZ"
  | "ASSIGNMENT"
  | "PROJECT"
  | "PRESENTATION"
  | "CLASS"
  | "TASK"
  | "OTHER";

export const EVENT_TYPE_LABELS: Record<EventType, string> = {
  EXAM: "امتحان",
  QUIZ: "کوییز",
  ASSIGNMENT: "تکلیف",
  PROJECT: "پروژه",
  PRESENTATION: "ارائه",
  CLASS: "کلاس",
  TASK: "کار شخصی",
  OTHER: "سایر",
};

export const EVENT_TYPES = Object.keys(EVENT_TYPE_LABELS) as EventType[];

// Colour classes for each event type (light/dark aware)
export const EVENT_TYPE_COLORS: Record<
  EventType,
  { dot: string; bg: string; text: string; border: string }
> = {
  EXAM: {
    dot: "bg-red-500",
    bg: "bg-red-500/10 dark:bg-red-500/15",
    text: "text-red-700 dark:text-red-400",
    border: "border-r-red-500",
  },
  QUIZ: {
    dot: "bg-amber-500",
    bg: "bg-amber-500/10 dark:bg-amber-500/15",
    text: "text-amber-700 dark:text-amber-400",
    border: "border-r-amber-500",
  },
  ASSIGNMENT: {
    dot: "bg-emerald-500",
    bg: "bg-emerald-500/10 dark:bg-emerald-500/15",
    text: "text-emerald-700 dark:text-emerald-400",
    border: "border-r-emerald-500",
  },
  PROJECT: {
    dot: "bg-teal-500",
    bg: "bg-teal-500/10 dark:bg-teal-500/15",
    text: "text-teal-700 dark:text-teal-400",
    border: "border-r-teal-500",
  },
  PRESENTATION: {
    dot: "bg-blue-500",
    bg: "bg-blue-500/10 dark:bg-blue-500/15",
    text: "text-blue-700 dark:text-blue-400",
    border: "border-r-blue-500",
  },
  CLASS: {
    dot: "bg-violet-500",
    bg: "bg-violet-500/10 dark:bg-violet-500/15",
    text: "text-violet-700 dark:text-violet-400",
    border: "border-r-violet-500",
  },
  TASK: {
    dot: "bg-orange-500",
    bg: "bg-orange-500/10 dark:bg-orange-500/15",
    text: "text-orange-700 dark:text-orange-400",
    border: "border-r-orange-500",
  },
  OTHER: {
    dot: "bg-gray-400",
    bg: "bg-gray-400/10 dark:bg-gray-400/15",
    text: "text-gray-600 dark:text-gray-400",
    border: "border-r-gray-400",
  },
};

export interface CalendarEvent {
  id: number;
  title: string;
  event_date: string;
  event_time: string | null;
  date_label: string;
  description: string | null;
  is_done: boolean;
  event_type: EventType;
  course_id: number | null;
  course_name: string | null;
}

export interface CalendarEventInput {
  title: string;
  event_date: string;
  event_time?: string | null;
  description?: string | null;
  is_done?: boolean;
  event_type?: EventType;
  course_id?: number | null;
}

export type RepeatType = "NONE" | "DAILY" | "WEEKLY" | "MONTHLY";

export const REPEAT_LABELS: Record<RepeatType, string> = {
  NONE: "بدون تکرار",
  DAILY: "هر روز",
  WEEKLY: "هر هفته",
  MONTHLY: "هر ماه",
};

export const REPEAT_TYPES = Object.keys(REPEAT_LABELS) as RepeatType[];

export type AlertOffset = "AT_TIME" | "HOURS_1" | "DAYS_1";

export const ALERT_LABELS: Record<AlertOffset, string> = {
  AT_TIME: "در زمان رویداد",
  HOURS_1: "۱ ساعت قبل",
  DAYS_1: "۱ روز قبل",
};

export const ALERT_OFFSETS = Object.keys(ALERT_LABELS) as AlertOffset[];

export interface Reminder {
  id: number;
  title: string;
  description: string | null;
  course_id: number | null;
  course_name: string | null;
  local_datetime: string;
  display: string;
  repeat_type: RepeatType;
  repeat_label: string;
  is_active: boolean;
  alert_offsets: AlertOffset[];
}

export interface ReminderInput {
  title: string;
  local_datetime: string;
  description?: string | null;
  course_id?: number | null;
  repeat_type?: RepeatType;
  is_active?: boolean;
  alert_offsets?: AlertOffset[];
}

export interface Announcement {
  id: number;
  title: string;
  text: string | null;
  source: "telegram" | "eitaa";
  source_url: string | null;
  file_type: "photo" | "document" | null;
  created_at: string;
  display: string;
}

export interface AnnouncementChannel {
  id: number;
  platform: "telegram" | "eitaa";
  url: string;
  handle: string;
  created_at: string;
}

export interface UniversityLink {
  id: number;
  title: string;
  url: string;
  description: string | null;
  has_credentials: boolean;
}

export interface LinkInput {
  title: string;
  url: string;
  description?: string | null;
  username?: string | null;
  password?: string | null;
}

export interface LinkCredentials {
  has_credentials: boolean;
  username?: string;
  password?: string;
  url?: string;
}

export interface LinkBookmarklet {
  has_bookmarklet: boolean;
  bookmarklet?: string;
  title?: string;
  url?: string;
}
