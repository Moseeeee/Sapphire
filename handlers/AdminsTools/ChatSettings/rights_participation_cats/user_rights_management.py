import asyncio
import re
import time
from typing import OrderedDict

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup,
    ChatMemberAdministrator, ChatMemberOwner,
    ChatPermissions, ChatMemberRestricted
)

from handlers.BotAutomaticWork.BotCreatedGlobal import get_bot_for_chat
from handlers.BotAutomaticWork.universal_bot import bot
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import rate_limit_with_cleanup, get_random_text
from BotAutomaticWork.users.checks.check_UserId.check_users_id import resolve_id
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global

tg_user_rights_management = Router()

# === СИСТЕМНЫЕ ПРАВА TELEGRAM API (Для загрузки из базы данных) ===
ALL_TELEGRAM_PERMISSIONS = [
    "can_send_messages", "can_send_audios", "can_send_documents", "can_send_photos",
    "can_send_videos", "can_send_video_notes", "can_send_voice_notes", "can_send_polls",
    "can_send_other_messages", "can_add_web_page_previews", "can_react_to_messages",
    "can_edit_tag", "can_change_info", "can_invite_users", "can_pin_messages", "can_manage_topics"
]

# === МЕДИА-СПЕКТР (Объединяем в один пакет для стабильной блокировки) ===
MEDIA_KEYS = [
    "can_send_audios", "can_send_documents", "can_send_photos", "can_send_videos",
    "can_send_video_notes", "can_send_voice_notes", "can_send_polls",
    "can_send_other_messages", "can_react_to_messages"
]

# === ТО, ЧТО ВИДИТ АДМИНИСТРАТОР В ИНТЕРФЕЙСЕ ===
DISPLAY_PERMISSIONS = {
    "can_send_messages": "Отправка сообщений",
    "send_media": "Вся медиатека",  # Наша супер-кнопка 📦
    "can_add_web_page_previews": "Превью ссылок",
    "can_edit_tag": "Изменение своего тега",
    "can_change_info": "Изменение инфо чата",
    "can_invite_users": "Приглашение участников",
    "can_pin_messages": "Закрепление сообщений",
    "can_manage_topics": "Управление темами",
}

# === УПРАВЛЕНИЕ СЕССИЯМИ ===
user_sessions = OrderedDict()
MAX_SESSIONS = 100
SESSION_TIMEOUT = 600


def build_chat_keyboard(user_id: int, rights: dict) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for attr, label in DISPLAY_PERMISSIONS.items():
        # Особая логика для супер-кнопки медиа: если ХОТЯ БЫ ОДНО медиа разрешено, кнопка горит ✅
        if attr == "send_media":
            is_allowed = all(rights.get(k, True) for k in MEDIA_KEYS)
        else:
            is_allowed = rights.get(attr, True)

        status = "✅" if is_allowed else "❌"
        row.append(InlineKeyboardButton(
            text=f"{status} {label}",
            callback_data=f"u_tgl:{attr}:{user_id}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="🔒 Применить ограничения", callback_data=f"u_aply:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def cleanup_session(chat_id: int, user_id: int):
    await asyncio.sleep(SESSION_TIMEOUT)
    key = (chat_id, user_id)
    if key in user_sessions:
        user_sessions.pop(key, None)


def cleanup_old_sessions():
    while len(user_sessions) > MAX_SESSIONS:
        key, session = user_sessions.popitem(last=False)
        if "task" in session:
            session["task"].cancel()


async def get_target_id(message: Message) -> tuple[int | None, str | None]:
    args = message.text.split()
    if not args:
        return None, None
    args.pop(0)
    user_id = None
    user_arg = None

    for arg in args:
        if arg.startswith('@') or (arg.isdigit() and len(arg) > 5):
            user_arg = arg
            break

    if user_arg:
        user_id = await resolve_id(message, user_arg)
    elif message.reply_to_message and message.reply_to_message.from_user:
        user_id = message.reply_to_message.from_user.id

    return user_id, None


@tg_user_rights_management.message(F.text.regexp(re.compile(r'^\+права\s+', re.IGNORECASE)))
async def cmd_restrict_user_menu(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 99):
        return

    if message.chat.type not in ("group", "supergroup"):
        return

    target_id, _ = await get_target_id(message)
    if not target_id:
        return await message.reply(
            'Пользователь не указан. Ответьте на сообщение пользователя или укажите его через @username.')

    chat_id = message.chat.id
    actual_bot = get_bot_for_chat(chat_id)

    me = await actual_bot.get_me()
    if int(target_id) == int(me.id):
        return await message.reply("Нельзя настраивать права самому боту.")

    bot_member = await actual_bot.get_chat_member(chat_id, me.id)
    if not isinstance(bot_member, ChatMemberAdministrator) or not bot_member.can_restrict_members:
        return await message.reply("У бота нет прав на ограничение участников (Блокировать).")

    target_member = await actual_bot.get_chat_member(chat_id, target_id)
    if isinstance(target_member, (ChatMemberAdministrator, ChatMemberOwner)):
        return await message.reply("Нельзя ограничить администратора или создателя чата.")

    target_rights = {}

    # Загружаем реальные индивидуальные права
    if isinstance(target_member, ChatMemberRestricted):
        for attr in ALL_TELEGRAM_PERMISSIONS:
            target_rights[attr] = getattr(target_member, attr, True)
    else:
        try:
            chat_info = await actual_bot.get_chat(chat_id)
            chat_perms = chat_info.permissions
        except Exception:
            chat_perms = None

        for attr in ALL_TELEGRAM_PERMISSIONS:
            if chat_perms and hasattr(chat_perms, attr):
                target_rights[attr] = getattr(chat_perms, attr, True)
            else:
                target_rights[attr] = True

    key = (chat_id, target_id)
    if key in user_sessions:
        user_sessions[key]["task"].cancel()
        user_sessions.pop(key, None)

    cleanup_task = asyncio.create_task(cleanup_session(chat_id, target_id))
    user_sessions[key] = {
        "rights": target_rights,
        "task": cleanup_task,
        "created_at": time.time(),
    }
    user_sessions.move_to_end(key)
    cleanup_old_sessions()
    user_link = await user_link_global(target_id)

    await message.reply(
        f"Настройка разрешений для <b>{user_link}</b>:",
        reply_markup=build_chat_keyboard(target_id, target_rights),
        parse_mode='HTML',
        disable_web_page_preview=True
    )


@tg_user_rights_management.message(F.text.regexp(re.compile(r'^\+права$', re.IGNORECASE)))
async def cmd_restrict_user_reply_only(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 99):
        return
    await cmd_restrict_user_menu(message)


@tg_user_rights_management.callback_query(F.data.startswith("u_tgl:"))
@rate_limit_with_cleanup(limit=1)
async def toggle_user_permission(callback: CallbackQuery):
    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        return await callback.answer("Ошибка данных.", show_alert=True)

    _, attr, user_id_str = parts
    chat_id = callback.message.chat.id

    try:
        user_id = int(user_id_str)
    except ValueError:
        return await callback.answer("Неверный идентификатор.", show_alert=True)

    key = (chat_id, user_id)
    session = user_sessions.get(key)
    if not session:
        return await callback.answer("Сессия устарела.", show_alert=True)

    # ЛОГИКА ОДНОЙ КНОПКИ ДЛЯ МЕДИА:
    if attr == "send_media":
        # Проверяем текущее глобальное состояние пакета медиа
        current_media_state = all(session["rights"].get(k, True) for k in MEDIA_KEYS)
        new_state = not current_media_state
        # Переключаем СРАЗУ ВЕСЬ список медиа-прав в одну сторону
        for k in MEDIA_KEYS:
            session["rights"][k] = new_state
    else:
        # Для обычных одиночных кнопок
        session["rights"][attr] = not session["rights"][attr]

    markup = build_chat_keyboard(user_id, session["rights"])
    await callback.message.edit_reply_markup(reply_markup=markup)
    await callback.answer()


@tg_user_rights_management.callback_query(F.data.startswith("u_aply:"))
@rate_limit_with_cleanup(limit=1)
async def apply_user_rights(callback: CallbackQuery):
    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return

    parts = callback.data.split(":")
    if len(parts) != 2:
        return await callback.answer("Ошибка данных.", show_alert=True)

    _, user_id_str = parts
    chat_id = callback.message.chat.id

    try:
        user_id = int(user_id_str)
    except ValueError:
        return await callback.answer("Неверный идентификатор.", show_alert=True)

    key = (chat_id, user_id)
    session = user_sessions.get(key)
    if not session:
        return await callback.answer("Сессия устарела.", show_alert=True)

    session["task"].cancel()
    user_sessions.pop(key, None)

    actual_bot = get_bot_for_chat(chat_id)

    try:
        user_link = await user_link_global(user_id)

        current_member = await actual_bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if current_member.status in ["administrator", "creator"]:
            await callback.message.edit_text(
                f"Не удалось применить ограничения. <b>{user_link}</b> теперь является администратором чата.",
                parse_mode='HTML'
            )
            return

        permissions_dict = session["rights"].copy()
        chat_permissions = None

        while True:
            try:
                chat_permissions = ChatPermissions(**permissions_dict)
                break
            except TypeError as e:
                err_msg = str(e)
                match = re.search(r"keyword argument '(\w+)'|argument '(\w+)'", err_msg)
                if match:
                    bad_arg = match.group(1) or match.group(2)
                    if bad_arg in permissions_dict:
                        permissions_dict.pop(bad_arg)
                        continue
                raise e

        await actual_bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=chat_permissions,
            until_date=0
        )

        await callback.message.edit_text(
            f"✅ Исключения и ограничения для пользователя <b>{user_link}</b> успешно сохранены!",
            parse_mode='HTML', disable_web_page_preview=True
        )

    except TelegramAPIError as e:
        await callback.message.edit_text(f"⚠️ Telegram API: {e.message}")
    except Exception as e:
        await callback.message.edit_text(f"⚠️ Ошибка: {str(e)}")

    await callback.answer()


async def garbage_collector():
    while True:
        await asyncio.sleep(300)
        now = time.time()
        to_remove = [
            key for key, sess in user_sessions.items()
            if now - sess.get("created_at", 0) > SESSION_TIMEOUT
        ]
        for key in to_remove:
            if key in user_sessions:
                user_sessions[key]["task"].cancel()
                user_sessions.pop(key, None)