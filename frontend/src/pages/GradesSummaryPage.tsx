import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Spinner from "../components/Spinner";
import { ApiError, api } from "../lib/api";
import type { GradesSummary } from "../lib/types";

type PageState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: GradesSummary };

function fa(value: number): string {
  return value.toLocaleString("fa-IR", { maximumFractionDigits: 2 });
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "ارتباط با سرور برقرار نشد";
}

export default function GradesSummaryPage() {
  const navigate = useNavigate();
  const [page, setPage] = useState<PageState>({ kind: "loading" });

  const load = useCallback(async () => {
    setPage({ kind: "loading" });
    try {
      const data = await api.gradesSummary();
      setPage({ kind: "ready", data });
    } catch (error: unknown) {
      setPage({ kind: "error", message: errorMessage(error) });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (page.kind === "loading") {
    return <Spinner label="در حال بارگذاری نمرات…" />;
  }

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

  const { courses, totals, item_count } = page.data;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-bold">📝 نمرات</h1>
        <p className="text-xs opacity-70">جمع‌بندی همهٔ درس‌های این ترم</p>
      </div>

      <section className="rounded-2xl bg-gradient-to-bl from-emerald-600 to-emerald-800 p-5 text-white">
        <p className="text-xs opacity-90">نمرهٔ تجمیعی کل درس‌ها</p>
        <p className="mt-1 text-3xl font-bold">{fa(totals.percent)}٪</p>
        <p className="mt-1 text-sm opacity-90">
          {fa(totals.total)} از {fa(totals.maximum)} — {fa(item_count)} آیتم نمره
        </p>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/25">
          <div
            className="h-full rounded-full bg-white"
            style={{ width: `${Math.min(100, Math.max(0, totals.percent))}%` }}
          />
        </div>
      </section>

      {courses.length === 0 ? (
        <section className="rounded-2xl bg-black/5 p-6 text-center">
          <p className="text-sm opacity-70">
            هنوز درسی اضافه نکرده‌اید. اول درس‌های ترم را ثبت کنید.
          </p>
          <Link
            to="/courses"
            className="mt-3 inline-block rounded-xl bg-blue-600 px-4 py-2 text-sm font-bold text-white active:opacity-80"
          >
            رفتن به درس‌ها
          </Link>
        </section>
      ) : (
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-bold opacity-70">بر اساس درس</h2>
          {courses.map((course) => (
            <button
              key={course.course_id}
              type="button"
              onClick={() => navigate(`/courses/${course.course_id}/grades`)}
              className="flex items-center justify-between gap-3 rounded-2xl bg-black/5 p-4 text-right active:opacity-80"
            >
              <div>
                <p className="text-sm font-bold">{course.name}</p>
                <p className="mt-0.5 text-xs opacity-70">
                  {course.item_count === 0
                    ? "بدون نمره"
                    : `${fa(course.item_count)} آیتم نمره`}
                </p>
              </div>
              <div className="text-left">
                <p className="text-sm font-bold">
                  {fa(course.totals.total)} از {fa(course.totals.maximum)}
                </p>
                <p className="mt-0.5 text-xs opacity-70">{fa(course.totals.percent)}٪</p>
              </div>
            </button>
          ))}
        </section>
      )}
    </div>
  );
}
