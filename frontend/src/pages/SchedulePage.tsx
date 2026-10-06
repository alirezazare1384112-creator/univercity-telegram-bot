import { useCallback, useEffect, useRef, useState } from "react";
import Spinner from "../components/Spinner";
import { ApiError, api } from "../lib/api";
import { getWebApp } from "../lib/telegram";
import type { ScheduleInfo } from "../lib/types";

type PageState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "empty" }
  | { kind: "ready"; info: ScheduleInfo; fileUrl: string };

function haptic(type: "success" | "error"): void {
  getWebApp()?.HapticFeedback?.notificationOccurred(type);
}

export default function SchedulePage() {
  const [page, setPage] = useState<PageState>({ kind: "loading" });
  const [uploading, setUploading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const fileUrlRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    setPage({ kind: "loading" });
    setConfirming(false);
    try {
      const info = await api.schedule();
      if (!info.exists) {
        setPage({ kind: "empty" });
        return;
      }
      const blob = await api.scheduleFile();
      if (fileUrlRef.current) URL.revokeObjectURL(fileUrlRef.current);
      fileUrlRef.current = URL.createObjectURL(blob);
      setPage({ kind: "ready", info, fileUrl: fileUrlRef.current });
    } catch (error: unknown) {
      const message =
        error instanceof ApiError ? error.message : "ارتباط با سرور برقرار نشد";
      setPage({ kind: "error", message });
      haptic("error");
    }
  }, []);

  useEffect(() => {
    void load();
    return () => {
      if (fileUrlRef.current) URL.revokeObjectURL(fileUrlRef.current);
    };
  }, [load]);

  const onFileSelected = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = "";
      if (!file) return;
      setUploading(true);
      try {
        await api.uploadSchedule(file);
        haptic("success");
        await load();
      } catch (error: unknown) {
        const message =
          error instanceof ApiError ? error.message : "آپلود انجام نشد";
        setPage({ kind: "error", message });
        haptic("error");
      } finally {
        setUploading(false);
      }
    },
    [load],
  );

  const onDelete = useCallback(async () => {
    try {
      await api.deleteSchedule();
      haptic("success");
      await load();
    } catch (error: unknown) {
      const message =
        error instanceof ApiError ? error.message : "حذف انجام نشد";
      setPage({ kind: "error", message });
      haptic("error");
    }
  }, [load]);

  const pickFile = () => fileInputRef.current?.click();

  if (page.kind === "loading" || uploading) {
    return <Spinner label={uploading ? "در حال آپلود برنامه…" : "در حال بارگذاری برنامه…"} />;
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

  const input = (
    <input
      ref={fileInputRef}
      type="file"
      hidden
      accept="image/*,application/pdf,.doc,.docx,.xls,.xlsx,.zip"
      onChange={(event) => void onFileSelected(event)}
    />
  );

  if (page.kind === "empty") {
    return (
      <section className="flex flex-col items-center gap-4 rounded-2xl bg-black/5 p-8 text-center">
        <span className="text-4xl">📅</span>
        <div>
          <h1 className="text-lg font-bold">برنامهٔ هفتگی</h1>
          <p className="mt-1 text-sm opacity-70">
            هنوز برنامه‌ای ثبت نکرده‌اید. عکس یا فایل برنامه را اضافه کنید.
          </p>
        </div>
        {input}
        <button
          type="button"
          onClick={pickFile}
          className="rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-bold text-white active:opacity-80"
        >
          افزودن برنامه
        </button>
      </section>
    );
  }

  const { info, fileUrl } = page;
  const isPhoto = info.file_type === "photo";
  const fileName = info.caption ?? "برنامه هفتگی";

  return (
    <section className="flex flex-col gap-4">
      <h1 className="text-lg font-bold">برنامهٔ هفتگی</h1>

      {isPhoto ? (
        <img
          src={fileUrl}
          alt={fileName}
          className="w-full rounded-2xl border border-black/10 bg-white"
        />
      ) : (
        <a
          href={fileUrl}
          download={fileName}
          className="flex items-center gap-3 rounded-2xl bg-black/5 p-4 active:opacity-80"
        >
          <span className="text-3xl">📄</span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-bold">{fileName}</span>
            <span className="block text-xs opacity-70">برای دریافت ضربه بزنید</span>
          </span>
        </a>
      )}

      {info.caption && !isPhoto ? null : <p className="text-center text-xs opacity-70">{info.caption}</p>}

      <div className="flex gap-3">
        <button
          type="button"
          onClick={pickFile}
          className="flex-1 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-bold text-white active:opacity-80"
        >
          تغییر برنامه
        </button>
        {confirming ? (
          <div className="flex flex-1 gap-2">
            <button
              type="button"
              onClick={() => void onDelete()}
              className="flex-1 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-bold text-white active:opacity-80"
            >
              حذف شود
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="flex-1 rounded-xl bg-black/10 px-4 py-2.5 text-sm font-bold active:opacity-80"
            >
              انصراف
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="flex-1 rounded-xl bg-red-600/10 px-4 py-2.5 text-sm font-bold text-red-700 active:opacity-80"
          >
            حذف
          </button>
        )}
      </div>
      {input}
    </section>
  );
}
