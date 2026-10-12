import { useEffect, useMemo, useState } from "react";
import { PlusIcon, TrashIcon, XIcon } from "../components/Icons";
import { getWebApp } from "../lib/telegram";

const KEY = "moadel-data-v2";

type Cell = string | number;

interface PastRow {
  title: Cell;
  units: Cell;
  gpa: Cell;
}

interface CourseRow {
  name: Cell;
  units: Cell;
  grade: Cell;
}

interface GpaState {
  past: PastRow[];
  current: CourseRow[];
}

type PageConfirm = "register" | "clear";
type RowTarget = { table: "current" | "past"; index: number };

interface Calc {
  pastUnits: number;
  pastPoints: number;
  curUnits: number;
  curPoints: number;
  gradedUnits: number;
  semGpa: number | null;
  cumGpa: number | null;
  totalUnits: number;
  missing: number;
  bad: number;
}

function haptic(type: "success" | "error"): void {
  getWebApp()?.HapticFeedback?.notificationOccurred(type);
}

/** Empty default — no pre-filled courses or past GPA. The user starts
 *  with a single blank row and adds their own. */
function defaultState(): GpaState {
  return {
    past: [],
    current: [{ name: "", units: "3", grade: "" }],
  };
}

function loadState(): GpaState {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<GpaState> | null;
      if (parsed && Array.isArray(parsed.past) && Array.isArray(parsed.current)) {
        return {
          past: parsed.past.map((row) => ({
            title: row?.title ?? "",
            units: row?.units ?? "",
            gpa: row?.gpa ?? "",
          })),
          current: parsed.current.map((row) => ({
            name: row?.name ?? "",
            units: row?.units ?? "",
            grade: row?.grade ?? "",
          })),
        };
      }
    }
  } catch {
    /* خرابی در ذخیره‌سازی: به حالت پیش‌فرض برمی‌گردیم */
  }
  return defaultState();
}

function norm(value: Cell): string {
  return String(value ?? "")
    .replace(/[\u06F0-\u06F9]/g, (d) => String(d.charCodeAt(0) - 0x06f0))
    .replace(/[\u0660-\u0669]/g, (d) => String(d.charCodeAt(0) - 0x0660))
    .replace(/[\u066B\u066C\uFF0E\u061C]/g, ".")
    .replace(/[,،]/g, ".");
}

function num(value: Cell): number | null {
  const parsed = parseFloat(norm(value));
  return Number.isNaN(parsed) ? null : parsed;
}

function fa2(value: number): string {
  return value.toLocaleString("fa-IR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function faU(value: number): string {
  return Number.isInteger(value) ? value.toLocaleString("fa-IR") : fa2(value);
}

function calcOf(state: GpaState): Calc {
  let pastUnits = 0;
  let pastPoints = 0;
  state.past.forEach((row) => {
    const units = num(row.units) || 0;
    const gpa = num(row.gpa);
    if (units > 0 && gpa !== null) {
      pastUnits += units;
      pastPoints += units * gpa;
    }
  });

  let curUnits = 0;
  let gradedUnits = 0;
  let curPoints = 0;
  let missing = 0;
  let bad = 0;
  state.current.forEach((course) => {
    const units = num(course.units);
    if (units === null || units <= 0) return;
    curUnits += units;
    const raw = norm(course.grade).trim();
    if (raw === "") {
      missing += 1;
      return;
    }
    const grade = num(raw);
    if (grade === null || grade < 0 || grade > 20) {
      bad += 1;
      return;
    }
    gradedUnits += units;
    curPoints += units * grade;
  });

  const semGpa = gradedUnits > 0 ? curPoints / gradedUnits : null;
  const totalUnits = pastUnits + gradedUnits;
  const cumGpa = totalUnits > 0 ? (pastPoints + curPoints) / totalUnits : null;

  return {
    pastUnits,
    pastPoints,
    curUnits,
    curPoints,
    gradedUnits,
    semGpa,
    cumGpa,
    totalUnits,
    missing,
    bad,
  };
}

function gpaColor(gpa: number | null): string {
  if (gpa === null) return "text-white";
  if (gpa >= 17) return "text-emerald-300";
  if (gpa >= 14) return "text-amber-300";
  return "text-red-300";
}

function Stat({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub: string;
  accent?: string;
}) {
  return (
    <div className="rounded-2xl bg-black/5 p-4 transition-colors dark:bg-white/5">
      <p className="text-[11px] opacity-70">{label}</p>
      <p className={`mt-1 text-2xl font-bold ${accent ?? ""}`}>{value}</p>
      <p className="mt-0.5 text-[11px] opacity-60">{sub}</p>
    </div>
  );
}

const GRID_COLS = "grid grid-cols-[minmax(0,1fr)_50px_56px_32px] gap-2";

function rowInputClass(bad: boolean, center: boolean): string {
  return [
    "w-full rounded-lg border bg-white px-2.5 py-2 text-xs outline-none transition-colors",
    "focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20",
    "dark:bg-black/30 dark:text-white",
    center ? "text-center" : "",
    bad ? "border-red-400 bg-red-50 dark:bg-red-900/20" : "border-black/10 dark:border-white/10",
  ]
    .filter(Boolean)
    .join(" ");
}

function rowDeleteClass(): string {
  return "flex h-full min-h-[34px] items-center justify-center rounded-lg bg-red-600/10 text-red-600 transition-colors active:opacity-80 dark:text-red-400 dark:bg-red-900/20";
}

export default function GpaPage() {
  const [state, setState] = useState<GpaState>(loadState);
  const [confirm, setConfirm] = useState<PageConfirm | null>(null);
  const [delRow, setDelRow] = useState<RowTarget | null>(null);

  // Debounced localStorage write: every 500ms instead of every keystroke.
  const [debouncedState, setDebouncedState] = useState(state);
  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedState(state), 500);
    return () => window.clearTimeout(t);
  }, [state]);
  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(debouncedState));
    } catch {
      /* حالت خصوصی یا پر بودن حافظه: رد می‌کنیم */
    }
  }, [debouncedState]);

  const s = useMemo(() => calcOf(state), [state]);

  function updateCurrent(index: number, key: keyof CourseRow, value: string): void {
    setDelRow(null);
    setState((prev) => ({
      ...prev,
      current: prev.current.map((row, i) =>
        i === index ? ({ ...row, [key]: value } as CourseRow) : row,
      ),
    }));
  }

  function updatePast(index: number, key: keyof PastRow, value: string): void {
    setDelRow(null);
    setState((prev) => ({
      ...prev,
      past: prev.past.map((row, i) =>
        i === index ? ({ ...row, [key]: value } as PastRow) : row,
      ),
    }));
  }

  function addCourse(): void {
    setDelRow(null);
    setState((prev) => ({
      ...prev,
      current: [...prev.current, { name: "", units: "3", grade: "" }],
    }));
  }

  function addPast(): void {
    setDelRow(null);
    setState((prev) => ({
      ...prev,
      past: [...prev.past, { title: "ترم جدید", units: "", gpa: "" }],
    }));
  }

  function deleteRowConfirmed(): void {
    if (!delRow) return;
    haptic("success");
    if (delRow.table === "current") {
      setState((prev) => ({
        ...prev,
        current: prev.current.filter((_, i) => i !== delRow.index),
      }));
    } else {
      setState((prev) => ({
        ...prev,
        past: prev.past.filter((_, i) => i !== delRow.index),
      }));
    }
    setDelRow(null);
  }

  function registerTerm(): void {
    const sem = s.semGpa;
    if (sem === null) return;
    haptic("success");
    setState((prev) => ({
      past: [...prev.past, { title: "ترم (ثبت‌شده)", units: s.gradedUnits, gpa: sem }],
      current: [{ name: "", units: "3", grade: "" }],
    }));
    setConfirm(null);
    setDelRow(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function confirmYes(): void {
    if (confirm === "register") {
      registerTerm();
      return;
    }
    haptic("success");
    setDelRow(null);
    setState({ past: [], current: [{ name: "", units: "3", grade: "" }] });
    setConfirm(null);
  }

  const confirmText =
    confirm === "register"
      ? s.missing > 0
        ? `${faU(s.missing)} درس هنوز نمره ندارد. با همین وضعیت ثبت شود؟ ترم جاری به سوابق اضافه و جدول دروس پاک می‌شود.`
        : "این ترم به سوابق اضافه شود و جدول دروس پاک شود؟"
      : "همه داده‌ها (سوابق و ترم جاری) پاک شود؟";

  const warnings: string[] = [];
  if (s.missing > 0) {
    warnings.push(`${faU(s.missing)} درس هنوز نمره ندارد و در محاسبه لحاظ نشده است.`);
  }
  if (s.bad > 0) {
    warnings.push(`${faU(s.bad)} نمره نامعتبر است (باید بین ۰ تا ۲۰ باشد).`);
  }

  const heroSub =
    s.cumGpa === null
      ? "هنوز نمره‌ای وارد نشده است"
      : `${faU(s.totalUnits)} واحد گذرانده${s.missing > 0 ? ` · ${faU(s.missing)} درس بدون نمره` : ""}`;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-bold">📊 معدل</h1>
        <p className="text-xs opacity-70">
          نمرات را وارد کنید؛ معدل ترم جاری و کل به‌صورت خودکار محاسبه می‌شود.
        </p>
      </div>

      {/* Hero card with gradient + GPA color coding */}
      <section className="overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-600 via-purple-600 to-indigo-800 p-6 text-white shadow-lg shadow-indigo-500/20">
        <p className="text-xs opacity-90">معدل کل (سوابق + ترم جاری)</p>
        <p className={`mt-2 text-5xl font-black tracking-tight ${gpaColor(s.cumGpa)}`}>
          {s.cumGpa === null ? "—" : fa2(s.cumGpa)}
        </p>
        <p className="mt-2 text-xs opacity-90">{heroSub}</p>
      </section>

      <section className="grid grid-cols-2 gap-3">
        <Stat
          label="معدل ترم جاری"
          value={s.semGpa === null ? "—" : fa2(s.semGpa)}
          sub={
            s.semGpa === null
              ? "نمره‌ای وارد نشده"
              : `${faU(s.gradedUnits)} واحد از ${faU(s.curUnits)}`
          }
          accent={s.semGpa !== null ? gpaColor(s.semGpa).replace("text-white", "text-indigo-600 dark:text-indigo-400") : ""}
        />
        <Stat
          label="کل واحدها"
          value={faU(s.totalUnits)}
          sub={`این ترم: ${faU(s.gradedUnits)} واحد`}
        />
      </section>

      {warnings.length > 0 ? (
        <p className="rounded-2xl bg-amber-500/15 px-4 py-3 text-xs leading-6 text-amber-800 dark:text-amber-300">
          ⚠ {warnings.join(" ")}
        </p>
      ) : null}

      <section className="flex flex-col gap-2">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setConfirm("register")}
            disabled={s.semGpa === null}
            className="flex items-center gap-1.5 rounded-xl bg-emerald-600 px-4 py-2.5 text-xs font-bold text-white transition-opacity active:opacity-80 disabled:opacity-50"
          >
            ✓ ثبت ترم در سوابق
          </button>
          <button
            type="button"
            onClick={() => setConfirm("clear")}
            className="flex items-center gap-1.5 rounded-xl bg-red-600/10 px-4 py-2.5 text-xs font-bold text-red-700 transition-colors active:opacity-80 dark:text-red-400"
          >
            <TrashIcon className="h-4 w-4" />
            پاک کردن همه
          </button>
        </div>
        {confirm !== null ? (
          <div className="rounded-2xl bg-amber-500/10 p-4">
            <p className="text-xs leading-6">{confirmText}</p>
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={confirmYes}
                className={[
                  "flex flex-1 items-center justify-center gap-1.5 rounded-xl px-3 py-2.5 text-xs font-bold text-white transition-opacity active:opacity-80",
                  confirm === "register" ? "bg-emerald-600" : "bg-red-600",
                ].join(" ")}
              >
                بله
              </button>
              <button
                type="button"
                onClick={() => setConfirm(null)}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-black/10 px-3 py-2.5 text-xs font-bold transition-colors active:opacity-80 dark:bg-white/10"
              >
                <XIcon className="h-4 w-4" />
                انصراف
              </button>
            </div>
          </div>
        ) : null}
      </section>

      {/* Current semester courses */}
      <section className="rounded-2xl bg-black/5 p-4 dark:bg-white/5">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-bold">📚 دروس ترم جاری</h2>
          <span className="rounded-full bg-black/10 px-3 py-1 text-[11px] font-bold opacity-70 dark:bg-white/10">
            {faU(s.curUnits)} واحد
          </span>
        </div>

        <div className={`${GRID_COLS} mt-3 text-[10px] font-bold opacity-60`}>
          <span>نام درس</span>
          <span className="text-center">واحد</span>
          <span className="text-center">نمره</span>
          <span />
        </div>

        <div className="mt-2 flex flex-col gap-2">
          {state.current.map((course, i) => {
            if (delRow && delRow.table === "current" && delRow.index === i) {
              return (
                <div key={i} className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={deleteRowConfirmed}
                    className="flex items-center justify-center gap-1 rounded-lg bg-red-600 px-2 py-2.5 text-[11px] font-bold text-white transition-opacity active:opacity-80"
                  >
                    <TrashIcon className="h-3.5 w-3.5" />
                    حذف شود
                  </button>
                  <button
                    type="button"
                    onClick={() => setDelRow(null)}
                    className="flex items-center justify-center gap-1 rounded-lg bg-black/10 px-2 py-2.5 text-[11px] font-bold transition-colors active:opacity-80 dark:bg-white/10"
                  >
                    <XIcon className="h-3.5 w-3.5" />
                    انصراف
                  </button>
                </div>
              );
            }
            const raw = norm(course.grade).trim();
            const grade = num(raw);
            const bad = raw !== "" && (grade === null || grade < 0 || grade > 20);
            const units = num(course.units);
            const unitsBad = units === null || units < 0;
            return (
              <div key={i} className={`${GRID_COLS} items-center`}>
                <input
                  type="text"
                  className={rowInputClass(false, false)}
                  placeholder="نام درس"
                  value={course.name == null ? "" : String(course.name)}
                  onChange={(e) => updateCurrent(i, "name", e.target.value)}
                />
                <input
                  type="text"
                  inputMode="decimal"
                  className={rowInputClass(unitsBad, true)}
                  placeholder="۳"
                  value={course.units == null ? "" : String(course.units)}
                  onChange={(e) => updateCurrent(i, "units", e.target.value)}
                />
                <input
                  type="text"
                  inputMode="decimal"
                  className={rowInputClass(bad, true)}
                  placeholder="—"
                  value={course.grade == null ? "" : String(course.grade)}
                  onChange={(e) => updateCurrent(i, "grade", e.target.value)}
                />
                <button
                  type="button"
                  aria-label="حذف درس"
                  onClick={() => setDelRow({ table: "current", index: i })}
                  className={rowDeleteClass()}
                >
                  <XIcon className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          })}
        </div>

        <button
          type="button"
          onClick={addCourse}
          className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-xl bg-blue-600 px-3 py-2.5 text-xs font-bold text-white transition-opacity active:opacity-80"
        >
          <PlusIcon className="h-4 w-4" />
          افزودن درس
        </button>
      </section>

      {/* Past semesters */}
      <section className="rounded-2xl bg-black/5 p-4 dark:bg-white/5">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-bold">🗂 سوابق ترم‌های قبلی</h2>
          <span className="rounded-full bg-black/10 px-3 py-1 text-[11px] font-bold opacity-70 dark:bg-white/10">
            {faU(s.pastUnits)} واحد
            {s.pastUnits > 0 ? ` · معدل ${fa2(s.pastPoints / s.pastUnits)}` : ""}
          </span>
        </div>

        <div className={`${GRID_COLS} mt-3 text-[10px] font-bold opacity-60`}>
          <span>شرح</span>
          <span className="text-center">واحد</span>
          <span className="text-center">معدل</span>
          <span />
        </div>

        <div className="mt-2 flex flex-col gap-2">
          {state.past.map((row, i) => {
            if (delRow && delRow.table === "past" && delRow.index === i) {
              return (
                <div key={i} className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={deleteRowConfirmed}
                    className="flex items-center justify-center gap-1 rounded-lg bg-red-600 px-2 py-2.5 text-[11px] font-bold text-white transition-opacity active:opacity-80"
                  >
                    <TrashIcon className="h-3.5 w-3.5" />
                    حذف شود
                  </button>
                  <button
                    type="button"
                    onClick={() => setDelRow(null)}
                    className="flex items-center justify-center gap-1 rounded-lg bg-black/10 px-2 py-2.5 text-[11px] font-bold transition-colors active:opacity-80 dark:bg-white/10"
                  >
                    <XIcon className="h-3.5 w-3.5" />
                    انصراف
                  </button>
                </div>
              );
            }
            const rawGpa = norm(row.gpa).trim();
            const gpa = num(rawGpa);
            const badGpa = rawGpa !== "" && (gpa === null || gpa < 0 || gpa > 20);
            return (
              <div key={i} className={`${GRID_COLS} items-center`}>
                <input
                  type="text"
                  className={rowInputClass(false, false)}
                  placeholder="شرح ترم"
                  value={row.title == null ? "" : String(row.title)}
                  onChange={(e) => updatePast(i, "title", e.target.value)}
                />
                <input
                  type="text"
                  inputMode="decimal"
                  className={rowInputClass(false, true)}
                  placeholder="۰"
                  value={row.units == null ? "" : String(row.units)}
                  onChange={(e) => updatePast(i, "units", e.target.value)}
                />
                <input
                  type="text"
                  inputMode="decimal"
                  className={rowInputClass(badGpa, true)}
                  placeholder="۰"
                  value={row.gpa == null ? "" : String(row.gpa)}
                  onChange={(e) => updatePast(i, "gpa", e.target.value)}
                />
                <button
                  type="button"
                  aria-label="حذف سوابق"
                  onClick={() => setDelRow({ table: "past", index: i })}
                  className={rowDeleteClass()}
                >
                  <XIcon className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          })}
        </div>

        <button
          type="button"
          onClick={addPast}
          className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-xl bg-blue-600 px-3 py-2.5 text-xs font-bold text-white transition-opacity active:opacity-80"
        >
          <PlusIcon className="h-4 w-4" />
          افزودن سوابق
        </button>
      </section>

      <footer className="text-center text-[11px] leading-6 opacity-60">
        داده‌ها فقط در همین دستگاه ذخیره می‌شوند.
      </footer>
    </div>
  );
}
