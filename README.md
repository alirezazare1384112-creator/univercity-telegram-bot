# 🎓 ربات دستیار دانشجو (Student Assistant Bot)

[![CI](https://github.com/alirezazare1384112-creator/univercity-telegram-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/alirezazare1384112-creator/univercity-telegram-bot/actions/workflows/ci.yml)

ربات تلگرامی برای دانشجوها: برنامه هفتگی، درس‌ها، نمرات، معدل و یادآوری — با
**Python 3.13 + python-telegram-bot v22 + SQLAlchemy 2 (async) + Alembic**.

همهٔ متن‌ها فارسی و با تقویم شمسی (`jdatetime`) نمایش داده می‌شوند.

---

## ۱. قابلیت‌ها

| منو | وضعیت | توضیح |
|---|---|---|
| 📅 برنامه هفتگی | ✅ | عکس/سند (هر نوع فایل)، جایگزینی مستقیم از همان صفحه، فقط یک نسخهٔ فعال برای هر دانشجو |
| 📚 درس‌های من | ✅ | ویزارد افزودن/ویرایش/حذف درس (نام، واحد، استاد، ترم، سال تحصیلی) |
| 📝 نمرات من | ✅ | آیتم نمره برای هر درس + مجموع و درصد |
| 🧮 محاسبه معدل | ✅ | دکمهٔ خارجی به `GPA_CALCULATOR_URL` (بدون محاسبهٔ محلی) |
| ⏰ یادآوری‌ها | ✅ | ساخت/ویرایش/توقف/حذف، تکرار روزانه/هفتگی/ماهانه، ۳ نوع هشدار |
| 📚 جزوه‌ها | ✅ | دسته‌بندی بر اساس درس‌های خودت (دکمهٔ هر درس → جزوه‌هایش)؛ ذخیرهٔ فایل با عنوان و توضیح؛ ارسال مجدد، ویرایش، حذف |
| 🔗 سامانه‌های دانشگاه | ✅ | نشانک شخصی هر دانشجو؛ دکمهٔ URL با یک لمس سایت را باز می‌کند؛ ۴ سایت مهم دانشگاه (گلستان، تغذیه، LMS، سامانه خرده) به‌صورت ثابت |
| 📢 اطلاعیه‌ها | ✅ | ذخیره از **تلگرام** (فوروارد کانال) یا **ایتا** (متن + لینک `eitaa.com`) با پیوند مستقیم؛ دکمهٔ باز کردن دو کانال ایتا در منو؛ **دریافت خودکار** پست‌های متنی همان کانال‌ها (هر ۵ دقیقه) |
| 📆 تقویم و کارهای آینده | ✅ | رویداد با تاریخ شمسی/نسبی (فردا) + ساعت اختیاری، انجام‌شده‌ها، ویرایش/حذف |
| 👤 پروفایل | ✅ | شماره دانشجویی، رشته، دانشگاه، ترم |
| 🛠 پنل ادمین | ✅ | فقط برای `ADMIN_IDS`؛ فرمان `/admin` → آمار سامانه، لیست کاربران، ارسال همگگانی، همگام‌سازی ایتا با یک کلیک |

---

## ۲. معماری

```
Telegram update
   │
   ▼
[-1] middleware: capture_user      ← هر آپدیت = یک ردیف در users
   │
   ▼
[0]  ConversationHandler هر بخش    ← ویزاردها و دکمه‌های inline
   │        │
   │        ▼
   │   Repository (فقط SQL/ORM، بدون منطق کسب‌وکار)
   │        │
   │        ▼
   │   SQLAlchemy async + Alembic migration
   │
   ▼
[1]  fallback: متن ناشناخته → منوی اصلی

پس‌زمینه: app/scheduler.py  هر ۳۰ ثانیه ردیف‌های سررسیدِ
reminder_notifications را می‌خواند و پیام می‌فرستد.
```

### قراردادهای پروژه (مهم)

1. **همهٔ datetimeها در دیتابیس `naive UTC` است**؛ تبدیل به وقت تهران فقط در
   لایهٔ نمایش (`app/utils/datetime_utils.py`).
2. **پیام‌ها Plain text** — بدون Markdown/HTML تا متن کاربر هرگز باعث خطای
   Telegram نشود.
3. **هر `async with get_session()` یک تراکنش است** (commit در موفقیت، rollback
   در خطا، بستن همیشگی). **هرگز دو session همزمان باز نمی‌شود** — اول همه‌چیز
   خوانده می‌شود، بعد تصمیم گرفته و دوباره session جدید باز می‌شود.
4. **Enum پایتونی استفاده نمی‌شود**؛ مقادیر `String + CheckConstraint` هستند تا
   SQLite و PostgreSQL یک‌جور رفتار کنند و migration ساده بماند.
5. **منطق دسترسی داخل Repository** است: هر کوئری با `user_id` محدود می‌شود،
   پس دانشجوی الف هرگز دادهٔ ب را نمی‌بیند.
6. **متن‌ها/لیبل دکمه‌ها منبع واحد دارند** (`app/bot/keyboards/`)؛ هیچ handlerی
   لیبل دکمهٔ جای دیگر را hard-code نمی‌کند.
7. **Conversationها از هم مستقل‌اند** و هیچ دکمه‌ای بین آن‌ها لینک نشده
   (جلوگیری از تداخل state).
8. **Scheduler دیتابیس‌محور است** نه `JobQueue`/APScheduler: یادآوری‌های ارسال
   نشده در جدول می‌مانند و بعد از ری‌استارت از دست نمی‌روند.

---

## ۳. ساختار پروژه

```
student_assistant_bot/
├── run.py                     # نقطهٔ شروع: python run.py [--check]
├── .env / .env.example        # تنظیمات (هرگز commit نمی‌شود)
├── alembic.ini
├── pytest.ini
├── requirements.txt
├── app/
│   ├── config.py              # Settings از .env + نرمال‌سازی DATABASE_URL
│   ├── main.py                # build_application / healthcheck / run_bot
│   ├── scheduler.py           # poller یادآوری‌ها (start/stop در PTB lifecycle)
│   ├── logging_config.py
│   ├── bot/
│   │   ├── middlewares.py     # capture_user
│   │   ├── helpers.py         # answer / current_user_id / is_admin
│   │   ├── keyboards/         # لیبل‌های منو و کیبوردها
│   │   ├── states/            # state هر Conversation
│   │   └── handlers/          # start, schedule, courses, grades, gpa, calendar, notes, links, announcements, profile, reminders
│   ├── database/
│   │   ├── database.py        # engine / get_session / PRAGMA های SQLite
│   │   ├── models/            # User, Admin, WeeklySchedule, Course, GradeItem, Note,
│   │   │                      # UniversityLink, Announcement, CalendarEvent, Reminder, ... NotificationLog
│   │   ├── repositories/      # فقط دسترسی به داده
│   │   └── migrations/        # Alembic (versions/)
│   ├── services/              # منطق کسب‌وکار (مثلاً reminder_service)
│   └── utils/                 # datetime_utils (شمسی), validation
└── tests/                     # pytest + aiosqlite in-memory
```

---

## ۴. نمودار ER

```mermaid
erDiagram
    USERS ||--o{ WEEKLY_SCHEDULES : "عکس برنامه"
    USERS ||--o{ COURSES : "درس‌های ترم"
    USERS ||--o{ REMINDERS : "یادآوری"
    USERS ||--o{ NOTES : "جزوه‌ها"
    USERS ||--o{ UNIVERSITY_LINKS : "نشانک‌ها"
    USERS ||--o{ ANNOUNCEMENTS : "اطلاعیه‌ها"
    USERS ||--o{ CALENDAR_EVENTS : "رویدادهای تقویم"
    USERS ||--o{ NOTIFICATION_LOGS : "لاگ پیام‌ها"
    COURSES ||--o{ GRADE_ITEMS : "نمره‌ها"
    COURSES ||--o{ REMINDERS : "مرتبط با درس (SET NULL)"
    COURSES ||--o{ NOTES : "مرتبط با درس (SET NULL)"
    REMINDERS ||--o{ REMINDER_NOTIFICATIONS : "هر هشدار یک ردیف"

    USERS {
        bigint id PK
        bigint telegram_id UK
        varchar username
        varchar first_name
        varchar last_name
        varchar student_number
        varchar field_of_study
        varchar university
        varchar semester
        text bio
        bool is_active
        datetime created_at
        datetime updated_at
    }
    ADMINS {
        bigint id PK
        bigint telegram_id UK
        varchar username
        bool is_active
    }
    WEEKLY_SCHEDULES {
        bigint id PK
        bigint user_id FK
        varchar telegram_file_id
        varchar file_type "photo|document"
        text caption
        bool is_active "فقط یکی فعال"
    }
    COURSES {
        bigint id PK
        bigint user_id FK
        varchar name
        int units "units > 0"
        varchar teacher_name
        varchar semester
        varchar academic_year
    }
    GRADE_ITEMS {
        bigint id PK
        bigint course_id FK
        varchar title
        float score "score >= 0"
        float max_score "max_score > 0"
        text description
    }
    NOTES {
        bigint id PK
        bigint user_id FK
        bigint course_id FK "nullable"
        varchar title
        text description
        varchar file_type "photo|document"
        varchar file_id "Telegram file_id"
        varchar file_name "نام فایل سند"
        datetime created_at
    }
    UNIVERSITY_LINKS {
        bigint id PK
        bigint user_id FK
        varchar title
        varchar url "فقط http/https"
        text description
        datetime created_at
    }
    ANNOUNCEMENTS {
        bigint id PK
        bigint user_id FK
        varchar source "telegram|eitaa"
        varchar title
        text text
        varchar source_url "پیوند t.me"
        varchar file_type "photo|document"
        varchar file_id "Telegram file_id"
        datetime created_at
    }
    CALENDAR_EVENTS {
        bigint id PK
        bigint user_id FK
        varchar title
        date event_date "روز محلی دانشجو"
        time event_time "ساعت محلی، NULL = تمام‌روز"
        text description
        bool is_done
        datetime created_at
    }
    REMINDERS {
        bigint id PK
        bigint user_id FK
        bigint course_id FK "nullable"
        varchar title
        text description
        datetime reminder_datetime "naive UTC"
        varchar repeat_type "NONE|DAILY|WEEKLY|MONTHLY"
        bool is_active
    }
    REMINDER_NOTIFICATIONS {
        bigint id PK
        bigint reminder_id FK
        varchar alert_offset "AT_TIME|HOURS_1|DAYS_1"
        datetime fire_datetime "naive UTC"
        bool is_sent
        datetime sent_at
    }
    NOTIFICATION_LOGS {
        bigint id PK
        bigint user_id FK "SET NULL"
        varchar notification_type "REMINDER|ANNOUNCEMENT|BROADCAST"
        bigint related_id
        varchar status "SENT|FAILED"
        text error_message
        datetime sent_at
    }
```

### حذف‌ها (ON DELETE)

* `users` حذف شود → برنامه، درس‌ها، نمرات و یادآوری‌ها **CASCADE** می‌شوند.
* `courses` حذف شود → نمره‌هایش CASCADE و `reminders.course_id` می‌شود **SET NULL**.
* `users` حذف شود → `notification_logs.user_id` می‌شود **SET NULL** (لاگ باید بماند).
* `admins` جدولی **کاملاً جدا** از `users` است.

---

## ۵. Migrationها

| نسخه | تغییر |
|---|---|
| `b0e95f17be96` | جدول اولیه: `users`, `admins` |
| `b37bc974aa3e` | `weekly_schedules` (+ ایندکس یکتای «یک برنامهٔ فعال») |
| `75c57cf86947` | `courses` |
| `b3d3d6c5bf65` | `grade_items` |
| `8707cb6e187f` | `reminders`, `reminder_notifications`, `notification_logs` |
| `40bbe636b0de` | `notes` |
| `9872b21078f7` | `university_links` |
| `ded7b70453a2` | `announcements` |
| `8d20aa2d75e9` | `calendar_events` |

```bash
py -3.13 -m alembic upgrade head      # اعمال همهٔ migrationها
py -3.13 -m alembic current           # نسخهٔ فعلی
py -3.13 -m alembic check             # آیا مدل‌ها با دیتابیس mismatch دارند؟
```

---

## ۶. راه‌اندازی

### ۶.۱ پیش‌نیاز

* Python **3.13**
* یک توکن ربات از [@BotFather](https://t.me/BotFather)

### ۶.۲ نصب

```bash
cd student_assistant_bot
py -3.13 -m venv .venv
# ویندوز:
.venv\Scripts\activate      # لینوکس/مک: source .venv/bin/activate
py -3.13 -m pip install -r requirements.txt
```

### ۶.۳ پیکربندی (`.env`)

```bash
cp .env.example .env         # ویندوز: copy .env.example .env
```

| کلید | توضیح |
|---|---|
| `BOT_TOKEN` | توکن از @BotFather (الزامی برای اجرا) |
| `DATABASE_URL` | توسعه: `sqlite:///./data/bot.db` — تولید: `postgresql://USER:PASS@HOST:5432/DB` |
| `GPA_CALCULATOR_URL` | آدرس سایت محاسبهٔ معدل |
| `ADMIN_IDS` | شناسه‌های تلگرام ادمین، جداشده با **کاما** |
| `TIMEZONE` | پیش‌فرض `Asia/Tehran` (برای نمایش/پارس تاریخ) |
| `EITAA_SYNC_URLS` | کانال‌های ایتا برای دریافت خودکار اطلاعیه، جداشده با کاما (خالی = غیرفعال) |
| `EITAA_SYNC_SECONDS` | فاصلهٔ بررسی صفحهٔ کانال‌ها به ثانیه؛ پیش‌فرض `300`، حداقل `60` |
| `LOG_LEVEL` / `LOG_DIR` | سطح و مسیر لاگ |

> تغییر `DATABASE_URL` بین SQLite و PostgreSQL **فقط یک خط** است؛
> `normalize_database_url` پیشوند درایور async (`+aiosqlite` / `+asyncpg`) را
> خودش اضافه می‌کند.

### ۶.۴ اجرا

```bash
py -3.13 run.py --check      # چک محیط بدون نیاز به توکن (دیتابیس + migration)
py -3.13 run.py              # شروع ربات + API مینی‌اپ (یک پروسه)
py -3.13 run.py --bot        # فقط ربات، بدون API
```

`--check` چاپ می‌کند: `database_url`، `timezone`، `admin_ids`، `eitaa_sync`،
وضعیت توکن، اتصال دیتابیس، لیست جدول‌ها و نسخهٔ alembic.

اگر توکن خالی یا placeholder باشد، ربات با پیام راهنمای شفاف متوقف می‌شود.

### ۶.۵ فرانت‌اند Mini App (`frontend/`)

React + TypeScript + Vite + Tailwind؛ فارسی/RTL، فونت وزیرمتن و تم تلگرام:

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173  (پروکسی /api → 127.0.0.1:8000)
npm run build      # خروجی production در frontend/dist
```

در توسعه، Vite درخواست‌های `/api` را به API همان پروسهٔ ربات (پورت ۸۰۰۰)
می‌فرستد؛ ورود با `initData` امضاشدهٔ تلگرام انجام می‌شود.

---

## ۷. تست

```bash
py -3.13 -m pip install -r requirements-dev.txt
py -3.13 -m pytest                 # همه
py -3.13 -m pytest tests/test_reminders.py -q
py -3.13 -m ruff check .           # lint (importها، کد بلااستفاده، الگوهای خطرناک)
```

تست‌ها با **SQLite در حافظه** (`aiosqlite://`) اجرا می‌شوند، هیچ تماس شبکه‌ای
با تلگرام ندارند و هر تست دیتابیس خودش را دارد. تعداد فعلی: **۲۷۹ تست**.
پیکربندی lint در `ruff.toml` است.

در گیت‌هاب هم با هر `push` گردش کار `CI` (فایل `.github/workflows/ci.yml`)
اجرا می‌شود: ruff → alembic → تست‌ها → `run.py --check`؛ وضعیت آن با آیکون
بالای همین صفحه مشخص است.

---

## ۸. استقرار (Deploy)

### ۸.۱ لینوکس با systemd

`/etc/systemd/system/student-bot.service`:

```ini
[Unit]
Description=Student Assistant Bot
After=network-online.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/opt/student_assistant_bot
Environment=ENV_FILE=/opt/student_assistant_bot/.env
ExecStart=/opt/student_assistant_bot/.venv/bin/python run.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now student-bot
journalctl -u student-bot -f        # مشاهدهٔ لاگ
```

### ۸.۲ مهاجرت از SQLite به PostgreSQL

1. `DATABASE_URL=postgresql://USER:PASS@HOST:5432/bot` را در `.env` بگذارید.
2. `py -3.13 -m pip install -r requirements.txt` (درایور `asyncpg` هست).
3. `py -3.13 -m alembic upgrade head`
4. `py -3.13 run.py --check` و سپس `py -3.13 run.py`

### ۸.۳ نکات بهره‌وری

* ربات با **long polling** اجرا می‌شود، پس نیازی به webhook و دامنه نیست.
* **تک‌پروسه** اجرا کنید (چند پروسه همزمان باعث دوباره ارسال شدن یادآوری‌ها
  می‌شود). یک نمونه کافی است.
* `drop_pending_updates=True` هنگام استارت آپدیت‌های قدیمی را نادیده می‌گیرد.
* `.env` را هرگز commit نکنید (در `.gitignore` هست).
* فایل‌های برنامه به‌صورت `file_id` تلگرام ذخیره می‌شوند؛ روی دیسک کپی نمی‌شوند.

---

## ۹. عیب‌یابی

| مشکل | راه‌حل |
|---|---|
| `BOT_TOKEN is empty` | `.env` را بسازید و توکن را بگذارید |
| `alembic = not applied yet` | `py -3.13 -m alembic upgrade head` |
| `alembic check` خطا داد | migration جدید لازم است: `alembic revision --autogenerate -m "..."` |
| `zoneinfo.ZoneInfoNotFoundError` | `py -3.13 -m pip install tzdata` |
| `database is locked` | مطمئن شوید فقط **یک** نمونه از ربات اجراست |
| یادآوری ارسال نشد | لاگ‌های `logs/` و جدول `notification_logs` را ببینید؛ ردیفِ سررسید بعد از ری‌استارت دوباره ارسال می‌شود |

---

## ۱۰. قابلیت‌های تکمیل‌شده

* [x] ثبت/به‌روزرسانی کاربر با هر پیام (`capture_user`) + جداسازی کامل دادهٔ هر دانشجو
* [x] `/start`، `/help` و منوی اصلی دائمی + راهنمای متن‌های ناشناخته
* [x] دکمه‌های منوی اصلی **همیشه** کار می‌کنند — حتی وسط هر ویزارد یا مرحلهٔ انتظار
      (هر مرحله متن‌های آزاد، برچسب‌های منو را استثنا می‌کند و `allow_reentry` دکمهٔ
      همان ویژگی را مستقیم به منوی خودش برمی‌گرداند)
* [x] **ناوبری یک‌کانونه**: با باز شدن هر ویژگی (دکمهٔ منو، `/start`، دکمهٔ معدل)،
      ویژگیِ بازِ قبلی خودکار بسته می‌شود — عکسِ جزوه هرگز به‌جای برنامه هفتگی
      ذخیره نمی‌شود؛ «اطلاعیه‌ها» هم قبل از «جزوه‌ها» ثبت می‌شود تا فورواردِ پست
      به ادعای فایلِ جزوه نیفتد
* [x] 📅 برنامه هفتگی (عکس/سند، آپلود مستقیم از صفحهٔ برنامه، فقط یک نسخهٔ فعال، مشاهده و حذف)
* [x] 📚 درس‌های ترم (ویزارد کامل، اعتبارسنجی واحد `> 0`)
* [x] 📝 نمرات هر درس (نمرهٔ کامل `> 0`، `نمره ≤ نمره کامل`، مجموع و درصد)
* [x] 🧮 دکمهٔ محاسبهٔ معدل (لینک به سایت خارجی)
* [x] 📚 جزوه‌ها/فایل‌ها (دسته‌بندی بر اساس درس + سطل «بدون درس»؛ عکس یا سند + عنوان + توضیح، ارسال مجدد، ویرایش، حذف)
* [x] 🔗 سامانه‌های دانشگاه (نشانک شخصی + دکمهٔ URL + اعتبارسنجی http/https؛
  ۴ سایت مهم دانشگاه به‌صورت ثابت در منو)
* [x] 📢 اطلاعیه‌ها با دو منبع — تلگرام (فوروارد → متن/عکس/سند + پیوند `t.me`) و
  ایتا (متن + لینک `eitaa.com` → پیوند مستقیم)؛ آیکون منبع در لیست و جزئیات؛
  دکمهٔ باز کردن دو کانال رسمی ایتا در منو؛ **دریافت خودکار** پست‌های متنی همان
  کانال‌ها از صفحهٔ عمومی (`EITAA_SYNC_URLS`، هر `EITAA_SYNC_SECONDS` ثانیه)
* [x] ⏰ یادآوری‌ها (تکرار روزانه/هفتگی/ماهانه + ۳ هشدار + توقف/فعال‌سازی)
* [x] سرویس ارسال خودکار یادآوری‌ها (poller پایدار بین ری‌استارت‌ها + لاگ ارسال؛
  همان حلقه همگام‌سازی کانال‌های ایتا را هم اجرا می‌کند)
* [x] 👤 پروفایل دانشجو
* [x] مهاجرت‌های Alembic + تشخیص Drift با `alembic check`
* [x] 📆 تقویم و کارهای آینده (تاریخ شمسی/نسبی + ساعت اختیاری، انجام/بازگردانی، ویرایش، حذف)
* [x] 🛠 پنل ادمین (فقط `ADMIN_IDS`: آمار، کاربران، ارسال همگگانی، همگام‌سازی ایتا)
* [x] ۲۷۹ تست خودکار (بدون شبکه) + `run.py --check` — شامل تست‌های
  جداسازی دادهٔ دانشجوها (IDOR)، سفر کامل کاربر (End-to-End) و ری‌استارت
* [x] 📱 بک‌اند Mini App (FastAPI در همان پروسهٔ ربات + احراز هویت `initData` تلگرام)
* [x] 🎨 اسکلت فرانت‌اند Mini App (React + TS + Vite + Tailwind، RTL فارسی، صفحهٔ اتصال)
* [x] CI روی گیت‌هاب (GitHub Actions با هر push: ruff + alembic + تست‌ها)

## ۱۱. قابلیت‌های نیازمند API / سرویس خارجی

| قابلیت | چه لازم دارد |
|---|---|
| 🧮 محاسبهٔ واقعی معدل | سایت یا سرویس مجزا (الان فقط لینک خارجی می‌دهد) |
| 📢 اطلاعیه‌ها (وارد کردن خودکار از تلگرام) | ربات باید **Admin کانال** باشد؛ روش فعلی (فوروارد دستی) بدون API خارجی کار می‌کند |
| 📢 اطلاعیه‌ها (اتصال واقعی ایتا) | ✅ دریافت خودکار **متن** پست‌ها از صفحهٔ عمومی کانال پیاده شد (بدون API)؛ اما **عکس/ویدیو** و دریافت لحظه‌ای نیاز به Bot API دارد که ایتا ندارد — فقط «برنامه/برنامک» با SDK در `developer.eitaa.com` |
| 📆 تقویم/کارهای آینده | نیازی ندارد — کاملاً از دادهٔ داخلی ساخته می‌شود ✅ |
| 🔗 سامانه‌های دانشگاه | فقط URL؛ نیاز به API ندارد |
| اطلاع‌رسانی از سمت ادمین | نیازمند دسترسی به Bot API (موجود) و اختیار `ADMIN_IDS` |
