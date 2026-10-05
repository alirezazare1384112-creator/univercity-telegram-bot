"""🔗 سامانه‌های دانشگاه - the student's own bookmark list."""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot.helpers import answer, current_user_id
from app.bot.keyboards.common import BACK, CANCEL, inline_buttons, url_buttons
from app.bot.keyboards.main_menu import LINKS, main_menu_keyboard, menu_buttons_filter
from app.bot.states.link_states import LinkState
from app.database.database import get_session
from app.database.repositories import LinkRepository
from app.utils.validation import validate_short_text, validate_url

logger = logging.getLogger(__name__)

CREATE_FIELDS: tuple[str, ...] = ("title", "url", "description")
EDIT_FIELDS: frozenset[str] = frozenset(CREATE_FIELDS)

PROMPTS: dict[str, str] = {
    "title": "عنوان سامانه را بنویس.\nمثال: آموزش یکپارچه",
    "url": (
        "آدرس سامانه را بفرست.\n"
        "مثال: https://portal.university.ir\n"
        "اگر https ننویسی، خودم اضافه می‌کنم."
    ),
    "description": "توضیح (اختیاری).\nبرای رد شدن دکمه «⏭ رد شد» را بزن.",
}
FIELD_LABELS: dict[str, str] = {
    "title": "عنوان",
    "url": "آدرس",
    "description": "توضیح",
}
FIELD_TO_MODEL: dict[str, str] = {
    "title": "title",
    "url": "url",
    "description": "description",
}

SKIP = "⏭ رد شد"
ADD_LINK = "➕ لینک جدید"
MANAGE = "✏️ مدیریت لینک‌ها"
NO_LINKS = "هنوز لینکی ذخیره نکرده‌ای.\nبا دکمه «➕ لینک جدید» اولین سامانه را اضافه کن."

IMPORTANT_LINKS: tuple[tuple[str, str], ...] = (
    ("🎓 گلستان", "https://golestan.ardakan.ac.ir/home/Default.htm"),
    ("🍽 تغذیه", "https://feed.ardakan.ac.ir/"),
    ("💻 آموزش مجازی", "https://lms.ardakan.ac.ir/"),
    ("📌 سامانه خرده", "https://pa.ardakan.ac.ir/"),
)


# --- text builders ------------------------------------------------------
def _detail_text(link) -> str:
    lines = [
        "🔗 سامانه",
        "",
        f"📌 عنوان: {link.title}",
        f"🌐 آدرس: {link.url}",
        f"📝 توضیح: {link.description or '—'}",
    ]
    return "\n".join(lines)


# --- keyboards ----------------------------------------------------------
def _text_keyboard(field: str):
    rows: list[list[tuple[str, str]]] = []
    if field == "description":
        rows.append([(SKIP, "link:skip")])
    rows.append([(CANCEL, "link:cancel")])
    return inline_buttons(rows)


def _important_rows() -> list[list[tuple[str, str]]]:
    """Two URL buttons per row so the row stays readable on a phone."""
    return [list(IMPORTANT_LINKS[i : i + 2]) for i in range(0, len(IMPORTANT_LINKS), 2)]


def _menu_keyboard(links: list) -> InlineKeyboardMarkup:
    # link rows open directly in the browser (one tap, no callback);
    # the action rows below are ordinary callback buttons.
    open_rows = url_buttons([[(link.title, link.url)] for link in links])
    important = url_buttons(_important_rows())
    actions = inline_buttons(
        ([[(MANAGE, "link:manage")]] if links else [])
        + [[(ADD_LINK, "link:add")], [("🔙 منوی اصلی", "link:exit")]]
    )
    return InlineKeyboardMarkup(
        open_rows.inline_keyboard + important.inline_keyboard + actions.inline_keyboard
    )


def _manage_keyboard(links: list) -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = [
        [(f"✏️ {link.title}", f"link:open:{link.id}"), ("🗑", f"link:delete:{link.id}")]
        for link in links
    ]
    rows.append([(ADD_LINK, "link:add")])
    rows.append([(BACK, "link:list"), ("🔙 منوی اصلی", "link:exit")])
    return inline_buttons(rows)


def _detail_keyboard(link) -> InlineKeyboardMarkup:
    link_id = link.id
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔗 باز کردن", url=link.url)],
            [
                InlineKeyboardButton("✏️ عنوان", callback_data=f"link:edit:{link_id}:title"),
                InlineKeyboardButton("✏️ آدرس", callback_data=f"link:edit:{link_id}:url"),
            ],
            [
                InlineKeyboardButton(
                    "✏️ توضیح", callback_data=f"link:edit:{link_id}:description"
                )
            ],
            [InlineKeyboardButton("🗑 حذف لینک", callback_data=f"link:delete:{link_id}")],
            [
                InlineKeyboardButton("🔙 لیست لینک‌ها", callback_data="link:list"),
                InlineKeyboardButton("🔙 منوی اصلی", callback_data="link:exit"),
            ],
        ]
    )


# --- screens ------------------------------------------------------------
async def _load(user_id: int):
    async with get_session() as session:
        return await LinkRepository(session).list_by_user(user_id)


async def _show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    links = await _load(user_id)
    await answer(
        update,
        context,
        "🔗 سامانه‌های دانشگاه\n\n" + (NO_LINKS if not links else "روی هر کدام بزن تا باز شود:"),
        reply_markup=_menu_keyboard(links),
    )
    return LinkState.MENU


async def links_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("link_wizard", None)
    user_id = await current_user_id(update, context)
    if user_id is None:
        await answer(update, context, "ابتدا /start را بزن.")
        return ConversationHandler.END
    return await _show_menu(update, context, user_id)


async def _show_manage(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    links = await _load(user_id)
    if not links:
        await answer(update, context, NO_LINKS, reply_markup=_menu_keyboard(links))
        return LinkState.MENU
    await answer(
        update,
        context,
        "✏️ مدیریت لینک‌ها\n\nعنوان را برای ویرایش و 🗑 را برای حذف بزن.",
        reply_markup=_manage_keyboard(links),
    )
    return LinkState.MANAGE


async def on_manage_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    return await _show_manage(update, context, user_id)


async def _show_detail(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, link_id: int
):
    async with get_session() as session:
        link = await LinkRepository(session).get(link_id, user_id)

    if link is None:
        await answer(update, context, "این لینک پیدا نشد.")
        return await _show_menu(update, context, user_id)

    context.user_data["link_id"] = link_id
    await answer(update, context, _detail_text(link), reply_markup=_detail_keyboard(link))
    return LinkState.DETAIL


async def on_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    link_id = int((query.data or "").split(":")[-1])
    return await _show_detail(update, context, user_id, link_id)


# --- wizard -------------------------------------------------------------
def _next_field(wizard: dict) -> str | None:
    if wizard["mode"] == "edit":
        return None
    try:
        index = CREATE_FIELDS.index(wizard["field"])
    except ValueError:  # pragma: no cover - defensive
        return None
    return CREATE_FIELDS[index + 1] if index + 1 < len(CREATE_FIELDS) else None


async def _ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    wizard = context.user_data["link_wizard"]
    field = wizard["field"]
    prefix = "✏️ ویرایش\n" if wizard["mode"] == "edit" else "➕ لینک جدید\n"
    await answer(update, context, prefix + PROMPTS[field], reply_markup=_text_keyboard(field))
    return LinkState.WIZARD


async def _start_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE, wizard: dict):
    context.user_data["link_wizard"] = wizard
    return await _ask(update, context)


async def on_add_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    return await _start_wizard(
        update,
        context,
        {"mode": "create", "link_id": None, "field": "title", "data": {}},
    )


async def on_edit_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    _, _, link_id, field = (query.data or "").split(":")
    if field not in EDIT_FIELDS:  # pragma: no cover - defensive
        return LinkState.DETAIL
    return await _start_wizard(
        update,
        context,
        {"mode": "edit", "link_id": int(link_id), "field": field, "data": {}},
    )


async def _advance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wizard = context.user_data["link_wizard"]
    nxt = _next_field(wizard)
    if nxt is None:
        return await _finish(update, context)
    wizard["field"] = nxt
    context.user_data["link_wizard"] = wizard
    return await _ask(update, context)


async def _finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wizard = context.user_data.pop("link_wizard", None) or {}
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END

    data = dict(wizard.get("data") or {})
    link_id: int | None = None
    missing = False

    async with get_session() as session:
        repo = LinkRepository(session)
        if wizard["mode"] == "create":
            link = await repo.create(
                user_id=user_id,
                title=data.get("title", ""),
                url=data.get("url", ""),
                description=data.get("description"),
            )
        else:
            link = await repo.get(int(wizard["link_id"]), user_id)
            if link is None:
                missing = True
            else:
                field = wizard["field"]
                await repo.update(link, **{FIELD_TO_MODEL[field]: data.get(field)})
        if link is not None:
            link_id = link.id

    if missing or link_id is None:
        await answer(update, context, "این لینک دیگر وجود ندارد.")
        return await _show_menu(update, context, user_id)

    verb = "✅ لینک ذخیره شد." if wizard["mode"] == "create" else "✅ تغییرات ذخیره شد."
    await answer(update, context, verb)
    return await _show_detail(update, context, user_id, link_id)


async def on_wizard_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wizard = context.user_data.get("link_wizard")
    user_id = await current_user_id(update, context)
    if wizard is None or user_id is None:
        return ConversationHandler.END

    field = wizard["field"]
    raw = (update.effective_message.text or "").strip()

    if raw in (CANCEL, BACK, "/cancel"):
        context.user_data.pop("link_wizard", None)
        await answer(update, context, "عملیات لغو شد.")
        return await _show_menu(update, context, user_id)

    if field == "title":
        ok, value, error = validate_short_text(
            raw, FIELD_LABELS[field], max_length=64, required=True
        )
    elif field == "url":
        ok, value, error = validate_url(raw, FIELD_LABELS[field])
    else:
        ok, value, error = validate_short_text(
            raw, FIELD_LABELS[field], max_length=200, required=False
        )

    if not ok:
        await answer(update, context, f"⚠️ {error}", reply_markup=_text_keyboard(field))
        return LinkState.WIZARD

    wizard.setdefault("data", {})[field] = value
    context.user_data["link_wizard"] = wizard
    return await _advance(update, context)


async def on_skip_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    wizard = context.user_data.get("link_wizard")
    user_id = await current_user_id(update, context)
    if wizard is None or user_id is None:
        return ConversationHandler.END

    wizard.setdefault("data", {})[wizard["field"]] = None
    context.user_data["link_wizard"] = wizard
    return await _advance(update, context)


# --- delete -------------------------------------------------------------
async def on_delete_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    link_id = int((query.data or "").split(":")[-1])
    await answer(
        update,
        context,
        "این لینک حذف شود؟",
        reply_markup=inline_buttons(
            [
                [("✅ بله، حذف شود", f"link:delete:{link_id}:yes")],
                [(CANCEL, "link:delete:no")],
            ]
        ),
    )
    return LinkState.DETAIL


async def on_delete_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    link_id = int((query.data or "").split(":")[2])

    async with get_session() as session:
        repo = LinkRepository(session)
        link = await repo.get(link_id, user_id)
        deleted = link is not None
        if link is not None:
            await repo.delete(link)

    await answer(
        update, context, "✅ لینک حذف شد." if deleted else "این لینک پیدا نشد."
    )
    return await _show_manage(update, context, user_id)


async def on_delete_cancelled(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    link_id = context.user_data.get("link_id")
    if link_id:
        return await _show_detail(update, context, user_id, int(link_id))
    return await _show_menu(update, context, user_id)


# --- conversation exits -------------------------------------------------
async def exit_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query is not None:
        await update.callback_query.answer()
    context.user_data.pop("link_wizard", None)
    await answer(update, context, "به منوی اصلی برگشتی 👇", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("link_wizard", None)
    await answer(update, context, "عملیات لغو شد.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


def build_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text([LINKS]), links_menu),
            CallbackQueryHandler(links_menu, pattern=r"^link:list$"),
        ],
        states={
            LinkState.MENU: [
                CallbackQueryHandler(on_add_clicked, pattern=r"^link:add$"),
                CallbackQueryHandler(on_manage_clicked, pattern=r"^link:manage$"),
                CallbackQueryHandler(on_open, pattern=r"^link:open:\d+$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^link:exit$"),
                MessageHandler(filters.Text([LINKS]), links_menu),
            ],
            LinkState.MANAGE: [
                CallbackQueryHandler(on_open, pattern=r"^link:open:\d+$"),
                CallbackQueryHandler(on_add_clicked, pattern=r"^link:add$"),
                CallbackQueryHandler(on_delete_confirmed, pattern=r"^link:delete:\d+:yes$"),
                CallbackQueryHandler(on_delete_cancelled, pattern=r"^link:delete:no$"),
                CallbackQueryHandler(on_delete_clicked, pattern=r"^link:delete:\d+$"),
                CallbackQueryHandler(links_menu, pattern=r"^link:list$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^link:exit$"),
                MessageHandler(filters.Text([LINKS]), links_menu),
            ],
            LinkState.DETAIL: [
                CallbackQueryHandler(on_edit_clicked, pattern=r"^link:edit:\d+:\w+$"),
                CallbackQueryHandler(on_delete_confirmed, pattern=r"^link:delete:\d+:yes$"),
                CallbackQueryHandler(on_delete_cancelled, pattern=r"^link:delete:no$"),
                CallbackQueryHandler(on_delete_clicked, pattern=r"^link:delete:\d+$"),
                CallbackQueryHandler(on_manage_clicked, pattern=r"^link:manage$"),
                CallbackQueryHandler(links_menu, pattern=r"^link:list$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^link:exit$"),
                MessageHandler(filters.Text([LINKS]), links_menu),
            ],
            LinkState.WIZARD: [
                CallbackQueryHandler(on_skip_clicked, pattern=r"^link:skip$"),
                CallbackQueryHandler(links_menu, pattern=r"^link:list$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^link:exit$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_buttons_filter(), on_wizard_text),
            ],
        },
        fallbacks=[
            CommandHandler(["start", "cancel"], cancel_conversation),
            MessageHandler(filters.Text([BACK]), cancel_conversation),
            CallbackQueryHandler(cancel_conversation, pattern=r"^link:cancel$"),
        ],
        name="links_conversation",
        persistent=False,
        allow_reentry=True,
    )
