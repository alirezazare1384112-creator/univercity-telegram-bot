import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckIcon, EditIcon, PlusIcon, TrashIcon, XIcon } from "../components/Icons";
import Spinner from "../components/Spinner";
import { ApiError, api } from "../lib/api";
import {
  J_MONTHS,
  daysInMonth,
  isoToJalali,
  jalaliToIso,
  todayIso,
  todayJalali,
  type JalaliDate,
} from "../lib/jalali";
import { getWebApp } from "../lib/telegram";
import {
  EVENT_TYPES,
  EVENT_TYPE_LABELS,
  EVENT_TYPE_COLORS,
  type CalendarEvent,
  type CalendarEventInput,
  type Course,
  type EventType,
} from "../lib/types";

type Filter = "all" | "academic" | "personal" | "EXAM" | "PRESENTATION" | "ASSIGNMENT";

type PageState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; events: CalendarEvent[]; courses: Course[] };

interface FormState {
  id: number | null;
  title: string;
  event_type: EventType;
  event_date: string;
  event_time: string;
  course_id: string;
  description: string;
  is_done: boolean;
}

const EMPTY_FORM: FormState = {
  id: null, title: "", event_type: "TASK", event_date: "", event_time: "",
  course_id: "", description: "", is_done: false,
};

const WEEKDAYS = ["ش", "ی", "د", "س", "چ", "پ", "ج"];
const WEEKDAY_NAMES = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"];
const ACADEMIC_TYPES: ReadonlySet<EventType> = new Set([
  "EXAM", "QUIZ", "ASSIGNMENT", "PROJECT", "PRESENTATION", "CLASS",
]);
const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "همه" }, { key: "academic", label: "دانشگاهی" },
  { key: "personal", label: "شخصی" }, { key: "EXAM", label: "امتحانات" },
  { key: "PRESENTATION", label: "ارائه‌ها" }, { key: "ASSIGNMENT", label: "تکالیف" },
];

function haptic(type: "success" | "error"): void {
  getWebApp()?.HapticFeedback?.notificationOccurred(type);
}
function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "ارتباط با سرور برقرار نشد";
}
function fa(n: number): string {
  return n.toLocaleString("fa-IR");
}

/** Empty cells before day 1 in a Saturday-first Jalali month grid (0..6). */
function firstWeekdayOffset(jy: number, jm: number): number {
  const iso = jalaliToIso({ jy, jm, jd: 1 });
  const [gy, gm, gd] = iso.split("-").map(Number);
  const jsDay = new Date(gy, gm - 1, gd).getDay();
  return (jsDay + 1) % 7;
}

/** Weekday index where 0 = Saturday ... 6 = Friday. */
function jalaliWeekday(j: JalaliDate): number {
  return (firstWeekdayOffset(j.jy, j.jm) + j.jd - 1) % 7;
}

function matchesFilter(event: CalendarEvent, filter: Filter): boolean {
  if (filter === "all") return true;
  if (filter === "academic") return ACADEMIC_TYPES.has(event.event_type);
  if (filter === "personal") return event.event_type === "TASK";
  if (filter === "EXAM") return event.event_type === "EXAM";
  if (filter === "PRESENTATION") return event.event_type === "PRESENTATION";
  return event.event_type === "ASSIGNMENT";
}

function daysUntil(eventDate: string): number {
  const diff = new Date(eventDate).getTime() - new Date(todayIso()).getTime();
  return Math.round(diff / 86_400_000);
}

function countdownLabel(eventDate: string): string {
  const d = daysUntil(eventDate);
  if (d === 0) return "امروز";
  if (d === 1) return "فردا";
  if (d > 1) return `${fa(d)} روز`;
  return "گذشته";
}

function countdownUrgency(eventDate: string, isDone: boolean): "urgent" | "soon" | "normal" | "past" {
  if (isDone) return "normal";
  const d = daysUntil(eventDate);
  if (d < 0) return "past";
  if (d <= 2) return "urgent";
  if (d <= 7) return "soon";
  return "normal";
}

function toInput(e: CalendarEvent): CalendarEventInput {
  return {
    title: e.title, event_date: e.event_date, event_time: e.event_time,
    description: e.description, is_done: e.is_done,
    event_type: e.event_type, course_id: e.course_id,
  };
}

function byDateTime(a: CalendarEvent, b: CalendarEvent): number {
  return a.event_date.localeCompare(b.event_date)
    || (a.event_time ?? "\uffff").localeCompare(b.event_time ?? "\uffff");
}

function thisMonthStart(): JalaliDate {
  const t = todayJalali();
  return { jy: t.jy, jm: t.jm, jd: 1 };
}

export default function CalendarPage() {
  const [page, setPage] = useState<PageState>({ kind: "loading" });
  const [view, setView] = useState<JalaliDate>(thisMonthStart);
  const [selectedIso, setSelectedIso] = useState<string>(() => todayIso());
  const [filter, setFilter] = useState<Filter>("all");
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  const load = useCallback(async () => {
    setPage({ kind: "loading" });
    try {
      const [pending, done, courses] = await Promise.all([
        api.calendarEvents(false), api.calendarEvents(true), api.courses(),
      ]);
      setPage({ kind: "ready", events: [...pending, ...done], courses });
    } catch (error: unknown) {
      setPage({ kind: "error", message: errorMessage(error) });
      haptic("error");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  const formOpen = form !== null;
  useEffect(() => {
    if (formOpen) window.scrollTo({ top: 0, behavior: "smooth" });
  }, [formOpen]);

  const openCreate = () => {
    setBanner(null);
    setForm({ ...EMPTY_FORM, event_date: selectedIso || todayIso() });
  };
  const openEdit = (e: CalendarEvent) => {
    setBanner(null);
    setConfirmId(null);
    setForm({
      id: e.id, title: e.title, event_type: e.event_type, event_date: e.event_date,
      event_time: e.event_time ?? "", is_done: e.is_done, description: e.description ?? "",
      course_id: e.course_id === null ? "" : String(e.course_id),
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
    if (!title) { setBanner("عنوان رویداد را وارد کنید."); haptic("error"); return; }
    if (!form.event_date) { setBanner("تاریخ رویداد را انتخاب کنید."); haptic("error"); return; }
    const payload: CalendarEventInput = {
      title, event_date: form.event_date, event_time: form.event_time || null,
      description: form.description.trim() || null, is_done: form.is_done,
      event_type: form.event_type, course_id: form.course_id ? Number(form.course_id) : null,
    };
    setSaving(true);
    try {
      if (form.id === null) await api.createEvent(payload);
      else await api.updateEvent(form.id, payload);
      haptic("success");
      const j = isoToJalali(payload.event_date);
      setView({ jy: j.jy, jm: j.jm, jd: 1 });
      setSelectedIso(payload.event_date);
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

  const toggle = async (e: CalendarEvent) => {
    try {
      await api.updateEvent(e.id, { ...toInput(e), is_done: !e.is_done });
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

  const goPrev = () => setView((v) => v.jm === 1 ? { jy: v.jy - 1, jm: 12, jd: 1 } : { ...v, jm: v.jm - 1, jd: 1 });
  const goNext = () => setView((v) => v.jm === 12 ? { jy: v.jy + 1, jm: 1, jd: 1 } : { ...v, jm: v.jm + 1, jd: 1 });
  const goToday = () => { const t = todayJalali(); setView({ jy: t.jy, jm: t.jm, jd: 1 }); setSelectedIso(todayIso()); };
  const selectDay = (iso: string) => {
    const j = isoToJalali(iso);
    setView({ jy: j.jy, jm: j.jm, jd: 1 });
    setSelectedIso(iso);
  };

  // --- derived data ---
  const allEvents = page.kind === "ready" ? page.events : [];
  const todayStr = todayIso();

  const filteredEvents = useMemo(
    () => allEvents.filter((e) => matchesFilter(e, filter)),
    [allEvents, filter],
  );
  const eventsByDate = useMemo(() => {
    const m = new Map<string, CalendarEvent[]>();
    for (const e of filteredEvents) {
      const arr = m.get(e.event_date);
      if (arr) arr.push(e);
      else m.set(e.event_date, [e]);
    }
    return m;
  }, [filteredEvents]);

  const dayCount = daysInMonth(view.jy, view.jm);
  const offset = firstWeekdayOffset(view.jy, view.jm);
  const calendarCells = useMemo(() => {
    const cells: ({ day: number; iso: string } | null)[] =
      Array.from({ length: offset }, () => null);
    for (let d = 1; d <= dayCount; d++) {
      cells.push({ day: d, iso: jalaliToIso({ jy: view.jy, jm: view.jm, jd: d }) });
    }
    return cells;
  }, [view, dayCount, offset]);

  const selectedDayEvents = useMemo(
    () => [...(eventsByDate.get(selectedIso) ?? [])].sort(byDateTime),
    [eventsByDate, selectedIso],
  );
  const upcomingEvents = useMemo(
    () => filteredEvents
      .filter((e) => e.event_date !== selectedIso && daysUntil(e.event_date) >= 0 && !e.is_done)
      .sort(byDateTime)
      .slice(0, 10),
    [filteredEvents, selectedIso],
  );
  const summary = useMemo(() => {
    let exams = 0, presentations = 0, remaining = 0, overdue = 0;
    for (const e of allEvents) {
      if (e.is_done) continue;
      remaining++;
      if (e.event_date < todayStr) {
        overdue++;
      } else if (e.event_date >= todayStr) {
        if (e.event_type === "EXAM" || e.event_type === "QUIZ") exams++;
        else if (e.event_type === "PRESENTATION") presentations++;
      }
    }
    return { exams, presentations, remaining, overdue };
  }, [allEvents, todayStr]);

  if (page.kind === "loading") return <Spinner label="در حال بارگذاری تقویم…" />;
  if (page.kind === "error") {
    return (
      <section className="rounded-2xl bg-black/5 p-6 text-center dark:bg-white/5">
        <p className="text-sm">{page.message}</p>
        <button type="button" onClick={() => void load()}
          className="mt-3 rounded-xl bg-blue-600 px-4 py-2 text-sm font-bold text-white transition-opacity active:opacity-80">
          تلاش دوباره
        </button>
      </section>
    );
  }

  const field = "w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 focus:outline-none dark:bg-black/30 dark:text-white dark:border-white/10";
  const formJ: JalaliDate = form?.event_date ? isoToJalali(form.event_date) : todayJalali();
  const nowJ = todayJalali();
  const years: number[] = [];
  for (let y = Math.min(nowJ.jy - 1, formJ.jy); y <= Math.max(nowJ.jy + 3, formJ.jy); y++) years.push(y);
  const selectedJ = isoToJalali(selectedIso);
  const selectedLabel = `${WEEKDAY_NAMES[jalaliWeekday(selectedJ)]} ${fa(selectedJ.jd)} ${J_MONTHS[selectedJ.jm - 1]}`;

  return (
    <section className="flex flex-col gap-4">
      {/* ── A. Header (gradient hero) ── */}
      <section className="overflow-hidden rounded-3xl bg-gradient-to-br from-violet-600 via-purple-600 to-indigo-700 p-5 text-white shadow-lg shadow-purple-500/20">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h1 className="text-xl font-black">تقویم من</h1>
            <p className="mt-0.5 text-xs opacity-80">{J_MONTHS[view.jm - 1]} {fa(view.jy)}</p>
          </div>
          <button type="button" onClick={goToday}
            className="rounded-xl bg-white/15 px-3 py-2 text-xs font-bold backdrop-blur-sm transition-colors active:bg-white/25">
            امروز
          </button>
        </div>
      </section>

      {/* ── B. Summary cards (compact) ── */}
      <div className="grid grid-cols-4 gap-2">
        <SummaryCard label="امتحان" value={summary.exams} icon="📝" accent="bg-red-500/15" />
        <SummaryCard label="ارائه" value={summary.presentations} icon="🎤" accent="bg-blue-500/15" />
        <SummaryCard label="باقی" value={summary.remaining} icon="📋" accent="bg-orange-500/15" />
        <SummaryCard label="عقب‌افتاده" value={summary.overdue} icon="⏰" accent="bg-rose-500/15" />
      </div>

      {/* ── Month navigation ── */}
      <div className="flex items-center justify-between gap-2 rounded-2xl bg-black/5 p-2 dark:bg-white/5">
        <button type="button" onClick={goPrev} aria-label="ماه قبل"
          className="flex h-9 w-9 items-center justify-center rounded-xl bg-black/5 text-xl transition-colors active:bg-black/10 dark:bg-white/10 dark:active:bg-white/20">›</button>
        <p className="text-sm font-bold">{J_MONTHS[view.jm - 1]} {fa(view.jy)}</p>
        <button type="button" onClick={goNext} aria-label="ماه بعد"
          className="flex h-9 w-9 items-center justify-center rounded-xl bg-black/5 text-xl transition-colors active:bg-black/10 dark:bg-white/10 dark:active:bg-white/20">‹</button>
      </div>

      {/* ── D. Filters ── */}
      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button key={f.key} type="button" onClick={() => setFilter(f.key)}
            className={`rounded-full px-3 py-1.5 text-xs font-bold transition-all active:scale-95 ${
              filter === f.key
                ? "bg-blue-600 text-white shadow-sm"
                : "bg-black/10 text-current dark:bg-white/10"
            }`}>
            {f.label}
          </button>
        ))}
      </div>

      {/* ── C. Calendar grid ── */}
      <div className="rounded-2xl bg-black/5 p-3 dark:bg-white/5">
        <div className="grid grid-cols-7 gap-1 text-center">
          {WEEKDAYS.map((w) => (
            <div key={w} className="py-1 text-[11px] font-bold opacity-40">{w}</div>
          ))}
        </div>
        <div className="grid grid-cols-7 gap-1">
          {calendarCells.map((cell, idx) => {
            if (!cell) return <div key={`e-${idx}`} />;
            const dayEvents = eventsByDate.get(cell.iso) ?? [];
            const isToday = cell.iso === todayStr;
            const isSelected = cell.iso === selectedIso;
            const hasUndone = dayEvents.some((e) => !e.is_done);
            const dots = dayEvents.slice(0, 4);
            const extra = dayEvents.length - 4;
            return (
              <button key={cell.iso} type="button" onClick={() => setSelectedIso(cell.iso)}
                className={`relative flex aspect-square flex-col items-center justify-start gap-0.5 rounded-xl p-1 text-xs transition-all active:scale-90 ${
                  isSelected
                    ? "bg-blue-600 text-white shadow-md shadow-blue-500/30"
                    : isToday
                      ? "bg-blue-600/10 font-bold text-blue-600 dark:bg-blue-500/15 dark:text-blue-400"
                      : dayEvents.length > 0
                        ? "bg-black/5 dark:bg-white/5"
                        : "text-current"
                }`}>
                <span className={`leading-none ${isToday && !isSelected ? "" : ""}`}>{fa(cell.day)}</span>
                {dayEvents.length > 0 && (
                  <div className="flex flex-wrap items-center justify-center gap-0.5">
                    {dots.map((e) => (
                      <span key={e.id} className={`h-1.5 w-1.5 rounded-full ${
                        isSelected ? "bg-white/80" : e.is_done ? `${EVENT_TYPE_COLORS[e.event_type].dot} opacity-40` : EVENT_TYPE_COLORS[e.event_type].dot
                      }`} />
                    ))}
                    {extra > 0 && (
                      <span className={`text-[8px] font-bold leading-none ${isSelected ? "opacity-90" : "opacity-60"}`}>+{fa(extra)}</span>
                    )}
                  </div>
                )}
                {hasUndone && cell.iso < todayStr && !isSelected && (
                  <span className="absolute right-1 top-1 h-1.5 w-1.5 rounded-full bg-rose-500" />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Add / edit form ── */}
      {form && (
        <div className="flex flex-col gap-3 rounded-2xl bg-black/5 p-4 dark:bg-white/5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold">{form.id === null ? "➕ رویداد جدید" : "✏️ ویرایش رویداد"}</h2>
            <button type="button" onClick={() => { setForm(null); setBanner(null); }} aria-label="بستن"
              className="flex h-7 w-7 items-center justify-center rounded-lg bg-black/10 transition-colors active:opacity-70 dark:bg-white/10">
              <XIcon className="h-4 w-4" />
            </button>
          </div>

          <input className={field} placeholder="عنوان *"
            value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />

          <div className="grid grid-cols-2 gap-2">
            <select className={field} value={form.event_type} aria-label="نوع رویداد"
              onChange={(e) => setForm({ ...form, event_type: e.target.value as EventType })}>
              {EVENT_TYPES.map((t) => <option key={t} value={t}>{EVENT_TYPE_LABELS[t]}</option>)}
            </select>
            <input type="time" className={field} value={form.event_time} aria-label="ساعت"
              onChange={(e) => setForm({ ...form, event_time: e.target.value })} />
          </div>

          <div className="grid grid-cols-3 gap-2">
            <select className={field} value={formJ.jy} aria-label="سال"
              onChange={(e) => setDatePart("jy", Number(e.target.value))}>
              {years.map((y) => <option key={y} value={y}>{fa(y)}</option>)}
            </select>
            <select className={field} value={formJ.jm} aria-label="ماه"
              onChange={(e) => setDatePart("jm", Number(e.target.value))}>
              {J_MONTHS.map((name, i) => <option key={name} value={i + 1}>{name}</option>)}
            </select>
            <select className={field} value={formJ.jd} aria-label="روز"
              onChange={(e) => setDatePart("jd", Number(e.target.value))}>
              {Array.from({ length: daysInMonth(formJ.jy, formJ.jm) }, (_, i) => i + 1).map((d) => (
                <option key={d} value={d}>{fa(d)}</option>
              ))}
            </select>
          </div>

          <select className={field} value={form.course_id} aria-label="درس"
            onChange={(e) => setForm({ ...form, course_id: e.target.value })}>
            <option value="">بدون درس</option>
            {page.courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>

          <textarea className={`${field} min-h-16`} placeholder="توضیح (اختیاری)"
            value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />

          <div className="flex gap-3">
            <button type="button" onClick={() => void save()} disabled={saving}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-bold text-white transition-opacity active:opacity-80 disabled:opacity-60">
              <CheckIcon className="h-4 w-4" />
              {saving ? "در حال ذخیره…" : "ذخیره"}
            </button>
            <button type="button" onClick={() => { setForm(null); setBanner(null); }}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-black/10 px-4 py-2.5 text-sm font-bold transition-colors active:opacity-80 dark:bg-white/10">
              <XIcon className="h-4 w-4" />
              انصراف
            </button>
          </div>
        </div>
      )}

      {banner && (
        <p className="rounded-xl bg-red-600/10 px-3 py-2 text-center text-xs text-red-700 dark:text-red-400">{banner}</p>
      )}

      {/* ── D. Selected day events ── */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <h2 className="flex flex-wrap items-center gap-2 text-sm font-bold">
            <span>{selectedLabel}</span>
            {selectedIso === todayStr && (
              <span className="rounded-full bg-blue-600/10 px-2 py-0.5 text-[10px] text-blue-700 dark:text-blue-400">امروز</span>
            )}
            {selectedDayEvents.length > 0 && (
              <span className="rounded-full bg-black/10 px-2 py-0.5 text-[10px] dark:bg-white/10">{fa(selectedDayEvents.length)} رویداد</span>
            )}
          </h2>
          <button type="button" onClick={openCreate}
            className="flex items-center gap-1 rounded-lg bg-black/10 px-2.5 py-1 text-[11px] font-bold transition-colors active:opacity-70 dark:bg-white/10">
            <PlusIcon className="h-3.5 w-3.5" />
            این روز
          </button>
        </div>

        {selectedDayEvents.length === 0 ? (
          <div className="flex flex-col items-center gap-3 rounded-2xl bg-gradient-to-br from-violet-500/5 to-indigo-500/5 p-8 text-center dark:from-violet-500/10 dark:to-indigo-500/10">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-violet-500/10 text-3xl">🗓️</div>
            <p className="text-sm opacity-70">رویدادی برای این روز ثبت نشده است.</p>
            <button type="button" onClick={openCreate}
              className="flex items-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2 text-xs font-bold text-white transition-opacity active:opacity-80">
              <PlusIcon className="h-4 w-4" />
              افزودن رویداد
            </button>
          </div>
        ) : (
          <ul className="flex flex-col gap-2">
            {selectedDayEvents.map((event) => {
              const colors = EVENT_TYPE_COLORS[event.event_type];
              const confirming = confirmId === event.id;
              const isOverdue = !event.is_done && event.event_date < todayStr;
              return (
                <li key={event.id} className={`relative overflow-hidden rounded-2xl ${colors.bg} ${event.is_done ? "opacity-60" : ""}`}>
                  <span className={`absolute inset-y-0 right-0 w-1 ${colors.dot}`} aria-hidden="true" />
                  <div className="p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className={`truncate font-bold ${event.is_done ? "line-through" : ""}`}>{event.title}</p>
                        <div className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px] opacity-70">
                          {event.event_time && <span>🕒 {event.event_time}</span>}
                          {event.course_name && <span>· {event.course_name}</span>}
                          {isOverdue && <span className="font-bold text-rose-600 dark:text-rose-400">· عقب‌افتاده</span>}
                        </div>
                      </div>
                      <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${colors.text} ${colors.bg}`}>
                        {EVENT_TYPE_LABELS[event.event_type]}
                      </span>
                    </div>
                    {event.description && <p className="mt-2 whitespace-pre-wrap text-xs opacity-80">{event.description}</p>}
                    <div className="mt-3 flex gap-2">
                      <button type="button" onClick={() => toggle(event)}
                        className={`flex flex-1 items-center justify-center gap-1 rounded-xl px-3 py-2 text-xs font-bold transition-opacity active:opacity-80 ${
                          event.is_done
                            ? "bg-amber-500/10 text-amber-700 dark:text-amber-400"
                            : "bg-emerald-600/10 text-emerald-700 dark:text-emerald-400"
                        }`}>
                        <CheckIcon className="h-3.5 w-3.5" />
                        {event.is_done ? "برگشت به انتظار" : "انجام شد"}
                      </button>
                      <button type="button" onClick={() => openEdit(event)} aria-label="ویرایش"
                        className="flex items-center justify-center rounded-xl bg-black/10 px-3 py-2 text-blue-700 transition-colors active:opacity-80 dark:bg-white/10 dark:text-blue-400">
                        <EditIcon className="h-4 w-4" />
                      </button>
                      {confirming ? (
                        <>
                          <button type="button" onClick={() => remove(event.id)} aria-label="حذف نهایی"
                            className="flex items-center justify-center rounded-xl bg-red-600 px-3 py-2 text-white transition-opacity active:opacity-80">
                            <TrashIcon className="h-4 w-4" />
                          </button>
                          <button type="button" onClick={() => setConfirmId(null)} aria-label="انصراف"
                            className="flex items-center justify-center rounded-xl bg-black/10 px-3 py-2 transition-colors active:opacity-80 dark:bg-white/10">
                            <XIcon className="h-4 w-4" />
                          </button>
                        </>
                      ) : (
                        <button type="button" onClick={() => setConfirmId(event.id)} aria-label="حذف"
                          className="flex items-center justify-center rounded-xl bg-red-600/10 px-3 py-2 text-red-700 transition-colors active:opacity-80 dark:text-red-400">
                          <TrashIcon className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* ── E. Upcoming events ── */}
      {upcomingEvents.length > 0 && (
        <div className="flex flex-col gap-2">
          <h2 className="text-sm font-bold">رویدادهای پیش‌رو</h2>
          <ul className="flex flex-col gap-2">
            {upcomingEvents.map((e) => {
              const colors = EVENT_TYPE_COLORS[e.event_type];
              const urgency = countdownUrgency(e.event_date, e.is_done);
              const urgencyClass = urgency === "urgent" ? "bg-rose-500/15 text-rose-700 dark:text-rose-400"
                : urgency === "soon" ? "bg-amber-500/15 text-amber-700 dark:text-amber-400"
                : "bg-black/10 dark:bg-white/10";
              return (
                <li key={e.id}>
                  <button type="button" onClick={() => { selectDay(e.event_date); window.scrollTo({ top: 0, behavior: "smooth" }); }}
                    className="flex w-full items-center gap-3 rounded-2xl bg-black/5 p-3 text-right transition-all active:scale-95 dark:bg-white/5">
                    <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${colors.dot}`} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-bold">{e.title}</p>
                      <p className="mt-0.5 truncate text-[11px] opacity-70">
                        {EVENT_TYPE_LABELS[e.event_type]}{e.course_name ? ` · ${e.course_name}` : ""}{e.event_time ? ` · ${e.event_time}` : ""}{` · ${e.date_label}`}
                      </p>
                    </div>
                    <span className={`shrink-0 rounded-full px-2.5 py-1 text-[10px] font-bold ${urgencyClass}`}>
                      {countdownLabel(e.event_date)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* ── Floating add button (FAB) ── */}
      {!form && (
        <button type="button" onClick={openCreate}
          className="fixed bottom-24 left-1/2 z-20 flex h-14 w-14 -translate-x-1/2 items-center justify-center rounded-full bg-blue-600 text-white shadow-lg shadow-blue-500/40 transition-all active:scale-90"
          aria-label="افزودن رویداد">
          <PlusIcon className="h-6 w-6" />
        </button>
      )}
    </section>
  );
}

function SummaryCard({ label, value, icon, accent }: { label: string; value: number; icon: string; accent: string }) {
  return (
    <div className="flex flex-col items-center gap-1 rounded-2xl bg-black/5 p-2.5 text-center dark:bg-white/5">
      <div className={`flex h-8 w-8 items-center justify-center rounded-xl text-sm ${accent}`}>{icon}</div>
      <span className="text-lg font-black leading-none">{fa(value)}</span>
      <span className="text-[9px] leading-tight opacity-60">{label}</span>
    </div>
  );
}
