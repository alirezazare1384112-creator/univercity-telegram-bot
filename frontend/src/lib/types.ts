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
}

export interface DashboardCounts {
  courses: number;
  notes: number;
  announcements: number;
  reminders: number;
  events_today: number;
  links: number;
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
