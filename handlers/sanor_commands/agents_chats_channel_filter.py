import re
from typing import OrderedDict

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup,
    ChatMemberAdministrator, ChatMemberOwner
)

from BotAutomaticWork.Gonfig.config import sanor_ID
from BotAutomaticWork.users.checks.check_UserId.check_users_id import resolve_id
# Импорты утилит из вашей структуры проекта
from handlers.BotAutomaticWork.BotCreatedGlobal import get_bot_for_chat
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import rate_limit_with_cleanup, get_random_text
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global

tg_channels_links_management = Router()

# === СТАТИЧЕСКИЙ СПИСОК КАНАЛОВ И ЧАТОВ ===
# Пропишите сюда ID ваших каналов и чатов (через запятую)
channels_and_chats = (-1002315959104, -1003346491683, -1003582454136, -1003469470290, -1002279817519)

# === СЕССИИ НАСТРОЙКИ ПРАВ В КАНАЛАХ ===
channel_admin_sessions = OrderedDict()  # (chat_id, user_id) → dict
MAX_SESSIONS = 100
SESSION_TIMEOUT = 600  # 10 минут

# === ВСЕ ПРАВА АДМИНИСТРАТОРА (Включая специфичные для каналов) ===
CHANNEL_PERMISSIONS = {
    "can_post_messages": "Публикация постов",
    "can_edit_messages": "Редактирование постов",
    "can_delete_messages": "Удаление чужих постов",
}


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ КЛАВИАТУР ===
def build_channel_rights_keyboard(target_chat_id: int, target_user_id: int, rights: dict) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for attr, label in CHANNEL_PERMISSIONS.items():
        status = "✅" if rights.get(attr, False) else "❌"
        row.append(InlineKeyboardButton(
            text=f"{status} {label}",
            callback_data=f"ch_tgl:{attr}:{target_chat_id}:{target_user_id}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="🚀 Подтвердить и выдать права",
                                         callback_data=f"ch_aply:{target_chat_id}:{target_user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def get_target_user_and_args(message: Message) -> tuple[int | None, list[str]]:
    """Парсер для извлечения целевого ID (через реплай или аргумент) и оставшегося текста"""
    args = message.text.split()
    if not args:
        return None, []
    args.pop(0)

    user_id = None
    user_arg = None

    for arg in args:
        if arg.startswith('@') or (arg.isdigit() and len(arg) > 5):
            user_arg = arg
            args.remove(arg)
            break

    if user_arg:
        user_id = await resolve_id(message, user_arg)
    elif message.reply_to_message and message.reply_to_message.from_user:
        user_id = message.reply_to_message.from_user.id

    return user_id, args


# === 1. ГЕНЕРАЦИЯ ОДНОРАЗОВЫХ ССЫЛОК ===

@tg_channels_links_management.message(F.text.lower().startswith("+ссылка"))
async def cmd_create_one_time_links(message: Message):

    if message.chat.type != "private":
        return

    if message.from_user.id != sanor_ID:
        return

    if not channels_and_chats or channels_and_chats == (''):
        return await message.reply("❌ Список <code>channels_and_chats</code> пуст или настроен неверно в коде.")

    target_id, _ = await get_target_user_and_args(message)
    user_label = f"для юзера {target_id}" if target_id else "одноразовая"

    status_msg = await message.reply("⏳ Генерирую одноразовые ссылки...")
    response = f"🔗 <b>Одноразовые ссылки (лимит: 1 вход):</b>\n\n"

    for chat_id in channels_and_chats:
        try:
            actual_bot = get_bot_for_chat(chat_id)
            chat_info = await actual_bot.get_chat(chat_id)
            title = chat_info.title

            link_object = await actual_bot.create_chat_invite_link(
                chat_id=chat_id,
                member_limit=1,
                name=f"One-time link {user_label}"
            )
            response += f"🔸 <b>{title}</b>:\n👉 {link_object.invite_link}\n\n"
        except TelegramAPIError as e:
            response += f"🔸 <b>ID {chat_id}</b>: ❌ Ошибка API ({e.message})\n\n"

    await status_msg.edit_text(response, parse_mode="HTML", disable_web_page_preview=True)


# === 2. БЫСТРАЯ ЗАЧИСТКА (КИК ИЗ ВСЕХ КАНАЛОВ) ===

@tg_channels_links_management.message(F.text.lower().startswith("-удалить"))
async def cmd_kick_from_all_managed(message: Message):
    if message.chat.type != "private":
        return

    if message.from_user.id != sanor_ID:
        return

    target_id, _ = await get_target_user_and_args(message)
    if not target_id:
        return await message.reply("⚠️ Укажите пользователя (через @username, ID или ответом на его сообщение).")

    if not channels_and_chats or channels_and_chats == (''):
        return await message.reply("❌ Список <code>channels_and_chats</code> пуст.")

    user_link = await user_link_global(target_id)
    status_msg = await message.reply(f"⏳ Начинаю каскадное удаление {user_link} из ресурсов...")

    report = f"🧹 <b>Результаты очистки для {user_link}:</b>\n\n"

    for chat_id in channels_and_chats:
        try:
            actual_bot = get_bot_for_chat(chat_id)
            chat_info = await actual_bot.get_chat(chat_id)
            title = chat_info.title
        except Exception:
            title = f"Ресурс {chat_id}"

        try:
            await actual_bot.ban_chat_member(chat_id=chat_id, user_id=target_id)
            await actual_bot.unban_chat_member(chat_id=chat_id, user_id=target_id)
            report += f"✅ <b>{title}</b>: Успешно удален\n"
        except TelegramAPIError as e:
            report += f"❌ <b>{title}</b>: Ошибка ({e.message})\n"

    await status_msg.edit_text(report, parse_mode="HTML", disable_web_page_preview=True)


# === 3. ВЫДАЧА ПРАВ В КАНАЛАХ С ИНТЕРФЕЙСОМ ===

# Переносим проверку приватного чата прямо в фильтры декоратора
@tg_channels_links_management.message(
    F.chat.type == "private",
    F.text.lower().startswith("+канал админ")
)
async def cmd_promote_channel_admin_start(message: Message):
    if message.from_user.id != sanor_ID:
        return

    # Парсер сам пропустит слово "канал" и найдёт юзера/ID дальше по тексту
    target_id, _ = await get_target_user_and_args(message)
    if not target_id:
        return await message.reply("⚠️ Укажите целевого пользователя кнопкой реплая или через @username.")

    if not channels_and_chats or channels_and_chats == (''):
        return await message.reply("❌ Список <code>channels_and_chats</code> пуст.")

    keyboard_buttons = []
    for chat_id in channels_and_chats:
        try:
            actual_bot = get_bot_for_chat(chat_id)
            chat_info = await actual_bot.get_chat(chat_id)
            title = chat_info.title
        except Exception:
            title = f"Ресурс ID {chat_id}"

        keyboard_buttons.append([InlineKeyboardButton(
            text=title,
            callback_data=f"ch_sel:{chat_id}:{target_id}"
        )])

    user_link = await user_link_global(target_id)
    await message.reply(
        f"Укажите целевой канал/чат из списка для настройки прав {user_link}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
        parse_mode="HTML"
    )


@tg_channels_links_management.callback_query(F.data.startswith("ch_sel:"))
@rate_limit_with_cleanup(limit=1)
async def process_channel_selection(callback: CallbackQuery):
    if not callback.message.reply_to_message or callback.from_user.id != callback.message.reply_to_message.from_user.id:
        return await callback.answer(get_random_text(), show_alert=True)

    _, chat_id_str, user_id_str = callback.data.split(":")
    chat_id, target_id = int(chat_id_str), int(user_id_str)

    actual_bot = get_bot_for_chat(chat_id)

    try:
        chat_info = await actual_bot.get_chat(chat_id)
        chat_title = chat_info.title

        target_member = await actual_bot.get_chat_member(chat_id, target_id)
        if isinstance(target_member, ChatMemberOwner):
            return await callback.answer("❌ Нельзя редактировать права создателя ресурса.", show_alert=True)

        initial_rights = {attr: False for attr in CHANNEL_PERMISSIONS}
        if isinstance(target_member, ChatMemberAdministrator):
            for attr in CHANNEL_PERMISSIONS:
                initial_rights[attr] = getattr(target_member, attr, False)

        key = (chat_id, target_id)
        if key in channel_admin_sessions:
            channel_admin_sessions.pop(key, None)

        channel_admin_sessions[key] = {"rights": initial_rights}
        if len(channel_admin_sessions) > MAX_SESSIONS:
            channel_admin_sessions.popitem(last=False)

        user_link = await user_link_global(target_id)

        await callback.message.edit_text(
            f"👑 Настройка прав администратора для {user_link} в ресурсе <b>«{chat_title}»</b>:",
            reply_markup=build_channel_rights_keyboard(chat_id, target_id, initial_rights),
            parse_mode="HTML"
        )
    except TelegramAPIError as e:
        await callback.answer(f"⚠️ Ошибка доступа бота к каналу: {e.message}", show_alert=True)


@tg_channels_links_management.callback_query(F.data.startswith("ch_tgl:"))
@rate_limit_with_cleanup(limit=1)
async def toggle_channel_permission(callback: CallbackQuery):
    if not callback.message.reply_to_message or callback.from_user.id != callback.message.reply_to_message.from_user.id:
        return await callback.answer(get_random_text(), show_alert=True)

    _, attr, chat_id_str, user_id_str = callback.data.split(":")
    chat_id, target_id = int(chat_id_str), int(user_id_str)

    key = (chat_id, target_id)
    session = channel_admin_sessions.get(key)
    if not session:
        return await callback.answer("⌛ Сессия устарела. Запустите команду заново.", show_alert=True)

    session["rights"][attr] = not session["rights"][attr]

    await callback.message.edit_reply_markup(
        reply_markup=build_channel_rights_keyboard(chat_id, target_id, session["rights"])
    )
    await callback.answer()


@tg_channels_links_management.callback_query(F.data.startswith("ch_aply:"))
@rate_limit_with_cleanup(limit=1)
async def apply_channel_admin_rights(callback: CallbackQuery):
    if not callback.message.reply_to_message or callback.from_user.id != callback.message.reply_to_message.from_user.id:
        return await callback.answer(get_random_text(), show_alert=True)

    _, chat_id_str, user_id_str = callback.data.split(":")
    chat_id, target_id = int(chat_id_str), int(user_id_str)

    key = (chat_id, target_id)
    session = channel_admin_sessions.pop(key, None)
    if not session:
        return await callback.answer("⌛ Сессия не найдена.", show_alert=True)

    actual_bot = get_bot_for_chat(chat_id)
    user_link = await user_link_global(target_id)

    try:
        chat_info = await actual_bot.get_chat(chat_id)
        chat_title = chat_info.title
    except Exception:
        chat_title = f"ID {chat_id}"

    promote_params = {"chat_id": chat_id, "user_id": target_id}
    for attr, val in session["rights"].items():
        promote_params[attr] = val

    while True:
        try:
            await actual_bot.promote_chat_member(**promote_params)
            break
        except TypeError as e:
            err_msg = str(e)
            match = re.search(r"argument '(\w+)'|keyword argument '(\w+)'", err_msg)
            if match:
                bad_arg = match.group(1) or match.group(2)
                if bad_arg in promote_params:
                    promote_params.pop(bad_arg)
                    continue
            raise e
        except TelegramAPIError as e:
            return await callback.message.edit_text(f"❌ Ошибка Telegram API при сохранении прав: {e.message}")

    await callback.message.edit_text(
        f"✅ Права администратора для {user_link} в канале/чате <b>«{chat_title}»</b> успешно применены!",
        parse_mode="HTML"
    )
    await callback.answer()