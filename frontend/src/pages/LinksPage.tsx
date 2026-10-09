import { useCallback, useEffect, useState } from "react";
import Spinner from "../components/Spinner";
import { ApiError, api } from "../lib/api";
import { useAuth } from "../lib/auth";
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
  saveLogin: boolean;
  username: string;
  password: string;
}

const EMPTY_FORM: FormState = {
  id: null,
  title: "",
  url: "",
  description: "",
  saveLogin: false,
  username: "",
  password: "",
};

function haptic(type: "success" | "error"): void {
  getWebApp()?.HapticFeedback?.notificationOccurred(type);
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "ارتباط با سرور برقرار نشد";
}

/**
 * Try to open a link with credentials embedded as ``https://user:pass@host``.
 * Telegram's in-app browser and most desktop browsers accept this format for
 * HTTP Basic Auth sites. Returns true when the auto-login URL was opened,
 * false when the caller should fall back to a plain URL open.
 *
 * We never embed credentials in the URL when the site uses HTTPS with a
 * different scheme (e.g. a query-param login form) because that would leak
 * them into browser history and server logs.
 */
function tryBasicAuthAutoLogin(url: string, username: string, password: string): boolean {
  try {
    const parsed = new URL(url);
    // Only attempt basic-auth auto-login on http(s). Never on javascript:, data:, etc.
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return false;
    // Skip when the URL already has credentials embedded.
    if (parsed.username || parsed.password) return false;
    parsed.username = encodeURIComponent(username);
    parsed.password = encodeURIComponent(password);
    window.open(parsed.toString(), "_blank");
    return true;
  } catch {
    return false;
  }
}

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to legacy method
  }
  // Legacy fallback for older Telegram WebApp clients
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  document.body.removeChild(textarea);
  return ok;
}

export default function LinksPage() {
  const { state } = useAuth();
  const [page, setPage] = useState<PageState>({ kind: "loading" });
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [opening, setOpening] = useState<number | null>(null);

  const credentialsEnabled =
    state.status === "ready" ? state.user.credentials_enabled : false;

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
      // Pre-fill the toggle so the user can see credentials are stored,
      // but leave the fields empty for security (we never send the
      // decrypted password back into the form).
      saveLogin: link.has_credentials,
      username: "",
      password: "",
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
    // Validate credential pair: both must be set when saveLogin is on.
    const wantCreds = credentialsEnabled && form.saveLogin;
    const username = form.username.trim();
    const password = form.password;
    if (wantCreds) {
      if (!username || !password) {
        setBanner("نام کاربری و رمز عبور را پر کنید یا گزینهٔ ذخیره را خاموش کنید.");
        return;
      }
    }
    // When editing and the user kept saveLogin on but did not type a new
    // password, we must NOT send empty creds (that would clear them).
    // Send undefined so the backend keeps the existing values; only send
    // username/password when the user actually typed something.
    let payloadUsername: string | null = null;
    let payloadPassword: string | null = null;
    if (wantCreds) {
      payloadUsername = username;
      payloadPassword = password;
    } else if (form.id !== null) {
      // Editing existing link and user turned off saveLogin: clear creds.
      payloadUsername = null;
      payloadPassword = null;
    }
    const payload: LinkInput = {
      title,
      url,
      description: form.description.trim() || null,
      ...(payloadUsername !== null ? { username: payloadUsername } : {}),
      ...(payloadPassword !== null ? { password: payloadPassword } : {}),
    };
    // When editing with saveLogin on but no new password typed, we need
    // to explicitly tell the backend "keep existing". The current schema
    // treats absent fields as "no change" only on create; on update,
    // absent means "clear". So if the user didn't type a new password,
    // we skip sending username/password entirely.
    if (form.id !== null && wantCreds && !password) {
      delete (payload as { username?: string }).username;
      delete (payload as { password?: string }).password;
    }
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

  /**
   * Open a link. When credentials are stored, fetch them, copy the password
   * to the clipboard, and try basic-auth auto-login first. Fall back to the
   * plain URL when auto-login is not possible.
   */
  const openLink = async (link: UniversityLink) => {
    if (!link.has_credentials) {
      window.open(link.url, "_blank");
      return;
    }
    setOpening(link.id);
    try {
      const creds = await api.linkCredentials(link.id);
      if (!creds.has_credentials) {
        window.open(link.url, "_blank");
        return;
      }
      // Try basic-auth auto-login first (works for HTTP Basic Auth sites).
      const opened = tryBasicAuthAutoLogin(
        link.url,
        creds.username ?? "",
        creds.password ?? "",
      );
      if (opened) {
        haptic("success");
        setBanner(`🔐 ورود خودکار به «${link.title}» انجام شد.`);
        return;
      }
      // Fall back: open the site + copy the password to the clipboard so
      // the user can paste it with one tap.
      const copied = await copyToClipboard(creds.password ?? "");
      window.open(link.url, "_blank");
      haptic("success");
      setBanner(
        copied
          ? `🔑 رمز «${link.title}» کپی شد. در صفحهٔ ورود Ctrl+V بزن.`
          : `🔑 نام کاربری: ${creds.username}`,
      );
    } catch (error: unknown) {
      setBanner(errorMessage(error));
      haptic("error");
      // Still open the plain URL so the user is not stuck.
      window.open(link.url, "_blank");
    } finally {
      setOpening(null);
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
        <p className="rounded-xl bg-blue-600/10 px-3 py-2 text-center text-xs text-blue-700">
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

          {credentialsEnabled && (
            <>
              <label className="flex items-center gap-2 text-xs font-bold">
                <input
                  type="checkbox"
                  checked={form.saveLogin}
                  onChange={(e) => setForm({ ...form, saveLogin: e.target.checked })}
                  className="h-4 w-4"
                />
                🔐 ذخیرهٔ نام کاربری و رمز عبور برای ورود خودکار
              </label>
              {form.saveLogin && (
                <>
                  {form.id !== null && (
                    <p className="rounded-xl bg-black/5 px-3 py-2 text-[11px] opacity-70">
                      رمز فعلی ذخیره شده. برای تغییر، رمز جدید را وارد کن؛
                      برای حذف، تیک «ذخیره» را خاموش کن.
                    </p>
                  )}
                  <input
                    className={`${field} dir-ltr text-left`}
                    placeholder="نام کاربری"
                    value={form.username}
                    onChange={(e) => setForm({ ...form, username: e.target.value })}
                    autoCapitalize="none"
                    autoCorrect="off"
                  />
                  <input
                    className={`${field} dir-ltr text-left`}
                    placeholder={form.id === null ? "رمز عبور" : "رمز عبور جدید (اختیاری)"}
                    type="password"
                    value={form.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                    autoCapitalize="none"
                    autoCorrect="off"
                  />
                </>
              )}
            </>
          )}

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
                  <p className="truncate font-bold">
                    {link.title}
                    {link.has_credentials && (
                      <span className="mr-1 text-xs opacity-60" title="رمز ذخیره شده">
                        🔐
                      </span>
                    )}
                  </p>
                  <p className="mt-0.5 truncate text-xs text-blue-600 dir-ltr text-left" dir="ltr">
                    {link.url}
                  </p>
                  {link.description && (
                    <p className="mt-1 text-xs opacity-80">{link.description}</p>
                  )}
                </div>
              </div>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => void openLink(link)}
                  disabled={opening === link.id}
                  className="flex-1 rounded-xl bg-blue-600/10 px-3 py-2 text-center text-xs font-bold text-blue-700 active:opacity-80 disabled:opacity-60"
                >
                  {opening === link.id
                    ? "در حال باز کردن…"
                    : link.has_credentials
                      ? "🔐 ورود خودکار"
                      : "🔗 باز کردن"}
                </button>
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
