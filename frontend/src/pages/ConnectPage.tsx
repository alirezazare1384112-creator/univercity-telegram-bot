import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../lib/api";
import { initTelegram, type TelegramWebApp } from "../lib/telegram";
import type { Me } from "../lib/types";

type State =
  | { kind: "loading" }
  | { kind: "no-telegram" }
  | { kind: "error"; message: string }
  | { kind: "connected"; me: Me };

function haptic(webApp: TelegramWebApp | null, type: "success" | "error"): void {
  webApp?.HapticFeedback?.notificationOccurred(type);
}

export default function ConnectPage() {
  const [state, setState] = useState<State>({ kind: "loading" });

  const connect = useCallback(() => {
    setState({ kind: "loading" });
    const webApp = initTelegram();
    if (!webApp?.initData) {
      setState({ kind: "no-telegram" });
      return;
    }
    api
      .me()
      .then((me) => {
        setState({ kind: "connected", me });
        haptic(webApp, "success");
      })
      .catch((error: unknown) => {
        const message =
          error instanceof ApiError
            ? `احراز هویت ناموفق: ${error.message}`
            : "ارتباط با سرور برقرار نشد";
        setState({ kind: "error", message });
        haptic(webApp, "error");
      });
  }, []);

  useEffect(() => {
    connect();
  }, [connect]);

  if (state.kind === "loading") {
    return (
      <section className="flex flex-col items-center gap-3 rounded-2xl bg-black/5 p-8 text-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-current border-t-transparent" />
        <p className="text-sm">در حال اتصال به دستیار دانشجو…</p>
      </section>
    );
  }

  if (state.kind === "no-telegram") {
    return (
      <section className="flex flex-col gap-3 rounded-2xl bg-black/5 p-6 text-center">
        <h1 className="text-lg font-bold">دستیار دانشجو</h1>
        <p className="text-sm leading-6">
          این صفحه باید <b>درون تلگرام</b> و از طریق دکمهٔ ربات باز شود تا
          احراز هویت انجام شود.
        </p>
        <p className="text-xs opacity-70">
          برای توسعه: ربات را اجرا کنید و در تلگرام دکمهٔ Mini App را بزنید.
        </p>
      </section>
    );
  }

  if (state.kind === "error") {
    return (
      <section className="flex flex-col gap-3 rounded-2xl bg-black/5 p-6 text-center">
        <h1 className="text-lg font-bold">اتصال ناموفق</h1>
        <p className="text-sm leading-6">{state.message}</p>
        <button
          type="button"
          onClick={connect}
          className="rounded-xl bg-blue-600 px-4 py-2 font-bold text-white active:opacity-80"
        >
          تلاش دوباره
        </button>
      </section>
    );
  }

  const { me } = state;
  const fullName = [me.first_name, me.last_name].filter(Boolean).join(" ");
  return (
    <section className="flex flex-col gap-4 rounded-2xl bg-black/5 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">اتصال برقرار است</h1>
        <span className="rounded-full bg-green-600/15 px-3 py-1 text-xs font-bold text-green-700">
          ✓ وارد شدید
        </span>
      </div>
      <div className="rounded-xl bg-white/70 p-4 text-sm leading-7 dark:bg-black/20">
        <p className="text-base font-bold">{fullName || "کاربر تلگرام"}</p>
        {me.username && <p className="opacity-70">@{me.username}</p>}
        <p className="opacity-70">شناسهٔ تلگرام: {me.telegram_id}</p>
        {me.student_number && <p>شمارهٔ دانشجویی: {me.student_number}</p>}
        {me.university && <p>{me.university}</p>}
      </div>
      <p className="text-center text-xs opacity-70">
        صفحهٔ اصلی داشبورد در مرحلهٔ بعد اضافه می‌شود.
      </p>
    </section>
  );
}
