import { useState } from "react";
import Spinner from "../components/Spinner";
import { ApiError, api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { getWebApp } from "../lib/telegram";
import type { ProfileInput } from "../lib/types";

function haptic(type: "success" | "error"): void {
  getWebApp()?.HapticFeedback?.notificationOccurred(type);
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "ارتباط با سرور برقرار نشد";
}

const PROFILE_FIELDS: { key: keyof ProfileInput; label: string; placeholder: string }[] = [
  { key: "student_number", label: "شماره دانشجویی", placeholder: "مثلاً 402123456" },
  { key: "field_of_study", label: "رشته تحصیلی", placeholder: "مهندسی کامپیوتر" },
  { key: "university", label: "دانشگاه", placeholder: "دانشگاه تهران" },
  { key: "semester", label: "ترم", placeholder: "مثلاً 1404-1" },
  { key: "bio", label: "درباره من", placeholder: "چند کلمه دربارهٔ خودتان" },
];

export default function ProfilePage() {
  const { state, retry } = useAuth();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<ProfileInput | null>(null);
  const [saving, setSaving] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);

  if (state.status === "loading") return <Spinner label="در حال بارگذاری پروفایل…" />;

  if (state.status === "guest" || state.status === "error") {
    return (
      <section className="rounded-2xl bg-black/5 p-6 text-center">
        <p className="text-sm">
          {state.status === "error" ? state.message : "برای دسترسی، اپ را از تلگرام باز کنید."}
        </p>
        <button
          type="button"
          onClick={retry}
          className="mt-3 rounded-xl bg-blue-600 px-4 py-2 text-sm font-bold text-white active:opacity-80"
        >
          تلاش دوباره
        </button>
      </section>
    );
  }

  const user = state.user;
  const field =
    "w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm dark:bg-black/20";

  const openEdit = () => {
    setBanner(null);
    setForm({
      student_number: user.student_number ?? "",
      field_of_study: user.field_of_study ?? "",
      university: user.university ?? "",
      semester: user.semester ?? "",
      bio: user.bio ?? "",
    });
  };

  const save = async () => {
    if (!form) return;
    const payload: ProfileInput = {
      student_number: form.student_number?.trim() || null,
      field_of_study: form.field_of_study?.trim() || null,
      university: form.university?.trim() || null,
      semester: form.semester?.trim() || null,
      bio: form.bio?.trim() || null,
    };
    setSaving(true);
    try {
      await api.updateMe(payload);
      haptic("success");
      setEditing(false);
      setBanner(null);
      retry();
    } catch (error: unknown) {
      setBanner(errorMessage(error));
      haptic("error");
    } finally {
      setSaving(false);
    }
  };

  const displayName =
    [user.first_name, user.last_name].filter(Boolean).join(" ") || "کاربر تلگرام";

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center gap-3 rounded-2xl bg-black/5 p-4">
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xl font-bold text-white">
          {(user.first_name || "ک").slice(0, 1)}
        </div>
        <div className="min-w-0">
          <p className="truncate font-bold">{displayName}</p>
          <p className="truncate text-xs opacity-70" dir="ltr">
            {user.username ? `@${user.username}` : `id: ${user.telegram_id}`}
          </p>
        </div>
      </div>

      {banner && (
        <p className="rounded-xl bg-red-600/10 px-3 py-2 text-center text-xs text-red-700">
          {banner}
        </p>
      )}

      {editing && form ? (
        <div className="flex flex-col gap-3 rounded-2xl bg-black/5 p-4">
          <h2 className="text-sm font-bold">ویرایش پروفایل</h2>
          {PROFILE_FIELDS.map((item) => (
            <label key={item.key} className="flex flex-col gap-1">
              <span className="text-[11px] font-bold opacity-70">{item.label}</span>
              {item.key === "bio" ? (
                <textarea
                  className={`${field} min-h-20`}
                  placeholder={item.placeholder}
                  value={form[item.key] ?? ""}
                  onChange={(e) => setForm({ ...form, [item.key]: e.target.value })}
                />
              ) : (
                <input
                  className={field}
                  placeholder={item.placeholder}
                  value={form[item.key] ?? ""}
                  onChange={(e) => setForm({ ...form, [item.key]: e.target.value })}
                />
              )}
            </label>
          ))}
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
                setEditing(false);
                setBanner(null);
              }}
              className="flex-1 rounded-xl bg-black/10 px-4 py-2.5 text-sm font-bold active:opacity-80"
            >
              انصراف
            </button>
          </div>
        </div>
      ) : (
        <div className="rounded-2xl bg-black/5 p-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold">اطلاعات دانشجویی</h2>
            <button
              type="button"
              onClick={openEdit}
              className="rounded-xl bg-blue-600/10 px-3 py-1.5 text-xs font-bold text-blue-700 active:opacity-80"
            >
              ✏️ ویرایش
            </button>
          </div>
          <dl className="mt-3 flex flex-col gap-2">
            {PROFILE_FIELDS.map((item) => (
              <div key={item.key} className="flex items-start justify-between gap-3">
                <dt className="shrink-0 text-xs opacity-70">{item.label}</dt>
                <dd className="min-w-0 text-left text-sm">
                  {item.key === "bio" ? (
                    <span className="whitespace-pre-wrap">{user.bio || "—"}</span>
                  ) : (
                    (user[item.key] as string | null) || "—"
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      <div className="rounded-2xl bg-black/5 p-4 text-xs leading-6 opacity-80">
        <h2 className="mb-1 text-sm font-bold opacity-100">تنظیمات</h2>
        <p>حداقل نسخهٔ تلگرام برای استفاده از مینی‌اپ: ۶٫۴</p>
        <p>
          حساب: <span dir="ltr">{user.username ? `@${user.username}` : user.telegram_id}</span>
        </p>
        <p>تمام داده‌ها فقط متعلق به شماست و در حساب تلگرامتان ذخیره می‌شود.</p>
      </div>
    </section>
  );
}
