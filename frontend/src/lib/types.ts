export interface Me {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  student_number: string | null;
  field_of_study: string | null;
  university: string | null;
  semester: string | null;
  bio: string | null;
  is_admin: boolean;
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

export interface CalendarEvent {
  id: number;
  title: string;
  event_date: string;
  event_time: string | null;
  date_label: string;
  description: string | null;
  is_done: boolean;
}

export interface CalendarEventInput {
  title: string;
  event_date: string;
  event_time?: string | null;
  description?: string | null;
  is_done?: boolean;
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
}

export interface LinkInput {
  title: string;
  url: string;
  description?: string | null;
}
