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

function StatCard({
  icon,
  label,
  value,
  to,
}: {
  icon: string;
  label: string;
  value: number;
  to?: string;
}) {
  const content = (
    <>
      <div className="text-xl leading-none">{icon}</div>
      <div className="mt-1 text-xl font-bold">{value.toLocaleString("fa-IR")}</div>
      <div className="mt-0.5 text-xs opacity-70">{label}</div>
    </>
  );
  const styles = "block rounded-2xl bg-black/5 p-4 text-center active:opacity-80";
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

  useEffect(() => {
    load();
  }, [load]);

  if (page.kind === "loading") return <Spinner label="در حال بارگذاری داشبورد…" />;
  if (page.kind === "error") {
    return (
      <section className="rounded-2xl bg-black/5 p-6 text-center">
        <p className="text-sm">{page.message}</p>
        <button
          type="button"
          onClick={load}
          className="mt-3 rounded-xl bg-blue-600 px-4 py-2 text-sm font-bold text-white active:opacity-80"
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
      <section className="rounded-2xl bg-gradient-to-bl from-blue-600 to-blue-800 p-5 text-white">
        <p className="text-lg font-bold">سلام {firstName} 👋</p>
        <p className="mt-1 text-sm opacity-90">{data.today}</p>
      </section>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatCard icon="📚" label="دروس" value={counts.courses} />
        <StatCard icon="📢" label="اطلاعیه‌ها" value={counts.announcements} />
        <StatCard icon="⏰" label="یادآوری‌ها" value={counts.reminders} />
        <StatCard
          icon="📆"
          label="رویدادهای امروز"
          value={counts.events_today}
          to="/calendar"
        />
        <StatCard icon="📖" label="جزوه‌ها" value={counts.notes} to="/notes" />
        <StatCard icon="🔗" label="لینک‌ها" value={counts.links} />
      </section>

      <section className="rounded-2xl bg-black/5 p-4">
        <h2 className="text-sm font-bold opacity-70">یادآوری بعدی</h2>
        {data.next_reminder ? (
          <div className="mt-2 flex items-center justify-between gap-3">
            <span className="text-sm font-bold">{data.next_reminder.title}</span>
            <span className="text-xs opacity-70">{data.next_reminder.when}</span>
          </div>
        ) : (
          <p className="mt-2 text-sm opacity-70">یادآوری آینده‌ای ندارید.</p>
        )}
      </section>

      <section className="rounded-2xl bg-black/5 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold opacity-70">برنامهٔ هفتگی</h2>
            <p className="mt-1 text-sm">
              {data.schedule ? "برنامهٔ شما ثبت شده است." : "هنوز برنامه‌ای ثبت نکرده‌اید."}
            </p>
          </div>
          <Link
            to="/schedule"
            className="shrink-0 rounded-xl bg-blue-600 px-3 py-2 text-xs font-bold text-white active:opacity-80"
          >
            {data.schedule ? "مشاهده" : "افزودن"}
          </Link>
        </div>
      </section>
    </div>
  );
}
