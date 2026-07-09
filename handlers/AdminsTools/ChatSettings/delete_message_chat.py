import logging
from typing import List, Optional, Tuple, Dict
import asyncio
import re

from aiogram import Router, F
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest

from BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang

sms_cleanup = Router()
logger = logging.getLogger(__name__)

# Константы лимитов Telegram Bot API
MAX_MESSAGES_PER_PURGE = 100  # Максимум для одного вызова deleteMessages
DELETE_DELAY = 0.05  # Задержка для поштучного фоллбэка
STATUS_MESSAGE_LIFETIME = 3  # Время отображения статуса "Успешно"


async def check_bot_permissions(message: Message) -> bool:
    """Проверяет права бота на удаление сообщений."""
    try:
        chat_member = await message.bot.get_chat_member(chat_id=message.chat.id, user_id=message.bot.id)
        if hasattr(chat_member, 'can_delete_messages'):
            return chat_member.can_delete_messages
        return chat_member.status in ["administrator", "creator"]
    except Exception as e:
        logger.error(f"Ошибка проверки прав: {e}")
        return False


async def execute_smart_purge(message: Message, message_ids: List[int]) -> Tuple[int, List[int]]:
    """Пакетное удаление до 100 сообщений с умным поштучным откатом."""
    if not message_ids:
        return 0, []

    chat_id = message.chat.id
    bot = message.bot

    try:
        await bot.delete_messages(chat_id=chat_id, message_ids=message_ids)
        return len(message_ids), []
    except TelegramBadRequest:
        deleted_count = 0
        failed_ids = []
        for msg_id in message_ids:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                deleted_count += 1
            except TelegramBadRequest as e:
                if "message to delete not found" in str(e).lower():
                    deleted_count += 1
                else:
                    failed_ids.append(msg_id)
            except Exception:
                failed_ids.append(msg_id)
            await asyncio.sleep(DELETE_DELAY)
        return deleted_count, failed_ids


async def show_result_and_cleanup(message: Message, status_id: Optional[int], text: str):
    """Выводит результат и полностью убирает за собой следы."""
    bot = message.bot
    chat_id = message.chat.id

    if status_id:
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=status_id, text=text, parse_mode='HTML')
            target_id = status_id
        except Exception:
            msg = await bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
            target_id = msg.message_id
    else:
        msg = await bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
        target_id = msg.message_id

    if target_id:
        await asyncio.sleep(STATUS_MESSAGE_LIFETIME)
        try:
            await bot.delete_message(chat_id=chat_id, message_id=target_id)
        except Exception:
            pass


def parse_message_link(link: str, current_chat_username: Optional[str] = None) -> Optional[Dict[str, any]]:
    """Универсальный парсер публичных и приватных ссылок Telegram."""
    try:
        url = link.split('?')[0]

        # 1. Приватная ссылка супергруппы: t.me/c/123456789/1122
        private_match = re.search(r't\.me/c/(-?\d+)/(\d+)', url)
        if private_match:
            chat_id = int(private_match.group(1))
            full_chat_id = int(f"-100{chat_id}") if chat_id > 0 else chat_id
            return {'chat_id': full_chat_id, 'message_id': int(private_match.group(2))}

        # 2. Публичная ссылка: t.me/username/1122
        public_match = re.search(r't\.me/([a-zA-Z0-9_]{5,})/(\d+)', url)
        if public_match:
            username = public_match.group(1).lower()
            if current_chat_username and username == current_chat_username.lower():
                return {'username_match': True, 'message_id': int(public_match.group(2))}
    except Exception:
        pass
    return None


@sms_cleanup.message(F.text.casefold().startswith((".дел", "/дел", "!дел", "дел", "-смс", ".смс", "/смс", "!смс")))
async def delete_single_handler(message: Message):
    """Точечное моментальное удаление без проверок времени."""
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 100):
        return

    target_id = None
    if message.reply_to_message:
        target_id = message.reply_to_message.message_id
    else:
        args = message.text.split()
        if len(args) > 1:
            arg = args[1]
            if 't.me/' in arg:
                link_data = parse_message_link(arg, message.chat.username)
                if link_data and (link_data.get('chat_id') == message.chat.id or link_data.get('username_match')):
                    target_id = link_data['message_id']
            else:
                try:
                    target_id = int(arg)
                except ValueError:
                    return

    if not target_id:
        return

    # Удаляем саму команду
    try:
        await message.delete()
    except Exception:
        pass

    # Сразу удаляем целевое сообщение
    try:
        await message.bot.delete_message(chat_id=message.chat.id, message_id=target_id)
    except Exception:
        pass


@sms_cleanup.message(F.text.casefold().startswith((".делв", "/делв", "!делв")))
async def purge_up_handler(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 100):
        return
    await purge_handler(message, direction="up")


@sms_cleanup.message(F.text.casefold().startswith((".делн", "/делн", "!делн")))
async def purge_down_handler(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 100):
        return
    await purge_handler(message, direction="down")


@sms_cleanup.message(F.text.casefold().startswith((".делк", "/делк", "!делк")))
async def purge_both_handler(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 100):
        return
    await purge_handler(message, direction="both")


async def purge_handler(message: Message, direction: str):
    """Гибкий обработчик направленной чистки (удаляет всё и сразу)."""

    args = message.text.split()
    target_id = message.reply_to_message.message_id if message.reply_to_message else None
    count = 1

    for arg in args[1:]:
        if 't.me/' in arg:
            ld = parse_message_link(arg, message.chat.username)
            if ld and (ld.get('chat_id') == message.chat.id or ld.get('username_match')):
                target_id = ld['message_id']
            continue

        if '-' in arg:
            try:
                s, e = map(int, arg.split('-'))
                return await delete_message_range(message, s, e)
            except ValueError:
                pass
            continue

        if arg.isdigit():
            val = int(arg)
            if val > 500 and target_id is None:
                target_id = val
            else:
                count = min(val, MAX_MESSAGES_PER_PURGE)

    if not target_id:
        return

    if direction == "down":
        msg_ids = list(range(target_id, target_id + count))
    elif direction == "up":
        msg_ids = list(range(target_id - count + 1, target_id + 1))
    else:
        msg_ids = list(range(target_id - count, target_id + count + 1))

    msg_ids = [m for m in msg_ids if m > 0]

    try:
        await message.delete()
    except Exception:
        pass

    dir_names = {"down": "ВНИЗ", "up": "ВВЕРХ", "both": "КРУГОМ"}

    status_msg = await message.bot.send_message(
        chat_id=message.chat.id,
        text=f"🌀 <b>Очистка {dir_names[direction]}...</b> Выполняется удаление {len(msg_ids)} сообщений.",
        parse_mode='HTML'
    )
    status_id = status_msg.message_id

    del_ok, del_err = await execute_smart_purge(message, msg_ids)

    res = f"✅ <b>Очищено!</b>\nУничтожено: {del_ok} сообщений."
    if del_err:
        res += f"\n❌ Не удалось: {len(del_err)}"
    await show_result_and_cleanup(message, status_id, res)


async def delete_message_range(message: Message, start_id: int, end_id: int):
    """Пакетное удаление строго заданного диапазона ID."""
    if start_id > end_id:
        start_id, end_id = end_id, start_id

    total = end_id - start_id + 1
    if total > MAX_MESSAGES_PER_PURGE:
        return

    msg_ids = list(range(start_id, end_id + 1))
    try:
        await message.delete()
    except Exception:
        pass

    del_ok, del_err = await execute_smart_purge(message, msg_ids)

    status_msg = await message.bot.send_message(
        chat_id=message.chat.id,
        text=f"🌀"
    )
    await show_result_and_cleanup(message, status_msg.message_id,
                                  f"✅ <b>Диапазон зачищен!</b>\nСтёрто: <b>{del_ok}</b> сообщений.")