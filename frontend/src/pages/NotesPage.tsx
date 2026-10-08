import { useCallback, useEffect, useState } from "react";
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
  const [mediaReady, setMediaReady] = useState(false);

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
    setMediaReady(false);
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
    setMediaReady(false);
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

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">جزوه‌ها</h1>
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

              {preview?.noteId === note.id && (
                <div className="mt-3">
                  {preview.kind === "image" && !mediaReady && (
                    <p className="rounded-xl bg-black/5 py-6 text-center text-xs opacity-60">
                      در حال بارگذاری تصویر…
                    </p>
                  )}
                  {preview.kind === "image" && (
                    <img
                      src={preview.url}
                      alt={note.title}
                      decoding="async"
                      onLoad={() => setMediaReady(true)}
                      onError={() => {
                        setBanner("نمایش تصویر ممکن نشد؛ فایل را دانلود کنید.");
                        closePreview();
                      }}
                      className={`max-h-80 w-full rounded-xl object-contain ${
                        mediaReady ? "" : "hidden"
                      }`}
                    />
                  )}
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
                  className="rounded-xl bg-black/10 px-3 py-2 text-xs font-bold active:opacity-80"
                >
                  ✏️
                </button>
                {confirmId === note.id ? (
                  <>
                    <button
                      type="button"
                      onClick={() => void remove(note.id)}
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
                    onClick={() => setConfirmId(note.id)}
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
