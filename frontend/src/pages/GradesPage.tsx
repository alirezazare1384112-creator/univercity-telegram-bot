import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { EditIcon, TrashIcon, XIcon } from "../components/Icons";
import Spinner from "../components/Spinner";
import { ApiError, api } from "../lib/api";
import { getWebApp } from "../lib/telegram";
import {
  GRADE_KINDS,
  GRADE_KIND_LABELS,
  type CourseGrades,
  type GradeInput,
  type GradeItem,
  type GradeKind,
} from "../lib/types";

type PageState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: CourseGrades };

interface FormState {
  id: number | null;
  title: string;
  score: string;
  max_score: string;
  kind: GradeKind;
  description: string;
}

const EMPTY_FORM: FormState = {
  id: null,
  title: "",
  score: "",
  max_score: "",
  kind: "OTHER",
  description: "",
};

function fa(value: number): string {
  return value.toLocaleString("fa-IR", { maximumFractionDigits: 2 });
}

function haptic(type: "success" | "error"): void {
  getWebApp()?.HapticFeedback?.notificationOccurred(type);
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "ارتباط با سرور برقرار نشد";
}

export default function GradesPage() {
  const { courseId } = useParams<{ courseId: string }>();
  const id = Number(courseId);

  const [page, setPage] = useState<PageState>({ kind: "loading" });
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!Number.isInteger(id) || id <= 0) {
      setPage({ kind: "error", message: "شناسهٔ درس نامعتبر است." });
      return;
    }
    setPage({ kind: "loading" });
    try {
      const data = await api.courseGrades(id);
      setPage({ kind: "ready", data });
    } catch (error: unknown) {
      setPage({ kind: "error", message: errorMessage(error) });
      haptic("error");
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const openCreate = () => {
    setBanner(null);
    setForm({ ...EMPTY_FORM });
  };

  const openEdit = (item: GradeItem) => {
    setBanner(null);
    setForm({
      id: item.id,
      title: item.title,
      score: String(item.score),
      max_score: String(item.max_score),
      kind: item.kind,
      description: item.description ?? "",
    });
  };

  const save = async () => {
    if (!form) return;
    const title = form.title.trim();
    const score = Number(form.score.replace(/٫/g, "."));
    const maxScore = Number(form.max_score.replace(/٫/g, "."));
    if (!title) {
      setBanner("عنوان نمره را وارد کنید.");
      return;
    }
    if (!Number.isFinite(score) || score < 0) {
      setBanner("نمره باید عددی بزرگ‌تر یا مساوی صفر باشد.");
      return;
    }
    if (!Number.isFinite(maxScore) || maxScore <= 0) {
      setBanner("نمرهٔ کامل باید بزرگ‌تر از صفر باشد.");
      return;
    }
    if (score > maxScore) {
      setBanner("نمره نمی‌تواند از نمرهٔ کامل بیشتر باشد.");
      return;
    }
    const payload: GradeInput = {
      title,
      score,
      max_score: maxScore,
      kind: form.kind,
      description: form.description.trim() || null,
    };
    setSaving(true);
    try {
      if (form.id === null) await api.createGrade(id, payload);
      else await api.updateGrade(id, form.id, payload);
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

  const remove = async (itemId: number) => {
    try {
      await api.deleteGrade(id, itemId);
      haptic("success");
      setConfirmId(null);
      await load();
    } catch (error: unknown) {
      setBanner(errorMessage(error));
      haptic("error");
    }
  };

  if (page.kind === "loading") return <Spinner label="در حال بارگذاری نمرات…" />;

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

  const { data } = page;
  const totals = data.totals;
  const field =
    "w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm dark:bg-black/20";

  return (
    <section className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-bold">نمرات {data.course.name}</h1>
        <p className="text-xs opacity-70">{fa(data.course.units)} واحد</p>
      </div>

      <section className="rounded-2xl bg-gradient-to-bl from-emerald-600 to-emerald-800 p-5 text-white">
        <p className="text-xs opacity-90">نمرهٔ تجمیعی</p>
        <p className="mt-1 text-3xl font-bold">{fa(totals.percent)}٪</p>
        <p className="mt-1 text-sm opacity-90">
          {fa(totals.total)} از {fa(totals.maximum)}
        </p>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/25">
          <div
            className="h-full rounded-full bg-white"
            style={{ width: `${Math.min(100, Math.max(0, totals.percent))}%` }}
          />
        </div>
      </section>

      {banner && (
        <p className="rounded-xl bg-red-600/10 px-3 py-2 text-center text-xs text-red-700">
          {banner}
        </p>
      )}

      {form && (
        <div className="flex flex-col gap-3 rounded-2xl bg-black/5 p-4">
          <h2 className="text-sm font-bold">{form.id === null ? "نمرهٔ جدید" : "ویرایش نمره"}</h2>
          <input
            className={field}
            placeholder="عنوان (مثلاً میان‌ترم) *"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <input
              className={field}
              placeholder="نمره *"
              inputMode="decimal"
              value={form.score}
              onChange={(e) => setForm({ ...form, score: e.target.value })}
            />
            <input
              className={field}
              placeholder="نمرهٔ کامل"
              inputMode="decimal"
              value={form.max_score}
              onChange={(e) => setForm({ ...form, max_score: e.target.value })}
            />
          </div>
          <select
            className={field}
            value={form.kind}
            onChange={(e) => setForm({ ...form, kind: e.target.value as GradeKind })}
          >
            {GRADE_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {GRADE_KIND_LABELS[kind]}
              </option>
            ))}
          </select>
          <textarea
            className={field}
            placeholder="توضیح (اختیاری)"
            rows={2}
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

      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold opacity-70">آیتم‌های نمره</h2>
        <button
          type="button"
          onClick={openCreate}
          className="rounded-xl bg-blue-600 px-3 py-2 text-xs font-bold text-white active:opacity-80"
        >
          + افزودن
        </button>
      </div>

      {data.items.length === 0 && !form ? (
        <div className="rounded-2xl bg-black/5 p-8 text-center">
          <span className="text-4xl">📝</span>
          <p className="mt-2 text-sm opacity-70">هنوز نمره‌ای ثبت نشده است.</p>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {data.items.map((item) => (
            <li key={item.id} className="rounded-2xl bg-black/5 p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-bold">{item.title}</p>
                  <p className="mt-0.5 text-xs opacity-70">
                    {fa(item.score)} از {fa(item.max_score)} · {fa(item.percent)}٪
                  </p>
                  {item.description && (
                    <p className="mt-1 text-xs opacity-60">{item.description}</p>
                  )}
                </div>
                <span className="shrink-0 rounded-full bg-indigo-600/10 px-2 py-1 text-[11px] font-bold text-indigo-700">
                  {GRADE_KIND_LABELS[item.kind]}
                </span>
              </div>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => openEdit(item)}
                  className="flex flex-1 items-center justify-center gap-1 rounded-xl bg-black/10 px-3 py-2 text-xs font-bold text-blue-700 active:opacity-80"
                >
                  <EditIcon className="h-4 w-4" />
                  ویرایش
                </button>
                {confirmId === item.id ? (
                  <>
                    <button
                      type="button"
                      onClick={() => void remove(item.id)}
                      className="flex flex-1 items-center justify-center gap-1 rounded-xl bg-red-600 px-3 py-2 text-xs font-bold text-white active:opacity-80"
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
                    onClick={() => setConfirmId(item.id)}
                    className="flex items-center justify-center gap-1 rounded-xl bg-red-600/10 px-3 py-2 text-xs font-bold text-red-700 active:opacity-80"
                    title="حذف"
                  >
                    <TrashIcon className="h-4 w-4" />
                    حذف
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
