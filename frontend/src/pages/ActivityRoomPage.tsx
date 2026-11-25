import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckIcon, EditIcon, PlusIcon, TrashIcon, XIcon } from "../components/Icons";
import Spinner from "../components/Spinner";
import { ApiError, api } from "../lib/api";
import { getWebApp } from "../lib/telegram";
import {
  ACTIVITY_CATEGORIES,
  ACTIVITY_CATEGORY_COLORS,
  ACTIVITY_CATEGORY_LABELS,
  ACTIVITY_DAY_NAMES,
  ACTIVITY_DAY_SHORT,
  type ActivityCategory,
  type WeeklyActivity,
  type WeeklyActivityInput,
} from "../lib/types";

type PageState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; activities: WeeklyActivity[] };

interface FormState {
  id: number | null;
  title: string;
  day_of_week: number;
  start_time: string;
  duration_hours: number;
  category: ActivityCategory;
  description: string;
  is_active: boolean;
}

const EMPTY_FORM: FormState = {
  id: null,
  title: "",
  day_of_week: 1,
  start_time: "09:00",
  duration_hours: 1,
  category: "STUDY",
  description: "",
  is_active: true,
};

const DURATION_PRESETS = [0.5, 1, 1.5, 2, 3];

function haptic(type: "success" | "error"): void {
  getWebApp()?.HapticFeedback?.notificationOccurred(type);
}

/** Convert "HH:MM" to a Persian-friendly "HH:MM" display (digits stay latin
 *  so the time picker matches, but we pad to HH:MM). */
function fmtTime(t: string): string {
  return t.length === 4 ? `0${t}` : t;
}

/** Compute end time "HH:MM" by adding duration_hours to start_time. */
function endTime(start: string, hours: number): string {
  const [h, m] = start.split(":").map(Number);
  if (Number.isNaN(h) || Number.isNaN(m)) return start;
  const total = h * 60 + m + Math.round(hours * 60);
  const eh = Math.floor(total / 60) % 24;
  const em = total % 60;
  return `${eh < 10 ? "0" : ""}${eh}:${em < 10 ? "0" : ""}${em}`;
}

/** Today's weekday in our 1..7 (Saturday..Friday) numbering. */
function todayDayOfWeek(): number {
  // JS getDay(): 0=Sunday ... 6=Saturday. Map to our Sat=1..Fri=7.
  const js = new Date().getDay();
  // js=6 (Sat) -> 1, js=0 (Sun) -> 2, ..., js=5 (Fri) -> 7
  return js === 6 ? 1 : js + 2;
}

export default function ActivityRoomPage() {
  const [page, setPage] = useState<PageState>({ kind: "loading" });
  const [selectedDay, setSelectedDay] = useState<number>(todayDayOfWeek());
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  const load = useCallback(async () => {
    setPage({ kind: "loading" });
    try {
      const activities = await api.activities();
      setPage({ kind: "ready", activities });
    } catch (error: unknown) {
      const message =
        error instanceof ApiError ? error.message : "ارتباط با سرور برقرار نشد";
      setPage({ kind: "error", message });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const activitiesByDay = useMemo(() => {
    const map: Record<number, WeeklyActivity[]> = {};
    for (let d = 1; d <= 7; d++) map[d] = [];
    if (page.kind === "ready") {
      for (const a of page.activities) {
        if (map[a.day_of_week]) map[a.day_of_week].push(a);
      }
    }
    return map;
  }, [page]);

  const totalCount = page.kind === "ready" ? page.activities.length : 0;
  const totalHours = useMemo(() => {
    if (page.kind !== "ready") return 0;
    return page.activities.reduce((sum, a) => sum + a.duration_hours, 0);
  }, [page]);

  const dayActivities = activitiesByDay[selectedDay] ?? [];
  const dayHours = dayActivities.reduce((s, a) => s + a.duration_hours, 0);

  const openCreate = () => {
    setBanner(null);
    setConfirmId(null);
    setForm({ ...EMPTY_FORM, day_of_week: selectedDay });
  };

  const openEdit = (a: WeeklyActivity) => {
    setBanner(null);
    setConfirmId(null);
    setForm({
      id: a.id,
      title: a.title,
      day_of_week: a.day_of_week,
      start_time: a.start_time,
      duration_hours: a.duration_hours,
      category: a.category,
      description: a.description ?? "",
      is_active: a.is_active,
    });
  };

  const closeForm = () => {
    setForm(null);
    setBanner(null);
  };

  const save = async () => {
    if (!form) return;
    const title = form.title.trim();
    if (!title) {
      setBanner("عنوان فعالیت را وارد کنید.");
      haptic("error");
      return;
    }
    if (!form.start_time || !/^\d{1,2}:\d{2}$/.test(form.start_time)) {
      setBanner("ساعت شروع را به درستی وارد کنید (مثلاً ۱۴:۰۰).");
      haptic("error");
      return;
    }
    if (!(form.duration_hours > 0 && form.duration_hours <= 24)) {
      setBanner("مدت زمان باید بین ۰ و ۲۴ ساعت باشد.");
      haptic("error");
      return;
    }

    const payload: WeeklyActivityInput = {
      title,
      day_of_week: form.day_of_week,
      start_time: fmtTime(form.start_time),
      duration_hours: form.duration_hours,
      description: form.description.trim() || null,
      category: form.category,
      is_active: form.is_active,
    };

    setSaving(true);
    try {
      if (form.id === null) {
        await api.createActivity(payload);
      } else {
        await api.updateActivity(form.id, payload);
      }
      haptic("success");
      setForm(null);
      setBanner(null);
      setSelectedDay(form.day_of_week);
      await load();
    } catch (error: unknown) {
      const message =
        error instanceof ApiError ? error.message : "ذخیره ناموفق بود.";
      setBanner(message);
      haptic("error");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id: number) => {
    try {
      await api.deleteActivity(id);
      haptic("success");
      setConfirmId(null);
      await load();
    } catch (error: unknown) {
      const message =
        error instanceof ApiError ? error.message : "حذف ناموفق بود.";
      setBanner(message);
      haptic("error");
      setConfirmId(null);
    }
  };

  if (page.kind === "loading") return <Spinner label="در حال بارگذاری اتاق فعالیت…" />;
  if (page.kind === "error") {
    return (
      <section className="rounded-2xl bg-black/5 p-6 text-center dark:bg-white/5">
        <p className="text-sm">{page.message}</p>
        <button
          type="button"
          onClick={load}
          className="mt-3 rounded-xl bg-blue-600 px-4 py-2 text-sm font-bold text-white transition-opacity active:opacity-80"
        >
          تلاش دوباره
        </button>
      </section>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Hero header */}
      <section className="overflow-hidden rounded-3xl bg-gradient-to-br from-emerald-600 via-teal-600 to-cyan-700 p-5 text-white shadow-lg shadow-teal-500/20">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-lg font-bold">🎯 اتاق فعالیت</p>
            <p className="mt-0.5 text-xs opacity-90">برنامه هفتگی فعالیت‌های شما</p>
          </div>
          <div className="rounded-2xl bg-white/15 px-3 py-2 text-center backdrop-blur-sm">
            <p className="text-xl font-black">
              {totalCount.toLocaleString("fa-IR")}
            </p>
            <p className="text-[10px] opacity-80">فعالیت</p>
          </div>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <div className="rounded-xl bg-white/10 px-3 py-2 text-center">
            <p className="text-base font-bold">
              {totalHours.toLocaleString("fa-IR", { maximumFractionDigits: 1 })} ساعت
            </p>
            <p className="text-[10px] opacity-80">در طول هفته</p>
          </div>
          <div className="rounded-xl bg-white/10 px-3 py-2 text-center">
            <p className="text-base font-bold">
              {dayHours.toLocaleString("fa-IR", { maximumFractionDigits: 1 })} ساعت
            </p>
            <p className="text-[10px] opacity-80">{ACTIVITY_DAY_NAMES[selectedDay]}</p>
          </div>
        </div>
      </section>

      {/* Day selector — horizontal pills */}
      <section className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1">
        {Array.from({ length: 7 }, (_, i) => i + 1).map((d) => {
          const count = activitiesByDay[d]?.length ?? 0;
          const active = d === selectedDay;
          return (
            <button
              key={d}
              type="button"
              onClick={() => {
                setSelectedDay(d);
                setForm(null);
                setConfirmId(null);
                getWebApp()?.HapticFeedback?.impactOccurred("light");
              }}
              className={[
                "flex min-w-[3.25rem] flex-col items-center gap-0.5 rounded-2xl px-3 py-2 transition-all active:scale-95",
                active
                  ? "bg-blue-600 text-white shadow-md shadow-blue-500/20"
                  : "bg-black/5 text-gray-700 dark:bg-white/5 dark:text-gray-300",
              ].join(" ")}
            >
              <span className="text-sm font-bold">{ACTIVITY_DAY_NAMES[d]}</span>
              <span
                className={[
                  "flex h-5 min-w-[1.25rem] items-center justify-center rounded-full px-1 text-[10px] font-bold",
                  active ? "bg-white/25" : count > 0 ? "bg-blue-500/15 text-blue-600 dark:text-blue-400" : "opacity-40",
                ].join(" ")}
              >
                {count.toLocaleString("fa-IR")}
              </span>
            </button>
          );
        })}
      </section>

      {/* Banner */}
      {banner && (
        <div className="rounded-xl border border-red-300/60 bg-red-500/10 px-4 py-2.5 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/15 dark:text-red-300">
          {banner}
        </div>
      )}

      {/* Selected day activities */}
      <section className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold opacity-80">
            برنامه {ACTIVITY_DAY_NAMES[selectedDay]}
          </h2>
          <button
            type="button"
            onClick={openCreate}
            className="flex items-center gap-1 rounded-lg bg-blue-600/10 px-2.5 py-1 text-xs font-bold text-blue-600 transition-opacity active:opacity-70 dark:bg-blue-500/15 dark:text-blue-400"
          >
            <PlusIcon className="h-3.5 w-3.5" />
            افزودن
          </button>
        </div>

        {dayActivities.length === 0 ? (
          /* Empty state */
          <div className="flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-black/10 bg-black/[0.02] p-8 text-center dark:border-white/10 dark:bg-white/[0.02]">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500/15 to-cyan-500/15 text-3xl">
              🗓️
            </div>
            <div>
              <p className="text-sm font-bold opacity-80">برنامه‌ای ثبت نشده</p>
              <p className="mt-1 text-xs opacity-60">
                برای {ACTIVITY_DAY_NAMES[selectedDay]} فعالیت اضافه کنید تا برنامه‌تان ساخته شود.
              </p>
            </div>
            <button
              type="button"
              onClick={openCreate}
              className="mt-1 flex items-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2 text-sm font-bold text-white transition-all active:scale-95"
            >
              <PlusIcon className="h-4 w-4" />
              افزودن فعالیت
            </button>
          </div>
        ) : (
          <ul className="flex flex-col gap-2">
            {dayActivities.map((a) => {
              const colors = ACTIVITY_CATEGORY_COLORS[a.category];
              const confirming = confirmId === a.id;
              return (
                <li
                  key={a.id}
                  className={[
                    "overflow-hidden rounded-2xl border-r-4 bg-white p-3 shadow-sm transition-all dark:bg-gray-900",
                    colors.border,
                    a.is_active ? "" : "opacity-50",
                  ].join(" ")}
                >
                  <div className="flex items-start gap-3">
                    {/* Time block */}
                    <div
                      className={[
                        "flex w-16 shrink-0 flex-col items-center rounded-xl px-2 py-1.5 text-center",
                        colors.bg,
                      ].join(" ")}
                    >
                      <span className={["text-sm font-black tabular-nums", colors.text].join(" ")}>
                        {a.start_time}
                      </span>
                      <span className={["text-[10px] opacity-80", colors.text].join(" ")}>
                        تا {endTime(a.start_time, a.duration_hours)}
                      </span>
                    </div>

                    {/* Body */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <p className={[
                          "truncate text-sm font-bold",
                          a.is_active ? "" : "line-through",
                        ].join(" ")}>
                          {a.title}
                        </p>
                        {!a.is_active && (
                          <span className="shrink-0 rounded-md bg-gray-500/10 px-1.5 py-0.5 text-[10px] font-bold text-gray-500 dark:text-gray-400">
                            غیرفعال
                          </span>
                        )}
                      </div>
                      {a.description && (
                        <p className="mt-0.5 line-clamp-2 text-xs opacity-70">{a.description}</p>
                      )}
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                        <span
                          className={[
                            "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-bold",
                            colors.bg,
                            colors.text,
                          ].join(" ")}
                        >
                          <span className={["h-1.5 w-1.5 rounded-full", colors.dot].join(" ")} />
                          {ACTIVITY_CATEGORY_LABELS[a.category]}
                        </span>
                        <span className="rounded-md bg-black/5 px-1.5 py-0.5 text-[10px] font-medium opacity-70 dark:bg-white/10">
                          {a.duration_hours.toLocaleString("fa-IR", { maximumFractionDigits: 1 })} ساعت
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="mt-2 flex items-center justify-end gap-1 border-t border-black/5 pt-2 dark:border-white/10">
                    {confirming ? (
                      <>
                        <span className="ml-auto text-xs opacity-70">حذف شود؟</span>
                        <button
                          type="button"
                          onClick={() => setConfirmId(null)}
                          className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-bold opacity-70 transition-opacity active:opacity-60"
                        >
                          <XIcon className="h-3.5 w-3.5" /> خیر
                        </button>
                        <button
                          type="button"
                          onClick={() => void remove(a.id)}
                          className="flex items-center gap-1 rounded-lg bg-red-500/15 px-2 py-1 text-xs font-bold text-red-600 transition-opacity active:opacity-70 dark:text-red-400"
                        >
                          <CheckIcon className="h-3.5 w-3.5" /> بله
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => openEdit(a)}
                          className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-bold text-blue-600 transition-opacity active:opacity-70 dark:text-blue-400"
                        >
                          <EditIcon className="h-3.5 w-3.5" /> ویرایش
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmId(a.id)}
                          className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-bold text-red-600 transition-opacity active:opacity-70 dark:text-red-400"
                        >
                          <TrashIcon className="h-3.5 w-3.5" /> حذف
                        </button>
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* Add/Edit form sheet */}
      {form && (
        <ActivityForm
          form={form}
          saving={saving}
          onChange={setForm}
          onCancel={closeForm}
          onSave={save}
        />
      )}

      {/* Floating add button */}
      {!form && (
        <button
          type="button"
          onClick={openCreate}
          aria-label="افزودن فعالیت"
          className="fixed bottom-20 right-4 z-20 flex h-14 w-14 items-center justify-center rounded-full bg-blue-600 text-white shadow-lg shadow-blue-500/30 transition-transform active:scale-90"
        >
          <PlusIcon className="h-6 w-6" />
        </button>
      )}
    </div>
  );
}

// --- Form sheet -----------------------------------------------------------

function ActivityForm({
  form,
  saving,
  onChange,
  onCancel,
  onSave,
}: {
  form: FormState;
  saving: boolean;
  onChange: (form: FormState) => void;
  onCancel: () => void;
  onSave: () => void;
}) {
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    onChange({ ...form, [key]: value });

  return (
    <div className="fixed inset-0 z-30 flex items-end justify-center bg-black/40 backdrop-blur-sm">
      <div className="flex max-h-[88vh] w-full max-w-md flex-col overflow-hidden rounded-t-3xl bg-white shadow-2xl dark:bg-gray-900">
        {/* Drag handle */}
        <div className="flex justify-center pt-2">
          <div className="h-1 w-10 rounded-full bg-black/20 dark:bg-white/20" />
        </div>

        <div className="flex items-center justify-between border-b border-black/5 px-5 py-3 dark:border-white/10">
          <h3 className="text-base font-bold">
            {form.id === null ? "افزودن فعالیت" : "ویرایش فعالیت"}
          </h3>
          <button
            type="button"
            onClick={onCancel}
            aria-label="بستن"
            className="rounded-lg p-1 opacity-60 transition-opacity active:opacity-40"
          >
            <XIcon className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {/* Title */}
          <label className="mb-1.5 block text-xs font-bold opacity-70">عنوان</label>
          <input
            type="text"
            value={form.title}
            onChange={(e) => set("title", e.target.value)}
            placeholder="مثلاً: مطالعه ریاضی"
            maxLength={128}
            className="mb-4 w-full rounded-xl border border-black/10 bg-black/[0.02] px-3 py-2.5 text-sm outline-none focus:border-blue-500 dark:border-white/10 dark:bg-white/5"
          />

          {/* Day selector */}
          <label className="mb-1.5 block text-xs font-bold opacity-70">روز هفته</label>
          <div className="mb-4 grid grid-cols-7 gap-1">
            {Array.from({ length: 7 }, (_, i) => i + 1).map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => set("day_of_week", d)}
                className={[
                  "flex flex-col items-center gap-0.5 rounded-lg py-1.5 text-xs transition-all active:scale-95",
                  form.day_of_week === d
                    ? "bg-blue-600 font-bold text-white"
                    : "bg-black/5 opacity-70 dark:bg-white/5",
                ].join(" ")}
              >
                <span>{ACTIVITY_DAY_SHORT[d]}</span>
              </button>
            ))}
          </div>

          {/* Start time + duration */}
          <div className="mb-4 grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1.5 block text-xs font-bold opacity-70">ساعت شروع</label>
              <input
                type="time"
                value={form.start_time}
                onChange={(e) => set("start_time", e.target.value)}
                className="w-full rounded-xl border border-black/10 bg-black/[0.02] px-3 py-2.5 text-sm tabular-nums outline-none focus:border-blue-500 dark:border-white/10 dark:bg-white/5 dark:[color-scheme:dark]"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-bold opacity-70">مدت (ساعت)</label>
              <input
                type="number"
                value={form.duration_hours}
                min={0.5}
                max={24}
                step={0.5}
                onChange={(e) =>
                  set("duration_hours", parseFloat(e.target.value) || 0)
                }
                className="w-full rounded-xl border border-black/10 bg-black/[0.02] px-3 py-2.5 text-sm tabular-nums outline-none focus:border-blue-500 dark:border-white/10 dark:bg-white/5"
              />
            </div>
          </div>

          {/* Duration quick presets */}
          <div className="mb-4 flex flex-wrap gap-1.5">
            {DURATION_PRESETS.map((h) => (
              <button
                key={h}
                type="button"
                onClick={() => set("duration_hours", h)}
                className={[
                  "rounded-lg px-2.5 py-1 text-xs font-bold transition-all active:scale-95",
                  form.duration_hours === h
                    ? "bg-blue-600 text-white"
                    : "bg-black/5 opacity-70 dark:bg-white/5",
                ].join(" ")}
              >
                {h.toLocaleString("fa-IR")} ساعت
              </button>
            ))}
          </div>

          {/* Category */}
          <label className="mb-1.5 block text-xs font-bold opacity-70">دسته‌بندی</label>
          <div className="mb-4 grid grid-cols-3 gap-1.5">
            {ACTIVITY_CATEGORIES.map((c) => {
              const colors = ACTIVITY_CATEGORY_COLORS[c];
              const active = form.category === c;
              return (
                <button
                  key={c}
                  type="button"
                  onClick={() => set("category", c)}
                  className={[
                    "flex items-center justify-center gap-1 rounded-xl px-2 py-2 text-xs font-bold transition-all active:scale-95",
                    active
                      ? [colors.bg, colors.text, "ring-2", colors.ring].join(" ")
                      : "bg-black/5 opacity-70 dark:bg-white/5",
                  ].join(" ")}
                >
                  <span className={["h-2 w-2 rounded-full", colors.dot].join(" ")} />
                  {ACTIVITY_CATEGORY_LABELS[c]}
                </button>
              );
            })}
          </div>

          {/* Description */}
          <label className="mb-1.5 block text-xs font-bold opacity-70">توضیحات (اختیاری)</label>
          <textarea
            value={form.description}
            onChange={(e) => set("description", e.target.value)}
            placeholder="جزئیات بیشتر…"
            rows={2}
            className="mb-4 w-full resize-none rounded-xl border border-black/10 bg-black/[0.02] px-3 py-2.5 text-sm outline-none focus:border-blue-500 dark:border-white/10 dark:bg-white/5"
          />

          {/* Active toggle */}
          <label className="flex items-center justify-between rounded-xl bg-black/[0.02] px-3 py-2.5 dark:bg-white/5">
            <span className="text-sm font-bold">فعال</span>
            <button
              type="button"
              onClick={() => set("is_active", !form.is_active)}
              className={[
                "relative h-6 w-11 rounded-full transition-colors",
                form.is_active ? "bg-blue-600" : "bg-black/20 dark:bg-white/20",
              ].join(" ")}
              aria-pressed={form.is_active}
              aria-label="فعال بودن فعالیت"
            >
              <span
                className={[
                  "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all",
                  form.is_active ? "left-0.5" : "left-[1.375rem]",
                ].join(" ")}
              />
            </button>
          </label>
        </div>

        {/* Footer */}
        <div className="flex gap-2 border-t border-black/5 px-5 py-3 dark:border-white/10">
          <button
            type="button"
            onClick={onCancel}
            disabled={saving}
            className="flex-1 rounded-xl bg-black/5 py-2.5 text-sm font-bold opacity-80 transition-opacity active:opacity-60 disabled:opacity-40 dark:bg-white/10"
          >
            انصراف
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={saving}
            className="flex-[2] rounded-xl bg-blue-600 py-2.5 text-sm font-bold text-white transition-opacity active:opacity-80 disabled:opacity-50"
          >
            {saving ? "در حال ذخیره…" : form.id === null ? "افزودن" : "ذخیره تغییرات"}
          </button>
        </div>
      </div>
    </div>
  );
}
