import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Spinner from "../components/Spinner";
import { ApiError, api } from "../lib/api";
import { getWebApp } from "../lib/telegram";
import type { Course, CourseInput } from "../lib/types";

type PageState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; courses: Course[] };

interface FormState {
  id: number | null;
  name: string;
  units: string;
  teacher_name: string;
  semester: string;
  academic_year: string;
}

const EMPTY_FORM: FormState = {
  id: null,
  name: "",
  units: "",
  teacher_name: "",
  semester: "",
  academic_year: "",
};

function haptic(type: "success" | "error"): void {
  getWebApp()?.HapticFeedback?.notificationOccurred(type);
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "ارتباط با سرور برقرار نشد";
}

export default function CoursesPage() {
  const navigate = useNavigate();
  const [page, setPage] = useState<PageState>({ kind: "loading" });
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  const load = useCallback(async () => {
    setPage({ kind: "loading" });
    try {
      const courses = await api.courses();
      setPage({ kind: "ready", courses });
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

  const openEdit = (course: Course) => {
    setBanner(null);
    setForm({
      id: course.id,
      name: course.name,
      units: String(course.units),
      teacher_name: course.teacher_name ?? "",
      semester: course.semester ?? "",
      academic_year: course.academic_year ?? "",
    });
  };

  const save = async () => {
    if (!form) return;
    const name = form.name.trim();
    if (!name) {
      setBanner("نام درس را وارد کنید.");
      return;
    }
    const units = Number(form.units || "3");
    if (!Number.isInteger(units) || units < 1 || units > 30) {
      setBanner("تعداد واحد باید بین ۱ تا ۳۰ باشد.");
      return;
    }
    const payload: CourseInput = {
      name,
      units,
      teacher_name: form.teacher_name.trim() || null,
      semester: form.semester.trim() || null,
      academic_year: form.academic_year.trim() || null,
    };
    setSaving(true);
    try {
      if (form.id === null) await api.createCourse(payload);
      else await api.updateCourse(form.id, payload);
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

  const remove = async (id: number) => {
    try {
      await api.deleteCourse(id);
      haptic("success");
      setConfirmId(null);
      await load();
    } catch (error: unknown) {
      setBanner(errorMessage(error));
      haptic("error");
    }
  };

  if (page.kind === "loading") return <Spinner label="در حال بارگذاری دروس…" />;

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

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">دروس</h1>
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
          <h2 className="text-sm font-bold">{form.id === null ? "درس جدید" : "ویرایش درس"}</h2>
          <input
            className={field}
            placeholder="نام درس *"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <input
              className={field}
              placeholder="واحد"
              inputMode="numeric"
              value={form.units}
              onChange={(e) => setForm({ ...form, units: e.target.value })}
            />
            <input
              className={field}
              placeholder="ترم (مثلاً پاییز)"
              value={form.semester}
              onChange={(e) => setForm({ ...form, semester: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <input
              className={field}
              placeholder="نام استاد"
              value={form.teacher_name}
              onChange={(e) => setForm({ ...form, teacher_name: e.target.value })}
            />
            <input
              className={field}
              placeholder="سال تحصیلی"
              inputMode="numeric"
              value={form.academic_year}
              onChange={(e) => setForm({ ...form, academic_year: e.target.value })}
            />
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

      {page.courses.length === 0 && !form ? (
        <div className="rounded-2xl bg-black/5 p-8 text-center">
          <span className="text-4xl">📚</span>
          <p className="mt-2 text-sm opacity-70">هنوز درسی ثبت نکرده‌اید.</p>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {page.courses.map((course) => (
            <li key={course.id} className="rounded-2xl bg-black/5 p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-bold">{course.name}</p>
                  <p className="mt-0.5 text-xs opacity-70">
                    {course.units.toLocaleString("fa-IR")} واحد
                    {course.teacher_name ? ` · ${course.teacher_name}` : ""}
                    {course.semester ? ` · ${course.semester}` : ""}
                    {course.academic_year ? ` · ${course.academic_year}` : ""}
                  </p>
                </div>
                <span className="shrink-0 rounded-full bg-blue-600/10 px-2 py-1 text-[11px] font-bold text-blue-700">
                  {course.units.toLocaleString("fa-IR")} واحد
                </span>
              </div>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => navigate(`/courses/${course.id}/grades`)}
                  className="flex-1 rounded-xl bg-emerald-600/10 px-3 py-2 text-xs font-bold text-emerald-700 active:opacity-80"
                >
                  📝 نمرات
                </button>
                <button
                  type="button"
                  onClick={() => openEdit(course)}
                  className="flex-1 rounded-xl bg-black/10 px-3 py-2 text-xs font-bold active:opacity-80"
                >
                  ✏️ ویرایش
                </button>
                {confirmId === course.id ? (
                  <>
                    <button
                      type="button"
                      onClick={() => void remove(course.id)}
                      className="flex-1 rounded-xl bg-red-600 px-3 py-2 text-xs font-bold text-white active:opacity-80"
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
                    onClick={() => setConfirmId(course.id)}
                    className="rounded-xl bg-red-600/10 px-3 py-2 text-xs font-bold text-red-700 active:opacity-80"
                  >
                    🗑 حذف
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
