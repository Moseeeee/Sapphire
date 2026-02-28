import asyncio
import re
import time
from typing import OrderedDict

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup,
    ChatMemberAdministrator, ChatMemberOwner
)

from handlers.BotAutomaticWork.BotCreatedGlobal import get_bot_for_chat
from handlers.BotAutomaticWork.universal_bot import bot
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import rate_limit_with_cleanup, get_random_text
from handlers.BotAutomaticWork.users.checks.check_users_id import resolve_id
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global

tg_admin_management = Router()

# === ПРАВА ===
MAIN_PERMISSIONS = {
    "can_change_info": "Инфо чата",
    "can_delete_messages": "Удалять сообщения",
    "can_manage_video_chats": "Видеочаты",
    "can_restrict_members": "Блокировать",
    "can_promote_members": "Назначать админов",
    "can_invite_users": "Приглашать",
    "can_pin_messages": "Закреплять",
    "can_manage_topics": "Темы (форум)",
    "is_anonymous": "Анонимность",
}

STORY_PERMISSIONS = {
    "can_post_stories": "Публиковать истории",
    "can_edit_stories": "Редактировать истории",
    "can_delete_stories": "Удалять истории",
}

# Все права (для инициализации)
ALL_PERMISSIONS = {**MAIN_PERMISSIONS, **STORY_PERMISSIONS}

# === УПРАВЛЕНИЕ СЕССИЯМИ ===
admin_sessions = OrderedDict()  # (chat_id, user_id) → dict
MAX_SESSIONS = 100
SESSION_TIMEOUT = 600  # 10 минут


def build_main_keyboard(chat_id: int, user_id: int, rights: dict,
                        bot_rights: ChatMemberAdministrator) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for attr, label in MAIN_PERMISSIONS.items():
        can_grant = getattr(bot_rights, attr, False)
        status = "✅" if rights.get(attr, False) else ("💔" if not can_grant else "❌")
        row.append(InlineKeyboardButton(
            text=f"{status} {label}",
            callback_data=f"toggle:main:{attr}:{chat_id}:{user_id}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Кнопка "Истории"
    story_status = "✅" if any(rights.get(p, False) for p in STORY_PERMISSIONS) else "❌"
    story_can_grant = any(getattr(bot_rights, p, False) for p in STORY_PERMISSIONS)
    if not story_can_grant:
        story_status = "💔"
    buttons.append([InlineKeyboardButton(
        text=f"{story_status} Истории",
        callback_data=f"special:stories:{chat_id}:{user_id}"
    )])

    buttons.append([InlineKeyboardButton(text="✅ Выдать права", callback_data=f"apply:{chat_id}:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_story_keyboard(chat_id: int, user_id: int, rights: dict,
                         bot_rights: ChatMemberAdministrator) -> InlineKeyboardMarkup:
    buttons = []
    for attr, label in STORY_PERMISSIONS.items():
        can_grant = getattr(bot_rights, attr, False)
        status = "✅" if rights.get(attr, False) else ("💔" if not can_grant else "❌")
        buttons.append([InlineKeyboardButton(
            text=f"{status} {label}",
            callback_data=f"toggle:story:{attr}:{chat_id}:{user_id}"
        )])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back:main:{chat_id}:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def cleanup_session(chat_id: int, user_id: int):
    await asyncio.sleep(SESSION_TIMEOUT)
    key = (chat_id, user_id)
    if key in admin_sessions:
        admin_sessions.pop(key, None)


def cleanup_old_sessions():
    while len(admin_sessions) > MAX_SESSIONS:
        key, session = admin_sessions.popitem(last=False)
        if "task" in session:
            session["task"].cancel()


async def is_user_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
    except:
        return False


async def get_target_id(message: Message) -> int | None:
    """Получить ID целевого пользователя из сообщения"""
    # 1. Проверяем reply_to_message
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id

    # 2. Пытаемся получить ID из текста команды (юзернейм, ID или упоминание)
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        mention = args[1]
        return await resolve_id(message, mention)

    # 3. Если ничего не найдено
    return None


# === ОСНОВНАЯ КОМАНДА ===
@tg_admin_management.message(F.text.regexp(re.compile(r'^\+админ\s+', re.IGNORECASE)))
async def cmd_promote_admin(message: Message):

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 41):
        return


    # Получаем ID целевого пользователя
    target_id = await get_target_id(message)
    if not target_id:
        await message.reply('❌ Пользователь не указан. Ответьте на сообщение пользователя или укажите его ID/юзернейм.')
        return

    if message.chat.type not in ("group", "supergroup"):
        return

    requester = message.from_user
    chat_id = message.chat.id

    if target_id == bot.id:
        return await message.reply("❌ Не могу назначить себя.")
    if not await is_user_admin(chat_id, requester.id):
        return await message.reply("❌ Только админы могут назначать админов.")

    actual_bot = get_bot_for_chat(chat_id)
    me = await actual_bot.get_me()
    bot_member = await actual_bot.get_chat_member(chat_id, me.id)
    if not isinstance(bot_member, ChatMemberAdministrator):
        return await message.reply("❌ Бот не админ.")
    if not bot_member.can_promote_members:
        return await message.reply("❌ У бота нет права назначать админов.")

    target_member = await bot.get_chat_member(chat_id, target_id)
    if isinstance(target_member, ChatMemberOwner):
        return await message.reply("❌ Нельзя менять владельца.")

    # Инициализация всех прав
    target_rights = {}
    if isinstance(target_member, ChatMemberAdministrator):
        for attr in ALL_PERMISSIONS:
            target_rights[attr] = getattr(target_member, attr, False)
    else:
        target_rights = {attr: False for attr in ALL_PERMISSIONS}

    key = (chat_id, target_id)
    if key in admin_sessions:
        admin_sessions[key]["task"].cancel()
        admin_sessions.pop(key, None)

    cleanup_task = asyncio.create_task(cleanup_session(chat_id, target_id))
    admin_sessions[key] = {
        "rights": target_rights,
        "bot_rights": bot_member,
        "task": cleanup_task,
        "created_at": time.time(),
    }
    admin_sessions.move_to_end(key)
    cleanup_old_sessions()
    user_link = await user_link_global(target_id)

    await message.reply(
        f"Права для <b>{user_link}</b>:",
        reply_markup=build_main_keyboard(chat_id, target_id, target_rights, bot_member),
        parse_mode='HTML',
        disable_web_page_preview=True
    )


# === КОМАНДА СНЯТИЯ АДМИНА ===
@tg_admin_management.message(lambda m: m.text and m.text.lower().startswith("-админ"))
async def cmd_demote_admin(message: Message):

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 41):
        return

    # Получаем ID целевого пользователя
    target_id = await get_target_id(message)
    if not target_id:
        await message.reply('❌ Пользователь не указан. Ответьте на сообщение пользователя или укажите его ID/юзернейм.')
        return

    if message.chat.type not in ("group", "supergroup"):
        return await message.reply("❌ Только в группах.")

    requester = message.from_user
    chat_id = message.chat.id

    if target_id == bot.id:
        return await message.reply("❌ Не могу снять с себя права.")
    if not await is_user_admin(chat_id, requester.id):
        return await message.reply("❌ Только админы могут снимать админов.")

    actual_bot = get_bot_for_chat(chat_id)
    me = await actual_bot.get_me()
    bot_member = await actual_bot.get_chat_member(chat_id, me.id)
    if not isinstance(bot_member, ChatMemberAdministrator):
        return await message.reply("❌ Бот не админ.")
    if not bot_member.can_promote_members:
        return await message.reply("❌ У бота нет права снимать админов.")

    target_member = await bot.get_chat_member(chat_id, target_id)
    if isinstance(target_member, ChatMemberOwner):
        return await message.reply("❌ Нельзя снять владельца.")

    # Проверяем, является ли цель администратором
    if not isinstance(target_member, ChatMemberAdministrator):
        return await message.reply("❌ Пользователь не является администратором.")

    try:
        # Снимаем права администратора
        await bot.promote_chat_member(
            chat_id=chat_id,
            user_id=target_id,
            can_manage_chat=False,
            can_delete_messages=False,
            can_manage_video_chats=False,
            can_restrict_members=False,
            can_promote_members=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False,
            can_manage_topics=False,
            can_post_stories=False,
            can_edit_stories=False,
            can_delete_stories=False
        )

        user_link = await user_link_global(target_id)
        await message.reply(f"✅ Администратор <b>{user_link}</b> снят с должности!",
                            parse_mode='HTML',
                           disable_web_page_preview=True)
    except TelegramAPIError as e:
        await message.reply(f"❌ Ошибка Telegram: {e.message}")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {str(e)}")


# === ОБРАБОТКА ПЕРЕКЛЮЧЕНИЙ ===
@tg_admin_management.callback_query(F.data.startswith("toggle:"))
@rate_limit_with_cleanup(limit=1)
async def toggle_permission(callback: CallbackQuery):

    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return

    parts = callback.data.split(":")
    if len(parts) != 5 or parts[0] != "toggle":
        return await callback.answer("❌ Ошибка данных.", show_alert=True)

    _, context, attr, chat_id_str, user_id_str = parts
    if context not in ("main", "story"):
        return await callback.answer("❌ Неизвестный контекст.", show_alert=True)

    try:
        chat_id = int(chat_id_str)
        user_id = int(user_id_str)
    except ValueError:
        return await callback.answer("❌ Неверный ID.", show_alert=True)

    key = (chat_id, user_id)
    session = admin_sessions.get(key)
    if not session:
        return await callback.answer("⚠️ Сессия устарела.", show_alert=True)

    bot_rights = session["bot_rights"]
    if not getattr(bot_rights, attr, False):
        return await callback.answer("💔 Бот не может выдать это право.", show_alert=True)

    session["rights"][attr] = not session["rights"][attr]

    markup = build_main_keyboard(chat_id, user_id, session["rights"], bot_rights) if context == "main" \
        else build_story_keyboard(chat_id, user_id, session["rights"], bot_rights)

    await callback.message.edit_reply_markup(reply_markup=markup)
    await callback.answer()


# === МЕНЮ ИСТОРИЙ ===
@tg_admin_management.callback_query(F.data.startswith("special:stories:"))
@rate_limit_with_cleanup(limit=1)
async def show_story_permissions(callback: CallbackQuery):

    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return

    parts = callback.data.split(":")
    if len(parts) != 4:
        return await callback.answer("❌ Ошибка данных.", show_alert=True)
    _, _, chat_id_str, user_id_str = parts
    try:
        chat_id = int(chat_id_str)
        user_id = int(user_id_str)
    except ValueError:
        return await callback.answer("❌ Неверный ID.", show_alert=True)

    key = (chat_id, user_id)
    session = admin_sessions.get(key)
    if not session:
        return await callback.answer("⚠️ Сессия устарела.", show_alert=True)

    await callback.message.edit_reply_markup(
        reply_markup=build_story_keyboard(chat_id, user_id, session["rights"], session["bot_rights"])
    )
    await callback.answer()


# === НАЗАД В ОСНОВНОЕ МЕНЮ ===
@tg_admin_management.callback_query(F.data.startswith("back:main:"))
@rate_limit_with_cleanup(limit=1)
async def back_to_main_permissions(callback: CallbackQuery):

    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return

    parts = callback.data.split(":")
    if len(parts) != 4:
        return await callback.answer("❌ Ошибка данных.", show_alert=True)
    _, _, chat_id_str, user_id_str = parts
    try:
        chat_id = int(chat_id_str)
        user_id = int(user_id_str)
    except ValueError:
        return await callback.answer("❌ Неверный ID.", show_alert=True)

    key = (chat_id, user_id)
    session = admin_sessions.get(key)
    if not session:
        return await callback.answer("⚠️ Сессия устарела.", show_alert=True)

    await callback.message.edit_reply_markup(
        reply_markup=build_main_keyboard(chat_id, user_id, session["rights"], session["bot_rights"])
    )
    await callback.answer()


# === ПРИМЕНЕНИЕ ПРАВ ===
@tg_admin_management.callback_query(F.data.startswith("apply:"))
@rate_limit_with_cleanup(limit=1)
async def apply_admin_rights(callback: CallbackQuery):

    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return

    parts = callback.data.split(":")
    if len(parts) != 3 or parts[0] != "apply":
        return await callback.answer("❌ Ошибка данных.", show_alert=True)

    _, chat_id_str, user_id_str = parts
    try:
        chat_id = int(chat_id_str)
        user_id = int(user_id_str)
    except ValueError:
        return await callback.answer("❌ Неверный ID.", show_alert=True)

    key = (chat_id, user_id)
    session = admin_sessions.get(key)
    if not session:
        return await callback.answer("⚠️ Сессия устарела.", show_alert=True)

    session["task"].cancel()
    admin_sessions.pop(key, None)

    try:
        # Фильтруем только поддерживаемые параметры promote_chat_member
        supported_keys = {
            "can_change_info": "can_change_info",
            "can_delete_messages": "can_delete_messages",
            "can_manage_video_chats": "can_manage_video_chats",
            "can_restrict_members": "can_restrict_members",
            "can_promote_members": "can_promote_members",
            "can_invite_users": "can_invite_users",
            "can_pin_messages": "can_pin_messages",
            "can_manage_topics": "can_manage_topics",
            "can_post_stories": "can_post_stories",
            "can_edit_stories": "can_edit_stories",
            "can_delete_stories": "can_delete_stories",
        }

        # Формируем параметры для promote_chat_member
        promote_params = {
            "chat_id": chat_id,
            "user_id": user_id,
        }

        # Добавляем только те права, которые поддерживаются
        for attr, param_name in supported_keys.items():
            if attr in session["rights"]:
                promote_params[param_name] = session["rights"][attr]

        # is_anonymous нужно передавать отдельно, если это специальное поле
        if "is_anonymous" in session["rights"]:
            promote_params["is_anonymous"] = session["rights"]["is_anonymous"]

        await bot.promote_chat_member(**promote_params)
        await callback.message.edit_text("✅ Права успешно выданы!")
    except TelegramAPIError as e:
        await callback.message.edit_text(f"❌ Telegram: {e.message}")
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {str(e)}")

    await callback.answer()


# === ФОНОВЫЙ СБОРЩИК МУСОРА ===
async def garbage_collector():
    while True:
        await asyncio.sleep(300)  # каждые 5 минут
        now = time.time()
        to_remove = [
            key for key, sess in admin_sessions.items()
            if now - sess.get("created_at", 0) > SESSION_TIMEOUT
        ]
        for key in to_remove:
            if key in admin_sessions:
                admin_sessions[key]["task"].cancel()
                admin_sessions.pop(key, None)