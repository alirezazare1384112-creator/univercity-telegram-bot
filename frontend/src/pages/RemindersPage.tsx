import { useCallback, useEffect, useState } from "react";
import Spinner from "../components/Spinner";
import { ApiError, api } from "../lib/api";
import { getWebApp } from "../lib/telegram";
import {
  ALERT_LABELS,
  ALERT_OFFSETS,
  REPEAT_LABELS,
  REPEAT_TYPES,
  type AlertOffset,
  type Course,
  type Reminder,
  type ReminderInput,
  type RepeatType,
} from "../lib/types";

type Tab = "active" | "paused";

type PageState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; reminders: Reminder[]; courses: Course[] };

interface FormState {
  id: number | null;
  title: string;
  local_datetime: string;
  description: string;
  course_id: string;
  repeat_type: RepeatType;
  alert_offsets: AlertOffset[];
  is_active: boolean;
}

const EMPTY_FORM: FormState = {
  id: null,
  title: "",
  local_datetime: "",
  description: "",
  course_id: "",
  repeat_type: "NONE",
  alert_offsets: ["AT_TIME"],
  is_active: true,
};

function haptic(type: "success" | "error"): void {
  getWebApp()?.HapticFeedback?.notificationOccurred(type);
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "ارتباط با سرور برقرار نشد";
}

function toInput(reminder: Reminder): ReminderInput {
  return {
    title: reminder.title,
    local_datetime: reminder.local_datetime.slice(0, 16),
    description: reminder.description,
    course_id: reminder.course_id,
    repeat_type: reminder.repeat_type,
    is_active: reminder.is_active,
    alert_offsets: reminder.alert_offsets,
  };
}

export default function RemindersPage() {
  const [page, setPage] = useState<PageState>({ kind: "loading" });
  const [tab, setTab] = useState<Tab>("active");
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  const load = useCallback(async () => {
    setPage({ kind: "loading" });
    try {
      const [reminders, courses] = await Promise.all([api.reminders(), api.courses()]);
      setPage({ kind: "ready", reminders, courses });
    } catch (error: unknown) {
      setPage({ kind: "error", message: errorMessage(error) });
      haptic("error");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openCreate = () => {
    setBanner(null);
    setForm({ ...EMPTY_FORM });
  };

  const openEdit = (reminder: Reminder) => {
    setBanner(null);
    setForm({
      id: reminder.id,
      title: reminder.title,
      local_datetime: reminder.local_datetime.slice(0, 16),
      description: reminder.description ?? "",
      course_id: reminder.course_id === null ? "" : String(reminder.course_id),
      repeat_type: reminder.repeat_type,
      alert_offsets: [...reminder.alert_offsets],
      is_active: reminder.is_active,
    });
  };

  const toggleOffset = (offset: AlertOffset, checked: boolean) => {
    if (!form) return;
    const next = checked
      ? [...form.alert_offsets, offset]
      : form.alert_offsets.filter((item) => item !== offset);
    setForm({ ...form, alert_offsets: next });
  };

  const save = async () => {
    if (!form) return;
    const title = form.title.trim();
    if (!title) {
      setBanner("عنوان یادآوری را وارد کنید.");
      return;
    }
    if (!form.local_datetime) {
      setBanner("تاریخ و ساعت را انتخاب کنید.");
      return;
    }
    if (form.alert_offsets.length === 0) {
      setBanner("حداقل یک هشدار انتخاب کنید.");
      return;
    }
    const payload: ReminderInput = {
      title,
      local_datetime: form.local_datetime,
      description: form.description.trim() || null,
      course_id: form.course_id ? Number(form.course_id) : null,
      repeat_type: form.repeat_type,
      is_active: form.is_active,
      alert_offsets: form.alert_offsets,
    };
    setSaving(true);
    try {
      if (form.id === null) await api.createReminder(payload);
      else await api.updateReminder(form.id, payload);
      haptic("success");
      setForm(null);
      setBanner(null);
      await load();
    } catch (error: unknown) {
      setBanner(errorMessage(error));
      haptic("error");
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (reminder: Reminder) => {
    try {
      await api.updateReminder(reminder.id, {
        ...toInput(reminder),
        is_active: !reminder.is_active,
      });
      haptic("success");
      await load();
    } catch (error: unknown) {
      setBanner(errorMessage(error));
      haptic("error");
    }
  };

  const remove = async (id: number) => {
    try {
      await api.deleteReminder(id);
      haptic("success");
      setConfirmId(null);
      await load();
    } catch (error: unknown) {
      setBanner(errorMessage(error));
      haptic("error");
    }
  };

  if (page.kind === "loading") return <Spinner label="در حال بارگذاری یادآوری‌ها…" />;

  if (page.kind === "error") {
    return (
      <section className="rounded-2xl bg-black/5 p-6 text-center">
        <p className="text-sm">{page.message}</p>
        <button
          type="button"
          onClick={() => void load()}
          className="mt-3 rounded-xl bg-blue-600 px-4 py-2 text-sm font-bold text-white active:opacity-80"
        >
          تلاش دوباره
        </button>
      </section>
    );
  }

  const field =
    "w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm dark:bg-black/20";
  const active = page.reminders.filter((reminder) => reminder.is_active);
  const paused = page.reminders.filter((reminder) => !reminder.is_active);
  const visible = tab === "active" ? active : paused;

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">یادآوری‌ها</h1>
        <button
          type="button"
          onClick={openCreate}
          className="rounded-xl bg-blue-600 px-3 py-2 text-xs font-bold text-white active:opacity-80"
        >
          + افزودن
        </button>
      </div>

      {banner && (
        <p className="rounded-xl bg-red-600/10 px-3 py-2 text-center text-xs text-red-700">
          {banner}
        </p>
      )}

      {form && (
        <div className="flex flex-col gap-3 rounded-2xl bg-black/5 p-4">
          <h2 className="text-sm font-bold">
            {form.id === null ? "یادآوری جدید" : "ویرایش یادآوری"}
          </h2>
          <input
            className={field}
            placeholder="عنوان *"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <input
            type="datetime-local"
            className={field}
            value={form.local_datetime}
            onChange={(e) => setForm({ ...form, local_datetime: e.target.value })}
          />
          <textarea
            className={`${field} min-h-16`}
            placeholder="توضیح (اختیاری)"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <select
              className={field}
              value={form.course_id}
              onChange={(e) => setForm({ ...form, course_id: e.target.value })}
            >
              <option value="">بدون درس</option>
              {page.courses.map((course) => (
                <option key={course.id} value={course.id}>
                  {course.name}
                </option>
              ))}
            </select>
            <select
              className={field}
              value={form.repeat_type}
              onChange={(e) =>
                setForm({ ...form, repeat_type: e.target.value as RepeatType })
              }
            >
              {REPEAT_TYPES.map((repeat) => (
                <option key={repeat} value={repeat}>
                  {REPEAT_LABELS[repeat]}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <p className="text-[11px] font-bold opacity-70">هشدارها:</p>
            {ALERT_OFFSETS.map((offset) => (
              <label
                key={offset}
                className="flex items-center gap-2 rounded-xl bg-white px-3 py-2 text-xs dark:bg-black/20"
              >
                <input
                  type="checkbox"
                  checked={form.alert_offsets.includes(offset)}
                  onChange={(e) => toggleOffset(offset, e.target.checked)}
                />
                {ALERT_LABELS[offset]}
              </label>
            ))}
          </div>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => void save()}
              disabled={saving}
              className="flex-1 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-bold text-white active:opacity-80 disabled:opacity-60"
            >
              {saving ? "در حال ذخیره…" : "ذخیره"}
            </button>
            <button
              type="button"
              onClick={() => {
                setForm(null);
                setBanner(null);
              }}
              className="flex-1 rounded-xl bg-black/10 px-4 py-2.5 text-sm font-bold active:opacity-80"
            >
              انصراف
            </button>
          </div>
        </div>
      )}

      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setTab("active")}
          className={`rounded-full px-3 py-1.5 text-xs font-bold active:opacity-80 ${
            tab === "active" ? "bg-blue-600 text-white" : "bg-black/10"
          }`}
        >
          فعال ({active.length.toLocaleString("fa-IR")})
        </button>
        <button
          type="button"
          onClick={() => setTab("paused")}
          className={`rounded-full px-3 py-1.5 text-xs font-bold active:opacity-80 ${
            tab === "paused" ? "bg-blue-600 text-white" : "bg-black/10"
          }`}
        >
          متوقف ({paused.length.toLocaleString("fa-IR")})
        </button>
      </div>

      {visible.length === 0 && !form ? (
        <div className="rounded-2xl bg-black/5 p-8 text-center">
          <span className="text-4xl">⏰</span>
          <p className="mt-2 text-sm opacity-70">
            {tab === "active" ? "یادآوری فعالی ندارید." : "یادآوری متوقفی ندارید."}
          </p>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {visible.map((reminder) => (
            <li key={reminder.id} className="rounded-2xl bg-black/5 p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-bold">{reminder.title}</p>
                  <p className="mt-0.5 text-xs opacity-70">
                    🕒 {reminder.display}
                    {reminder.course_name ? ` · ${reminder.course_name}` : ""}
                  </p>
                </div>
                <span
                  className={`shrink-0 rounded-full px-2 py-1 text-[11px] font-bold ${
                    reminder.is_active
                      ? "bg-emerald-600/10 text-emerald-700"
                      : "bg-amber-500/10 text-amber-700"
                  }`}
                >
                  {reminder.is_active ? "فعال" : "متوقف"}
                </span>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <span className="rounded-full bg-black/10 px-2 py-0.5 text-[11px]">
                  {reminder.repeat_label}
                </span>
                {reminder.alert_offsets.map((offset) => (
                  <span
                    key={offset}
                    className="rounded-full bg-blue-600/10 px-2 py-0.5 text-[11px] text-blue-700"
                  >
                    {ALERT_LABELS[offset]}
                  </span>
                ))}
              </div>
              {reminder.description && (
                <p className="mt-2 whitespace-pre-wrap text-xs opacity-80">
                  {reminder.description}
                </p>
              )}
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => void toggleActive(reminder)}
                  className={`flex-1 rounded-xl px-3 py-2 text-xs font-bold active:opacity-80 ${
                    reminder.is_active
                      ? "bg-amber-500/10 text-amber-700"
                      : "bg-emerald-600/10 text-emerald-700"
                  }`}
                >
                  {reminder.is_active ? "⏸ توقف" : "▶ ادامه"}
                </button>
                <button
                  type="button"
                  onClick={() => openEdit(reminder)}
                  className="rounded-xl bg-black/10 px-3 py-2 text-xs font-bold active:opacity-80"
                >
                  ✏️
                </button>
                {confirmId === reminder.id ? (
                  <>
                    <button
                      type="button"
                      onClick={() => void remove(reminder.id)}
                      className="rounded-xl bg-red-600 px-3 py-2 text-xs font-bold text-white active:opacity-80"
                    >
                      حذف شود
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmId(null)}
                      className="rounded-xl bg-black/10 px-3 py-2 text-xs font-bold active:opacity-80"
                    >
                      انصراف
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    onClick={() => setConfirmId(reminder.id)}
                    className="rounded-xl bg-red-600/10 px-3 py-2 text-xs font-bold text-red-700 active:opacity-80"
                  >
                    🗑
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
