import { useCallback, useEffect, useRef, useState } from "react";
import { EditIcon, PlusIcon, ShareIcon, TrashIcon, XIcon } from "../components/Icons";
import ImageViewer from "../components/ImageViewer";
import Spinner from "../components/Spinner";
import { ApiError, api } from "../lib/api";
import { getWebApp } from "../lib/telegram";
import type { Course, Note, NoteInput } from "../lib/types";

type PageState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; notes: Note[]; courses: Course[] };

type Filter = "all" | "none" | number;

interface FormState {
  id: number | null;
  title: string;
  description: string;
  course_id: string;
  file: File | null;
}

interface Preview {
  noteId: number;
  url: string;
  kind: "image" | "pdf" | "other";
}

const EMPTY_FORM: FormState = {
  id: null,
  title: "",
  description: "",
  course_id: "",
  file: null,
};

function haptic(type: "success" | "error"): void {
  getWebApp()?.HapticFeedback?.notificationOccurred(type);
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "ارتباط با سرور برقرار نشد";
}

export default function NotesPage() {
  const [page, setPage] = useState<PageState>({ kind: "loading" });
  const [filter, setFilter] = useState<Filter>("all");
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [loadingPreview, setLoadingPreview] = useState<number | null>(null);
  const [sendingId, setSendingId] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const noticeTimer = useRef(0);
  const [shareTarget, setShareTarget] = useState<Note | null>(null);
  const [shareIdInput, setShareIdInput] = useState("");
  const [sharing, setSharing] = useState(false);

  const load = useCallback(async () => {
    setPage({ kind: "loading" });
    try {
      const [notes, courses] = await Promise.all([api.notes(), api.courses()]);
      setPage({ kind: "ready", notes, courses });
    } catch (error: unknown) {
      setPage({ kind: "error", message: errorMessage(error) });
      haptic("error");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => () => window.clearTimeout(noticeTimer.current), []);

  const flashNotice = (message: string) => {
    setNotice(message);
    window.clearTimeout(noticeTimer.current);
    noticeTimer.current = window.setTimeout(() => setNotice(null), 3000);
  };

  const openCreate = () => {
    setBanner(null);
    setForm({ ...EMPTY_FORM });
  };

  const openEdit = (note: Note) => {
    setBanner(null);
    setForm({
      id: note.id,
      title: note.title,
      description: note.description ?? "",
      course_id: note.course_id === null ? "" : String(note.course_id),
      file: null,
    });
  };

  const save = async () => {
    if (!form) return;
    const title = form.title.trim();
    if (!title) {
      setBanner("عنوان جزوه را وارد کنید.");
      return;
    }
    if (form.id === null && !form.file) {
      setBanner("فایل جزوه را انتخاب کنید.");
      return;
    }
    // Client-side size guard: Vercel serverless caps request bodies at
    // 4.5MB. Files larger than 4MB must go through the Telegram bot chat.
    if (form.id === null && form.file && form.file.size > 4 * 1024 * 1024) {
      setBanner(
        "حجم فایل زیاد است. فایل‌های بزرگ‌تر از ۴ مگابایت را مستقیم به ربات تلگرام بفرست " +
        "(در چت ربات، فایل را آپلود کن) — ربات خودکار ذخیره می‌کند.",
      );
      haptic("error");
      return;
    }
    const meta: NoteInput = {
      title,
      description: form.description.trim() || null,
      course_id: form.course_id ? Number(form.course_id) : null,
    };
    setSaving(true);
    try {
      if (form.id === null && form.file) await api.uploadNote(form.file, meta);
      else if (form.id !== null) await api.updateNote(form.id, meta);
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

  const closePreview = () => {
    // Dropping the element lets the WebView release the decoded image/PDF.
    setPreview(null);
  };

  const remove = async (id: number) => {
    try {
      await api.deleteNote(id);
      if (preview?.noteId === id) closePreview();
      haptic("success");
      setConfirmId(null);
      await load();
    } catch (error: unknown) {
      setBanner(errorMessage(error));
      haptic("error");
    }
  };

  const showPreview = async (note: Note) => {
    if (loadingPreview !== null) return;
    setLoadingPreview(note.id);
    try {
      const { token, media_type } = await api.noteFileToken(note.id);
      const kind: Preview["kind"] = media_type.startsWith("image/")
        ? "image"
        : media_type === "application/pdf"
          ? "pdf"
          : "other";
      setPreview({
        noteId: note.id,
        url: `/api/notes/${note.id}/file?t=${encodeURIComponent(token)}`,
        kind,
      });
      haptic("success");
    } catch (error: unknown) {
      setBanner(errorMessage(error));
      haptic("error");
    } finally {
      setLoadingPreview(null);
    }
  };

  const sendToTelegram = async (note: Note) => {
    if (sendingId !== null) return;
    setSendingId(note.id);
    setNotice(null);
    try {
      await api.sendNoteToTelegram(note.id);
      haptic("success");
      flashNotice("در تلگرام ارسال شد ✅");
    } catch (error: unknown) {
      setBanner(errorMessage(error));
      haptic("error");
    } finally {
      setSendingId(null);
    }
  };

  const openShare = (note: Note) => {
    setShareTarget(note);
    setShareIdInput("");
    setBanner(null);
  };

  const submitShare = async () => {
    if (!shareTarget) return;
    const trimmed = shareIdInput.trim();
    if (!trimmed) {
      setBanner("شناسه تلگرام گیرنده را وارد کنید.");
      return;
    }
    // Accept both plain digits and @username-style (rare for IDs).
    const numericId = Number(trimmed.replace(/[^0-9]/g, ""));
    if (!Number.isFinite(numericId) || numericId <= 0) {
      setBanner("شناسه تلگرام باید عدد باشد.");
      return;
    }
    setSharing(true);
    try {
      const result = await api.shareNote(shareTarget.id, numericId);
      haptic("success");
      flashNotice(`جزوه برای ${result.recipient} ارسال شد ✅`);
      setShareTarget(null);
      setShareIdInput("");
      setBanner(null);
    } catch (error: unknown) {
      setBanner(errorMessage(error));
      haptic("error");
    } finally {
      setSharing(false);
    }
  };

  if (page.kind === "loading") return <Spinner label="در حال بارگذاری جزوه‌ها…" />;

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

  const visible = page.notes.filter((note) => {
    if (filter === "all") return true;
    if (filter === "none") return note.course_id === null;
    return note.course_id === filter;
  });

  const previewNote = preview
    ? page.notes.find((note) => note.id === preview.noteId) ?? null
    : null;

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">جزوه‌ها</h1>
        <button
          type="button"
          onClick={openCreate}
          className="flex items-center gap-1 rounded-xl bg-blue-600 px-3 py-2 text-xs font-bold text-white active:opacity-80"
        >
          <PlusIcon className="h-4 w-4" />
          افزودن
        </button>
      </div>

      {banner && (
        <p className="rounded-xl bg-red-600/10 px-3 py-2 text-center text-xs text-red-700">
          {banner}
        </p>
      )}

      {notice && (
        <p className="rounded-xl bg-emerald-600/10 px-3 py-2 text-center text-xs font-bold text-emerald-700">
          {notice}
        </p>
      )}

      {form && (
        <div className="flex flex-col gap-3 rounded-2xl bg-black/5 p-4">
          <h2 className="text-sm font-bold">
            {form.id === null ? "جزوه جدید" : "ویرایش جزوه"}
          </h2>
          {form.id === null && (
            <label className="rounded-xl border border-dashed border-black/20 px-3 py-3 text-center text-xs opacity-80">
              {form.file ? `📁 ${form.file.name}` : "📁 انتخاب فایل *"}
              <input
                type="file"
                className="hidden"
                onChange={(e) =>
                  setForm({ ...form, file: e.target.files?.[0] ?? null })
                }
              />
            </label>
          )}
          <input
            className={field}
            placeholder="عنوان *"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <textarea
            className={`${field} min-h-20`}
            placeholder="توضیح (اختیاری)"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <select
            className={field}
            value={form.course_id}
            onChange={(e) => setForm({ ...form, course_id: e.target.value })}
          >
            <option value="">بدون درس</option>
            {page.courses.map((course) => (
              <option key={course.id} value={course.id}>
                {course.name}
              </option>
            ))}
          </select>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => void save()}
              disabled={saving}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-bold text-white active:opacity-80 disabled:opacity-60"
            >
              {saving ? "در حال ذخیره…" : "ذخیره"}
            </button>
            <button
              type="button"
              onClick={() => {
                setForm(null);
                setBanner(null);
              }}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-black/10 px-4 py-2.5 text-sm font-bold active:opacity-80"
            >
              <XIcon className="h-4 w-4" />
              انصراف
            </button>
          </div>
        </div>
      )}

      {page.courses.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setFilter("all")}
            className={`rounded-full px-3 py-1.5 text-xs font-bold active:opacity-80 ${
              filter === "all" ? "bg-blue-600 text-white" : "bg-black/10"
            }`}
          >
            همه ({page.notes.length.toLocaleString("fa-IR")})
          </button>
          <button
            type="button"
            onClick={() => setFilter("none")}
            className={`rounded-full px-3 py-1.5 text-xs font-bold active:opacity-80 ${
              filter === "none" ? "bg-blue-600 text-white" : "bg-black/10"
            }`}
          >
            بدون درس
          </button>
          {page.courses.map((course) => (
            <button
              key={course.id}
              type="button"
              onClick={() => setFilter(course.id)}
              className={`rounded-full px-3 py-1.5 text-xs font-bold active:opacity-80 ${
                filter === course.id ? "bg-blue-600 text-white" : "bg-black/10"
              }`}
            >
              {course.name}
            </button>
          ))}
        </div>
      )}

      {visible.length === 0 && !form ? (
        <div className="rounded-2xl bg-black/5 p-8 text-center">
          <span className="text-4xl">📂</span>
          <p className="mt-2 text-sm opacity-70">هنوز جزوه‌ای ذخیره نکرده‌اید.</p>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {visible.map((note) => (
            <li key={note.id} className="rounded-2xl bg-black/5 p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-bold">
                    {note.file_type === "photo" ? "🖼 " : "📄 "}
                    {note.title}
                  </p>
                  <p className="mt-0.5 truncate text-xs opacity-70">
                    {note.course_name ?? "بدون درس"}
                    {note.file_name ? ` · ${note.file_name}` : ""}
                  </p>
                </div>
              </div>
              {note.description && (
                <p className="mt-2 whitespace-pre-wrap text-xs opacity-80">
                  {note.description}
                </p>
              )}

              {preview?.noteId === note.id && preview.kind !== "image" && (
                <div className="mt-3">
                  {preview.kind === "pdf" && (
                    <>
                      <iframe
                        title={note.title}
                        src={preview.url}
                        className="h-72 w-full rounded-xl border-0 bg-white"
                      />
                      <a
                        href={preview.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-2 block rounded-xl bg-blue-600/10 px-3 py-2 text-center text-xs font-bold text-blue-700"
                      >
                        ⬇️ باز کردن در برنامهٔ PDF / دانلود
                      </a>
                    </>
                  )}
                  {preview.kind === "other" && (
                    <a
                      href={preview.url}
                      download={note.file_name ?? "file"}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block rounded-xl bg-blue-600/10 px-3 py-2 text-center text-xs font-bold text-blue-700"
                    >
                      ⬇️ دانلود {note.file_name ?? "فایل"}
                    </a>
                  )}
                </div>
              )}

              <div className="mt-3 flex gap-2">
                {preview?.noteId === note.id ? (
                  <button
                    type="button"
                    onClick={closePreview}
                    className="flex-1 rounded-xl bg-black/10 px-3 py-2 text-xs font-bold active:opacity-80"
                  >
                    ✕ بستن پیش‌نمایش
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => void showPreview(note)}
                    disabled={loadingPreview !== null}
                    className="flex-1 rounded-xl bg-blue-600/10 px-3 py-2 text-xs font-bold text-blue-700 active:opacity-80 disabled:opacity-60"
                  >
                    {loadingPreview === note.id ? "در حال باز کردن…" : "👁 مشاهده"}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => openEdit(note)}
                  className="flex items-center justify-center rounded-xl bg-black/10 px-3 py-2 text-xs font-bold text-blue-700 active:opacity-80"
                  title="ویرایش"
                >
                  <EditIcon className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  title="ارسال در تلگرام"
                  aria-label="ارسال در تلگرام"
                  onClick={() => void sendToTelegram(note)}
                  disabled={sendingId !== null}
                  className="rounded-xl bg-blue-600/10 px-3 py-2 text-xs font-bold text-blue-700 active:opacity-80 disabled:opacity-60"
                >
                  {sendingId === note.id ? "…" : "📤"}
                </button>
                <button
                  type="button"
                  title="اشتراک‌گذاری با دوست"
                  aria-label="اشتراک‌گذاری"
                  onClick={() => openShare(note)}
                  className="flex items-center justify-center rounded-xl bg-emerald-600/10 px-3 py-2 text-xs font-bold text-emerald-700 transition-colors active:opacity-80 dark:text-emerald-400"
                >
                  <ShareIcon className="h-4 w-4" />
                </button>
                {confirmId === note.id ? (
                  <>
                    <button
                      type="button"
                      onClick={() => void remove(note.id)}
                      className="flex items-center gap-1 rounded-xl bg-red-600 px-3 py-2 text-xs font-bold text-white active:opacity-80"
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
                    onClick={() => setConfirmId(note.id)}
                    className="flex items-center justify-center rounded-xl bg-red-600/10 px-3 py-2 text-xs font-bold text-red-700 active:opacity-80"
                    title="حذف"
                  >
                    <TrashIcon className="h-4 w-4" />
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {preview?.kind === "image" && (
        <ImageViewer
          url={preview.url}
          alt={previewNote?.title ?? "جزوه"}
          onClose={closePreview}
        />
      )}

      {shareTarget && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-4"
          onClick={() => !sharing && setShareTarget(null)}
        >
          <div
            className="w-full max-w-md rounded-2xl bg-white p-5 dark:bg-neutral-900"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <h3 className="flex items-center gap-1.5 text-base font-bold">
                <ShareIcon className="h-5 w-5 text-emerald-600" />
                اشتراک‌گذاری جزوه
              </h3>
              <button
                type="button"
                onClick={() => !sharing && setShareTarget(null)}
                className="flex items-center justify-center rounded-lg bg-black/10 p-1.5 text-xs"
                title="بستن"
                disabled={sharing}
              >
                <XIcon className="h-4 w-4" />
              </button>
            </div>

            <p className="mb-3 text-xs opacity-70">
              جزوه «{shareTarget.title}» برای کدام کاربر ارسال شود؟
            </p>

            <input
              type="text"
              inputMode="numeric"
              className="w-full rounded-xl border border-black/10 bg-white px-3 py-2.5 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 focus:outline-none dark:bg-black/30 dark:text-white"
              placeholder="شناسه تلگرام گیرنده (مثلاً ۱۲۳۴۵۶۷۸۹)"
              value={shareIdInput}
              onChange={(e) => setShareIdInput(e.target.value)}
              disabled={sharing}
              dir="ltr"
            />
            <p className="mt-2 text-[11px] leading-5 opacity-60">
              💡 شناسه تلگرام را می‌توانید از تنظیمات تلگرام گیرنده پیدا کنید.
              گیرنده باید حداقل یک‌بار ربات را باز کرده باشد.
            </p>

            {banner && (
              <p className="mt-3 rounded-xl bg-red-600/10 px-3 py-2 text-center text-xs text-red-700 dark:text-red-400">
                {banner}
              </p>
            )}

            <div className="mt-4 flex gap-3">
              <button
                type="button"
                onClick={() => void submitShare()}
                disabled={sharing}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-bold text-white transition-opacity active:opacity-80 disabled:opacity-60"
              >
                <ShareIcon className="h-4 w-4" />
                {sharing ? "در حال ارسال…" : "ارسال"}
              </button>
              <button
                type="button"
                onClick={() => !sharing && setShareTarget(null)}
                disabled={sharing}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-black/10 px-4 py-3 text-sm font-bold transition-colors active:opacity-80 disabled:opacity-60 dark:bg-white/10"
              >
                <XIcon className="h-4 w-4" />
                انصراف
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
