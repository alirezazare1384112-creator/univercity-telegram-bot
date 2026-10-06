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
