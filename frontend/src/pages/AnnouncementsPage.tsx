import { useCallback, useEffect, useRef, useState } from "react";
import Spinner from "../components/Spinner";
import { ApiError, api } from "../lib/api";
import { getWebApp } from "../lib/telegram";
import type { Announcement } from "../lib/types";

type PageState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; announcements: Announcement[] };

interface Preview {
  url: string;
  type: string;
}

const SOURCE_LABELS = { telegram: "تلگرام", eitaa: "ایتا" } as const;

function haptic(type: "success" | "error"): void {
  getWebApp()?.HapticFeedback?.notificationOccurred(type);
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "ارتباط با سرور برقرار نشد";
}

export default function AnnouncementsPage() {
  const [page, setPage] = useState<PageState>({ kind: "loading" });
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [previews, setPreviews] = useState<Record<number, Preview>>({});
  const [loadingPreview, setLoadingPreview] = useState<number | null>(null);
  const previewsRef = useRef(previews);
  previewsRef.current = previews;

  const load = useCallback(async () => {
    setPage({ kind: "loading" });
    try {
      const announcements = await api.announcements();
      setPage({ kind: "ready", announcements });
    } catch (error: unknown) {
      setPage({ kind: "error", message: errorMessage(error) });
      haptic("error");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const current = previewsRef;
    return () => {
      for (const preview of Object.values(current.current)) {
        URL.revokeObjectURL(preview.url);
      }
    };
  }, []);

  const remove = async (id: number) => {
    try {
      await api.deleteAnnouncement(id);
      haptic("success");
      setConfirmId(null);
      await load();
    } catch (error: unknown) {
      setBanner(errorMessage(error));
      haptic("error");
    }
  };

  const showPreview = async (announcement: Announcement) => {
    if (previews[announcement.id] || loadingPreview === announcement.id) return;
    setLoadingPreview(announcement.id);
    try {
      const blob = await api.announcementFile(announcement.id);
      const url = URL.createObjectURL(blob);
      setPreviews((prev) => ({ ...prev, [announcement.id]: { url, type: blob.type } }));
      haptic("success");
    } catch (error: unknown) {
      setBanner(errorMessage(error));
      haptic("error");
    } finally {
      setLoadingPreview(null);
    }
  };

  if (page.kind === "loading") return <Spinner label="در حال بارگذاری اطلاعیه‌ها…" />;

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
        <h1 className="text-lg font-bold">اطلاعیه‌ها</h1>
        <span className="text-xs opacity-60">
          {page.announcements.length.toLocaleString("fa-IR")} مورد
        </span>
      </div>

      {banner && (
        <p className="rounded-xl bg-red-600/10 px-3 py-2 text-center text-xs text-red-700">
          {banner}
        </p>
      )}

      {page.announcements.length === 0 ? (
        <div className="rounded-2xl bg-black/5 p-8 text-center">
          <span className="text-4xl">📢</span>
          <p className="mt-2 text-sm opacity-70">
            اطلاعیه‌ای ذخیره نکرده‌اید. پست‌های کانال را در ربات ذخیره کنید.
          </p>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {page.announcements.map((announcement) => (
            <li key={announcement.id} className="rounded-2xl bg-black/5 p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-bold">
                    {announcement.source === "telegram" ? "📨 " : "📮 "}
                    {announcement.title}
                  </p>
                  <p className="mt-0.5 text-xs opacity-70">
                    {SOURCE_LABELS[announcement.source]} · {announcement.display}
                  </p>
                </div>
              </div>

              {announcement.text && (
                <p
                  className={`mt-2 whitespace-pre-wrap text-xs leading-5 opacity-90 ${
                    expanded[announcement.id] ? "" : "line-clamp-4"
                  }`}
                >
                  {announcement.text}
                </p>
              )}
              {announcement.text && announcement.text.length > 160 && (
                <button
                  type="button"
                  onClick={() =>
                    setExpanded((prev) => ({
                      ...prev,
                      [announcement.id]: !prev[announcement.id],
                    }))
                  }
                  className="mt-1 text-[11px] font-bold text-blue-600 active:opacity-80"
                >
                  {expanded[announcement.id] ? "کمتر" : "بیشتر"}
                </button>
              )}

              {previews[announcement.id] &&
                (previews[announcement.id].type.startsWith("image/") ? (
                  <img
                    src={previews[announcement.id].url}
                    alt={announcement.title}
                    className="mt-3 max-h-64 w-full rounded-xl object-contain"
                  />
                ) : (
                  <iframe
                    title={announcement.title}
                    src={previews[announcement.id].url}
                    className="mt-3 h-64 w-full rounded-xl border-0 bg-white"
                  />
                ))}

              <div className="mt-3 flex gap-2">
                {announcement.file_type && (
                  <button
                    type="button"
                    onClick={() => void showPreview(announcement)}
                    disabled={loadingPreview === announcement.id}
                    className="flex-1 rounded-xl bg-blue-600/10 px-3 py-2 text-xs font-bold text-blue-700 active:opacity-80 disabled:opacity-60"
                  >
                    {loadingPreview === announcement.id
                      ? "در حال باز کردن…"
                      : "👁 مشاهده رسانه"}
                  </button>
                )}
                {announcement.source_url && (
                  <a
                    href={announcement.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className={`rounded-xl bg-black/10 px-3 py-2 text-xs font-bold active:opacity-80 ${
                      announcement.file_type ? "" : "flex-1 text-center"
                    }`}
                  >
                    🔗 پست اصلی
                  </a>
                )}
                {confirmId === announcement.id ? (
                  <>
                    <button
                      type="button"
                      onClick={() => void remove(announcement.id)}
                      className="rounded-xl bg-red-600 px-3 py-2 text-xs font-bold text-white active:opacity-80"
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
                    onClick={() => setConfirmId(announcement.id)}
                    className="rounded-xl bg-red-600/10 px-3 py-2 text-xs font-bold text-red-700 active:opacity-80"
                  >
                    🗑
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
