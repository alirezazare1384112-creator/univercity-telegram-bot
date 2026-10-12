import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Spinner from "../components/Spinner";
import { ApiError, api } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { Dashboard } from "../lib/types";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: Dashboard };

/** A tappable stat card with a coloured icon badge. */
function StatCard({
  icon,
  label,
  value,
  to,
  accent,
}: {
  icon: string;
  label: string;
  value: number;
  to?: string;
  accent: string;
}) {
  const content = (
    <div className="flex flex-col items-center gap-1.5">
      <div
        className={`flex h-11 w-11 items-center justify-center rounded-2xl text-xl ${accent}`}
      >
        {icon}
      </div>
      <div className="text-xl font-black">{value.toLocaleString("fa-IR")}</div>
      <div className="text-[11px] opacity-70">{label}</div>
    </div>
  );
  const styles =
    "block rounded-2xl bg-black/5 p-4 text-center transition-all active:scale-95 active:opacity-80 dark:bg-white/5";
  if (to) {
    return (
      <Link to={to} className={styles}>
        {content}
      </Link>
    );
  }
  return <div className={styles}>{content}</div>;
}

export default function DashboardPage() {
  const { state } = useAuth();
  const [page, setPage] = useState<State>({ kind: "loading" });

  const load = useCallback(() => {
    setPage({ kind: "loading" });
    api
      .dashboard()
      .then((data) => setPage({ kind: "ready", data }))
      .catch((error: unknown) => {
        const message =
          error instanceof ApiError ? error.message : "ارتباط با سرور برقرار نشد";
        setPage({ kind: "error", message });
      });
  }, []);

  const userId = state.status === "ready" ? state.user.id : null;
  useEffect(() => {
    load();
  }, [load, userId]);

  if (page.kind === "loading") return <Spinner label="در حال بارگذاری داشبورد…" />;
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

  const { data } = page;
  const firstName =
    (state.status === "ready" && state.user.first_name) ||
    data.user.first_name ||
    "دوست عزیز";
  const counts = data.counts;

  return (
    <div className="flex flex-col gap-4">
      {/* Hero greeting card */}
      <section className="overflow-hidden rounded-3xl bg-gradient-to-br from-blue-600 via-indigo-600 to-purple-700 p-6 text-white shadow-lg shadow-indigo-500/20">
        <p className="text-xl font-bold">سلام {firstName} 👋</p>
        <p className="mt-1.5 text-sm opacity-90">{data.today}</p>
        {data.next_reminder ? (
          <div className="mt-4 flex items-center gap-2 rounded-2xl bg-white/15 px-4 py-3 backdrop-blur-sm">
            <span className="text-lg">⏰</span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-bold">{data.next_reminder.title}</p>
              <p className="text-[11px] opacity-80">{data.next_reminder.when}</p>
            </div>
          </div>
        ) : null}
      </section>

      {/* Stat grid */}
      <section className="grid grid-cols-3 gap-3">
        <StatCard
          icon="📚"
          label="دروس"
          value={counts.courses}
          to="/courses"
          accent="bg-blue-500/15"
        />
        <StatCard
          icon="📝"
          label="نمرات"
          value={counts.grade_items}
          to="/grades"
          accent="bg-emerald-500/15"
        />
        <StatCard
          icon="📖"
          label="جزوه‌ها"
          value={counts.notes}
          to="/notes"
          accent="bg-amber-500/15"
        />
        <StatCard
          icon="📢"
          label="اطلاعیه‌ها"
          value={counts.announcements}
          to="/announcements"
          accent="bg-rose-500/15"
        />
        <StatCard
          icon="⏰"
          label="یادآوری‌ها"
          value={counts.reminders}
          to="/reminders"
          accent="bg-cyan-500/15"
        />
        <StatCard
          icon="📆"
          label="امروز"
          value={counts.events_today}
          to="/calendar"
          accent="bg-violet-500/15"
        />
      </section>

      {/* Quick action cards */}
      <section className="grid grid-cols-2 gap-3">
        <Link
          to="/gpa"
          className="flex flex-col gap-2 rounded-2xl bg-gradient-to-br from-indigo-500/10 to-purple-500/10 p-4 transition-all active:scale-95 dark:from-indigo-500/15 dark:to-purple-500/15"
        >
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/20 text-lg">
            📊
          </div>
          <div>
            <p className="text-sm font-bold">معدل</p>
            <p className="text-[11px] opacity-70">محاسبه معدل ترم و کل</p>
          </div>
        </Link>
        <Link
          to="/schedule"
          className="flex flex-col gap-2 rounded-2xl bg-gradient-to-br from-blue-500/10 to-cyan-500/10 p-4 transition-all active:scale-95 dark:from-blue-500/15 dark:to-cyan-500/15"
        >
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/20 text-lg">
            📅
          </div>
          <div>
            <p className="text-sm font-bold">برنامه هفتگی</p>
            <p className="text-[11px] opacity-70">
              {data.schedule ? "ثبت شده ✓" : "ثبت نشده"}
            </p>
          </div>
        </Link>
        <Link
          to="/links"
          className="flex flex-col gap-2 rounded-2xl bg-gradient-to-br from-emerald-500/10 to-teal-500/10 p-4 transition-all active:scale-95 dark:from-emerald-500/15 dark:to-teal-500/15"
        >
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/20 text-lg">
            🔗
          </div>
          <div>
            <p className="text-sm font-bold">لینک‌ها</p>
            <p className="text-[11px] opacity-70">{counts.links} لینک ذخیره شده</p>
          </div>
        </Link>
        <Link
          to="/profile"
          className="flex flex-col gap-2 rounded-2xl bg-gradient-to-br from-amber-500/10 to-orange-500/10 p-4 transition-all active:scale-95 dark:from-amber-500/15 dark:to-orange-500/15"
        >
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/20 text-lg">
            👤
          </div>
          <div>
            <p className="text-sm font-bold">پروفایل</p>
            <p className="text-[11px] opacity-70">اطلاعات دانشجویی</p>
          </div>
        </Link>
      </section>
    </div>
  );
}
