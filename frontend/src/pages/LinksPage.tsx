import { useCallback, useEffect, useState } from "react";
import Spinner from "../components/Spinner";
import { ApiError, api } from "../lib/api";
import { getWebApp } from "../lib/telegram";
import type { LinkInput, UniversityLink } from "../lib/types";

type PageState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; links: UniversityLink[] };

interface FormState {
  id: number | null;
  title: string;
  url: string;
  description: string;
}

const EMPTY_FORM: FormState = { id: null, title: "", url: "", description: "" };

function haptic(type: "success" | "error"): void {
  getWebApp()?.HapticFeedback?.notificationOccurred(type);
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "ارتباط با سرور برقرار نشد";
}

export default function LinksPage() {
  const [page, setPage] = useState<PageState>({ kind: "loading" });
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  const load = useCallback(async () => {
    setPage({ kind: "loading" });
    try {
      const links = await api.links();
      setPage({ kind: "ready", links });
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

  const openEdit = (link: UniversityLink) => {
    setBanner(null);
    setForm({
      id: link.id,
      title: link.title,
      url: link.url,
      description: link.description ?? "",
    });
  };

  const save = async () => {
    if (!form) return;
    const title = form.title.trim();
    const url = form.url.trim();
    if (!title) {
      setBanner("عنوان لینک را وارد کنید.");
      return;
    }
    if (!/^https?:\/\//i.test(url)) {
      setBanner("آدرس باید با http:// یا https:// شروع شود.");
      return;
    }
    const payload: LinkInput = {
      title,
      url,
      description: form.description.trim() || null,
    };
    setSaving(true);
    try {
      if (form.id === null) await api.createLink(payload);
      else await api.updateLink(form.id, payload);
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
      await api.deleteLink(id);
      haptic("success");
      setConfirmId(null);
      await load();
    } catch (error: unknown) {
      setBanner(errorMessage(error));
      haptic("error");
    }
  };

  if (page.kind === "loading") return <Spinner label="در حال بارگذاری لینک‌ها…" />;

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
        <h1 className="text-lg font-bold">لینک‌های دانشگاه</h1>
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
          <h2 className="text-sm font-bold">{form.id === null ? "لینک جدید" : "ویرایش لینک"}</h2>
          <input
            className={field}
            placeholder="عنوان *"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <input
            className={`${field} dir-ltr text-left`}
            placeholder="https://…"
            value={form.url}
            onChange={(e) => setForm({ ...form, url: e.target.value })}
            autoCapitalize="none"
            autoCorrect="off"
          />
          <input
            className={field}
            placeholder="توضیح (اختیاری)"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
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

      {page.links.length === 0 && !form ? (
        <div className="rounded-2xl bg-black/5 p-8 text-center">
          <span className="text-4xl">🔗</span>
          <p className="mt-2 text-sm opacity-70">هنوز لینکی ذخیره نکرده‌اید.</p>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {page.links.map((link) => (
            <li key={link.id} className="rounded-2xl bg-black/5 p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-bold">{link.title}</p>
                  <p className="mt-0.5 truncate text-xs text-blue-600 dir-ltr text-left" dir="ltr">
                    {link.url}
                  </p>
                  {link.description && (
                    <p className="mt-1 text-xs opacity-80">{link.description}</p>
                  )}
                </div>
              </div>
              <div className="mt-3 flex gap-2">
                <a
                  href={link.url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex-1 rounded-xl bg-blue-600/10 px-3 py-2 text-center text-xs font-bold text-blue-700 active:opacity-80"
                >
                  🔗 باز کردن
                </a>
                <button
                  type="button"
                  onClick={() => openEdit(link)}
                  className="rounded-xl bg-black/10 px-3 py-2 text-xs font-bold active:opacity-80"
                >
                  ✏️
                </button>
                {confirmId === link.id ? (
                  <>
                    <button
                      type="button"
                      onClick={() => void remove(link.id)}
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
                    onClick={() => setConfirmId(link.id)}
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
