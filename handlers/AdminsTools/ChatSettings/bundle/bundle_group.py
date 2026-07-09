import logging
import html
from collections import defaultdict
from datetime import timedelta, datetime
import re

from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from handlers.AdminsTools.ChatSettings.PuchCommandSettings.push_command_settingsDB import check_push_status
from handlers.AdminsTools.ChatSettings.Stats.msg_stats_users.SmsStatsDB import get_stats
from handlers.AdminsTools.ChatSettings.bundle.bundle_admins.bundle_admins_db import is_bundle_admin, add_bundle_log
from handlers.AdminsTools.ChatSettings.bundle.bundle_db import (
    get_bundle_by_name, get_bundle_by_chat, get_bundle_chats,
    get_bundle_owner, is_chat_in_any_bundle, add_chat_to_bundle,
    move_chat_to_bundle, is_chat_in_bundle, remove_chat_from_bundle,
    get_bundle_chats_with_descriptions
)

from handlers.AdminsTools.ChatSettings.ChatAdmins.ChatAdminsDB import (
    check_admin_for_rang, add_admin_for_rang, update_admin_for_rang,
    del_admin_for_rang, add_history_admin_for_rang
)
from handlers.AdminsTools.ChatSettings.DkCommands.UpdateCommandSettingsDB import (
    get_command_info, get_commands_by_section, get_commands_by_under_section,
    add_dk_for_chats
)
from handlers.BotAutomaticWork.Gonfig.config import boss_agent
from handlers.AdminsTools.ChatSettings.ChatAdmins.ChatAdmins import is_telegram_owner

from handlers.AdminsTools.CommandsModerations.bans.ban import perform_ban, perform_unban
from handlers.AdminsTools.CommandsModerations.mute.mute import perform_mute, perform_unmute
from handlers.AdminsTools.CommandsModerations.warns.warnsDB import add_warn, remove_warn
from handlers.BotAutomaticWork.universal_bot import bot
from handlers.BotAutomaticWork.users.GenderUtils import g
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from BotAutomaticWork.users.checks.check_UserId.check_users_id import resolve_id
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global
from handlers.BotAutomaticWork.parse_time_auto import parse_time_string
from handlers.BotAutomaticWork.AddChatsBot.link.chats_global_link import chat_global_link
from handlers.UserCommands.SettingsUsersProfile.GenderSettings.GenderSettingsDB import get_user_gender

logger = logging.getLogger(__name__)
group_bundle = Router()


# ------------------------------------------------------------
# Улучшенный парсер времени
# ------------------------------------------------------------
def parse_time_improved(time_str: str):
    if not time_str:
        return None
    time_str = time_str.lower().strip()
    if time_str in ["навсегда", "permanent", "forever", "навечно", "вечно"]:
        return 'навсегда'
    parsed = parse_time_string(time_str)
    if parsed is not None:
        return parsed
    patterns = [
        (r'(\d+)\s*(?:минут[ыуа]?|мин|м(?![её]))', 60),
        (r'(\d+)\s*(?:час[ауов]?|ч|х\b)', 3600),
        (r'(\d+)\s*(?:день|дня|дней|дн|д\b)', 86400),
        (r'(\d+)\s*(?:недел[яиьюе]|нед|н\b)', 604800),
        (r'(\d+)\s*(?:месяц[аев]?|мес)', 2592000),
        (r'(\d+)\s*(?:секунд[ыу]?|сек|с\b)', 1),
    ]
    total_seconds = 0
    for pattern, multiplier in patterns:
        matches = re.findall(pattern, time_str)
        for match in matches:
            try:
                total_seconds += int(match) * multiplier
            except ValueError:
                continue
    if total_seconds > 0:
        return timedelta(seconds=total_seconds)
    cleaned = re.sub(r'[^\d\sчмнднсекгуаяитль]', '', time_str)
    if cleaned != time_str:
        parsed = parse_time_string(cleaned)
        if parsed is not None:
            return parsed
    logger.warning(f"Не удалось распарсить время: '{time_str}'")
    return None


# ------------------------------------------------------------
# Вспомогательные функции
# ------------------------------------------------------------
async def resolve_bundle_id_group(message: types.Message, explicit_name: str = None):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if explicit_name:
        return await get_bundle_by_name(user_id, explicit_name)
    bundle_info = await get_bundle_by_chat(chat_id)
    return bundle_info['id'] if bundle_info else None


async def get_bundle_chats_with_permissions(bundle_id: int, bot_id: int):
    chats = await get_bundle_chats(bundle_id)
    valid = []
    reasons = []
    for cid in chats:
        try:
            bot_member = await bot.get_chat_member(cid, bot_id)
            if bot_member.status not in ('administrator', 'creator'):
                reasons.append(f"⚠️ Чат {cid}: бот не администратор (статус {bot_member.status})")
                continue
        except Exception as e:
            reasons.append(f"⚠️ Чат {cid}: ошибка проверки бота – {html.escape(str(e))}")
            continue
        valid.append(cid)
    return valid, reasons


async def safe_action(chat_id: int, action: str, **kwargs):
    try:
        gender = await get_user_gender(kwargs['user_id'])

        if action == 'ban':
            success, msg = await perform_ban(chat_id=chat_id, **kwargs)
            return success, msg
        elif action == 'unban':
            success = await perform_unban(chat_id=chat_id, user_id=kwargs['user_id'])
            return success, f"разбан{g('ен', gender)}" if success else "ошибка разбана"
        elif action == 'mute':
            success, msg = await perform_mute(chat_id=chat_id, **kwargs)
            return success, msg
        elif action == 'unmute':
            success = await perform_unmute(chat_id=chat_id, user_id=kwargs['user_id'])
            return success, f"размуч{g('ен', gender)}" if success else "ошибка размута"
        elif action == 'warn':
            count = await add_warn(
                chat_id, kwargs['user_id'], kwargs['admin_id'],
                kwargs.get('reason', "Не указана"), kwargs.get('duration', None)
            )
            return (count > 0, "варн выдан" if count > 0 else "ошибка")
        elif action == 'unwarn':
            await remove_warn(chat_id, kwargs['user_id'], None)
            return (True, "варн снят")
        else:
            return (False, "неизвестное действие")
    except Exception as e:
        logger.error(f"safe_action error in chat {chat_id}: {e}", exc_info=True)
        return (False, html.escape(str(e)))






# ------------------------------------------------------------
# Управление рангами и правами команд по связке
# ------------------------------------------------------------

async def promote_in_bundle(message: types.Message, target_user_id: int, new_rank: int = None):
    """Повысить пользователя во всех чатах связки."""
    bundle_id = await resolve_bundle_id_group(message, None)
    if not bundle_id:
        await message.answer("Этот чат не привязан к связке")
        return

    owner = await get_bundle_owner(bundle_id)
    if owner != message.from_user.id and not await is_bundle_admin(bundle_id, message.from_user.id, required_rank=2):
        push_status = await check_push_status(message.chat.id)
        if push_status == 'on':
            await message.answer("Только владелец или связной администратор (ранг 2+) может управлять рангами.")
        return

    chats = await get_bundle_chats(bundle_id)
    if not chats:
        await message.answer("В связке нет чатов.")
        return

    results = []
    success_in_any = False
    for chat_id in chats:
        try:
            current_rank = await check_admin_for_rang(target_user_id, chat_id)
            if current_rank == 0:
                target_rank = new_rank if new_rank is not None else 1
            else:
                target_rank = new_rank if new_rank is not None else current_rank + 1

            if target_rank > 5:
                results.append((chat_id, False, "ранг не может быть выше 5"))
                continue

            # Проверка прав администратора, выполняющего действие
            admin_rank = await check_admin_for_rang(message.from_user.id, chat_id)
            if admin_rank < target_rank and message.from_user.id not in boss_agent:
                results.append((chat_id, False, "ваш ранг ниже целевого"))
                continue

            # Проверка на владельца чата в Telegram
            is_tg_owner = await is_telegram_owner(message.bot, chat_id, target_user_id)
            if is_tg_owner and message.from_user.id not in boss_agent:
                results.append((chat_id, False, "нельзя изменять ранг создателя чата"))
                continue

            if current_rank == 0:
                await add_admin_for_rang(target_user_id, chat_id, target_rank, message.from_user.id, admin_rank, datetime.now().strftime("%d.%m.%Y %H:%M"))
            else:
                await update_admin_for_rang(target_rank, message.from_user.id, admin_rank, datetime.now().strftime("%d.%m.%Y %H:%M"), target_user_id, chat_id)
            await add_history_admin_for_rang(target_user_id, chat_id, target_rank, current_rank, message.from_user.id, admin_rank, datetime.now().strftime("%d.%m.%Y %H:%M"))
            results.append((chat_id, True, f"ранг {current_rank} → {target_rank}"))
            success_in_any = True
        except Exception as e:
            results.append((chat_id, False, str(e)))
            logger.error(f"promote error in chat {chat_id}: {e}")

    await send_bundle_action_report(message, "Повышение", target_user_id, results, success_in_any)


async def demote_in_bundle(message: types.Message, target_user_id: int, new_rank: int = None):
    """Понизить пользователя во всех чатах связки."""
    bundle_id = await resolve_bundle_id_group(message, None)
    if not bundle_id:
        await message.answer("Этот чат не привязан к связке.")
        return

    owner = await get_bundle_owner(bundle_id)
    if owner != message.from_user.id and not await is_bundle_admin(bundle_id, message.from_user.id, required_rank=2):
        push_status = await check_push_status(message.chat.id)
        if push_status == 'on':
            await message.answer("Только владелец или связной администратор (ранг 2+) может управлять рангами.")
        return

    chats = await get_bundle_chats(bundle_id)
    if not chats:
        await message.answer("В связке нет чатов.")
        return

    results = []
    success_in_any = False
    for chat_id in chats:
        try:
            current_rank = await check_admin_for_rang(target_user_id, chat_id)
            if current_rank == 0:
                results.append((chat_id, False, "пользователь не администратор"))
                continue

            if new_rank is None:
                target_rank = current_rank - 1
                if target_rank < 0:
                    target_rank = 0
            else:
                target_rank = new_rank

            if target_rank < 0 or target_rank > 4:
                results.append((chat_id, False, "недопустимый ранг (0-5)"))
                continue

            if target_rank >= current_rank:
                results.append((chat_id, False, "новый ранг должен быть ниже текущего"))
                continue

            admin_rank = await check_admin_for_rang(message.from_user.id, chat_id)
            if current_rank >= admin_rank and message.from_user.id not in boss_agent:
                # Проверка на владельца чата в Telegram
                is_tg_owner = await is_telegram_owner(message.bot, chat_id, message.from_user.id)
                if not is_tg_owner:
                    results.append((chat_id, False, "вы не можете понижать администратора равного или высшего ранга"))
                    continue

            if target_rank == 0:
                await del_admin_for_rang(target_user_id, chat_id)
            else:
                await update_admin_for_rang(target_rank, message.from_user.id, admin_rank, datetime.now().strftime("%d.%m.%Y %H:%M"), target_user_id, chat_id)
            await add_history_admin_for_rang(target_user_id, chat_id, target_rank, current_rank, message.from_user.id, admin_rank, datetime.now().strftime("%d.%m.%Y %H:%M"))
            results.append((chat_id, True, f"ранг {current_rank} → {target_rank}"))
            success_in_any = True
        except Exception as e:
            results.append((chat_id, False, str(e)))
            logger.error(f"demote error in chat {chat_id}: {e}")

    await send_bundle_action_report(message, "Понижение", target_user_id, results, success_in_any)


async def remove_admin_in_bundle(message: types.Message, target_user_id: int):
    """Снять пользователя с должности администратора во всех чатах связки."""
    bundle_id = await resolve_bundle_id_group(message, None)
    if not bundle_id:
        await message.answer("❌ Этот чат не привязан к связке.")
        return

    owner = await get_bundle_owner(bundle_id)
    if owner != message.from_user.id and not await is_bundle_admin(bundle_id, message.from_user.id, required_rank=2):
        push_status = await check_push_status(message.chat.id)
        if push_status == 'on':
            await message.answer("Только владелец или связной администратор (ранг 2+) может управлять рангами.")
        return

    chats = await get_bundle_chats(bundle_id)
    if not chats:
        await message.answer("В связке нет чатов.")
        return

    results = []
    success_in_any = False
    for chat_id in chats:
        try:
            current_rank = await check_admin_for_rang(target_user_id, chat_id)
            if current_rank == 0:
                results.append((chat_id, False, "пользователь не администратор"))
                continue

            admin_rank = await check_admin_for_rang(message.from_user.id, chat_id)
            if current_rank >= admin_rank and message.from_user.id not in boss_agent:
                is_tg_owner = await is_telegram_owner(message.bot, chat_id, message.from_user.id)
                if not is_tg_owner:
                    results.append((chat_id, False, "недостаточно прав для снятия этого администратора"))
                    continue

            await del_admin_for_rang(target_user_id, chat_id)
            await add_history_admin_for_rang(target_user_id, chat_id, 0, current_rank, message.from_user.id, admin_rank, datetime.now().strftime("%d.%m.%Y %H:%M"))
            results.append((chat_id, True, "снят"))
            success_in_any = True
        except Exception as e:
            results.append((chat_id, False, str(e)))
            logger.error(f"remove_admin error in chat {chat_id}: {e}")

    await send_bundle_action_report(message, "Снятие админа", target_user_id, results, success_in_any)


async def set_command_access_in_bundle(message: types.Message, target_value: str, rang: int):
    """
    Установить уровень доступа команды/раздела/подраздела для всей связки.
    target_value: ID команды, название команды, или "раздел.подраздел"
    rang: 0-6 (6 - выключить)
    """
    from handlers.AdminsTools.ChatSettings.DkCommands.UpdateCommandSettings import identify_target_type

    bundle_id = await resolve_bundle_id_group(message, None)
    if not bundle_id:
        await message.answer("Этот чат не привязан к связке.")
        return

    owner = await get_bundle_owner(bundle_id)
    if owner != message.from_user.id:
        push_status = await check_push_status(message.chat.id)
        if push_status == 'on':
            await message.answer("Только владелец связки может изменять права команд.")
        return

    # Определяем тип цели
    target_type, target_id = await identify_target_type(target_value)
    if target_type == "not_found":
        await message.answer("Команда, раздел или подраздел не найдены.")
        return

    # Получаем список команды для изменения
    commands = []
    if target_type == "command":
        cmd_info = await get_command_info(command_id=target_id)
        if cmd_info:
            commands = [cmd_info]
    elif target_type == "under_section":
        commands = await get_commands_by_under_section(target_id)
    elif target_type == "section":
        commands = await get_commands_by_section(target_id)

    if not commands:
        await message.answer("Нет команд для изменения.")
        return

    # Применяем изменения во всех чатах связки
    chats = await get_bundle_chats(bundle_id)
    if not chats:
        await message.answer("В связке нет чатов.")
        return

    results = []
    total_updated = 0
    PROTECTED_COMMAND_ID = 61  # ID команды "настройка доступа команд"

    for chat_id in chats:
        updated_count = 0
        for cmd in commands:
            cmd_id = cmd['CommandId']
            if cmd_id == PROTECTED_COMMAND_ID and rang == 6:
                continue  # защищённую команду нельзя отключить
            await add_dk_for_chats(chat_id, cmd_id, rang)
            updated_count += 1
        results.append((chat_id, updated_count))
        total_updated += updated_count

    target_name = target_value
    if target_type == "command" and commands:
        target_name = commands[0].get('CommandName', target_value)
    elif target_type == "under_section":
        target_name = f"подраздел {target_value}"
    elif target_type == "section":
        target_name = f"раздел {target_value}"

    status_text = "выключена" if rang == 6 else f"установлен ранг {rang}"
    await message.answer(
        f"✅ Для связки: командам «{target_name}» {status_text}"
    )


async def send_bundle_action_report(message: types.Message, action_name: str, target_user_id: int, results: list, success_in_any: bool):
    """Отправляет отчёт о выполнении действия во всех чатах."""
    total = len(results)
    success_count = sum(1 for _, ok, _ in results if ok)
    user_link = await user_link_global(target_user_id)
    admin_link = await user_link_global(message.from_user.id)

    resp = f"🔔 <b>{action_name} по связке для {user_link}</b>\n👮‍♂️ {admin_link}\nУспешно: {success_count}/{total}\n"
    #if total <= 20:
        #resp += "\n📋 Детали:\n"
        #for chat_id, ok, msg in results:
            #try:
                #chat = await bot.get_chat(chat_id)
                #chat_name = chat.title or str(chat_id)
            #except:
                #chat_name = str(chat_id)
            #resp += f"{'✅' if ok else '❌'} {html.escape(chat_name)}: {html.escape(msg)}\n"
    #else:
        #resp += f"\n✅ {success_count} чатов, ❌ {total - success_count}"
    await message.reply(resp, parse_mode="HTML", disable_web_page_preview=True)

    if success_in_any:
        # Логируем действие (опционально, если есть своя таблица логов)
        pass

# ------------------------------------------------------------
# Добавление / удаление чата
# ------------------------------------------------------------
@group_bundle.message(F.text.regexp(r'(?i)^\+связка\s+\S+'))
async def add_chat(message: types.Message):
    if message.chat.type in ('private', 'channel'):
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    lines = message.text.split('\n', 1)
    first_line = lines[0].strip()
    description = lines[1].strip() if len(lines) > 1 else ""
    args = first_line.split(maxsplit=1)
    if len(args) < 2:
        return
    name = args[1].strip()
    safe_name = html.escape(name)
    bundle_id = await get_bundle_by_name(user_id, name)
    if not bundle_id:
        push_status = await check_push_status(chat_id)
        if push_status == 'on':
            await message.answer(f"Вы не владелец связки «{safe_name}».")
        return
    owner = await get_bundle_owner(bundle_id)
    if owner != user_id and not await is_bundle_admin(bundle_id, user_id, required_rank=2):
        push_status = await check_push_status(chat_id)
        if push_status == 'on':
            await message.answer("Недостаточно прав для управления чатами связки (нужен ранг 2).")
        return
    existing = await is_chat_in_any_bundle(chat_id)
    if existing:
        if existing == bundle_id:
            push_status = await check_push_status(chat_id)
            if push_status == 'on':
                await message.answer("Чат уже в этой связке.")
            return
        desc_encoded = description.replace('_', '\\_') if description else ""
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Да, переместить", callback_data=f"move_{bundle_id}_{chat_id}_{desc_encoded}")],
            [InlineKeyboardButton(text="Нет", callback_data="cancel_move")]
        ])
        push_status = await check_push_status(chat_id)
        if push_status == 'on':
            await message.answer(f"Чат уже в другой связке. Переместить в «{safe_name}»?", reply_markup=kb)
        return
    if await add_chat_to_bundle(bundle_id, chat_id, user_id, description):
        await message.answer(f"✅ Чат добавлен в связку «{safe_name}».")
    else:
        await message.answer("Ошибка добавления.")


@group_bundle.callback_query(lambda c: c.data.startswith("move_"))
async def move_chat_callback(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("Ошибка данных", show_alert=True)
        return
    bundle_id = int(parts[1])
    chat_id = int(parts[2])
    description = '_'.join(parts[3:]) if len(parts) > 3 else ""
    description = description.replace('\\_', '_')
    user_id = callback.from_user.id
    owner = await get_bundle_owner(bundle_id)
    if owner != user_id and not await is_bundle_admin(bundle_id, user_id, required_rank=2):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return
    if await move_chat_to_bundle(chat_id, bundle_id, user_id, description):
        await callback.message.edit_text("✅ Чат перемещён.")
    else:
        await callback.message.edit_text("Ошибка перемещения.")
    await callback.answer()


@group_bundle.callback_query(lambda c: c.data == "cancel_move")
async def cancel_move(callback: types.CallbackQuery):
    await callback.message.edit_text("Перемещение отменено.")
    await callback.answer()


@group_bundle.message(F.text.regexp(r'(?i)^\-связка(\s|$)'))
async def remove_chat(message: types.Message):
    if message.chat.type in ('private', 'channel'):
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    bundle_id = await resolve_bundle_id_group(message, None)
    if not bundle_id:
        push_status = await check_push_status(chat_id)
        if push_status == 'on':
            await message.answer("Этот чат не привязан ни к одной связке.")
        return
    owner = await get_bundle_owner(bundle_id)
    if owner != user_id and not await is_bundle_admin(bundle_id, user_id, required_rank=2):
        push_status = await check_push_status(chat_id)
        if push_status == 'on':
            await message.answer("Недостаточно прав для удаления чата из связки (нужен ранг 2).")
        return
    if not await is_chat_in_bundle(chat_id, bundle_id):
        push_status = await check_push_status(chat_id)
        if push_status == 'on':
            await message.answer("Этот чат не состоит в указанной связке (ошибка данных).")
        return
    await remove_chat_from_bundle(bundle_id, chat_id)
    await message.answer(f"✅ Чат удалён из связки.")


# ------------------------------------------------------------
# Команда .связка (показать список чатов с описаниями)
# ------------------------------------------------------------
@group_bundle.message(F.text.regexp(r'(?i)^[!./]связка\s*$'))
@group_bundle.message(F.text.regexp(r'(?i)^[!./]связка\s+чатов\s*$'))
@group_bundle.message(F.text.regexp(r'(?i)^[!./]чаты\s*$'))
async def show_bundle_chats(message: types.Message):
    if message.chat.type in ('private', 'channel'):
        return

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 82):
        return

    bundle_id = await resolve_bundle_id_group(message, None)
    if not bundle_id:
        await message.answer("Этот чат не привязан ни к одной связке. Сначала добавьте его через +связка <название>")
        return
    chats_with_desc = await get_bundle_chats_with_descriptions(bundle_id)
    if not chats_with_desc:
        await message.answer("ℹВ этой связке нет чатов.")
        return
    text = f"📋 <b>Чаты в связке</b>\n\n"
    for idx, entry in enumerate(chats_with_desc, 1):
        chat_id = entry['chat_id']
        description = entry['description']
        chat_link = await chat_global_link(chat_id)  # уже безопасная ссылка
        safe_desc = html.escape(description) if description else ""
        text += f"{idx}. {chat_link}\n"
        if safe_desc:
            text += f"{safe_desc}\n"
        text += "\n"
    await message.answer(text.strip(), parse_mode="HTML", disable_web_page_preview=True)


# ------------------------------------------------------------
# Парсинг аргументов команды наказаний
# ------------------------------------------------------------
def parse_command_args(args_text: str):
    words = args_text.split()
    if not words:
        return None, None, None

    user_mention = None
    remaining_words = []
    for w in words:
        # Проверяем, является ли слово идентификатором пользователя
        is_user = (
            w.startswith('@') or                          # @username
            (w.isdigit() and len(w) >= 5) or              # числовой ID (от 5 цифр)
            't.me/' in w or                               # t.me/username
            'telegram.me/' in w or                        # telegram.me/username
            'tg://' in w                                  # tg://user?id=12345
        )
        if is_user and user_mention is None:
            user_mention = w
            continue
        remaining_words.append(w)
    remaining = ' '.join(remaining_words).strip()
    duration_obj = None
    duration_str = None
    if remaining:
        parsed = parse_time_string(remaining)
        if parsed is not None:
            duration_obj = parsed
            duration_str = remaining
        else:
            parsed2 = parse_time_improved(remaining)
            if parsed2 is not None:
                if parsed2 == 'навсегда':
                    duration_obj = None
                    duration_str = 'навсегда'
                else:
                    duration_obj = parsed2
                    duration_str = remaining
    return user_mention, duration_obj, duration_str


# ------------------------------------------------------------
# Основная функция обработки действий
# ------------------------------------------------------------
async def process_action(message: types.Message, action: str):
    lines = message.text.split('\n', 1)
    first_line = lines[0].strip()
    reason = lines[1].strip() if len(lines) > 1 else ""
    safe_reason = html.escape(reason)

    if first_line and first_line[0] in '!./':
        first_line = first_line[1:].lstrip()
    if first_line.lower().startswith('связка'):
        first_line = first_line[6:].lstrip()
    else:
        await message.answer("Неверный формат команды.")
        return

    if not first_line:
        await message.answer("Не указано действие.")
        return
    action_words = first_line.split(maxsplit=1)
    if len(action_words) < 1:
        await message.answer("Не указано действие.")
        return
    args_str = action_words[1] if len(action_words) > 1 else ""

    user_mention, duration_obj, duration_str = parse_command_args(args_str)

    user_id = None
    if user_mention:
        user_id = await resolve_id(message, user_mention)
        if not user_id:
            await message.answer("Пользователь не найден.")
            return
    elif message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    else:
        await message.answer("Укажите пользователя (упоминанием или ответом).")
        return

    duration = duration_obj
    duration_str = duration_str or ""

    bundle_id = await resolve_bundle_id_group(message, None)
    if not bundle_id:
        await message.answer("Этот чат не привязан ни к одной связке. Сначала добавьте его через +связка <название>")
        return

    owner = await get_bundle_owner(bundle_id)
    if owner != message.from_user.id and not await is_bundle_admin(bundle_id, message.from_user.id, required_rank=1):
        push_status = await check_push_status(message.chat.id)
        if push_status == 'on':
            await message.answer("Только владелец или связной администратор (ранг 1+) может применять наказания.")
        return

    bot_id = message.bot.id
    chats, reasons = await get_bundle_chats_with_permissions(bundle_id, bot_id)
    if not chats:
        error_text = "⚠️ Нет доступных чатов для выполнения действия.\n"
        if reasons:
            error_text += "\n<b>Причины отказа:</b>\n" + "\n".join(html.escape(r) for r in reasons[:10])
        await message.answer(error_text, parse_mode="HTML")
        return

    user_link = await user_link_global(user_id)
    results = []
    success_in_any = False
    for chat_id in chats:
        kwargs = {
            'user_id': user_id,
            'admin_id': message.from_user.id,
            'reason': safe_reason if safe_reason else "Не указана",
            'duration': duration
        }
        success, msg = await safe_action(chat_id, action, **kwargs)
        if success:
            success_in_any = True
        try:
            chat = await bot.get_chat(chat_id)
            chat_name = chat.title or str(chat_id)
        except:
            chat_name = str(chat_id)
        results.append((html.escape(chat_name), success, html.escape(msg)))

        gender = await get_user_gender(user_id)

        action_ru = {
            'ban': f'забан{g("ен", gender)}', 'unban': f'разбан{g("ен", gender)}',
            'mute': f'замуч{g("ен", gender)}', 'unmute': f'размуч{g("ен", gender)}',
            'warn': 'получил варн', 'unwarn': 'снят варн'
        }.get(action, action)

        message_text = f"{user_link} {action_ru} по всей связке."
        await bot.send_message(chat_id=str(chat_id), text=message_text, parse_mode="HTML")

    total = len(results)
    success_count = sum(1 for _, s, _ in results if s)
    admin_link = await user_link_global(message.from_user.id)


    resp = f"🔔 <b>Действие по связке для {user_link}</b> \n👮‍♂️ {admin_link}\nУспешно: {success_count}/{total}\n"
    if safe_reason:
        resp += f"💬 Причина: {safe_reason}\n"
    #if total <= 20:
     #   resp += "\n📋 Детали:\n"
      #  for name, ok, m in results:
       #     resp += f"{'✅' if ok else '❌'} {name}: {m}\n"
    #else:
     #   resp += f"\n✅ {success_count} чатов, ❌ {total - success_count}"
    await message.reply(resp, parse_mode="HTML", disable_web_page_preview=True)


    if success_in_any:
        await add_bundle_log(bundle_id, message.from_user.id, user_id, action, reason, duration_str, success=True)


# ------------------------------------------------------------
# Команды наказаний
# ------------------------------------------------------------
@group_bundle.message(F.text.regexp(r'(?i)^[!./]связка\s+бан(\s|$).*'))
async def cmd_ban(message: types.Message):
    await process_action(message, 'ban')

@group_bundle.message(F.text.regexp(r'(?i)^[!./]связка\s+мут(\s|$).*'))
async def cmd_mute(message: types.Message):
    await process_action(message, 'mute')

#@group_bundle.message(F.text.regexp(r'(?i)^[!./]связка\s+варн(\s|$).*'))
async def cmd_warn(message: types.Message):
    await process_action(message, 'warn')

@group_bundle.message(F.text.regexp(r'(?i)^[!./]связка\s+снять\s+бан(\s|$).*'))
async def cmd_unban(message: types.Message):
    await process_action(message, 'unban')

@group_bundle.message(F.text.regexp(r'(?i)^[!./]связка\s+снять\s+мут(\s|$).*'))
async def cmd_unmute(message: types.Message):
    await process_action(message, 'unmute')

#@group_bundle.message(F.text.regexp(r'(?i)^[!./]связка\s+снять\s+варн(\s|$).*'))
async def cmd_unwarn(message: types.Message):
    await process_action(message, 'unwarn')

# Короткие синонимы
@group_bundle.message(F.text.regexp(r'(?i)^[!./]связка\s+разбан(\s|$).*'))
async def cmd_unban_short(message: types.Message):
    await process_action(message, 'unban')

@group_bundle.message(F.text.regexp(r'(?i)^[!./]связка\s+размут(\s|$).*'))
async def cmd_unmute_short(message: types.Message):
    await process_action(message, 'unmute')

#@group_bundle.message(F.text.regexp(r'(?i)^[!./]связка\s+снятьварн(\s|$).*'))
async def cmd_unwarn_short(message: types.Message):
    await process_action(message, 'unwarn')




# ------------------------------------------------------------
# Команды управления рангами по связке
# ------------------------------------------------------------
@group_bundle.message(F.text.regexp(r'(?i)^[!./]связка\s+повысить\s+\S+(\s+\d+)?$'))
async def cmd_promote_bundle(message: types.Message):
    """.связка повысить @user [ранг]"""
    parts = message.text.split(maxsplit=3)
    if len(parts) < 3:
        await message.answer("Использование: .связка повысить @user [ранг]")
        return
    target = parts[2]
    new_rank = None
    if len(parts) > 3 and parts[3].isdigit():
        new_rank = int(parts[3])
        if new_rank < 1 or new_rank > 5:
            await message.answer("Ранг должен быть от 1 до 5.")
            return
    user_id = await resolve_id(message, target)
    if not user_id:
        await message.answer("Пользователь не найден.")
        return
    await promote_in_bundle(message, user_id, new_rank)


@group_bundle.message(F.text.regexp(r'(?i)^[!./]связка\s+понизить\s+\S+(\s+\d+)?$'))
async def cmd_demote_bundle(message: types.Message):
    """.связка понизить @user [ранг]"""
    parts = message.text.split(maxsplit=3)
    if len(parts) < 3:
        await message.answer("Использование: .связка понизить @user [ранг]")
        return
    target = parts[2]
    new_rank = None
    if len(parts) > 3 and parts[3].isdigit():
        new_rank = int(parts[3])
        if new_rank < 0 or new_rank > 4:
            await message.answer("Ранг должен быть от 0 до 4.")
            return
    user_id = await resolve_id(message, target)
    if not user_id:
        await message.answer("Пользователь не найден.")
        return
    await demote_in_bundle(message, user_id, new_rank)


@group_bundle.message(F.text.regexp(r'(?i)^[!./]связка\s+снять\s+\S+$'))
async def cmd_remove_admin_bundle(message: types.Message):
    """.связка снять админа @user"""
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Использование: .связка снять  @user")
        return
    target = parts[1]
    user_id = await resolve_id(message, target)
    if not user_id:
        await message.answer("Пользователь не найден.")
        return
    await remove_admin_in_bundle(message, user_id)


@group_bundle.message(F.text.regexp(r'(?i)^[!./]связка\s+рк\s+\S+\s+\d+$'))
async def cmd_set_command_rang_bundle(message: types.Message):
    """.связка рк <команда/раздел/подраздел> <ранг>"""
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        await message.answer("Использование: .связка рк <команда/раздел/подраздел> <ранг>")
        return
    target_value = parts[2]
    rang_str = parts[3]
    if not rang_str.isdigit():
        await message.answer("Ранг должен быть числом от 0 до 6.")
        return
    rang = int(rang_str)
    if rang < 0 or rang > 6:
        await message.answer("Ранг должен быть от 0 до 6 (6 — выключить).")
        return
    await set_command_access_in_bundle(message, target_value, rang)




# ------------------------------------------------------------
# Статистика
# ------------------------------------------------------------

# Константа для количества записей на страницу
STATS_PER_PAGE = 50


def build_stats_keyboard(bundle_id: int, period: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру для пагинации статистики."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=f"stats_{bundle_id}_{period}_{page - 1}"
        ))
    nav_buttons.append(InlineKeyboardButton(
        text=f"{page + 1}/{max(1, total_pages)}",
        callback_data="stats_current"
    ))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(
            text="Вперед ➡️",
            callback_data=f"stats_{bundle_id}_{period}_{page + 1}"
        ))
    if nav_buttons:
        keyboard.inline_keyboard.append(nav_buttons)
    return keyboard


@group_bundle.message(F.text.regexp(r'(?i)^[!./]связка\s+стата(\s+\S+)?$'))
async def cmd_stats(message: types.Message):
    text = message.text.strip()
    if text and text[0] in '!./':
        text = text[1:].lstrip()
    parts = text.split(maxsplit=2)
    if len(parts) < 2 or parts[0].lower() != 'связка' or parts[1].lower() != 'стата':
        await message.answer("Использование: .связка стата [день/неделя/месяц/год/всего]")
        return
    period = 'день'
    page = 0
    if len(parts) > 2:
        # Может быть период, а может быть страница?
        candidate = parts[2].lower()
        if candidate in ('день', 'неделя', 'месяц', 'год', 'всего', 'вся'):
            period = candidate
        elif candidate.isdigit():
            page = max(0, int(candidate) - 1)
        else:
            # Неизвестный параметр
            pass
    bundle_id = await resolve_bundle_id_group(message, None)
    if not bundle_id:
        await message.answer("Этот чат не привязан к связке.")
        return
    owner = await get_bundle_owner(bundle_id)
    if owner != message.from_user.id and not await is_bundle_admin(bundle_id, message.from_user.id, required_rank=1):
        push_status = await check_push_status(message.chat.id)
        if push_status == 'on':
            await message.answer("Только владелец или связной администратор может смотреть статистику.")
        return
    chats = await get_bundle_chats(bundle_id)
    if not chats:
        await message.answer("В связке нет чатов.")
        return

    # Собираем всю статистику
    total_stats = defaultdict(int)
    for chat_id in chats:
        try:
            raw = await get_stats(chat_id, period)
            for uid, _, cnt in raw:
                total_stats[uid] += cnt
        except Exception:
            continue
    if not total_stats:
        await message.answer("Нет данных за этот период.")
        return

    # Сортируем и разбиваем на страницы
    sorted_stats = sorted(total_stats.items(), key=lambda x: x[1], reverse=True)
    total_users = len(sorted_stats)
    total_pages = (total_users + STATS_PER_PAGE - 1) // STATS_PER_PAGE
    page = min(page, total_pages - 1) if total_pages > 0 else 0
    start_idx = page * STATS_PER_PAGE
    end_idx = min(start_idx + STATS_PER_PAGE, total_users)
    page_stats = sorted_stats[start_idx:end_idx]

    period_name = {
        'день': 'день', 'неделя': 'неделю', 'месяц': 'месяц',
        'год': 'год', 'всего': 'всё время', 'вся': 'всё время'
    }.get(period, period)
    total_msgs = sum(total_stats.values())

    lines = [f"📈 Статистика по связке за {period_name} (стр. {page + 1}/{max(1, total_pages)}):\n"]
    for i, (uid, cnt) in enumerate(page_stats, start=start_idx + 1):
        try:
            mention = await user_link_global(uid)
        except:
            mention = f"ID {uid}"
        lines.append(f"{i}. {mention} — {cnt}")
    lines.append(f"\nВсего сообщений: {total_msgs}")

    # Клавиатура для пагинации
    keyboard = build_stats_keyboard(bundle_id, period, page, total_pages) if total_pages > 1 else None
    await message.reply("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)


# ------------------------------------------------------------
# Callback для переключения страниц статистики
# ------------------------------------------------------------
@group_bundle.callback_query(lambda c: c.data.startswith("stats_"))
async def stats_pagination(callback: types.CallbackQuery):
    # Проверяем, что пользователь тот же, кто запрашивал статистику
    if (not callback.message.reply_to_message or
        callback.from_user.id != callback.message.reply_to_message.from_user.id):
        await callback.answer("Это не ваш запрос.", show_alert=True)
        return

    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("Ошибка данных", show_alert=True)
        return
    bundle_id = int(parts[1])
    period = parts[2]
    page = int(parts[3])

    # Проверяем права (владелец или связной админ)
    owner = await get_bundle_owner(bundle_id)
    if owner != callback.from_user.id and not await is_bundle_admin(bundle_id, callback.from_user.id, required_rank=1):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    chats = await get_bundle_chats(bundle_id)
    if not chats:
        await callback.answer("В связке нет чатов.", show_alert=True)
        return

    total_stats = defaultdict(int)
    for chat_id in chats:
        try:
            raw = await get_stats(chat_id, period)
            for uid, _, cnt in raw:
                total_stats[uid] += cnt
        except Exception:
            continue
    if not total_stats:
        await callback.answer("Нет данных.", show_alert=True)
        return

    sorted_stats = sorted(total_stats.items(), key=lambda x: x[1], reverse=True)
    total_users = len(sorted_stats)
    total_pages = (total_users + STATS_PER_PAGE - 1) // STATS_PER_PAGE
    if page < 0 or page >= total_pages:
        await callback.answer("Страница не существует", show_alert=True)
        return

    start_idx = page * STATS_PER_PAGE
    end_idx = min(start_idx + STATS_PER_PAGE, total_users)
    page_stats = sorted_stats[start_idx:end_idx]

    period_name = {
        'день': 'день', 'неделя': 'неделю', 'месяц': 'месяц',
        'год': 'год', 'всего': 'всё время', 'вся': 'всё время'
    }.get(period, period)
    total_msgs = sum(total_stats.values())

    lines = [f"📈 Статистика по связке за {period_name} (стр. {page + 1}/{max(1, total_pages)}):\n"]
    for i, (uid, cnt) in enumerate(page_stats, start=start_idx + 1):
        try:
            mention = await user_link_global(uid)
        except:
            mention = f"ID {uid}"
        lines.append(f"{i}. {mention} — {cnt}")
    lines.append(f"\nВсего сообщений: {total_msgs}")

    keyboard = build_stats_keyboard(bundle_id, period, page, total_pages) if total_pages > 1 else None
    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)
    await callback.answer()


@group_bundle.callback_query(lambda c: c.data == "stats_current")
async def stats_current_page(callback: types.CallbackQuery):
    await callback.answer()