import { useCallback, useEffect, useState } from "react";
import { EditIcon, TrashIcon, XIcon } from "../components/Icons";
import Spinner from "../components/Spinner";
import { ApiError, api } from "../lib/api";
import {
  J_MONTHS,
  daysInMonth,
  isoToJalali,
  jalaliToIso,
  todayIso,
  todayJalali,
} from "../lib/jalali";
import type { JalaliDate } from "../lib/jalali";
import { getWebApp } from "../lib/telegram";
import type { CalendarEvent, CalendarEventInput } from "../lib/types";

type Tab = "pending" | "done";

type PageState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; pending: CalendarEvent[]; done: CalendarEvent[] };

interface FormState {
  id: number | null;
  title: string;
  event_date: string;
  event_time: string;
  description: string;
  is_done: boolean;
}

const EMPTY_FORM: FormState = {
  id: null,
  title: "",
  event_date: "",
  event_time: "",
  description: "",
  is_done: false,
};

function haptic(type: "success" | "error"): void {
  getWebApp()?.HapticFeedback?.notificationOccurred(type);
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "ارتباط با سرور برقرار نشد";
}

function fa(n: number): string {
  return n.toLocaleString("fa-IR");
}

function toInput(event: CalendarEvent): CalendarEventInput {
  return {
    title: event.title,
    event_date: event.event_date,
    event_time: event.event_time,
    description: event.description,
    is_done: event.is_done,
  };
}

export default function CalendarPage() {
  const [page, setPage] = useState<PageState>({ kind: "loading" });
  const [tab, setTab] = useState<Tab>("pending");
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  const load = useCallback(async () => {
    setPage({ kind: "loading" });
    try {
      const [pending, done] = await Promise.all([
        api.calendarEvents(false),
        api.calendarEvents(true),
      ]);
      setPage({ kind: "ready", pending, done });
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
    setForm({ ...EMPTY_FORM, event_date: todayIso() });
  };

  const openEdit = (event: CalendarEvent) => {
    setBanner(null);
    setForm({
      id: event.id,
      title: event.title,
      event_date: event.event_date,
      event_time: event.event_time ?? "",
      description: event.description ?? "",
      is_done: event.is_done,
    });
  };

  const setDatePart = (part: "jy" | "jm" | "jd", value: number) => {
    if (!form) return;
    const base: JalaliDate = form.event_date ? isoToJalali(form.event_date) : todayJalali();
    const next: JalaliDate = { ...base, [part]: value };
    const dim = daysInMonth(next.jy, next.jm);
    if (next.jd > dim) next.jd = dim;
    setForm({ ...form, event_date: jalaliToIso(next) });
  };

  const save = async () => {
    if (!form) return;
    const title = form.title.trim();
    if (!title) {
      setBanner("عنوان رویداد را وارد کنید.");
      return;
    }
    if (!form.event_date) {
      setBanner("تاریخ رویداد را انتخاب کنید.");
      return;
    }
    const payload: CalendarEventInput = {
      title,
      event_date: form.event_date,
      event_time: form.event_time || null,
      description: form.description.trim() || null,
      is_done: form.is_done,
    };
    setSaving(true);
    try {
      if (form.id === null) await api.createEvent(payload);
      else await api.updateEvent(form.id, payload);
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

  const toggle = async (event: CalendarEvent) => {
    try {
      await api.updateEvent(event.id, { ...toInput(event), is_done: !event.is_done });
      haptic("success");
      await load();
    } catch (error: unknown) {
      setBanner(errorMessage(error));
      haptic("error");
    }
  };

  const remove = async (id: number) => {
    try {
      await api.deleteEvent(id);
      haptic("success");
      setConfirmId(null);
      await load();
    } catch (error: unknown) {
      setBanner(errorMessage(error));
      haptic("error");
    }
  };

  if (page.kind === "loading") return <Spinner label="در حال بارگذاری تقویم…" />;

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
  const events = tab === "pending" ? page.pending : page.done;

  const j: JalaliDate = form?.event_date ? isoToJalali(form.event_date) : todayJalali();
  const nowJ = todayJalali();
  const years: number[] = [];
  for (let y = Math.min(nowJ.jy - 1, j.jy); y <= Math.max(nowJ.jy + 3, j.jy); y++) years.push(y);
  const dayCount = daysInMonth(j.jy, j.jm);

  const groups: { label: string; events: CalendarEvent[] }[] = [];
  for (const event of events) {
    const last = groups.at(-1);
    if (last && last.label === event.date_label) last.events.push(event);
    else groups.push({ label: event.date_label, events: [event] });
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">تقویم</h1>
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
          <h2 className="text-sm font-bold">{form.id === null ? "رویداد جدید" : "ویرایش رویداد"}</h2>
          <input
            className={field}
            placeholder="عنوان *"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <div className="grid grid-cols-3 gap-2">
            <select
              className={field}
              value={j.jy}
              onChange={(e) => setDatePart("jy", Number(e.target.value))}
              aria-label="سال"
            >
              {years.map((y) => (
                <option key={y} value={y}>
                  {fa(y)}
                </option>
              ))}
            </select>
            <select
              className={field}
              value={j.jm}
              onChange={(e) => setDatePart("jm", Number(e.target.value))}
              aria-label="ماه"
            >
              {J_MONTHS.map((name, i) => (
                <option key={name} value={i + 1}>
                  {name}
                </option>
              ))}
            </select>
            <select
              className={field}
              value={j.jd}
              onChange={(e) => setDatePart("jd", Number(e.target.value))}
              aria-label="روز"
            >
              {Array.from({ length: dayCount }, (_, i) => i + 1).map((d) => (
                <option key={d} value={d}>
                  {fa(d)}
                </option>
              ))}
            </select>
          </div>
          <input
            type="time"
            className={field}
            value={form.event_time}
            onChange={(e) => setForm({ ...form, event_time: e.target.value })}
          />
          <p className="text-[11px] opacity-60">ساعت را خالی بگذارید برای رویداد تمام‌روز.</p>
          <textarea
            className={`${field} min-h-16`}
            placeholder="توضیح (اختیاری)"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
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
          onClick={() => setTab("pending")}
          className={`rounded-full px-3 py-1.5 text-xs font-bold active:opacity-80 ${
            tab === "pending" ? "bg-blue-600 text-white" : "bg-black/10"
          }`}
        >
          در انتظار ({page.pending.length.toLocaleString("fa-IR")})
        </button>
        <button
          type="button"
          onClick={() => setTab("done")}
          className={`rounded-full px-3 py-1.5 text-xs font-bold active:opacity-80 ${
            tab === "done" ? "bg-blue-600 text-white" : "bg-black/10"
          }`}
        >
          انجام شده ({page.done.length.toLocaleString("fa-IR")})
        </button>
      </div>

      {events.length === 0 && !form ? (
        <div className="rounded-2xl bg-black/5 p-8 text-center">
          <span className="text-4xl">📆</span>
          <p className="mt-2 text-sm opacity-70">
            {tab === "pending" ? "رویداد در پیش ندارید." : "هنوز رویدادی را انجام نداده‌اید."}
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {groups.map((group) => (
            <div key={group.label}>
              <h2 className="mb-2 text-xs font-bold opacity-60">{group.label}</h2>
              <ul className="flex flex-col gap-3">
                {group.events.map((event) => (
                  <li
                    key={event.id}
                    className="rounded-2xl bg-black/5 p-4"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p
                          className={`truncate font-bold ${
                            event.is_done ? "line-through opacity-60" : ""
                          }`}
                        >
                          {event.event_time ? `🕐 ${event.event_time} · ` : "🗓 "}
                          {event.title}
                        </p>
                      </div>
                    </div>
                    {event.description && (
                      <p className="mt-1 whitespace-pre-wrap text-xs opacity-80">
                        {event.description}
                      </p>
                    )}
                    <div className="mt-3 flex gap-2">
                      <button
                        type="button"
                        onClick={() => void toggle(event)}
                        className={`flex-1 rounded-xl px-3 py-2 text-xs font-bold active:opacity-80 ${
                          event.is_done
                            ? "bg-amber-500/10 text-amber-700"
                            : "bg-emerald-600/10 text-emerald-700"
                        }`}
                      >
                        {event.is_done ? "↩ برگرد به در انتظار" : "✔ انجام شد"}
                      </button>
                      <button
                        type="button"
                        onClick={() => openEdit(event)}
                        className="flex items-center justify-center rounded-xl bg-black/10 px-3 py-2 text-xs font-bold text-blue-700 active:opacity-80"
                        title="ویرایش"
                      >
                        <EditIcon className="h-4 w-4" />
                      </button>
                      {confirmId === event.id ? (
                        <>
                          <button
                            type="button"
                            onClick={() => void remove(event.id)}
                            className="flex items-center gap-1 rounded-xl bg-red-600 px-3 py-2 text-xs font-bold text-white active:opacity-80"
                          >
                            <TrashIcon className="h-4 w-4" />
                            حذف شود
                          </button>
                          <button
                            type="button"
                            onClick={() => setConfirmId(null)}
                            className="flex items-center justify-center rounded-xl bg-black/10 px-3 py-2 text-xs font-bold active:opacity-80"
                            title="انصراف"
                          >
                            <XIcon className="h-4 w-4" />
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setConfirmId(event.id)}
                          className="flex items-center justify-center rounded-xl bg-red-600/10 px-3 py-2 text-xs font-bold text-red-700 active:opacity-80"
                          title="حذف"
                        >
                          <TrashIcon className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
