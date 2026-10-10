import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Spinner from "../components/Spinner";
import { ApiError, api } from "../lib/api";
import { getWebApp } from "../lib/telegram";
import type { AdminStats, AdminUsers } from "../lib/types";

type PageState =
  | { kind: "loading" }
  | { kind: "denied" }
  | { kind: "error"; message: string }
  | { kind: "ready"; stats: AdminStats; users: AdminUsers };

const STAT_CARDS: { key: keyof AdminStats; label: string; icon: string }[] = [
  { key: "users", label: "کاربران", icon: "👥" },
  { key: "active_users", label: "فعال", icon: "✅" },
  { key: "admins", label: "ادمین‌ها", icon: "🛡" },
  { key: "courses", label: "درس‌ها", icon: "📚" },
  { key: "grades", label: "نمرات", icon: "📝" },
  { key: "reminders", label: "یادآوری‌ها", icon: "⏰" },
  { key: "announcements", label: "اطلاعیه‌ها", icon: "📢" },
  { key: "notes", label: "جزوه‌ها", icon: "🗂" },
  { key: "links", label: "لینک‌ها", icon: "🔗" },
  { key: "events", label: "رویدادها", icon: "📅" },
  { key: "schedules", label: "برنامه هفتگی", icon: "🗓" },
];

function haptic(type: "success" | "error"): void {
  getWebApp()?.HapticFeedback?.notificationOccurred(type);
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "ارتباط با سرور برقرار نشد";
}

export default function AdminPage() {
  const [page, setPage] = useState<PageState>({ kind: "loading" });
  const navigate = useNavigate();

  const load = useCallback(async () => {
    setPage({ kind: "loading" });
    try {
      const [stats, users] = await Promise.all([api.adminStats(), api.adminUsers()]);
      setPage({ kind: "ready", stats, users });
    } catch (error: unknown) {
      if (error instanceof ApiError && error.status === 403) {
        setPage({ kind: "denied" });
        // Being denied is expected for non-admins — don't vibrate.
      } else {
        setPage({ kind: "error", message: errorMessage(error) });
        haptic("error");
      }
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (page.kind === "loading") return <Spinner label="در حال بارگذاری پنل ادمین…" />;

  if (page.kind === "denied") {
    return (
      <section className="rounded-2xl bg-black/5 p-6 text-center">
        <span className="text-4xl">🔒</span>
        <p className="mt-2 text-sm">شما دسترسی ادمین ندارید.</p>
        <button
          type="button"
          onClick={() => navigate("/")}
          className="mt-3 rounded-xl bg-blue-600 px-4 py-2 text-sm font-bold text-white active:opacity-80"
        >
          بازگشت به خانه
        </button>
      </section>
    );
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

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">🛠 پنل ادمین</h1>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-xl bg-black/10 px-3 py-1.5 text-xs font-bold active:opacity-80"
        >
          🔄 به‌روزرسانی
        </button>
      </div>

      <section className="grid grid-cols-3 gap-2">
        {STAT_CARDS.map((card) => (
          <div key={card.key} className="rounded-2xl bg-black/5 p-3 text-center">
            <span className="text-lg">{card.icon}</span>
            <p className="mt-1 text-lg font-bold">
              {page.stats[card.key].toLocaleString("fa-IR")}
            </p>
            <p className="text-[11px] opacity-70">{card.label}</p>
          </div>
        ))}
      </section>

      <section className="flex flex-col gap-3 rounded-2xl bg-black/5 p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold">👥 کاربران</h2>
          <span className="text-xs opacity-70">
            کل: {page.users.total.toLocaleString("fa-IR")} · فعال:{" "}
            {page.users.active.toLocaleString("fa-IR")}
          </span>
        </div>

        {page.users.users.length === 0 ? (
          <p className="py-4 text-center text-xs opacity-70">کاربری ثبت نشده است.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {page.users.users.map((user) => {
              const name =
                [user.first_name, user.last_name].filter(Boolean).join(" ") || "بدون نام";
              return (
                <li
                  key={user.id}
                  className="flex items-center gap-3 rounded-xl bg-black/5 p-3"
                >
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-blue-600 text-sm font-bold text-white">
                    {name.slice(0, 1)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-bold">{name}</p>
                    <p className="truncate text-[11px] opacity-70" dir="ltr">
                      {user.username ? `@${user.username}` : `tg: ${user.telegram_id}`}
                    </p>
                  </div>
                  <span
                    className={`shrink-0 rounded-lg px-2 py-1 text-[10px] font-bold ${
                      user.is_active
                        ? "bg-emerald-600/10 text-emerald-700"
                        : "bg-red-600/10 text-red-700"
                    }`}
                  >
                    {user.is_active ? "فعال" : "غیرفعال"}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </section>
  );
}
