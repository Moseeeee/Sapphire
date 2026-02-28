import asyncio
import logging
from datetime import datetime
from typing import List, Tuple
import pytz

from handlers.AdminsTools.ChatSettings.message_pinned.pin_smsDB import remove_pinned_message
from handlers.AdminsTools.CommandsModerations.warns.warnsDB import clear_expired_warns
from handlers.AdminsTools.CommandsModerations.mute.muteDB import remove_mute_info
from handlers.AdminsTools.CommandsModerations.bans.banDB import remove_ban_info
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global
from handlers.BotAutomaticWork.universal_bot import bot


logger = logging.getLogger(__name__)
MOSCOW_TZ = pytz.timezone('Europe/Moscow')


def get_moscow_time() -> datetime:
    """Получить текущее время в московском часовом поясе."""
    return datetime.now(MOSCOW_TZ)


async def get_expired_punishments() -> List[Tuple[int, int, str]]:
    """Получает список истекших банов и мутов."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            current_time = get_moscow_time()

            # Получаем все истекшие наказания одним запросом
            rows = await conn.fetch('''
                SELECT chat_id, user_id, types 
                FROM punishment_time 
                WHERE types IN ('ban', 'mute') 
                  AND time_end::TIMESTAMPTZ <= $1::TIMESTAMPTZ
            ''', current_time)

            return [(row['chat_id'], row['user_id'], row['types']) for row in rows]

    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def get_expired_warns() -> List[Tuple[int, int]]:
    """Получает список истекших предупреждений."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            current_time = get_moscow_time()
            rows = await conn.fetch('''
                SELECT chat_id, user_id 
                FROM warns 
                WHERE expires_at::TIMESTAMPTZ <= $1::TIMESTAMPTZ
            ''', current_time)
            return [(row['chat_id'], row['user_id']) for row in rows]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def perform_auto_unban(chat_id: int, user_id: int) -> bool:
    """Выполняет автоматический разбан."""
    try:
        await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
        await remove_ban_info(chat_id, user_id)

        user_link = await user_link_global(user_id)
        await bot.send_message(
            chat_id=chat_id,
            text=f'✅ {user_link} был разбанен.\nТеперь он может вернуться в чат!',
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        return True
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


async def perform_auto_unmute(chat_id: int, user_id: int) -> bool:
    """Выполняет автоматический размут."""
    try:
        chat = await bot.get_chat(chat_id)
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=chat.permissions
        )
        await remove_mute_info(chat_id, user_id)
        return True
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


async def perform_auto_unpin(chat_id: int, message_id: int) -> bool:
    """Автоматически открепляет сообщение"""
    try:
        await bot.unpin_chat_message(chat_id=chat_id, message_id=message_id)
        await remove_pinned_message(chat_id, message_id)
        pin_text = f'<a href="https://t.me/c/{str(chat_id)[4:]}/{message_id}">Сообщение</a>'
        await bot.send_message(chat_id=chat_id,
                               text=f'{pin_text} было откреплено!')
        return True
    except Exception as e:
        logger.error(f"Ошибка при автооткреплении: {e}")
        await remove_pinned_message(chat_id, message_id)
        return False


async def get_expired_pinned_messages_auto() -> List[Tuple[int, int]]:
    """Получает список сообщений для автооткрепления"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            current_time = get_moscow_time()
            rows = await conn.fetch('''
                SELECT chat_id, message_id 
                FROM pinned_messages 
                WHERE unpin_time::TIMESTAMPTZ <= $1::TIMESTAMPTZ
            ''', current_time)
            return [(row['chat_id'], row['message_id']) for row in rows]
    except Exception as e:
        logger.error(f"Ошибка при получении истекших закреплений: {e}")
        return []


async def get_next_check_interval() -> int:
    """Определяет оптимальный интервал до следующей проверки."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            current_time = get_moscow_time()

            # Находим ближайшее время окончания наказания или варна
            result = await conn.fetchval('''
                SELECT MIN(next_time) FROM (
                    SELECT MIN(time_end::TIMESTAMPTZ) AS next_time FROM punishment_time WHERE time_end::TIMESTAMPTZ > $1::TIMESTAMPTZ
                    UNION ALL
                    SELECT MIN(expires_at::TIMESTAMPTZ) AS next_time FROM warns WHERE expires_at::TIMESTAMPTZ > $1::TIMESTAMPTZ
                    UNION ALL
                    SELECT MIN(unpin_time::TIMESTAMPTZ) AS next_time FROM pinned_messages WHERE unpin_time::TIMESTAMPTZ > $1::TIMESTAMPTZ
                ) AS sub
            ''', current_time)

            if result:
                # Если результат уже является datetime объектом
                if isinstance(result, datetime):
                    next_expiry = result
                else:
                    next_expiry = datetime.fromisoformat(str(result)).replace(tzinfo=MOSCOW_TZ)

                current_time_moscow = get_moscow_time()
                seconds_until_next = (next_expiry - current_time_moscow).total_seconds()

                # Оптимизация: не реже 1 минуты, не чаще 1 дня
                if seconds_until_next <= 60:
                    return 60
                elif seconds_until_next <= 300:  # 5 мин
                    return 60
                elif seconds_until_next <= 3600:  # 1 час
                    return 300
                elif seconds_until_next <= 86400:  # 1 день
                    return 3600
                else:
                    return 86400

        return 3600  # По умолчанию — раз в час

    except Exception as e:
        logger.error(e, exc_info=True)
        return 3600


async def auto_punishment_check():
    """Основной цикл автоматической проверки наказаний и закреплений"""
    logger.info("🔁 Система автоматической проверки наказаний и закреплений запущена")
    while True:
        try:
            check_interval = await get_next_check_interval()

            # Проверяем истекшие наказания
            expired_punishments = await get_expired_punishments()
            expired_warns = await get_expired_warns()
            expired_pins = await get_expired_pinned_messages_auto()

            # Обрабатываем истекшие наказания
            if expired_punishments:
                for chat_id, user_id, p_type in expired_punishments:
                    if p_type == 'ban':
                        await perform_auto_unban(chat_id, user_id)
                    elif p_type == 'mute':
                        await perform_auto_unmute(chat_id, user_id)
                    await asyncio.sleep(0.5)

            # Обрабатываем истекшие варны
            if expired_warns:
                await clear_expired_warns()

            # Обрабатываем истекшие закрепления
            if expired_pins:
                for chat_id, message_id in expired_pins:
                    await perform_auto_unpin(chat_id, message_id)
                    await asyncio.sleep(0.5)

            await asyncio.sleep(check_interval)

        except asyncio.CancelledError:
            logger.info("Система автоматической проверки остановлена")
            break
        except Exception as e:
            logger.error(f"Ошибка в автоматической проверке: {e}")
            await asyncio.sleep(3600)


async def start_auto_punishment_check() -> str:
    """Запускает фоновую задачу автоматической проверки."""
    try:
        logger.info("🚀 Запуск системы автоматической проверки наказаний...")
        asyncio.create_task(auto_punishment_check())
        return 'ok'
    except Exception as e:
        logger.error(e, exc_info=True)
        return 'error'