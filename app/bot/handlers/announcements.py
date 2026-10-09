"""📢 اطلاعیه‌ها - announcements saved from Telegram channels.

How it works: the student presses ➕ ذخیره اطلاعیه and then forwards a
channel post to the bot. The bot keeps the text and (for public
channels) a direct ``t.me`` link to the original post.

There are two sources:

* **تلگرام** (default) - a forwarded post (or typed text / photo).
* **ایتا** - content that came from an Eitaa channel: the student pastes
  the message text together with its ``eitaa.com`` link. Eitaa has no
  Telegram-style bot API (see developer.eitaa.com: it only offers web
  mini-apps), so nothing is fetched automatically.

Everything is per-user, like the rest of the bot.
"""

from __future__ import annotations

import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot.helpers import answer, chat_id, current_user_id
from app.bot.keyboards.common import BACK, CANCEL, inline_buttons
from app.bot.keyboards.main_menu import (
    ANNOUNCEMENTS,
    MENU_LABELS,
    main_menu_keyboard,
    menu_buttons_filter,
)
from app.bot.states.announcement_states import AnnouncementState
from app.config import get_settings
from app.database.database import get_session
from app.database.models.announcement import (
    ANNOUNCEMENT_DOCUMENT,
    ANNOUNCEMENT_EITAA,
    ANNOUNCEMENT_PHOTO,
    ANNOUNCEMENT_TELEGRAM,
    MAX_TEXT_LENGTH,
)
from app.database.repositories import AnnouncementRepository, UserChannelRepository
from app.services.channel_sync import normalize_channel_url
from app.utils.datetime_utils import format_jalali

logger = logging.getLogger(__name__)

ADD_POST = "➕ ذخیره اطلاعیه"
SRC_TELEGRAM = "📨 از تلگرام"
SRC_EITAA = "📮 از ایتا"
MY_CHANNELS = "📡 کانال‌های من"
ADD_CHANNEL = "➕ افزودن کانال"
NO_CHANNELS = (
    "هنوز کانالی اضافه نکرده‌ای.\n"
    f"با دکمهٔ «{ADD_CHANNEL}» لینک کانال ایتا یا تلگرامی‌ات را بفرست تا "
    "پست‌های جدیدش خودکار به اطلاعیه‌هایت بیاید."
)
PROMPT_ADD_CHANNEL = (
    "لینک کانال را بفرست:\n"
    "📮 ایتا: https://eitaa.com/namakanel\n"
    "📨 تلگرام: https://t.me/namakanel\n\n"
    "هر چند دقیقه پست‌های جدید کانال خودکار به اطلاعیه‌هایت اضافه می‌شود "
    "و بهت اطلاع داده می‌شود.\n"
    f"برای انصراف «{CANCEL}» را بزن."
)
CHANNEL_SAVED = "✅ کانال «{handle}» اضافه شد.\nتا چند دقیقه پست‌های جدیدش خودکار می‌آید."
CHANNEL_EXISTS = "این کانال قبلاً در لیست تو هست."
CHANNEL_INVALID = (
    "این لینک معتبر نیست. لینک کامل کانال را بفرست "
    "(مثلاً https://t.me/yaad یا https://eitaa.com/yaad)."
)
NO_POSTS = (
    "هنوز اطلاعیه‌ای ذخیره نکرده‌ای.\n"
    f"با دکمه «{ADD_POST}» اولین پیام کانال را اضافه کن."
)
PROMPT_SOURCE = (
    "اطلاعیه از کجا آمده؟\n"
    "تلگرام = فوروارد پیام کانال، ایتا = متن + لینک پیام ایتا."
)
PROMPT_TELEGRAM = (
    "پیام کانال را فوروارد کن تا ذخیره کنم.\n"
    "متن ساده هم قبول است (عکس یا سند با متن توضیحی).\n"
    f"برای انصراف «{CANCEL}» را بزن."
)
PROMPT_EITAA = (
    "متن اطلاعیهٔ ایتا را بفرست؛ اگر لینکش را هم بگذاری "
    "(مثلاً https://eitaa.com/...) دکمهٔ باز کردن می‌سازم.\n"
    f"برای انصراف «{CANCEL}» را بزن."
)
TITLE_FALLBACK = "اطلاعیه"

EITAA_CHANNELS: tuple[tuple[str, str], ...] = (
    ("📢 رسانه دانشگاه", "https://eitaa.com/ArdakanUni_Resaneh"),
    ("📌 چنل آموزش اردکان", "https://eitaa.com/atriardakani"),
)

SOURCE_NAMES: dict[str, str] = {
    ANNOUNCEMENT_TELEGRAM: "تلگرام",
    ANNOUNCEMENT_EITAA: "ایتا",
}

# https://eitaa.com/channel/123  (trailing punctuation is trimmed)
_EITAA_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:eitaa\.com|eitaa\.ir)/[^\s<>()\"']+",
    re.IGNORECASE,
)
# ASCII + Arabic punctuation a pasted link may end with
_TRAILING_PUNCTUATION = ".,;:!?)}]»،؛"


def _first_eitaa_link(text: str | None) -> str | None:
    """First Eitaa link found in the text, if any."""
    match = _EITAA_URL_RE.search(text or "")
    if match is None:
        return None
    return match.group(0).rstrip(_TRAILING_PUNCTUATION)


# --- extraction ---------------------------------------------------------
def _extract_file(message) -> tuple[str, str] | None:
    """``(file_type, file_id)`` of a photo/document message, else ``None``."""
    if message.photo:
        return ANNOUNCEMENT_PHOTO, message.photo[-1].file_id  # Telegram sends several sizes
    if message.document:
        return ANNOUNCEMENT_DOCUMENT, message.document.file_id
    return None


def _origin_info(message) -> tuple[str | None, str | None]:
    """``(source_title, t.me_url)`` of a forwarded message, else ``(None, None)``."""
    origin = getattr(message, "forward_origin", None)
    if origin is None:
        return None, None

    # channel / group the post was forwarded from
    chat = getattr(origin, "chat", None) or getattr(origin, "sender_chat", None)
    if chat is not None:
        title = chat.title or chat.username
        if title:
            username = getattr(chat, "username", None)
            origin_id = getattr(origin, "message_id", None)
            if username and origin_id:
                return title, f"https://t.me/{username}/{origin_id}"
            return title, None

    # forwarded from a person (or a hidden sender)
    user = getattr(origin, "sender_user", None)
    if user is not None:
        name = user.first_name or user.username
        if name:
            return name, None
    name = getattr(origin, "sender_user_name", None)
    if isinstance(name, str) and name.strip():
        return name.strip(), None
    return None, None


def _derive_title(origin_title: str | None, text: str | None) -> str:
    """Channel title, else the first line of the post, else a generic one."""
    if origin_title:
        return origin_title.strip()[:128]
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line[:128]
    return TITLE_FALLBACK


# --- text builders ------------------------------------------------------
def _list_text(announcements: list) -> str:
    if not announcements:
        return NO_POSTS
    tz = get_settings().timezone
    lines = ["📢 اطلاعیه‌های من", ""]
    for index, item in enumerate(announcements, start=1):
        lines.append(
            f"{index}) {item.source_icon} {item.title} "
            f"({format_jalali(item.created_at, tz)[:10]})"
        )
    return "\n".join(lines)


def _header_text(announcement) -> str:
    """Short part - also used as the caption of a photo/document."""
    tz = get_settings().timezone
    lines = [
        "📢 اطلاعیه",
        "",
        f"📌 عنوان: {announcement.title}",
        f"{announcement.source_icon} منبع: "
        f"{SOURCE_NAMES.get(announcement.source, announcement.source)}",
    ]
    if announcement.source_url:
        lines.append(f"🔗 پیوند: {announcement.source_url}")
    lines.append(f"🕒 ذخیره شده: {format_jalali(announcement.created_at, tz)}")
    return "\n".join(lines)


# --- keyboards ----------------------------------------------------------
def _menu_keyboard(announcements: list) -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = [
        [(f"{item.source_icon} {item.title[:48]}", f"ann:open:{item.id}")]
        for item in announcements
    ]
    rows.append([(ADD_POST, "ann:add")])
    rows.append([(MY_CHANNELS, "ann:ch")])
    keyboard = list(inline_buttons(rows).inline_keyboard)
    keyboard.append(
        [InlineKeyboardButton(label, url=url) for label, url in EITAA_CHANNELS]
    )
    keyboard.append([InlineKeyboardButton("🔙 منوی اصلی", callback_data="ann:exit")])
    return InlineKeyboardMarkup(keyboard)


def _detail_keyboard(announcement) -> InlineKeyboardMarkup:
    """Delete/list rows; a source link (t.me / eitaa) opens as a URL button."""
    inline = inline_buttons(
        [
            [("🗑 حذف اطلاعیه", f"ann:delete:{announcement.id}")],
            [("🔙 لیست اطلاعیه‌ها", "ann:list"), ("🔙 منوی اصلی", "ann:exit")],
        ]
    )
    if not announcement.source_url:
        return inline
    url_row = [
        [InlineKeyboardButton("🔗 باز کردن منبع", url=announcement.source_url)]
    ]
    return InlineKeyboardMarkup(url_row + list(inline.inline_keyboard))


def _waiting_keyboard():
    return inline_buttons(
        [
            [(SRC_TELEGRAM, "ann:src:telegram"), (SRC_EITAA, "ann:src:eitaa")],
            [(CANCEL, "ann:cancel")],
        ]
    )


def _channels_keyboard(channels: list) -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = [
        [(f"🗑 {channel.handle[:40]}", f"ann:chdel:{channel.id}")]
        for channel in channels
    ]
    rows.append([(ADD_CHANNEL, "ann:chadd")])
    rows.append(
        [("🔙 لیست اطلاعیه‌ها", "ann:list"), ("🔙 منوی اصلی", "ann:exit")]
    )
    return inline_buttons(rows)


def _add_channel_prompt_keyboard():
    return inline_buttons([[(CANCEL, "ann:chcancel")]])


# --- screens ------------------------------------------------------------
async def _load(user_id: int):
    async with get_session() as session:
        return await AnnouncementRepository(session).list_by_user(user_id)


async def _show_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    announcements = await _load(user_id)
    await answer(
        update,
        context,
        _list_text(announcements),
        reply_markup=_menu_keyboard(announcements),
    )
    return AnnouncementState.MENU


async def announcements_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    context.user_data.pop("ann_source", None)
    user_id = await current_user_id(update, context)
    if user_id is None:
        await answer(update, context, "ابتدا /start را بزن.")
        return ConversationHandler.END
    return await _show_menu(update, context, user_id)


async def _show_detail(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, announcement_id: int
):
    async with get_session() as session:
        announcement = await AnnouncementRepository(session).get(announcement_id, user_id)

    if announcement is None:
        await answer(update, context, "این اطلاعیه پیدا نشد.")
        return await _show_menu(update, context, user_id)

    context.user_data["announcement_id"] = announcement_id
    header = _header_text(announcement)
    body = announcement.text or ""
    keyboard = _detail_keyboard(announcement)
    target = chat_id(update)

    if announcement.file_type == ANNOUNCEMENT_PHOTO:
        try:
            await context.bot.send_photo(
                chat_id=target,
                photo=announcement.file_id,
                caption=header[:1024],  # Telegram's caption limit
                reply_markup=keyboard if not body else None,
            )
        except Exception:
            logger.exception("Could not resend announcement %s", announcement_id)
            await answer(update, context, header + "\n\n" + body, reply_markup=keyboard)
            return AnnouncementState.DETAIL
        if body:
            await answer(update, context, body)
        return AnnouncementState.DETAIL

    if announcement.file_type == ANNOUNCEMENT_DOCUMENT:
        try:
            await context.bot.send_document(
                chat_id=target,
                document=announcement.file_id,
                caption=header[:1024],
                reply_markup=keyboard if not body else None,
            )
        except Exception:
            logger.exception("Could not resend announcement %s", announcement_id)
            await answer(update, context, header + "\n\n" + body, reply_markup=keyboard)
            return AnnouncementState.DETAIL
        if body:
            await answer(update, context, body)
        return AnnouncementState.DETAIL

    await answer(
        update, context, header + "\n\n" + body, reply_markup=keyboard
    )
    return AnnouncementState.DETAIL


async def on_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    announcement_id = int((query.data or "").split(":")[-1])
    return await _show_detail(update, context, user_id, announcement_id)


async def on_add_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask where the announcement comes from (Telegram or Eitaa).

    Telegram is pre-selected so a forward straight after the prompt is
    accepted without pressing a source button first.
    """
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    context.user_data["ann_source"] = ANNOUNCEMENT_TELEGRAM
    await answer(update, context, PROMPT_SOURCE, reply_markup=_waiting_keyboard())
    return AnnouncementState.WAITING


async def on_source_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pick the source: forward from Telegram, or paste Eitaa content."""
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END

    source = ANNOUNCEMENT_EITAA if (query.data or "").endswith("eitaa") else ANNOUNCEMENT_TELEGRAM
    context.user_data["ann_source"] = source
    prompt = PROMPT_EITAA if source == ANNOUNCEMENT_EITAA else PROMPT_TELEGRAM
    await answer(update, context, prompt, reply_markup=_waiting_keyboard())
    return AnnouncementState.WAITING


# --- my channels (per-user subscriptions) --------------------------------
async def _show_channels(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    async with get_session() as session:
        channels = await UserChannelRepository(session).list_by_user(user_id)
    if channels:
        listing = "\n".join(f"{channel.display}" for channel in channels)
        text = (
            "📡 کانال‌های من\n\n"
            f"{listing}\n\n"
            "پست‌های جدید این کانال‌ها خودکار به لیست اطلاعیه‌هایت اضافه "
            "می‌شود و بهت اطلاع داده می‌شود."
        )
    else:
        text = f"📡 کانال‌های من\n\n{NO_CHANNELS}"
    await answer(update, context, text, reply_markup=_channels_keyboard(channels))
    return AnnouncementState.CHANNELS


async def on_channels_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    return await _show_channels(update, context, user_id)


async def on_add_channel_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    await answer(update, context, PROMPT_ADD_CHANNEL, reply_markup=_add_channel_prompt_keyboard())
    return AnnouncementState.CHANNEL_ADD


async def on_channel_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A message arrived while the bot is waiting for the channel link."""
    message = update.effective_message
    user_id = await current_user_id(update, context)
    if user_id is None or message is None:
        return ConversationHandler.END

    raw = (message.text or "").strip()
    if raw in MENU_LABELS:  # navigation always wins over content
        return await announcements_menu(update, context)
    if raw in (CANCEL, BACK, "/cancel"):
        return await _show_channels(update, context, user_id)

    normalized = normalize_channel_url(raw)
    if normalized is None:
        await answer(update, context, CHANNEL_INVALID, reply_markup=_add_channel_prompt_keyboard())
        return AnnouncementState.CHANNEL_ADD

    platform, url, handle = normalized
    async with get_session() as session:
        channel, created = await UserChannelRepository(session).add(
            user_id=user_id, platform=platform, url=url, handle=handle
        )
    await answer(
        update,
        context,
        (CHANNEL_SAVED if created else CHANNEL_EXISTS).format(handle=channel.handle),
    )
    return await _show_channels(update, context, user_id)


async def on_channel_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    channel_id = int((query.data or "").split(":")[-1])
    async with get_session() as session:
        repository = UserChannelRepository(session)
        channel = await repository.get(channel_id, user_id)
        if channel is not None:
            await repository.delete(channel)
    return await _show_channels(update, context, user_id)


async def on_channel_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query is not None:
        await update.callback_query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    return await _show_channels(update, context, user_id)


# --- saving a post ------------------------------------------------------
async def _save(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    *,
    text: str,
    file_info: tuple[str, str] | None,
):
    message = update.effective_message
    origin_title, origin_url = _origin_info(message)
    source = context.user_data.get("ann_source", ANNOUNCEMENT_TELEGRAM)
    if source == ANNOUNCEMENT_EITAA:
        # Eitaa content arrives as typed text; the pasted link is the source
        source_url = _first_eitaa_link(text) or origin_url
    else:
        source_url = origin_url
    title = _derive_title(origin_title, text)

    async with get_session() as session:
        announcement = await AnnouncementRepository(session).create(
            user_id=user_id,
            title=title,
            source=source,
            text=text,
            source_url=source_url,
            file_type=file_info[0] if file_info else None,
            file_id=file_info[1] if file_info else None,
        )
        announcement_id = announcement.id

    await answer(update, context, "✅ اطلاعیه ذخیره شد.")
    return await _show_detail(update, context, user_id, announcement_id)


def _raw_content(message) -> str:
    """Text of the post, capped to what the column accepts."""
    return ((message.text or message.caption or "").strip())[:MAX_TEXT_LENGTH]


async def on_post_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """A text message arrived while the bot is waiting for the post."""
    message = update.effective_message
    user_id = await current_user_id(update, context)
    if user_id is None or message is None:
        return ConversationHandler.END

    raw = _raw_content(message)
    eitaa_mode = context.user_data.get("ann_source") == ANNOUNCEMENT_EITAA

    # a main menu label is navigation, not announcement content
    if raw in MENU_LABELS:
        context.user_data.pop("ann_source", None)
        return await announcements_menu(update, context)
    if raw in (CANCEL, BACK, "/cancel"):
        context.user_data.pop("ann_source", None)
        await answer(update, context, "عملیات لغو شد.")
        return await _show_menu(update, context, user_id)
    if not raw:  # pragma: no cover - filters guarantee some text
        prompt = PROMPT_EITAA if eitaa_mode else PROMPT_TELEGRAM
        await answer(update, context, f"⚠️ {prompt}")
        return AnnouncementState.WAITING

    return await _save(update, context, user_id, text=raw, file_info=None)


async def on_post_file(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """A photo/document arrived while the bot is waiting for the post."""
    message = update.effective_message
    user_id = await current_user_id(update, context)
    if user_id is None or message is None:
        return ConversationHandler.END

    file_info = _extract_file(message)
    if file_info is None:  # pragma: no cover - filters guarantee a file
        return AnnouncementState.WAITING
    return await _save(
        update, context, user_id, text=_raw_content(message), file_info=file_info
    )


# --- delete -------------------------------------------------------------
async def on_delete_clicked(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    announcement_id = int((query.data or "").split(":")[-1])
    await answer(
        update,
        context,
        "این اطلاعیه حذف شود؟",
        reply_markup=inline_buttons(
            [
                [("✅ بله، حذف شود", f"ann:delete:{announcement_id}:yes")],
                [(CANCEL, "ann:delete:no")],
            ]
        ),
    )
    return AnnouncementState.DETAIL


async def on_delete_confirmed(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    announcement_id = int((query.data or "").split(":")[2])

    async with get_session() as session:
        repo = AnnouncementRepository(session)
        announcement = await repo.get(announcement_id, user_id)
        deleted = announcement is not None
        if announcement is not None:
            await repo.delete(announcement)

    await answer(
        update,
        context,
        "✅ اطلاعیه حذف شد." if deleted else "این اطلاعیه پیدا نشد.",
    )
    return await _show_menu(update, context, user_id)


async def on_delete_cancelled(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    announcement_id = context.user_data.get("announcement_id")
    if announcement_id:
        return await _show_detail(update, context, user_id, int(announcement_id))
    return await _show_menu(update, context, user_id)


# --- conversation exits -------------------------------------------------
async def exit_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    if update.callback_query is not None:
        await update.callback_query.answer()
    await answer(update, context, "به منوی اصلی برگشتی 👇", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def cancel_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    if update.callback_query is not None:
        await update.callback_query.answer()
    # clear the whole wizard, including the chosen source: a cancelled
    # "add" must not start the next one in Eitaa mode by accident
    context.user_data.pop("ann_source", None)
    context.user_data.pop("announcement_id", None)
    await answer(update, context, "عملیات لغو شد.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


def build_conversation() -> ConversationHandler:
    file_filter = filters.PHOTO | filters.Document.ALL
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text([ANNOUNCEMENTS]), announcements_menu),
            CallbackQueryHandler(announcements_menu, pattern=r"^ann:list$"),
        ],
        states={
            AnnouncementState.MENU: [
                CallbackQueryHandler(on_add_clicked, pattern=r"^ann:add$"),
                CallbackQueryHandler(on_channels_clicked, pattern=r"^ann:ch$"),
                CallbackQueryHandler(on_open, pattern=r"^ann:open:\d+$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^ann:exit$"),
                MessageHandler(filters.Text([ANNOUNCEMENTS]), announcements_menu),
            ],
            AnnouncementState.WAITING: [
                CallbackQueryHandler(on_source_clicked, pattern=r"^ann:src:"),
                CallbackQueryHandler(on_open, pattern=r"^ann:open:\d+$"),
                CallbackQueryHandler(announcements_menu, pattern=r"^ann:list$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^ann:exit$"),
                # pressing another menu label stops the wait (navigation wins)
                MessageHandler(filters.Text([ANNOUNCEMENTS]), announcements_menu),
                MessageHandler(file_filter & ~filters.COMMAND, on_post_file),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_buttons_filter(), on_post_text),
            ],
            AnnouncementState.CHANNELS: [
                CallbackQueryHandler(on_channels_clicked, pattern=r"^ann:ch$"),
                CallbackQueryHandler(on_add_channel_clicked, pattern=r"^ann:chadd$"),
                CallbackQueryHandler(on_channel_delete, pattern=r"^ann:chdel:\d+$"),
                CallbackQueryHandler(announcements_menu, pattern=r"^ann:list$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^ann:exit$"),
                MessageHandler(filters.Text([ANNOUNCEMENTS]), announcements_menu),
            ],
            AnnouncementState.CHANNEL_ADD: [
                CallbackQueryHandler(on_channel_cancel, pattern=r"^ann:chcancel$"),
                CallbackQueryHandler(announcements_menu, pattern=r"^ann:list$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^ann:exit$"),
                MessageHandler(filters.Text([ANNOUNCEMENTS]), announcements_menu),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_buttons_filter(), on_channel_text),
            ],
            AnnouncementState.DETAIL: [
                CallbackQueryHandler(on_delete_confirmed, pattern=r"^ann:delete:\d+:yes$"),
                CallbackQueryHandler(on_delete_cancelled, pattern=r"^ann:delete:no$"),
                CallbackQueryHandler(on_delete_clicked, pattern=r"^ann:delete:\d+$"),
                CallbackQueryHandler(on_open, pattern=r"^ann:open:\d+$"),
                CallbackQueryHandler(announcements_menu, pattern=r"^ann:list$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^ann:exit$"),
                MessageHandler(filters.Text([ANNOUNCEMENTS]), announcements_menu),
            ],
        },
        fallbacks=[
            CommandHandler(["start", "cancel"], cancel_conversation),
            MessageHandler(filters.Text([BACK]), cancel_conversation),
            CallbackQueryHandler(cancel_conversation, pattern=r"^ann:cancel$"),
        ],
        name="announcements_conversation",
        persistent=False,
        allow_reentry=True,
    )
