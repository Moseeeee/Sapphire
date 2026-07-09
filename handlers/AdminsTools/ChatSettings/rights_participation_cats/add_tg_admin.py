import asyncio
import re
import time
import inspect
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
from BotAutomaticWork.users.checks.check_UserId.check_users_id import resolve_id
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global

tg_admin_management = Router()

# === АКТУАЛЬНЫЕ ПРАВА АДМИНИСТРАТОРОВ ===
MAIN_PERMISSIONS = {
    "can_manage_chat": "Управление чатом",
    "can_delete_messages": "Удалять сообщения",
    "can_manage_video_chats": "Видеочаты",
    "can_restrict_members": "Блокировать",
    "can_promote_members": "Назначать админов",
    "can_change_info": "Инфо чата",
    "can_invite_users": "Приглашать",
    "can_pin_messages": "Закреплять",
    "can_manage_topics": "Темы (форум)",
    "can_manage_tags": "Теги участников",  # Возвращено на базу 🏷️
    "is_anonymous": "Анонимность",
}

STORY_PERMISSIONS = {
    "can_post_stories": "Публиковать истории",
    "can_edit_stories": "Редактировать истории",
    "can_delete_stories": "Удалять истории",
}

ALL_PERMISSIONS = {**MAIN_PERMISSIONS, **STORY_PERMISSIONS}

# === УПРАВЛЕНИЕ СЕССИЯМИ ===
admin_sessions = OrderedDict()  # (chat_id, user_id) → dict
MAX_SESSIONS = 100
SESSION_TIMEOUT = 600  # 10 минут


def build_main_keyboard(user_id: int, rights: dict, bot_rights: ChatMemberAdministrator) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for attr, label in MAIN_PERMISSIONS.items():
        can_grant = getattr(bot_rights, attr, False)
        status = "✅" if rights.get(attr, False) else ("💔" if not can_grant else "❌")
        row.append(InlineKeyboardButton(
            text=f"{status} {label}",
            callback_data=f"a_tgl:m:{attr}:{user_id}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    story_status = "✅" if any(rights.get(p, False) for p in STORY_PERMISSIONS) else "❌"
    story_can_grant = any(getattr(bot_rights, p, False) for p in STORY_PERMISSIONS)
    if not story_can_grant:
        story_status = "💔"

    buttons.append([InlineKeyboardButton(
        text=f"{story_status} Истории",
        callback_data=f"a_str:{user_id}"
    )])

    buttons.append([InlineKeyboardButton(text="✅ Выдать права", callback_data=f"a_aply:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_story_keyboard(user_id: int, rights: dict, bot_rights: ChatMemberAdministrator) -> InlineKeyboardMarkup:
    buttons = []
    for attr, label in STORY_PERMISSIONS.items():
        can_grant = getattr(bot_rights, attr, False)
        status = "✅" if rights.get(attr, False) else ("💔" if not can_grant else "❌")
        buttons.append([InlineKeyboardButton(
            text=f"{status} {label}",
            callback_data=f"a_tgl:s:{attr}:{user_id}"
        )])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"a_bak:{user_id}")])
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


async def get_target_id(message: Message) -> tuple[int | None, str | None]:
    """
    Анатомически точный парсер. Находит юзернейм или ID в любой точке текста,
    изолирует его от префикса и корректно обрабатывает реплаи.
    """
    args = message.text.split()
    if not args:
        return None, None

    args.pop(0)  # Удаляем саму команду (+админ или -админ)

    user_id = None
    user_arg = None

    # Шаг 1: Ищем среди ВСЕХ аргументов тот, который выглядит как юзернейм или ID
    for arg in args:
        if arg.startswith('@') or (arg.isdigit() and len(arg) > 5):
            user_arg = arg
            args.remove(arg)  # Вырезаем юзернейм/ID из списка аргументов префикса
            break

    # Шаг 2: Определяем целевой ID пользователя
    if user_arg:
        # Если юзернейм/ID явно написан в тексте — резолвим его (он в приоритете)
        user_id = await resolve_id(message, user_arg)
    elif message.reply_to_message and message.reply_to_message.from_user:
        # Если в тексте юзера нет, но есть реплай — берем из реплая
        user_id = message.reply_to_message.from_user.id

    # Шаг 3: Всё, что осталось в аргументах (до или после юзернейма) — это чистый префикс
    prefix = " ".join(args).strip() if args else None

    return user_id, prefix


@tg_admin_management.message(F.text.regexp(re.compile(r'^\+админ\s+', re.IGNORECASE)))
async def cmd_promote_admin(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 41):
        return

    if message.chat.type not in ("group", "supergroup"):
        return

    target_id, prefix = await get_target_id(message)
    if not target_id:
        return await message.reply(
            'Пользователь не найден или не указан. Ответьте на сообщение или укажите через @username.')

    chat_id = message.chat.id
    actual_bot = get_bot_for_chat(chat_id)

    me = await actual_bot.get_me()
    if int(target_id) == int(me.id):
        return await message.reply("Не могу назначить самого бота администратором.")

    bot_member = await actual_bot.get_chat_member(chat_id, me.id)
    if not isinstance(bot_member, ChatMemberAdministrator):
        return await message.reply("Бот не является администратором в этом чате.")
    if not bot_member.can_promote_members:
        return await message.reply("У бота нет права «Назначение администраторов».")

    target_member = await actual_bot.get_chat_member(chat_id, target_id)
    if isinstance(target_member, ChatMemberOwner):
        return await message.reply("Нельзя изменять права владельца чата.")

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
        "prefix": prefix,
    }
    admin_sessions.move_to_end(key)
    cleanup_old_sessions()
    user_link = await user_link_global(target_id)

    admin_title = f"\n🏷 Будет установлен префикс: <b>{prefix}</b>" if prefix else ""
    await message.reply(
        f"Настройка прав администратора для <b>{user_link}</b>:{admin_title}",
        reply_markup=build_main_keyboard(target_id, target_rights, bot_member),
        parse_mode='HTML',
        disable_web_page_preview=True
    )


@tg_admin_management.message(lambda m: m.text and m.text.lower().startswith("-админ"))
async def cmd_demote_admin(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 41):
        return

    if message.chat.type not in ("group", "supergroup"):
        return

    target_id, prefix = await get_target_id(message)
    if not target_id:
        return await message.reply('Пользователь не найден. Ответьте на сообщение или укажите через @.')

    chat_id = message.chat.id
    actual_bot = get_bot_for_chat(chat_id)

    me = await actual_bot.get_me()
    if int(target_id) == int(me.id):
        return await message.reply("Бот не может снять права сам с себя.")

    bot_member = await actual_bot.get_chat_member(chat_id, me.id)
    if not isinstance(bot_member, ChatMemberAdministrator):
        return await message.reply("Бот не админ.")
    if not bot_member.can_promote_members:
        return await message.reply("У бота нет прав разжаловать администраторов.")

    target_member = await actual_bot.get_chat_member(chat_id, target_id)
    if isinstance(target_member, ChatMemberOwner):
        return await message.reply("Нельзя снять создателя чата.")

    if not isinstance(target_member, ChatMemberAdministrator):
        return await message.reply("Gользователь не является администратором.")

    try:
        sig = inspect.signature(actual_bot.promote_chat_member)
        demote_params = {"chat_id": chat_id, "user_id": target_id}

        for param in sig.parameters.keys():
            if param.startswith("can_") or param == "is_anonymous":
                demote_params[param] = False

        await actual_bot.promote_chat_member(**demote_params)

        user_link = await user_link_global(target_id)
        await message.reply(f"✅ Администратор <b>{user_link}</b> успешно разжалован!",
                            parse_mode='HTML',
                            disable_web_page_preview=True)
    except TelegramAPIError as e:
        await message.reply(f"⚠️ Ошибка Telegram API: {e.message}")
    except Exception as e:
        await message.reply(f"⚠️ Ошибка: {str(e)}")


@tg_admin_management.message(F.text.regexp(re.compile(r'^\+админ$', re.IGNORECASE)))
async def cmd_promote_admin_reply_only(message: Message):
    await cmd_promote_admin(message)


@tg_admin_management.message(F.text.regexp(re.compile(r'^\-админ$', re.IGNORECASE)))
async def cmd_demote_admin_reply_only(message: Message):
    await cmd_demote_admin(message)


@tg_admin_management.callback_query(F.data.startswith("a_tgl:"))
@rate_limit_with_cleanup(limit=1)
async def toggle_admin_permission(callback: CallbackQuery):
    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return

    parts = callback.data.split(":")
    if len(parts) != 4:
        return await callback.answer("Ошибка данных сессии.", show_alert=True)

    _, context, attr, user_id_str = parts
    chat_id = callback.message.chat.id

    try:
        user_id = int(user_id_str)
    except ValueError:
        return await callback.answer("Неверный ID.", show_alert=True)

    key = (chat_id, user_id)
    session = admin_sessions.get(key)
    if not session:
        return await callback.answer("Сессия устарела, вызовите команду заново.", show_alert=True)

    bot_rights = session.get("bot_rights")
    if not bot_rights or not getattr(bot_rights, attr, False):
        return await callback.answer("💔 Бот сам не имеет этого права, поэтому не может делегировать его.",
                                     show_alert=True)

    session["rights"][attr] = not session["rights"][attr]

    markup = build_main_keyboard(user_id, session["rights"], session["bot_rights"]) if context == "m" \
        else build_story_keyboard(user_id, session["rights"], session["bot_rights"])

    await callback.message.edit_reply_markup(reply_markup=markup)
    await callback.answer()


@tg_admin_management.callback_query(F.data.startswith("a_str:"))
@rate_limit_with_cleanup(limit=1)
async def show_story_permissions(callback: CallbackQuery):
    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return

    parts = callback.data.split(":")
    _, user_id_str = parts
    chat_id = callback.message.chat.id
    try:
        user_id = int(user_id_str)
    except ValueError:
        return await callback.answer("Неверный ID.", show_alert=True)

    key = (chat_id, user_id)
    session = admin_sessions.get(key)
    if not session:
        return await callback.answer("Сессия устарела.", show_alert=True)

    await callback.message.edit_reply_markup(
        reply_markup=build_story_keyboard(user_id, session["rights"], session["bot_rights"])
    )
    await callback.answer()


@tg_admin_management.callback_query(F.data.startswith("a_bak:"))
@rate_limit_with_cleanup(limit=1)
async def back_to_main_permissions(callback: CallbackQuery):
    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return

    parts = callback.data.split(":")
    _, user_id_str = parts
    chat_id = callback.message.chat.id
    try:
        user_id = int(user_id_str)
    except ValueError:
        return await callback.answer("Неверный ID.", show_alert=True)

    key = (chat_id, user_id)
    session = admin_sessions.get(key)
    if not session:
        return await callback.answer("Сессия устарела.", show_alert=True)

    await callback.message.edit_reply_markup(
        reply_markup=build_main_keyboard(user_id, session["rights"], session["bot_rights"])
    )
    await callback.answer()


@tg_admin_management.callback_query(F.data.startswith("a_aply:"))
@rate_limit_with_cleanup(limit=1)
async def apply_admin_rights(callback: CallbackQuery):
    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return

    parts = callback.data.split(":")
    _, user_id_str = parts
    chat_id = callback.message.chat.id
    try:
        user_id = int(user_id_str)
    except ValueError:
        return await callback.answer("Неверный ID.", show_alert=True)

    key = (chat_id, user_id)
    session = admin_sessions.get(key)
    if not session:
        return await callback.answer("Сессия устарела.", show_alert=True)

    prefix = session.get("prefix")
    session["task"].cancel()
    admin_sessions.pop(key, None)

    actual_bot = get_bot_for_chat(chat_id)

    try:
        user_link = await user_link_global(user_id)

        # Шаг 1: Узнаем текущее состояние админа в Telegram перед изменениями
        try:
            current_member = await actual_bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            current_status = current_member.status
            # Извлекаем старый префикс, если он есть
            current_prefix = getattr(current_member, "custom_title", None)
        except Exception:
            current_status = "member"
            current_prefix = None

        # РЕШЕНИЕ БАГА 2: Если новый префикс не задан, но у юзера ОН УЖЕ БЫЛ —
        # берем старый префикс, чтобы Telegram не затёр его при обновлении прав!
        if not prefix and current_prefix:
            prefix = current_prefix

        # Шаг 2: Формируем параметры для изменения прав (передаем ВСЕ из сессии, и True, и False)
        promote_params = {"chat_id": chat_id, "user_id": user_id}
        for attr, value in session["rights"].items():
            promote_params[attr] = value

        # Наш хак для «пустой» админки ради префикса
        has_any_true_rights = any(val for k, val in promote_params.items() if k not in ["chat_id", "user_id"] and val is True)
        if prefix and not has_any_true_rights and current_status != "administrator":
            promote_params["can_manage_chat"] = True

        # РЕШЕНИЕ БАГА 1: Отказываемся от inspect.signature. Передаем параметры напрямую!
        # Если ваша версия aiogram не знает какой-то новый параметр, мы поймаем TypeError,
        # удалим только его и попробуем снова. Теперь измененные (и выключенные) права применятся железно.
        while True:
            try:
                await actual_bot.promote_chat_member(**promote_params)
                break
            except TypeError as e:
                err_msg = str(e)
                match = re.search(r"argument '(\w+)'", err_msg)
                if match:
                    bad_arg = match.group(1)
                    if bad_arg in promote_params:
                        promote_params.pop(bad_arg)
                        continue
                raise e  # Если ошибка не связана с именами аргументов, выбрасываем её дальше

        # Шаг 3: Применяем префикс (новый или сохраненный старый)
        if prefix:
            await asyncio.sleep(0.4)  # Даем Telegram обновить базу данных
            await actual_bot.set_chat_administrator_custom_title(
                chat_id=chat_id, user_id=user_id, custom_title=prefix
            )
            await callback.message.edit_text(
                f"✅ Права администратора <b>{user_link}</b> успешно обновлены.\n🏷 Префикс: «<b>{prefix}</b>»",
                parse_mode='HTML', disable_web_page_preview=True
            )
        else:
            await callback.message.edit_text(
                f"✅ Права администратора для <b>{user_link}</b> успешно обновлены!",
                parse_mode='HTML', disable_web_page_preview=True
            )

    except TelegramAPIError as e:
        await callback.message.edit_text(f"❌ Ошибка Telegram API: {e.message}")
    except Exception as e:
        await callback.message.edit_text(f"❌ Внутренняя ошибка: {str(e)}")

    await callback.answer()


async def garbage_collector():
    while True:
        await asyncio.sleep(300)
        now = time.time()
        to_remove = [
            key for key, sess in admin_sessions.items()
            if now - sess.get("created_at", 0) > SESSION_TIMEOUT
        ]
        for key in to_remove:
            if key in admin_sessions:
                admin_sessions[key]["task"].cancel()
                admin_sessions.pop(key, None)