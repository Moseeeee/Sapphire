import logging
import html
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from handlers.AdminsTools.ChatSettings.bundle.bundle_admins.bundle_admins_db import (
    add_bundle_admin, remove_bundle_admin, get_bundle_admins,
    is_bundle_admin, get_bundle_logs, get_bundle_logs_count
)
from handlers.AdminsTools.ChatSettings.bundle.bundle_db import get_bundle_by_chat, get_bundle_owner
from BotAutomaticWork.users.checks.check_UserId.check_users_id import resolve_id
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global
from handlers.UserCommands.SettingsUsersProfile.GenderSettings.GenderSettingsDB import get_user_gender
from handlers.BotAutomaticWork.users.GenderUtils import g

logger = logging.getLogger(__name__)
bundle_admins_router = Router()
LOGS_PER_PAGE = 10


async def resolve_bundle_id_by_chat(chat_id: int) -> int:
    info = await get_bundle_by_chat(chat_id)
    return info['id'] if info else None


async def format_log_line_html(log: dict) -> str:
    """Форматирует запись лога в HTML.
    Пример: 🔴 @user забанен, `12.04 14:32` - @admin
    ⏱️ Период: 7д
    💬 Причина: спам
    """
    gender = await get_user_gender(log['target_user_id'])

    action_emojis = {
        'ban': f'забан{g("ен", gender)}',
        'unban': f'разбан{g("ен", gender)}',
        'mute': f'замуч{g("ен", gender)}',
        'unmute': f'размуч{g("ен", gender)}',
        'warn': 'варн',
        'unwarn': 'снят варн'
    }

    action = {
        'ban': '🔴',
        'unban': '🟢',
        'mute': '🟡',
        'unmute': '⚪',
        'warn': '🟠',
        'unwarn': '🔵'
    }

    action_text = action_emojis.get(log['action'], log['action'])
    emoji_action = action.get(log['action'], log['action'])
    time_str = log['created_at'].strftime("%d.%m %H:%M")
    admin_link = log.get('admin_link', 'неизвестно')
    target_link = log.get('target_link', 'неизвестно')

    # Основная часть: эмодзи пользователь действие, время - админ
    line = f"{emoji_action} {target_link} {action_text}, <code>{time_str}</code> - {admin_link}"

    # Добавляем срок (если есть)
    if log.get('duration'):
        line += f"\n⏱️ <b>Период:</b> {html.escape(str(log['duration']))}"

    # Добавляем причину (если есть и не дефолтная)
    if log.get('reason') and log['reason'].strip() not in ('', 'Не указана'):
        line += f"\n💬 <b>Причина:</b> <i>{html.escape(log['reason'][:50])}</i>"

    line += '\n'
    return line


def build_logs_keyboard(bundle_id: int, target_user_id: int, page: int, total_pages: int) -> InlineKeyboardMarkup:
    keyboard = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=f"bundle_logs_{bundle_id}_{target_user_id}_{page - 1}"
        ))
    nav_row.append(InlineKeyboardButton(
        text=f"{page + 1}/{max(1, total_pages)}",
        callback_data="current_page"
    ))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(
            text="Вперед ➡️",
            callback_data=f"bundle_logs_{bundle_id}_{target_user_id}_{page + 1}"
        ))
    keyboard.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def send_logs_page(target, bundle_id: int, target_user_id: int,
                         logs: list, page: int, total_pages: int):
    """Отправляет или редактирует страницу логов (HTML-формат)."""
    if not logs:
        if isinstance(target, types.Message):
            await target.answer("📭 Нет логов на этой странице.")
        else:
            await target.message.edit_text("📭 Нет логов на этой странице.")
        return

    # Добавляем ссылки на пользователей
    for log in logs:
        log['admin_link'] = await user_link_global(log['admin_id'])
        log['target_link'] = await user_link_global(log['target_user_id'])

    lines = [f"📋 <b>Логи связки</b> | стр. {page + 1}/{max(1, total_pages)}\n"]
    for log in logs:
        lines.append(await format_log_line_html(log))

    text = "\n".join(lines)
    keyboard = build_logs_keyboard(bundle_id, target_user_id, page, total_pages)

    if isinstance(target, types.Message):
        await target.reply(text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)
    else:  # CallbackQuery
        await target.message.edit_text(text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)


@bundle_admins_router.message(F.text.regexp(r'(?i)^[!./]связка\s+назначить\s+\S+\s+\d+'))
async def cmd_add_bundle_admin(message: types.Message):
    if message.chat.type in ('private', 'channel'):
        await message.answer("❌ Команда доступна только в группах, привязанных к связке.")
        return
    text = message.text.strip()
    if text[0] in '!./':
        text = text[1:].lstrip()
    parts = text.split(maxsplit=3)
    if len(parts) < 4:
        await message.answer("❌ Использование: .связка назначить @username [ранг=1 или 2]")
        return
    target = parts[2]
    rank_str = parts[3]
    if not rank_str.isdigit():
        await message.answer("❌ Ранг должен быть числом (1 или 2).")
        return
    rank = int(rank_str)
    if rank not in (1, 2):
        await message.answer("❌ Ранг может быть 1 (наказания) или 2 (полное управление связкой).")
        return
    user_id = await resolve_id(message, target)
    if not user_id:
        await message.answer("❌ Пользователь не найден.")
        return
    bundle_id = await resolve_bundle_id_by_chat(message.chat.id)
    if not bundle_id:
        await message.answer("❌ Этот чат не привязан ни к одной связке.")
        return
    owner = await get_bundle_owner(bundle_id)
    if owner != message.from_user.id:
        await message.answer("❌ Только владелец связки может назначать связных администраторов.")
        return
    success = await add_bundle_admin(bundle_id, user_id, message.from_user.id, rank)
    if success:
        user_link = await user_link_global(user_id)
        gender = await get_user_gender(user_id)
        rank_desc = "полное управление" if rank == 2 else "наказания"
        await message.answer(f"✅ {user_link} назнач{g('ен', gender)} связным администратором (ранг {rank} – {rank_desc}).", parse_mode="HTML", disable_web_page_preview=True)
    else:
        await message.answer("❌ Ошибка при назначении.")


@bundle_admins_router.message(F.text.regexp(r'(?i)^[!./]связка\s+снять\s+админа\s+\S+'))
async def cmd_remove_bundle_admin(message: types.Message):
    if message.chat.type in ('private', 'channel'):
        return
    text = message.text.strip()
    if text[0] in '!./':
        text = text[1:].lstrip()
    parts = text.split(maxsplit=3)
    if len(parts) < 3:
        await message.answer("❌ Использование: .связка снять админа @username")
        return
    target = parts[2]
    user_id = await resolve_id(message, target)
    if not user_id:
        await message.answer("❌ Пользователь не найден.")
        return
    bundle_id = await resolve_bundle_id_by_chat(message.chat.id)
    if not bundle_id:
        await message.answer("❌ Этот чат не привязан к связке.")
        return
    owner = await get_bundle_owner(bundle_id)
    if owner != message.from_user.id:
        await message.answer("❌ Только владелец связки может удалять администраторов.")
        return
    success = await remove_bundle_admin(bundle_id, user_id)
    if success:
        user_link = await user_link_global(user_id)
        gender = await get_user_gender(user_id)
        await message.answer(f"✅ {user_link} удал{g('ён', gender)} из связных администраторов.",
                             parse_mode="HTML",
                             disable_web_page_preview=True)
    else:
        await message.answer("❌ Ошибка при удалении.")


@bundle_admins_router.message(F.text.regexp(r'(?i)^[!./]связка\s+админы$'))
async def cmd_list_bundle_admins(message: types.Message):
    if message.chat.type in ('private', 'channel'):
        return
    bundle_id = await resolve_bundle_id_by_chat(message.chat.id)
    if not bundle_id:
        await message.answer("❌ Этот чат не привязан к связке.")
        return
    admins = await get_bundle_admins(bundle_id)
    if not admins:
        await message.answer("ℹ️ В этой связке нет назначенных связных администраторов.")
        return
    text = "👥 <b>Связные администраторы:</b>\n\n"
    for a in admins:
        user_link = await user_link_global(a['user_id'])
        rank_desc = "полное управление" if a['rank'] == 2 else "наказания"
        text += f"• {user_link} (ранг {a['rank']} – {rank_desc})\n"
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


@bundle_admins_router.message(F.text.regexp(r'(?i)^[!./]связка\s+логи(\s+\S+)?$'))
async def cmd_bundle_logs(message: types.Message):
    if message.chat.type in ('private', 'channel'):
        return
    text = message.text.strip()
    if text[0] in '!./':
        text = text[1:].lstrip()
    parts = text.split(maxsplit=2)
    target_user = None
    if len(parts) > 2:
        target_user = parts[2]
    bundle_id = await resolve_bundle_id_by_chat(message.chat.id)
    if not bundle_id:
        await message.answer("❌ Этот чат не привязан к связке.")
        return
    owner = await get_bundle_owner(bundle_id)
    if owner != message.from_user.id and not await is_bundle_admin(bundle_id, message.from_user.id, required_rank=2):
        await message.answer("❌ Только владелец или связной администратор с рангом 2 может просматривать логи.")
        return
    target_user_id = None
    if target_user:
        target_user_id = await resolve_id(message, target_user)
        if not target_user_id:
            await message.answer("❌ Пользователь не найден.")
            return
    total = await get_bundle_logs_count(bundle_id, target_user_id)
    if total == 0:
        await message.answer("📭 Нет записей в логах связки.")
        return
    total_pages = (total + LOGS_PER_PAGE - 1) // LOGS_PER_PAGE
    page = 0
    logs = await get_bundle_logs(bundle_id, target_user_id, limit=LOGS_PER_PAGE, offset=page * LOGS_PER_PAGE)
    await send_logs_page(message, bundle_id, target_user_id, logs, page, total_pages)


@bundle_admins_router.callback_query(lambda c: c.data.startswith("bundle_logs_"))
async def logs_pagination_callback(callback: types.CallbackQuery):
    if (not callback.message.reply_to_message or
        callback.from_user.id != callback.message.reply_to_message.from_user.id):
        await callback.answer("❌ Это не ваш запрос.", show_alert=True)
        return

    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return

    try:
        bundle_id = int(parts[2])
    except ValueError:
        await callback.answer("❌ Неверный ID связки", show_alert=True)
        return

    # Определяем target_user_id и page
    if parts[3] == "None":
        target_user_id = None
        if len(parts) < 5:
            await callback.answer("❌ Ошибка данных: нет номера страницы", show_alert=True)
            return
        page = int(parts[4])
    else:
        try:
            target_user_id = int(parts[3])
        except ValueError:
            target_user_id = None
        if len(parts) < 5:
            await callback.answer("❌ Ошибка данных: нет номера страницы", show_alert=True)
            return
        page = int(parts[4])

    total = await get_bundle_logs_count(bundle_id, target_user_id)
    if total == 0:
        await callback.answer("❌ Логи пусты", show_alert=True)
        return

    total_pages = (total + LOGS_PER_PAGE - 1) // LOGS_PER_PAGE
    if page < 0 or page >= total_pages:
        await callback.answer("❌ Такой страницы нет", show_alert=True)
        return

    logs = await get_bundle_logs(bundle_id, target_user_id, limit=LOGS_PER_PAGE, offset=page * LOGS_PER_PAGE)
    if not logs:
        await callback.answer("❌ Нет записей", show_alert=True)
        return

    await send_logs_page(callback, bundle_id, target_user_id, logs, page, total_pages)
    await callback.answer()


@bundle_admins_router.callback_query(lambda c: c.data == "current_page")
async def current_page_callback(callback: types.CallbackQuery):
    await callback.answer()